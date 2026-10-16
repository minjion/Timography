"""Run real app lifecycle cases in separate processes with isolated databases."""
import argparse
from contextlib import closing
from datetime import date
import logging
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import customtkinter as ctk
import main as app
from core.database import TimographyDB
from core.backups import BackupManager
from core.instance_lock import InstanceLock
from ui.main_window import MainWindow
from ui.widget import DesktopWidget


class SmokeRoot(ctk.CTk):
    widget_mode = False
    restore_path = None
    quick_callback = None
    add_callback = None

    def settle(self, milliseconds=250):
        self.after(milliseconds, self.quit)
        super().mainloop()

    def mainloop(self, *args, **kwargs):
        self.update()
        self.settle()
        planner = next(child for child in self.winfo_children() if isinstance(child, MainWindow))
        widget = next(child for child in self.winfo_children() if isinstance(child, DesktopWidget))
        assert planner.active_tab == "today"
        assert bool(planner.winfo_viewable()) != self.widget_mode
        assert bool(widget.winfo_viewable()) == self.widget_mode
        if self.widget_mode:
            self.quick_callback()
            self.settle()
            popup = next(child for child in planner.winfo_children() if isinstance(child, app.QuickAddDialog))
            assert popup.winfo_viewable(), "Global Quick Add was hidden in widget mode"
            popup.destroy()
            self.add_callback()
            self.settle()
            popup = next(child for child in widget.winfo_children() if isinstance(child, app.EventDialog))
            assert popup.winfo_viewable(), "Widget Add Event dialog was hidden"
            popup.destroy()
        if self.restore_path:
            assert planner.view_focus.start_focus("Work before restore", "Study")
            self.after(300, lambda: planner.restore_callback(self.restore_path))
        else:
            self.after(400, lambda: self.tk.call(self.protocol("WM_DELETE_WINDOW")))
        super().mainloop(*args, **kwargs)


class ErrorCapture(logging.Handler):
    def __init__(self):
        super().__init__(logging.ERROR)
        self.errors = []

    def emit(self, record):
        self.errors.append(record.getMessage())


def run_case(case):
    capture = ErrorCapture()
    logging.getLogger().addHandler(capture)
    try:
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "planner.db")
            fixture = TimographyDB(path)
            fixture.initialize()
            event_id = fixture.add_event("Saved plan", "", "09:00", "10:00",
                date.today().isoformat(), "#58a6ff", "Study", "none", 10)
            fixture.set_setting("start_in_widget_mode", "1" if case == "widget" else "0")
            backup = None
            if case == "restore":
                backup = BackupManager(fixture).create_backup(Path(folder) / "selected-backup.db")
                fixture.update_event(event_id, title="Changed plan")
            interrupted = fixture.start_pomodoro("Interrupted work", tracked=True)
            fixture.checkpoint_pomodoro(interrupted, {date.today().isoformat(): 65}, 0)
            fixture.close()
            SmokeRoot.widget_mode, SmokeRoot.restore_path = case == "widget", str(backup) if backup else None
            restart = Mock()
            holder = InstanceLock(path) if case == "duplicate" else None
            if holder:
                assert holder.acquire()
            try:
                with (patch.object(app, "DB_PATH", path), patch.object(app.ctk, "CTk", SmokeRoot),
                      patch.object(app, "NotificationManager"), patch.object(app, "GlobalHotkeyManager") as hotkeys,
                      patch.object(app, "TrayManager") as tray, patch.object(app.messagebox, "showinfo") as info,
                      patch.object(app.messagebox, "showerror") as error):
                    SmokeRoot.quick_callback = staticmethod(lambda: hotkeys.call_args.kwargs["on_quick_add_callback"]())
                    SmokeRoot.add_callback = staticmethod(lambda: tray.call_args.args[3]())
                    assert app.main(restart_callback=restart) == 0
                    error.assert_not_called()
                    if case == "duplicate":
                        info.assert_called_once()
                        hotkeys.assert_not_called()
            finally:
                if holder:
                    holder.release()
            if case == "restore":
                restart.assert_called_once_with()
                with closing(sqlite3.connect(path)) as connection:
                    assert connection.execute("SELECT title FROM events WHERE id = ?", (event_id,)).fetchone()[0] == "Saved plan"
                safety = next((Path(folder) / "backups").glob("before-restore-*.db"))
                with closing(sqlite3.connect(safety)) as connection:
                    assert connection.execute("SELECT title FROM events WHERE id = ?", (event_id,)).fetchone()[0] == "Changed plan"
                    session = connection.execute("SELECT tracked_seconds, end_time FROM pomodoro_sessions WHERE title = 'Work before restore'").fetchone()
                    assert session and session[0] > 0 and session[1], "Active focus was not saved before restore"
            elif case != "duplicate":
                with closing(sqlite3.connect(path)) as connection:
                    assert connection.execute("SELECT end_time FROM pomodoro_sessions WHERE id = ?", (interrupted,)).fetchone()[0]
                restart.assert_not_called()
            lock = InstanceLock(path)
            assert lock.acquire(), "Shutdown retained the instance lock"
            lock.release()
        assert not capture.errors, "\n".join(capture.errors)
        print(f"OK lifecycle: {case}", flush=True)
    finally:
        logging.getLogger().removeHandler(capture)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=["planner", "widget", "restore", "duplicate"])
    args = parser.parse_args()
    if args.case:
        run_case(args.case)
    else:
        # CTk owns process-global polling state. A fresh interpreter per lifecycle
        # matches actual launch/restart and avoids carrying old Tcl interpreters.
        for case in ("planner", "widget", "restore", "duplicate"):
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--case", case],
                check=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        print("Both launch modes, interrupted recovery, restore/restart and duplicate-instance checks passed.")


if __name__ == "__main__":
    main()
