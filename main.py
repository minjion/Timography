"""Timography — Desktop Timetable Widget, Calendar & Productivity Platform."""
import sys
import os
import threading
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk
from config import APP_NAME, DB_PATH
from core.database import TimographyDB
from core.notifications import NotificationManager
from core.scheduler import ReminderScheduler
from core.undo_manager import UndoManager
from core.hotkeys import GlobalHotkeyManager
from ui.widget import DesktopWidget
from ui.main_window import MainWindow
from ui.event_dialog import EventDialog
from ui.tray import TrayManager
from ui.quick_add import QuickAddDialog

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    # Set appearance
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    
    # Create hidden root window
    root = ctk.CTk()
    root.withdraw()
    root.title(APP_NAME)
    
    # Initialize core components
    db = TimographyDB(DB_PATH)
    db.initialize()
    logger.info("Database initialized")
    
    undo_mgr = UndoManager(db)
    notifier = NotificationManager()
    
    reminder_scheduler = ReminderScheduler(db, notifier)
    reminder_scheduler.start()
    logger.info("Scheduler started")
    
    # Forward declarations for UI components
    desktop_widget = None
    main_window = None

    # Define shared refresh callback
    def refresh_all():
        try:
            if desktop_widget:
                desktop_widget.refresh()
        except Exception:
            pass
        try:
            if main_window:
                main_window.refresh()
        except Exception:
            pass
    
    # Define UI callbacks (all tab-based)
    def open_add_event(default_date=None):
        EventDialog(root, db, on_save_callback=refresh_all, default_date=default_date)
    
    def open_main_window(tab="calendar"):
        main_window.show()
        if tab:
            main_window.switch_tab(tab)

    def open_routines():
        open_main_window("routines")

    def open_quick_add():
        QuickAddDialog(root, db, on_created_callback=refresh_all, undo_mgr=undo_mgr)

    def open_pomodoro():
        open_main_window("focus")

    def open_exams():
        open_main_window("exams")

    def open_analytics():
        open_main_window("analytics")

    def on_checklist_stats_changed(completed: int, total: int):
        if desktop_widget:
            desktop_widget.update_checklist_progress(completed, total)
    
    # Global Hotkey Manager (Ctrl+Space -> Quick Add)
    hotkey_mgr = GlobalHotkeyManager(root, on_quick_add_callback=open_quick_add)
    hotkey_mgr.start()

    def quit_app():
        logger.info("Shutting down Timography...")
        hotkey_mgr.stop()
        reminder_scheduler.stop()
        tray.stop()
        root.quit()
        try:
            root.destroy()
        except Exception:
            pass
    
    # Create UI components
    desktop_widget = DesktopWidget(
        root, db,
        on_add_event=open_add_event,
        on_open_main=lambda: open_main_window("calendar"),
        on_quick_add=open_quick_add,
        on_open_pomodoro=open_pomodoro,
        on_open_exams=open_exams
    )
    logger.info("Desktop widget created")
    
    main_window = MainWindow(
        root, db,
        refresh_callback=refresh_all,
        on_checklist_stats_change=on_checklist_stats_changed,
        undo_mgr=undo_mgr,
        notifier=notifier
    )
    logger.info("Main window created")
    
    # Start system tray in background thread
    tray = TrayManager(
        root, desktop_widget,
        lambda: open_main_window("calendar"),
        open_add_event, quit_app,
        routines_callback=open_routines
    )
    tray_thread = threading.Thread(target=tray.run, daemon=True)
    tray_thread.start()
    logger.info("System tray started")
    
    # Handle root window close
    root.protocol("WM_DELETE_WINDOW", quit_app)
    
    logger.info("Timography is running with unified Tab Navigation!")
    
    # Start the main event loop
    root.mainloop()


if __name__ == "__main__":
    main()
