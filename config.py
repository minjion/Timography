import os

APP_NAME = "Timography"
APP_VERSION = "4.0.0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "timography.db")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
ICON_PATH = os.path.join(ASSETS_DIR, "icon.ico")

# Ensure directories exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

# Default settings
DEFAULT_REMINDER_MINUTES = 10
DEFAULT_WIDGET_X = 50
DEFAULT_WIDGET_Y = 50
DEFAULT_WIDGET_WIDTH = 300
DEFAULT_WIDGET_HEIGHT = 450
REFRESH_INTERVAL_MS = 60000  # 1 minute
SCHEDULER_CHECK_INTERVAL_SECONDS = 30

# Pomodoro Defaults (in minutes)
POMODORO_WORK_MINUTES = 25
POMODORO_SHORT_BREAK = 5
POMODORO_LONG_BREAK = 15
POMODORO_CYCLES_BEFORE_LONG = 4

# Hotkeys
QUICK_ADD_HOTKEY = "<ctrl>+<space>"

# Streak minimum minutes per day
STREAK_MIN_STUDY_MINUTES = 30
DEFAULT_STREAK_CATEGORIES = "Work,Study,Health,Personal"
DEFAULT_STREAK_INCLUDE_POMO = True
DEFAULT_STREAK_INCLUDE_CHECKLIST = True

# Theme
DEFAULT_THEME = "dark"

# Notifications
DEFAULT_MORNING_BRIEFING_HOUR = 8
DEFAULT_STREAK_WARNINGS = True
DEFAULT_WEEKLY_RECAP = True
