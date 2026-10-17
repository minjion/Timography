"""Run the production Qt entry point in fresh processes with isolated stores."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.database import TimographyDB
from core.instance_lock import InstanceLock
from core.task_service import TaskService
import main_qt


def run_case(case):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox
    import desktop_qt.controller as controller_module

    with tempfile.TemporaryDirectory() as folder:
        source, target = Path(folder) / "source.db", Path(folder) / "preview.db"
        original = TimographyDB(str(source))
        original.initialize()
        for routine in original.get_all_routines():
            original.delete_routine(routine["id"])
        TaskService(original).create_task("Original source task")
        original.close()
        source_bytes = source.read_bytes()
        if case == "existing":
            main_qt.prepare_database(source, target)
            existing = TimographyDB(str(target))
            existing.initialize()
            TaskService(existing).create_task("Keep preview changes")
            existing.close()
        errors, seen, popups = [], [], []
        real_controller = controller_module.PlannerController

        class ProbeController(real_controller):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                QTimer.singleShot(150, self.probe)
                QTimer.singleShot(5000, self.timeout)

            def timeout(self):
                if not self._closed:
                    errors.append("Qt launch journey timed out")
                    QApplication.instance().quit()

            def probe(self):
                try:
                    windows = [window for window in QApplication.topLevelWindows()
                               if window.objectName() == "mainWindow"]
                    assert len(windows) == 1 and windows[0].isVisible()
                    assert self.previewMode == (case != "direct")
                    titles = {task["title"] for task in self.tasks}
                    assert "Original source task" in titles
                    if case == "existing":
                        assert "Keep preview changes" in titles
                    assert self.createTask("New workflow task", "Study", 25)
                    new_id = next(task["id"] for task in self.tasks if task["title"] == "New workflow task")
                    assert self.startFocus(new_id)
                    seen.append(True)
                    QTimer.singleShot(250, windows[0].close)
                except Exception as exc:
                    errors.append(str(exc))
                    QApplication.instance().quit()

        arguments = ["--database", str(source)] if case == "direct" else ["--preview-database", str(target)]
        lock = InstanceLock(target)
        if case == "duplicate":
            assert lock.acquire()
        try:
            with patch.object(main_qt, "DB_PATH", str(source)), \
                    patch.object(controller_module, "PlannerController", ProbeController), \
                    patch.object(QMessageBox, "critical", side_effect=lambda *args: popups.append(args)), \
                    patch.object(QMessageBox, "information", return_value=None):
                result = main_qt.main(arguments)
            assert result == 0, (result, popups)
            assert not errors and not popups, (errors, popups)
            if case == "duplicate":
                assert not seen and not target.exists(), "Duplicate launch opened/modified the store"
                assert source.read_bytes() == source_bytes
                return
            assert seen
            used = source if case == "direct" else target
            if case != "direct":
                assert source.read_bytes() == source_bytes, "Preview wrote to the source"
            with closing(sqlite3.connect(used)) as connection:
                assert connection.execute("SELECT COUNT(*) FROM checklist_items WHERE title = 'New workflow task'").fetchone()[0] == 1
                seconds, ended = connection.execute("SELECT tracked_seconds, end_time FROM pomodoro_sessions ORDER BY id DESC LIMIT 1").fetchone()
                assert seconds > 0 and ended, "Closing the real window did not save partial focus"
            released = InstanceLock(used)
            assert released.acquire(), "Launcher retained the database lock after exit"
            released.release()
        finally:
            lock.release()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("preview", "existing", "direct", "duplicate"))
    options = parser.parse_args()
    if options.case:
        run_case(options.case)
        return
    for case in ("preview", "existing", "direct", "duplicate"):
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--case", case],
                       check=True, timeout=30)
    print("Qt launch, persistent preview, direct database, partial-focus close and instance exclusion passed.", flush=True)


if __name__ == "__main__":
    main()
