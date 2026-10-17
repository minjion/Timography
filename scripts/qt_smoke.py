"""Real Qt Quick pointer journeys and layout checks using disposable planner data."""
from contextlib import closing
from datetime import date
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from time import perf_counter
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QMetaObject, QPoint, QPointF, Qt, QUrl, qInstallMessageHandler
from PySide6.QtGui import QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import shiboken6

from core.database import TimographyDB
from desktop_qt.controller import PlannerController


def main():
    QQuickStyle.setStyle("Basic")
    app = QApplication.instance() or QApplication([])
    messages = []
    previous = qInstallMessageHandler(lambda kind, context, message: messages.append(message))
    errors = []
    old_hook = sys.excepthook
    sys.excepthook = lambda kind, value, trace: errors.append(str(value))
    folder = tempfile.TemporaryDirectory()
    db = TimographyDB(str(Path(folder.name) / "planner.db"))
    db.initialize()
    for routine in db.get_all_routines():
        db.delete_routine(routine["id"])
    planner = PlannerController(db)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("planner", planner)
    results = {}
    try:
        started = perf_counter()
        engine.load(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1] / "desktop_qt/qml/Main.qml")))
        assert engine.rootObjects(), "QML failed to load: " + "\n".join(messages)
        window = engine.rootObjects()[0]
        QTest.qWaitForWindowExposed(window, 3000)
        QTest.qWait(200)
        results["load_and_settle_ms"] = round((perf_counter() - started) * 1000, 1)

        def objects():
            # Delegates may have a visual parent without QObject ownership.
            seen, pending = set(), [window, window.contentItem()]
            while pending:
                obj = pending.pop()
                identity = shiboken6.getCppPointer(obj)[0]
                if identity in seen:
                    continue
                seen.add(identity)
                yield obj
                pending.extend(obj.children())
                if isinstance(obj, QQuickItem):
                    pending.extend(obj.childItems())

        def find(name, visible=True):
            candidates = [obj for obj in objects() if obj.objectName() == name]
            for obj in candidates:
                if not visible or not isinstance(obj, QQuickItem) or obj.isVisible():
                    return obj
            raise AssertionError(f"Missing {'visible ' if visible else ''}control {name}")

        def click(name):
            obj = find(name)
            assert isinstance(obj, QQuickItem), name
            point = obj.mapToScene(QPointF(obj.width() / 2, obj.height() / 2))
            assert 0 <= point.x() < window.width() and 0 <= point.y() < window.height(), (name, point)
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point.toPoint())
            QTest.qWait(70)

        def set_text(name, value):
            find(name).setProperty("text", value)

        def check_actions():
            for obj in objects():
                if not isinstance(obj, QQuickItem) or not obj.isVisible() or not obj.objectName():
                    continue
                if obj.objectName().startswith("nav") or obj.objectName() == "themeToggle":
                    point = obj.mapToScene(QPointF(0, 0))
                    assert point.x() >= 0 and point.y() >= 0
                    assert point.x() + obj.width() <= window.width() + 1
                    assert point.y() + obj.height() <= window.height() + 1

        set_text("captureTitle", "Read chapter and annotate unfamiliar concepts")
        click("captureButton")
        assert planner.taskCount == 1
        task_id = planner.tasks[0]["id"]
        assert find("captureTitle").property("text") == ""
        click("navTasks")
        click(f"taskSchedule_{task_id}")
        assert find("scheduleDialog", False).property("visible")
        set_text("scheduleDate", "2026-02-30")
        set_text("scheduleStart", "09:00")
        set_text("scheduleEnd", "10:00")
        click("scheduleSave")
        assert planner.errorMessage and not planner.tasks[0]["blocks"]
        assert find("scheduleDialog", False).property("visible"), "Invalid form must stay open"
        set_text("scheduleDate", date.today().isoformat())
        click("scheduleSave")
        assert len(planner.tasks[0]["blocks"]) == 1
        assert not find("scheduleDialog", False).property("visible")

        click(f"taskEdit_{task_id}")
        set_text("editTitle", "Read chapter · 日本語 notes")
        set_text("editNotes", "Keep the same task through planning and focus.")
        click("editSave")
        assert planner.tasks[0]["title"] == "Read chapter · 日本語 notes"
        assert planner.tasks[0]["notes"].startswith("Keep the same task")
        click(f"taskFocus_{task_id}")
        assert planner.activeTaskId == task_id and planner.focusPhase == "WORK"
        QTest.qWait(350)
        click("focusToggle")
        assert planner.focusPhase == "PAUSED"
        click("focusToggle")
        assert planner.focusPhase == "WORK"
        click("focusStop")
        assert not planner.focusRunning
        assert planner.service.task_focus_seconds(task_id) > 0
        click("navTasks")
        with patch.object(planner.service, "set_completed", side_effect=OSError("Simulated storage failure")):
            click(f"taskComplete_{task_id}")
            assert planner.errorMessage
            assert not find(f"taskComplete_{task_id}").property("checked"), "Failed completion must roll back the checkmark"
        planner.clearError()
        click(f"taskComplete_{task_id}")
        assert planner.completedCount == 1
        click("navReview")
        assert planner.recentSessions and planner.recentSessions[0]["minutes"] > 0

        if "--capture" in sys.argv:
            examples = [planner.service.create_task(title, category=category, estimate_minutes=estimate)
                        for title, category, estimate in (
                            ("Outline the next project milestone", "Work", 45),
                            ("Review lecture notes and prepare tomorrow's questions", "Study", 30),
                            ("Plan tomorrow's priorities", "Personal", 15))]
            planner.refresh()
            planner.setDarkMode(False)
            window.setProperty("page", 0)
            QTest.qWait(100)
            preview_image = Path(__file__).resolve().parents[1] / "artifacts/ui-audit/next-workflow-preview.png"
            preview_image.parent.mkdir(parents=True, exist_ok=True)
            window.grabWindow().save(str(preview_image))
            for example in examples:
                planner.service.delete_task(example)

        # Enough long rows to exercise ListView virtualization and wheel routing.
        for index in range(40):
            planner.service.create_task(f"Task {index + 1} — " + "a long title that should wrap naturally " * 3)
        planner.refresh()
        QTest.qWait(100)
        captures = Path(__file__).resolve().parents[1] / "artifacts/ui-audit"
        captures.mkdir(parents=True, exist_ok=True)
        combinations = 0
        for width, height in ((800, 600), (1280, 840)):
            window.resize(width, height)
            for dark in (False, True):
                planner.setDarkMode(dark)
                window.setProperty("page", 0)
                app.processEvents()
                primary = find("navToday")
                if window.property("page") == 0:
                    actual_color = primary.property("contentItem").property("color").name()
                    assert actual_color == ("#161b34" if dark else "#ffffff"), actual_color
                for page in range(4):
                    window.setProperty("page", page)
                    QTest.qWait(80)
                    check_actions()
                    image = window.grabWindow()
                    assert not image.isNull(), "Window did not render"
                    if "--capture" in sys.argv or (width == 1280 and page == 0):
                        image.save(str(captures / f"next-{width}-{'dark' if dark else 'light'}-{page}.png"))
                    combinations += 1

        window.setProperty("page", 1)
        QTest.qWait(100)
        task_list = find("taskList")
        assert task_list.property("contentHeight") > task_list.height()
        task_list.setProperty("contentY", 0)
        center = task_list.mapToScene(QPointF(task_list.width() / 2, task_list.height() / 2))
        global_point = QPointF(window.mapToGlobal(center.toPoint()))
        # Pixel deltas are the precision/trackpad path; angle units are not required.
        wheel = QWheelEvent(center, global_point, QPoint(0, -75), QPoint(0, 0),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.ScrollUpdate, False)
        app.sendEvent(window, wheel)
        QTest.qWait(100)
        assert task_list.property("contentY") > 0, "Pixel-only touchpad wheel did not scroll the task list"
        position = task_list.property("contentY")
        planner.refresh()
        QTest.qWait(80)
        assert abs(task_list.property("contentY") - position) < 1, "Unchanged refresh lost scroll position"
        planner.service.update_task(planner.tasks[-1]["id"], notes="Update while scrolling")
        planner.refresh()
        QTest.qWait(80)
        assert abs(task_list.property("contentY") - position) < 1, "Model update lost scroll position"

        # Many blocks must scroll inside the dialog, leaving its actions reachable.
        task_list.setProperty("contentY", 0)
        open_id = next(task["id"] for task in planner.tasks if not task["is_completed"])
        for hour in range(8, 20):
            planner.service.schedule_task(open_id, f"{date.today()}T{hour:02}:00", f"{date.today()}T{hour:02}:30")
        planner.refresh()
        window.resize(800, 600)
        QTest.qWait(100)
        QMetaObject.invokeMethod(task_list, "positionViewAtEnd")
        QTest.qWait(100)
        click(f"taskSchedule_{open_id}")
        popup = find("scheduleDialog", False)
        assert popup.property("height") <= window.height() - 47
        click("scheduleCancel")

        # The normal window close path must retain an unsaved session for retry.
        assert planner.startFocus(open_id)
        QTest.qWait(150)
        with patch.object(db, "checkpoint_pomodoro", return_value=False):
            assert not window.close()
            QTest.qWait(50)
            assert window.isVisible() and planner.errorMessage
        assert planner.stopFocus()
        export = Path(folder.name) / "export.db"
        assert planner.exportBackup(QUrl.fromLocalFile(str(export)).toString())
        with closing(sqlite3.connect(export)) as backup:
            assert backup.execute("SELECT COUNT(*) FROM checklist_items").fetchone()[0] == 41
        results["view_combinations"] = combinations
        results["task_count"] = planner.taskCount
        results["pixel_wheel_scroll"] = True
        results["qml_messages"] = messages
        assert not errors, errors
        assert not messages, "Qt/QML warnings: " + "\n".join(messages)
        print(json.dumps(results, indent=2), flush=True)
    finally:
        if sys.exc_info()[0] is not None:
            print("Qt messages:", messages, flush=True)
            if engine.rootObjects():
                engine.rootObjects()[0].grabWindow().save(str(Path(__file__).resolve().parents[1] / "artifacts/ui-audit/next-failure.png"))
        planner.close()
        if engine.rootObjects():
            engine.rootObjects()[0].close()
        shiboken6.delete(engine)
        db.close()
        folder.cleanup()
        qInstallMessageHandler(previous)
        sys.excepthook = old_hook


if __name__ == "__main__":
    main()
