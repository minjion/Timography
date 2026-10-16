"""Exercise release user journeys with disposable data and real Tk controls.

Run alone in a desktop session. Hardware touchpads/native tray/toasts are outside
this check; wheel events are injected into the actual Tk widgets.
"""
import argparse
import faulthandler
import sys
import traceback
import tempfile
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import customtkinter as ctk

from core.database import TimographyDB
from ui.main_window import MainWindow
from ui.widget import DesktopWidget
from ui.settings_dialog import SettingsDialog
from ui.theme import apply_theme, COLORS, get_current_theme


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args()
    faulthandler.dump_traceback_later(60, repeat=True)
    errors = []
    apply_theme("dark")
    root = ctk.CTk()
    root.withdraw()
    root.update()
    root.report_callback_exception = lambda kind, value, tb: errors.append(
        "".join(traceback.format_exception(kind, value, tb)))
    bgerror_recorder = root.register(lambda message, info: errors.append(f"Tcl background error: {message}\n{info}"))
    root.tk.call("proc", "bgerror", "message", f"{bgerror_recorder} $message $::errorInfo")
    db = TimographyDB(":memory:")
    db.initialize()
    today = date.today().isoformat()
    for routine in db.get_all_routines():
        db.delete_routine(routine["id"])
    event_id = db.add_event("Read the next chapter and annotate unfamiliar concepts", "",
                           "09:00", "10:00", today, "#bc8cff", "Study", "none", 10)
    for index in range(15):
        db.add_checklist_item(f"Review topic {index + 1} with a long title that must wrap inside its card", today)
    window = MainWindow(root, db)
    window.deiconify()
    window.attributes("-alpha", 1)

    def pump(ms=180):
        root.after(ms, root.quit)
        root.mainloop()

    def capture(name):
        if args.capture:
            from PIL import ImageGrab
            import ctypes
            output = Path(__file__).resolve().parents[1] / "artifacts/ui-audit"
            output.mkdir(parents=True, exist_ok=True)
            window.lift()
            pump()
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
            ImageGrab.grab(window=hwnd).save(output / f"release-{name}.png")

    def contained(widget):
        assert widget.winfo_ismapped(), f"Hidden action: {widget}"
        assert widget.winfo_width() > 8, f"Collapsed action: {widget}"
        assert widget.winfo_x() >= -1, f"Action escapes left boundary: {widget}"
        assert widget.winfo_x() + widget.winfo_width() <= widget.master.winfo_width() + 2, f"Action escapes right boundary: {widget}"

    def labels_fit(parent):
        for child in parent.winfo_children():
            if isinstance(child, ctk.CTkLabel) and child.cget("text").startswith(("Review topic", "Read the next chapter")):
                label = child._label
                assert label.winfo_reqwidth() <= label.winfo_width() + 2, f"Text clipped at DPI scale: {child.cget('text')} requested={label.winfo_reqwidth()} actual={label.winfo_width()} wrap={child.cget('wraplength')} scale={child._get_widget_scaling()}"
                assert label.winfo_reqheight() <= label.winfo_height() + 2, f"Wrapped text clipped vertically: {child.cget('text')}"
            labels_fit(child)

    try:
        assert window.active_tab == "today", "The app did not open the actionable Today view"
        window.geometry("900x600")
        today_view = window.view_today
        for theme in ("dark", "light"):
            window._on_theme_change(theme)
            window.switch_tab("today")
            today_view.refresh()
            pump(500)  # Allow DPI and wrapping geometry to settle before measuring.
            for action in (today_view.add_button, today_view.focus_button,
                           today_view.calendar_button, today_view.task_add_button):
                contained(action)
            for action in today_view._task_focus_buttons.values():
                contained(action)
            assert today_view.next_title.cget("text")
            assert today_view._apply_appearance_mode(today_view.cget("fg_color")) == COLORS["bg_primary"]
            capture(f"900-{theme}-today")
            labels_fit(today_view)
        print("OK Today small-display actions and both themes", flush=True)

        # Typing ordinary shortcut letters/numbers must remain in the task entry.
        today_view.task_entry.focus_force()
        pump()
        for key in ("n", "p", "c", "1", "7"):
            today_view.task_entry._entry.event_generate(f"<KeyPress-{key}>")
            pump(30)
            assert window.active_tab == "today", f"Typing {key} invoked a navigation shortcut"
        assert today_view.task_entry.get().endswith("npc17"), repr(today_view.task_entry.get())
        today_view.task_entry.delete(0, "end")

        # Capture, complete, undo and redo in the actual Today controls.
        today_view.task_entry.insert(0, "QA captured task")
        today_view.task_add_button.invoke()
        pump()
        created = next(item for item in db.get_checklist(today) if item["title"] == "QA captured task")
        # Today shows eight tasks: this newly captured task is reachable in Tasks.
        window.switch_tab("tasks")
        panel = window.view_tasks
        pump(500)
        labels_fit(panel)
        panel._rows[created["id"]]["cb"].toggle()
        pump()
        assert db.get_checklist_item(created["id"])["is_completed"] == 1
        window._undo()
        pump()
        assert db.get_checklist_item(created["id"])["is_completed"] == 0
        window._redo()
        pump()
        assert db.get_checklist_item(created["id"])["is_completed"] == 1
        window.switch_tab("today")
        pump()
        first_id = next(iter(today_view._task_controls))
        before = db.get_checklist_item(first_id)
        today_view._task_controls[first_id].set(not bool(before["is_completed"]))
        today_view._toggle_task(first_id)
        pump()
        assert bool(db.get_checklist_item(first_id)["is_completed"]) != bool(before["is_completed"])
        window._undo()
        pump()
        assert db.get_checklist_item(first_id) == before
        with patch.object(db, "toggle_checklist_item", return_value=False):
            today_view._task_controls[first_id].set(not bool(before["is_completed"]))
            today_view._toggle_task(first_id)
            assert today_view._task_controls[first_id].get() == bool(before["is_completed"])
            assert today_view.error_label.winfo_manager() == "pack"
        print("OK task capture, completion history and failed-write rollback", flush=True)

        # Ordinary view refreshes must respect a deliberate generated-task deletion.
        scheduled = next(item for item in db.get_checklist(today) if item["event_id"] == event_id)
        db.delete_checklist_item(scheduled["id"])
        today_view.refresh()
        assert not any(item["event_id"] == event_id for item in db.get_checklist(today))
        assert len(db.get_checklist(today)) == 16

        # A precision scroll on a descendant must only scroll the containing pane.
        canvas = today_view.content._parent_canvas
        canvas.yview_moveto(0)
        pump()
        before = canvas.yview()[0]
        for _ in range(6):
            today_view.next_title._label.event_generate("<MouseWheel>", delta=-1)
        pump()
        assert canvas.yview()[0] > before, "Today lost small precision-wheel deltas"
        print("OK preserved task deletions and Today precision scrolling", flush=True)

        # The hero action carries its event title/category/identity into the focus room.
        with patch("ui.today_view.datetime") as clock:
            clock.now.return_value = datetime.combine(date.today(), datetime.min.time()).replace(hour=9, minute=30)
            today_view.refresh()
            assert today_view.next_caption.cget("text") == "HAPPENING NOW"
            today_view.focus_button.invoke()
        pump()
        view = window.view_focus
        assert window.active_tab == "focus"
        assert view.engine.phase == view.engine.PHASE_WORK
        assert view.engine.event_id == event_id
        assert view.engine.category == "Study"
        assert view.task_entry.get() == db.get_event(event_id)["title"]
        session_id = view.db_session_id
        view._on_main_button_click()  # Pause through the real action.
        pump()
        assert view.engine.phase == view.engine.PHASE_PAUSED
        view._reset_timer()
        assert view.engine.phase == view.engine.PHASE_IDLE
        session = next(item for item in db.get_pomodoro_history() if item["id"] == session_id)
        assert session["end_time"] is not None
        assert session["tracked_seconds"] >= 0
        assert session["cycles_completed"] == 0
        print("OK Today event-context focus, pause and partial-session reset", flush=True)

        # Make the three source types visible among Today's pending tasks.
        for item in db.get_checklist(today):
            if not item["is_completed"]:
                db.toggle_checklist_item(item["id"])
        db.update_event(event_id, category="Work")
        routine_id = db.add_routine("Stretch before the next focused study block", "", "10:00", "10:30",
            days_of_week="0,1,2,3,4,5,6", color="#3fb950", category="Health", reminder_minutes=0)
        synced = db.sync_checklist_for_date(today)
        linked = next(item for item in synced if item["event_id"] == event_id)
        routine = next(item for item in synced if item["routine_id"] == routine_id)
        custom_id = db.add_checklist_item("Review topic independently without an event link", today)
        custom = db.get_checklist_item(custom_id)
        for item in (linked, routine):
            if item["is_completed"]:
                db.toggle_checklist_item(item["id"])
        window.switch_tab("today")
        today_view.refresh()
        pump(500)
        labels_fit(today_view)
        for action in today_view._task_focus_buttons.values():
            contained(action)
        expected_sources = ((linked, "Work", event_id), (routine, "Health", None), (custom, "Study", None))
        for item, category, linked_event in expected_sources:
            window.switch_tab("today")
            today_view.refresh()
            pump()
            today_view._task_focus_buttons[item["id"]].invoke()
            pump()
            assert window.active_tab == "focus"
            assert view.engine.title == item["title"]
            assert view.engine.category == category
            assert view.engine.event_id == linked_event
            session_id = view.db_session_id
            session = next(entry for entry in db.get_pomodoro_history() if entry["id"] == session_id)
            assert session["event_id"] == linked_event
            # A second task action must preserve the already-running focus session.
            count = len(db.get_pomodoro_history())
            today_view._focus_task(custom_id if item["id"] != custom_id else linked["id"])
            assert view.db_session_id == session_id
            assert len(db.get_pomodoro_history()) == count
            view._reset_timer()
        completed_id = next(item["id"] for item in db.get_checklist(today) if item["is_completed"])
        count = len(db.get_pomodoro_history())
        today_view._focus_task(completed_id)
        assert view.engine.phase == view.engine.PHASE_IDLE
        assert len(db.get_pomodoro_history()) == count
        print("OK task Focus actions preserve event/routine/custom context and active sessions", flush=True)

        # Manual edits in an idle Focus room remove the previous event association.
        window._start_focus_for_event(db.get_event(event_id))
        assert view.source_event_id == event_id
        view._reset_timer()
        view.task_entry.delete(0, "end")
        view.task_entry.insert(0, "Independent review")
        assert view.source_event_id is None
        view._on_main_button_click()
        assert view.engine.title == "Independent review" and view.engine.event_id is None
        view._reset_timer()
        window._start_focus_for_event(db.get_event(event_id))
        view._reset_timer()
        view.category_menu.set("Personal")
        assert view.source_event_id is None
        view._on_main_button_click()
        assert view.engine.category == "Personal" and view.engine.event_id is None
        view._reset_timer()
        print("OK idle title/category edits clear old event linkage", flush=True)

        # Opening Today Calendar must return to today's date from an older task day.
        window.current_date = date.today() - timedelta(days=4)
        window.switch_tab("today")
        today_view.calendar_button.invoke()
        pump()
        assert window.active_tab == "calendar" and window.current_date == date.today()
        widget = DesktopWidget(root, db)
        widget.hide_animated()
        widget.show()
        pump(260)
        assert widget.winfo_ismapped(), "An obsolete delayed hide won the newer show action"
        assert float(widget.attributes("-alpha")) > 0.8
        widget.hide_animated()
        widget.destroy()
        pump(260)
        print("OK widget show/hide reversal and destruction during animation", flush=True)
        with tempfile.TemporaryDirectory() as folder:
            exported = Path(folder) / "export.db"
            restore_requests = []
            dialog = SettingsDialog(window, db, on_theme_change=window._on_theme_change,
                                    on_restore=restore_requests.append)
            pump()
            with patch("ui.settings_dialog.filedialog.asksaveasfilename", return_value=str(exported)):
                dialog._export_backup()
                assert dialog.backup_btn.cget("state") == "disabled"
                pump(400)
                assert exported.is_file() and not dialog._data_busy
                assert "Backup saved" in dialog.data_status.cget("text")
            with patch("ui.settings_dialog.filedialog.askopenfilename", return_value=str(exported)), \
                    patch("ui.settings_dialog.messagebox.askyesno", return_value=False):
                dialog._select_restore()
                pump(400)
                assert "Restore cancelled" in dialog.data_status.cget("text")
                assert not restore_requests
            original_theme = get_current_theme()
            dialog._on_theme_preview("Dark" if original_theme == "light" else "Light")
            pump()
            dialog.destroy()
            assert get_current_theme() == original_theme
            pending = SettingsDialog(window, db)
            gate = threading.Event()
            completed = Mock()
            pending._run_data_job(lambda: gate.wait(1), completed)
            pending.destroy()
            gate.set()
            pump(260)
            completed.assert_not_called()
        print("OK Settings backup worker, cancelled restore, preview rollback and close while busy", flush=True)
        assert not errors, "\n".join(errors)
        print("Release UI journeys passed without Tk callback errors.", flush=True)
    finally:
        faulthandler.cancel_dump_traceback_later()
        root.destroy()
        db.close()


if __name__ == "__main__":
    main()
