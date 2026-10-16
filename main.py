"""Timography desktop application and its startup, recovery and shutdown lifecycle."""
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import threading
from tkinter import messagebox

import customtkinter as ctk
from config import APP_NAME, DB_PATH, BASE_DIR
from core.backups import BackupManager
from core.database import TimographyDB
from core.instance_lock import InstanceLock
from core.notifications import NotificationManager
from core.scheduler import ReminderScheduler
from core.undo_manager import UndoManager
from core.hotkeys import GlobalHotkeyManager
from core.ui_dispatch import UIDispatcher
from ui.widget import DesktopWidget
from ui.main_window import MainWindow
from ui.event_dialog import EventDialog
from ui.tray import TrayManager
from ui.quick_add import QuickAddDialog
from ui.theme import apply_theme

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main(restart_callback=None):
    root = ctk.CTk()
    root.withdraw()
    root.title(APP_NAME)
    db = TimographyDB(DB_PATH)
    lock = InstanceLock(DB_PATH)
    backups = BackupManager(db)
    dispatcher = UIDispatcher(root)
    hotkey_mgr = reminder_scheduler = tray = None
    desktop_widget = main_window = None
    restore_request = None
    closed = False
    startup_error = False
    file_handler = None
    log_path = Path(DB_PATH).resolve().parent / "logs" / "timography.log"

    def shutdown():
        nonlocal closed
        if closed:
            return
        closed = True
        dispatcher.close()
        for component in (hotkey_mgr, reminder_scheduler, tray):
            if component is not None:
                try:
                    component.stop()
                except Exception:
                    logger.exception("Background service shutdown failed")
        try:
            root.quit()
            # Cancel Tcl timers without deleting child-owned Python commands.
            # Widget destruction then releases those commands exactly once.
            for callback in root.tk.splitlist(root.tk.call("after", "info")):
                root.tk.call("after", "cancel", callback)
            root.destroy()  # Focus views persist and stop timers before SQLite closes.
        finally:
            db.close()

    def report_callback_exception(exc_type, exc_value, traceback):
        logger.error("UI action failed", exc_info=(exc_type, exc_value, traceback))
        if main_window is not None and not closed:
            main_window.set_status(f"Action failed: {exc_value}. Diagnostic log: {log_path}", error=True)

    def refresh_all():
        for view in (desktop_widget, main_window):
            if view is not None and not closed:
                try:
                    view.refresh()
                except Exception as exc:
                    logger.exception("View refresh failed")
                    if main_window is not None:
                        main_window.set_status(f"Could not refresh: {exc}", error=True)

    def open_main_window(tab="today"):
        if tab:
            main_window.switch_tab(tab)
        main_window.show()

    def open_add_event(default_date=None):
        parent = main_window
        if not main_window.winfo_viewable():
            if desktop_widget.winfo_viewable():
                parent = desktop_widget
            else:
                main_window.show()
        EventDialog(parent, db, on_save_callback=refresh_all, default_date=default_date, undo_mgr=undo_mgr)

    def open_quick_add():
        QuickAddDialog(main_window, db, on_created_callback=refresh_all, undo_mgr=undo_mgr)

    def on_checklist_stats_changed(completed, total):
        if desktop_widget:
            desktop_widget.update_checklist_progress(completed, total)

    def request_restore(path):
        nonlocal restore_request
        restore_request = path
        shutdown()

    root.report_callback_exception = report_callback_exception
    root.protocol("WM_DELETE_WINDOW", shutdown)

    try:
        if not lock.acquire():
            messagebox.showinfo(APP_NAME, "Timography is already running. Open your planner from its tray icon.", parent=root)
            return 0
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(file_handler)
        # A snapshot exists before any migration touches existing data.
        backups.create_automatic_backup()
        db.initialize()
        recovered = db.recover_interrupted_pomodoros()
        apply_theme(db.get_setting("theme", "dark"))
        undo_mgr = UndoManager(db)
        notifier = NotificationManager()
        reminder_scheduler = ReminderScheduler(db, notifier)
        reminder_scheduler.start()

        desktop_widget = DesktopWidget(root, db, on_add_event=open_add_event,
            on_open_main=lambda: open_main_window("today"), on_quick_add=open_quick_add,
            on_open_pomodoro=lambda: open_main_window("focus"), on_open_exams=lambda: open_main_window("exams"))
        main_window = MainWindow(root, db, refresh_callback=refresh_all,
            on_checklist_stats_change=on_checklist_stats_changed, undo_mgr=undo_mgr,
            notifier=notifier, settings_callback=reminder_scheduler.reload_settings,
            restore_callback=request_restore)
        desktop_widget.refresh_callback = refresh_all

        hotkey_mgr = GlobalHotkeyManager(root, on_quick_add_callback=open_quick_add, dispatch=dispatcher.post)
        hotkey_mgr.start()
        tray = TrayManager(root, desktop_widget, lambda: open_main_window("today"),
            open_add_event, shutdown, routines_callback=lambda: open_main_window("routines"), dispatch=dispatcher.post)
        threading.Thread(target=tray.run, name="Timography tray", daemon=True).start()

        if db.get_setting("start_in_widget_mode", "0") != "1":
            desktop_widget.hide()
            open_main_window("today")
        if recovered:
            main_window.set_status("Recovered an interrupted focus session from its last saved checkpoint.")
        if getattr(notifier, "_toaster", None) is None:
            main_window.set_status("Windows notifications are unavailable. Your schedule and focus timer still work.", error=True)
        logger.info("Timography ready; database %s", DB_PATH)
        root.mainloop()
    except Exception as exc:
        startup_error = True
        logger.exception("Timography could not start")
        if not closed:
            messagebox.showerror(APP_NAME, f"Timography could not start: {exc}\n\nYour data has not been replaced.\nDiagnostic log: {log_path}", parent=root)
    finally:
        shutdown()
        if restore_request:
            try:
                safety = backups.restore_backup(restore_request)
                logger.info("Restored backup; previous data saved to %s", safety)
            except Exception as exc:
                logger.exception("Restore failed; original data retained")
                messagebox.showerror("Restore failed", f"Your current data was retained.\n{exc}\n\nTimography will restart.")
            finally:
                db.close()
        lock.release()
        if file_handler:
            logging.getLogger().removeHandler(file_handler)
            file_handler.close()
    if restore_request:
        if restart_callback:
            restart_callback()
        else:
            os.execv(sys.executable, [sys.executable, str(Path(BASE_DIR) / "main.py")])
    return 1 if startup_error else 0


if __name__ == "__main__":
    sys.exit(main())
