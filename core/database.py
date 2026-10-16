import sqlite3
import logging
import threading
import json
import math
from copy import deepcopy
from functools import wraps
from datetime import datetime, date, timedelta
from core.validation import validate_date, time_minutes, validate_schedule, validate_settings

logger = logging.getLogger(__name__)

def _serialized_database(cls):
    """UI, reminders and analytics share one connection; serialize transactions."""
    def wrap(method):
        @wraps(method)
        def call(self, *args, **kwargs):
            with self._lock:
                changes = self.conn.total_changes if self.conn is not None else 0
                result = method(self, *args, **kwargs)
                if (method.__name__.startswith(("add_", "update_", "delete_", "toggle_", "set_", "start_", "generate_", "sync_"))
                        and self.conn is not None and self.conn.total_changes != changes):
                    self.invalidate_streak_cache()
                return result
        return call
    for name, method in list(vars(cls).items()):
        if callable(method) and not name.startswith("_"):
            setattr(cls, name, wrap(method))
    return cls


@_serialized_database
class TimographyDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        self._lock = threading.RLock()
        self._streak_cache = self._streak_cache_time = self._streak_cache_key = None
        self._range_cache = {}
        self._range_cache_changes = -1

    def _get_conn(self) -> sqlite3.Connection:
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
        return self.conn

    def get_revision(self):
        """Include writes from another app instance in snapshot invalidation."""
        conn = self._get_conn()
        return conn.total_changes, conn.execute("PRAGMA data_version").fetchone()[0]

    def initialize(self):
        conn = self._get_conn()
        has_settings = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'settings'").fetchone()
        seed_defaults = not has_settings or not self.get_setting("defaults_seeded", "")
        try:
            with conn:
                conn.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    date TEXT NOT NULL,
                    color TEXT DEFAULT '#58a6ff',
                    category TEXT DEFAULT 'Work',
                    recurring TEXT DEFAULT 'none',
                    reminder_minutes INTEGER DEFAULT 10,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                conn.execute('''
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    color TEXT NOT NULL
                )
                ''')
                conn.execute('''
                CREATE TABLE IF NOT EXISTS sent_reminders (
                    event_id INTEGER,
                    reminder_date TEXT,
                    sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (event_id, reminder_date)
                )
                ''')
                conn.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                ''')
                conn.execute("CREATE TABLE IF NOT EXISTS checklist_days (date TEXT PRIMARY KEY)")
                conn.execute('''
                CREATE TABLE IF NOT EXISTS routines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    color TEXT DEFAULT '#58a6ff',
                    category TEXT DEFAULT 'Study',
                    reminder_minutes INTEGER DEFAULT 0,
                    days_of_week TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                ''')

                conn.execute('''
                CREATE TABLE IF NOT EXISTS checklist_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    event_id INTEGER,
                    routine_id INTEGER,
                    date TEXT NOT NULL,
                    is_completed INTEGER DEFAULT 0,
                    completed_at TEXT,
                    sort_order INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                ''')

                conn.execute('''
                CREATE TABLE IF NOT EXISTS pomodoro_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER,
                    title TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    work_minutes INTEGER DEFAULT 25,
                    break_minutes INTEGER DEFAULT 5,
                    cycles_completed INTEGER DEFAULT 0,
                    cycles_target INTEGER DEFAULT 4,
                    category TEXT DEFAULT 'Study',
                    date TEXT NOT NULL
                )
                ''')
                # NULL distinguishes historical cycle estimates from measured work.
                columns = {r["name"] for r in conn.execute("PRAGMA table_info(pomodoro_sessions)")}
                if "tracked_seconds" not in columns:
                    conn.execute("ALTER TABLE pomodoro_sessions ADD COLUMN tracked_seconds REAL")
                conn.execute('''CREATE TABLE IF NOT EXISTS pomodoro_focus_days (
                    session_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    seconds REAL NOT NULL CHECK(seconds >= 0),
                    PRIMARY KEY (session_id, date)
                )''')
                conn.execute("CREATE INDEX IF NOT EXISTS focus_days_date ON pomodoro_focus_days(date)")
                if not conn.execute("SELECT 1 FROM settings WHERE key = 'focus_metrics_version'").fetchone():
                    # Previous preferences selected planned/task credits; recorded focus is now the goal.
                    conn.execute("INSERT OR REPLACE INTO settings VALUES ('streak_include_pomo', '1')")
                    conn.execute("INSERT INTO settings VALUES ('focus_metrics_version', '1')")

                conn.execute('''
                CREATE TABLE IF NOT EXISTS event_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    duration_minutes INTEGER DEFAULT 60,
                    color TEXT DEFAULT '#58a6ff',
                    category TEXT DEFAULT 'Work',
                    reminder_minutes INTEGER DEFAULT 10,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                ''')

                conn.execute('''
                CREATE TABLE IF NOT EXISTS action_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_type TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id INTEGER NOT NULL,
                    old_data TEXT,
                    new_data TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    is_undone INTEGER DEFAULT 0
                )
                ''')

                conn.execute('''
                CREATE TABLE IF NOT EXISTS exams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    date TEXT NOT NULL,
                    time TEXT DEFAULT '09:00',
                    subject TEXT DEFAULT '',
                    color TEXT DEFAULT '#f85149',
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                ''')

                cursor = conn.execute("SELECT COUNT(*) FROM categories")
                if seed_defaults and cursor.fetchone()[0] == 0:
                    default_cats = [
                        ("Work", "#58a6ff"),
                        ("Personal", "#3fb950"),
                        ("Health", "#f85149"),
                        ("Study", "#bc8cff"),
                        ("Social", "#f0883e"),
                        ("Routine", "#d29922"),
                        ("Other", "#8b949e")
                    ]
                    conn.executemany("INSERT INTO categories (name, color) VALUES (?, ?)", default_cats)

                cursor = conn.execute("SELECT COUNT(*) FROM routines")
                if seed_defaults and cursor.fetchone()[0] == 0:
                    default_routines = [
                        ("School / Classes", "School timetable block", "07:30", "11:45", "#58a6ff", "Study", 10, "1,2,3,4,5", 1),
                        ("Lunch Break", "Lunch & recharge", "12:00", "13:00", "#d29922", "Personal", 0, "0,1,2,3,4,5,6", 1),
                        ("Study Session", "Homework, reading, exam prep", "14:30", "17:00", "#bc8cff", "Study", 5, "1,2,3,4,5", 1),
                        ("Workout / Gym", "Daily fitness routine", "17:30", "18:30", "#f85149", "Health", 10, "1,3,5", 1),
                    ]
                    conn.executemany("""
                        INSERT INTO routines (title, description, start_time, end_time, color, category, reminder_minutes, days_of_week, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, default_routines)

                cursor = conn.execute("SELECT COUNT(*) FROM event_templates")
                if seed_defaults and cursor.fetchone()[0] == 0:
                    default_templates = [
                        ("Study Session (2h)", "Deep Study Session", "Focused homework and exam preparation", 120, "#bc8cff", "Study", 10),
                        ("Quick Review (30m)", "Quick Review", "Review flashcards & lecture notes", 30, "#bc8cff", "Study", 5),
                        ("Deep Work (90m)", "Deep Work Block", "Uninterrupted productive project work", 90, "#58a6ff", "Work", 10),
                        ("Gym Workout (1h)", "Gym Workout", "Cardio and strength training", 60, "#f85149", "Health", 15),
                        ("Lunch / Break (45m)", "Lunch & Recharge", "Step away from screen, eat well", 45, "#d29922", "Personal", 0),
                    ]
                    conn.executemany("""
                        INSERT INTO event_templates (name, title, description, duration_minutes, color, category, reminder_minutes)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, default_templates)
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('defaults_seeded', '1')")
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def add_event(self, title: str, description: str, start_time: str, end_time: str, date: str, color: str, category: str, recurring: str, reminder_minutes: int) -> int:
        validate_schedule(locals())
        if recurring not in ("none", "daily", "weekly", "monthly"):
            raise ValueError("Unsupported recurrence.")
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute(
                    "INSERT INTO events (title, description, start_time, end_time, date, color, category, recurring, reminder_minutes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (title, description, start_time, end_time, date, color, category, recurring, reminder_minutes)
                )
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to add event: {e}")
            return -1

    def update_event(self, event_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        old = self.get_event(event_id)
        if old is None:
            return False
        self._validate_columns("events", kwargs)
        validate_schedule({**old, **kwargs})
        if kwargs.get("recurring", old["recurring"]) not in ("none", "daily", "weekly", "monthly"):
            raise ValueError("Unsupported recurrence.")

        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        values.append(event_id)

        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute(f"UPDATE events SET {set_clause} WHERE id = ?", values)
                if {"date", "start_time", "reminder_minutes"} & kwargs.keys():
                    conn.execute("DELETE FROM sent_reminders WHERE event_id = ?", (event_id,))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to update event: {e}")
            return False

    def delete_event(self, event_id: int) -> bool:
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
                conn.execute("DELETE FROM sent_reminders WHERE event_id = ?", (event_id,))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to delete event: {e}")
            return False

    def get_event(self, event_id: int) -> dict | None:
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get event: {e}")
            return None

    def get_events_for_date(self, date_str: str, include_routines: bool = True) -> list[dict]:
        return self.get_events_for_range(date_str, date_str, include_routines).get(date_str, [])

    def get_events_for_week(self, start_date_str: str, include_routines: bool = True) -> dict[str, list[dict]]:
        start = date.fromisoformat(start_date_str)
        return self.get_events_for_range(start_date_str, (start + timedelta(days=6)).isoformat(), include_routines)

    def get_events_for_range(self, start_str: str, end_str: str,
                             include_routines: bool = True) -> dict[str, list[dict]]:
        """Expand occurrences from one events query and one optional routines query.

        Cache bounded snapshots; callers receive copies so filters and rendering cannot
        corrupt another consumer's data. Any SQLite write invalidates the snapshots.
        """
        start, end = date.fromisoformat(start_str), date.fromisoformat(end_str)
        if end < start:
            raise ValueError("End date must be on or after start date.")
        conn = self._get_conn()
        revision = self.get_revision()
        if self._range_cache_changes != revision:
            self._range_cache.clear()
            self._range_cache_changes = revision
        key = (start_str, end_str, include_routines)
        if key in self._range_cache:
            return deepcopy(self._range_cache[key])
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        result = {d.isoformat(): [] for d in days}
        rows = conn.execute("SELECT * FROM events WHERE (date BETWEEN ? AND ?) "
                            "OR (recurring != 'none' AND date <= ?) ORDER BY start_time, id",
                            (start_str, end_str, end_str)).fetchall()
        for row in rows:
            event = dict(row)
            try:
                origin = date.fromisoformat(event["date"])
            except ValueError:
                continue
            recurring = event["recurring"]
            if recurring == "none":
                occurrences = [origin] if start <= origin <= end else []
            elif recurring == "daily":
                occurrences = (d for d in days if d >= origin)
            elif recurring == "weekly":
                occurrences = (d for d in days if d >= origin and d.weekday() == origin.weekday())
            elif recurring == "monthly":
                occurrences = (d for d in days if d >= origin and d.day == origin.day)
            else:
                continue
            for occurrence in occurrences:
                result[occurrence.isoformat()].append({**event, "is_routine": False,
                                                       "occurrence_date": occurrence.isoformat()})
        if include_routines:
            routines = conn.execute("SELECT * FROM routines WHERE is_active = 1 ORDER BY start_time, id").fetchall()
            for row in routines:
                routine = dict(row)
                active = {v.strip() for v in routine["days_of_week"].split(",")}
                for d in days:
                    if d.strftime("%w") in active:
                        result[d.isoformat()].append({**routine, "id": -routine["id"],
                            "routine_id": routine["id"], "date": d.isoformat(),
                            "occurrence_date": d.isoformat(), "recurring": "routine", "is_routine": True})
        for events in result.values():
            events.sort(key=lambda event: (event["start_time"], event["id"]))
        if len(self._range_cache) >= 16:
            self._range_cache.pop(next(iter(self._range_cache)))
        self._range_cache[key] = result
        return deepcopy(result)

    def get_upcoming_reminders(self, now_datetime: datetime) -> list[dict]:
        today_str = now_datetime.strftime("%Y-%m-%d")
        tomorrow_str = (now_datetime + timedelta(days=1)).strftime("%Y-%m-%d")
        events = []
        for occurrence_date in (today_str, tomorrow_str):
            events.extend({**event, "occurrence_date": occurrence_date}
                for event in self.get_events_for_date(occurrence_date))
        upcoming = []

        conn = self._get_conn()
        try:
            for event in events:
                start_time_str = event["start_time"]
                reminder_minutes = event["reminder_minutes"]

                try:
                    occurrence = event["occurrence_date"]
                    event_dt = datetime.strptime(f"{occurrence} {start_time_str}", "%Y-%m-%d %H:%M")
                    reminder_dt = event_dt - timedelta(minutes=reminder_minutes)

                    if reminder_dt <= now_datetime < event_dt:
                        cursor = conn.execute("SELECT 1 FROM sent_reminders WHERE event_id = ? AND reminder_date = ?", (event["id"], occurrence))
                        if not cursor.fetchone():
                            upcoming.append(event)
                except ValueError:
                    continue
        except sqlite3.Error as e:
            logger.error(f"Failed to get upcoming reminders: {e}")

        return upcoming

    def mark_reminder_sent(self, event_id: int, date_str: str) -> None:
        conn = self._get_conn()
        try:
            with conn:
                conn.execute("INSERT OR IGNORE INTO sent_reminders (event_id, reminder_date) VALUES (?, ?)", (event_id, date_str))
        except sqlite3.Error as e:
            logger.error(f"Failed to mark reminder sent: {e}")

    def get_all_categories(self) -> list[dict]:
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT * FROM categories")
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get all categories: {e}")
            return []

    def add_category(self, name: str, color: str) -> int:
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute("INSERT INTO categories (name, color) VALUES (?, ?)", (name, color))
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to add category: {e}")
            return -1

    def delete_category(self, category_id: int) -> bool:
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to delete category: {e}")
            return False

    def get_setting(self, key: str, default: str = None) -> str | None:
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default
        except sqlite3.Error as e:
            logger.error(f"Failed to get setting: {e}")
            return default

    def set_setting(self, key: str, value: str) -> None:
        conn = self._get_conn()
        try:
            with conn:
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        except sqlite3.Error as e:
            logger.error(f"Failed to set setting: {e}")

    def set_settings(self, settings: dict):
        validate_settings(settings)
        with self._get_conn() as conn:
            conn.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", settings.items())

    def get_int_setting(self, key, default, minimum=0, maximum=1440):
        try:
            value = int(self.get_setting(key, str(default)))
            return value if minimum <= value <= maximum else default
        except (TypeError, ValueError):
            return default

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None
        self._range_cache.clear()
        self._range_cache_changes = -1
        self.invalidate_streak_cache()

    def _validate_columns(self, table, values):
        columns = {row["name"] for row in self._get_conn().execute(f"PRAGMA table_info({table})")}
        if set(values) - (columns - {"id", "created_at"}):
            raise ValueError("Unsupported record field.")

    def search_events(self, query: str) -> list[dict]:
        conn = self._get_conn()
        try:
            search_query = f"%{query}%"
            cursor = conn.execute("""
                SELECT * FROM events
                WHERE title LIKE ? OR description LIKE ?
                ORDER BY date DESC, start_time ASC
            """, (search_query, search_query))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to search events: {e}")
            return []

    # --- Routines CRUD ---

    def add_routine(self, title: str, description: str, start_time: str, end_time: str,
                    days_of_week: str, color: str = "#58a6ff", category: str = "Routine",
                    reminder_minutes: int = 0, is_active: int = 1) -> int:
        validate_schedule(locals())
        if not days_of_week or any(d.strip() not in "0123456" or len(d.strip()) != 1 for d in days_of_week.split(",")):
            raise ValueError("Select valid active days.")
        if is_active not in (0, 1):
            raise ValueError("Active state must be 0 or 1.")
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute("""
                    INSERT INTO routines (title, description, start_time, end_time, days_of_week, color, category, reminder_minutes, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (title, description, start_time, end_time, days_of_week, color, category, reminder_minutes, is_active))
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to add routine: {e}")
            return -1

    def update_routine(self, routine_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        self._validate_columns("routines", kwargs)
        old = self.get_routine(routine_id)
        if not old:
            return False
        validate_schedule({**old, **kwargs})
        days = kwargs.get("days_of_week", old["days_of_week"])
        if not days or any(day.strip() not in {"0", "1", "2", "3", "4", "5", "6"} for day in days.split(",")):
            raise ValueError("Select valid active days.")
        if kwargs.get("is_active", old["is_active"]) not in (0, 1):
            raise ValueError("Active state must be 0 or 1.")
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        values.append(routine_id)
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute(f"UPDATE routines SET {set_clause} WHERE id = ?", values)
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to update routine: {e}")
            return False

    def delete_routine(self, routine_id: int) -> bool:
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute("DELETE FROM routines WHERE id = ?", (routine_id,))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to delete routine: {e}")
            return False

    def get_routine(self, routine_id: int) -> dict | None:
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT * FROM routines WHERE id = ?", (routine_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get routine: {e}")
            return None

    def get_all_routines(self) -> list[dict]:
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT * FROM routines ORDER BY start_time ASC")
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get all routines: {e}")
            return []

    def toggle_routine(self, routine_id: int, is_active: int | bool = None) -> bool:
        conn = self._get_conn()
        try:
            with conn:
                if is_active is None:
                    cursor = conn.execute("""
                        UPDATE routines
                        SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END
                        WHERE id = ?
                    """, (routine_id,))
                else:
                    val = 1 if is_active else 0
                    cursor = conn.execute("UPDATE routines SET is_active = ? WHERE id = ?", (val, routine_id))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to toggle routine: {e}")
            return False

    def get_active_routines_for_weekday(self, weekday: str | int) -> list[dict]:
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT * FROM routines WHERE is_active = 1 ORDER BY start_time ASC")
            w_str = str(weekday)
            results = []
            for row in cursor.fetchall():
                r = dict(row)
                days = [d.strip() for d in r.get("days_of_week", "").split(",") if d.strip()]
                if w_str in days:
                    results.append(r)
            return results
        except sqlite3.Error as e:
            logger.error(f"Failed to get active routines for weekday: {e}")
            return []

    # --- Checklist CRUD & Auto-generation ---

    def generate_checklist_for_date(self, date_str: str) -> list[dict]:
        """Seed each date once; manual tasks do not prevent schedule generation.

        Deleting generated tasks is respected on subsequent visits. Sync Schedule
        explicitly adds missing occurrences and updates existing linked titles.
        """
        validate_date(date_str)
        conn = self._get_conn()
        if not conn.execute("SELECT 1 FROM checklist_days WHERE date = ?", (date_str,)).fetchone():
            with conn:
                self.sync_checklist_for_date(date_str)
                conn.execute("INSERT OR IGNORE INTO checklist_days (date) VALUES (?)", (date_str,))
        return self.get_checklist(date_str)

    def sync_checklist_for_date(self, date_str: str) -> list[dict]:
        validate_date(date_str)
        conn = self._get_conn()
        schedule = self.get_events_for_date(date_str)
        existing = self.get_checklist(date_str)
        linked = {(item["event_id"], item["routine_id"]): item for item in existing
                  if item["event_id"] is not None or item["routine_id"] is not None}
        next_order = max((item["sort_order"] for item in existing), default=-1) + 1
        active_keys = {(None, event["routine_id"]) if event["is_routine"] else (event["id"], None)
                       for event in schedule}
        with conn:
            for item in existing:
                source = (item["event_id"], item["routine_id"])
                if source != (None, None) and source not in active_keys:
                    if item["is_completed"]:
                        conn.execute("UPDATE checklist_items SET event_id = NULL, routine_id = NULL WHERE id = ?", (item["id"],))
                    else:
                        conn.execute("DELETE FROM checklist_items WHERE id = ?", (item["id"],))
            for event in schedule:
                key = (None, event["routine_id"]) if event["is_routine"] else (event["id"], None)
                title = f"{event['title']} ({event['start_time']} - {event['end_time']})"
                if key in linked:
                    if linked[key]["title"] != title:
                        conn.execute("UPDATE checklist_items SET title = ? WHERE id = ?", (title, linked[key]["id"]))
                else:
                    conn.execute("INSERT INTO checklist_items (title, event_id, routine_id, date, sort_order) "
                                 "VALUES (?, ?, ?, ?, ?)", (title, *key, date_str, next_order))
                    next_order += 1
            conn.execute("INSERT OR IGNORE INTO checklist_days (date) VALUES (?)", (date_str,))
        return self.get_checklist(date_str)

    def get_checklist(self, date_str: str) -> list[dict]:
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT * FROM checklist_items WHERE date = ? ORDER BY sort_order ASC, id ASC", (date_str,))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get checklist: {e}")
            return []

    def add_checklist_item(self, title: str, date_str: str, event_id: int = None, routine_id: int = None) -> int:
        validate_date(date_str)
        if not title.strip():
            raise ValueError("Enter a task title.")
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM checklist_items WHERE date = ?", (date_str,))
                next_order = cursor.fetchone()[0]
                cursor = conn.execute("""
                    INSERT INTO checklist_items (title, event_id, routine_id, date, sort_order)
                    VALUES (?, ?, ?, ?, ?)
                """, (title, event_id, routine_id, date_str, next_order))
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to add checklist item: {e}")
            return -1

    def toggle_checklist_item(self, item_id: int) -> bool:
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute("SELECT is_completed FROM checklist_items WHERE id = ?", (item_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                new_state = 0 if row["is_completed"] else 1
                completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if new_state else None
                conn.execute("UPDATE checklist_items SET is_completed = ?, completed_at = ? WHERE id = ?", (new_state, completed_at, item_id))
                return True
        except sqlite3.Error as e:
            logger.error(f"Failed to toggle checklist item: {e}")
            return False

    def delete_checklist_item(self, item_id: int) -> bool:
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute("DELETE FROM checklist_items WHERE id = ?", (item_id,))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to delete checklist item: {e}")
            return False

    def get_checklist_stats(self, date_str: str) -> dict:
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT COUNT(*) as total, SUM(CASE WHEN is_completed = 1 THEN 1 ELSE 0 END) as done FROM checklist_items WHERE date = ?", (date_str,))
            row = cursor.fetchone()
            total = row["total"] or 0
            done = row["done"] or 0
            pct = int((done / total * 100)) if total > 0 else 0
            return {"completed": done, "total": total, "percent": pct}
        except sqlite3.Error as e:
            logger.error(f"Failed to get checklist stats: {e}")
            return {"completed": 0, "total": 0, "percent": 0}

    # --- Pomodoro Sessions ---

    def start_pomodoro(self, title: str, category: str = "Study", event_id: int = None,
                       work_minutes: int = 25, break_minutes: int = 5, cycles_target: int = 4,
                       tracked: bool = False) -> int:
        if not title.strip() or not category.strip():
            raise ValueError("Enter a focus title and category.")
        if any(type(v) is not int or v <= 0 for v in (work_minutes, break_minutes, cycles_target)):
            raise ValueError("Focus durations and cycles must be positive integers.")
        conn = self._get_conn()
        today_str = datetime.now().strftime("%Y-%m-%d")
        start_time_iso = datetime.now().isoformat()
        try:
            with conn:
                cursor = conn.execute("""
                    INSERT INTO pomodoro_sessions (event_id, title, start_time, work_minutes, break_minutes, cycles_target, category, date, tracked_seconds)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (event_id, title, start_time_iso, work_minutes, break_minutes, cycles_target, category, today_str, 0 if tracked else None))
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to start pomodoro: {e}")
            return -1

    def update_pomodoro(self, session_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        self._validate_columns("pomodoro_sessions", kwargs)
        if {"tracked_seconds", "date", "start_time", "id"} & kwargs.keys():
            raise ValueError("Measured focus must be updated through checkpoint_pomodoro.")
        for name in ("work_minutes", "break_minutes", "cycles_target", "cycles_completed"):
            if name in kwargs and (type(kwargs[name]) is not int or kwargs[name] < (0 if name == "cycles_completed" else 1)):
                raise ValueError("Invalid focus duration or cycle count.")
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        values.append(session_id)
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute(f"UPDATE pomodoro_sessions SET {set_clause} WHERE id = ?", values)
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to update pomodoro: {e}")
            return False

    def get_pomodoro_history(self, limit: int = 50) -> list[dict]:
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT * FROM pomodoro_sessions ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get pomodoro history: {e}")
            return []

    def get_today_pomodoro_minutes(self, date_str: str) -> int:
        return int(self.get_focus_seconds_by_date(date_str, date_str).get(date_str, 0) / 60)

    def checkpoint_pomodoro(self, session_id: int, daily_seconds: dict[str, float],
                            cycles_completed: int, end_time: str = None) -> bool:
        """Persist cumulative measured work atomically; retries/stale snapshots cannot double count."""
        if type(cycles_completed) is not int or cycles_completed < 0:
            raise ValueError("Completed cycles must be a nonnegative integer.")
        for day, seconds in daily_seconds.items():
            validate_date(day)
            if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
                raise ValueError("Focus seconds must be finite and nonnegative.")
        if end_time is not None:
            datetime.fromisoformat(end_time)
        conn = self._get_conn()
        try:
            with conn:
                session = conn.execute("SELECT tracked_seconds FROM pomodoro_sessions WHERE id = ?", (session_id,)).fetchone()
                if session is None or session[0] is None:
                    return False
                conn.executemany("INSERT INTO pomodoro_focus_days VALUES (?, ?, ?) "
                    "ON CONFLICT(session_id, date) DO UPDATE SET seconds = MAX(seconds, excluded.seconds)",
                    [(session_id, day, seconds) for day, seconds in daily_seconds.items()])
                conn.execute("UPDATE pomodoro_sessions SET tracked_seconds = "
                    "(SELECT COALESCE(SUM(seconds), 0) FROM pomodoro_focus_days WHERE session_id = ?), "
                    "cycles_completed = MAX(cycles_completed, ?), end_time = COALESCE(?, end_time) WHERE id = ?",
                    (session_id, cycles_completed, end_time, session_id))
            self.invalidate_streak_cache()
            return True
        except sqlite3.Error:
            logger.exception("Failed to checkpoint focus session")
            return False

    def recover_interrupted_pomodoros(self) -> int:
        """Close abandoned measured sessions without inventing work after the last checkpoint."""
        conn = self._get_conn()
        with conn:
            cursor = conn.execute("UPDATE pomodoro_sessions SET end_time = ? WHERE tracked_seconds IS NOT NULL AND end_time IS NULL",
                                  (datetime.now().isoformat(),))
        return cursor.rowcount

    def get_focus_seconds_by_date(self, start_str: str, end_str: str,
                                  categories: list[str] = None) -> dict[str, float]:
        """Measured daily work, plus legacy completed-cycle estimates on their original date."""
        validate_date(start_str)
        validate_date(end_str)
        if end_str < start_str:
            raise ValueError("End date must be on or after start date.")
        conn = self._get_conn()
        rows = conn.execute("SELECT f.date, s.category, f.seconds FROM pomodoro_focus_days f "
            "JOIN pomodoro_sessions s ON s.id = f.session_id WHERE f.date BETWEEN ? AND ? "
            "UNION ALL SELECT date, category, MAX(0, work_minutes * cycles_completed * 60) "
            "FROM pomodoro_sessions WHERE tracked_seconds IS NULL AND date BETWEEN ? AND ?",
            (start_str, end_str, start_str, end_str))
        allowed = None if categories is None else {c.casefold() for c in categories}
        result = {}
        for day, category, seconds in rows:
            try:
                validate_date(day)
            except ValueError:
                continue
            if allowed is None or (category or "").casefold() in allowed:
                result[day] = result.get(day, 0) + seconds
        return result

    # --- Event Templates ---

    def add_template(self, name: str, title: str, description: str = "", duration_minutes: int = 60,
                     color: str = "#58a6ff", category: str = "Work", reminder_minutes: int = 10) -> int:
        if not name.strip() or not title.strip():
            raise ValueError("Enter a template name and title.")
        if not isinstance(duration_minutes, int) or not 1 <= duration_minutes <= 1439:
            raise ValueError("Template duration must be between 1 and 1439 minutes.")
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute("""
                    INSERT INTO event_templates (name, title, description, duration_minutes, color, category, reminder_minutes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (name, title, description, duration_minutes, color, category, reminder_minutes))
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to add template: {e}")
            return -1

    def get_all_templates(self) -> list[dict]:
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT * FROM event_templates ORDER BY id ASC")
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get all templates: {e}")
            return []

    def delete_template(self, template_id: int) -> bool:
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute("DELETE FROM event_templates WHERE id = ?", (template_id,))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to delete template: {e}")
            return False

    # --- Action Log (Undo / Redo) ---

    def get_checklist_item(self, item_id):
        row = self._get_conn().execute("SELECT * FROM checklist_items WHERE id = ?", (item_id,)).fetchone()
        return dict(row) if row else None

    def apply_history_action(self, redo=False):
        """Apply a snapshot and move history together, preserving record identities."""
        conn = self._get_conn()
        with conn:
            order, state = ("ASC", 1) if redo else ("DESC", 0)
            row = conn.execute(f"SELECT * FROM action_log WHERE is_undone = ? ORDER BY id {order} LIMIT 1", (state,)).fetchone()
            if not row:
                return None
            action = dict(row)
            table = {"event": "events", "checklist": "checklist_items"}.get(action["target_type"])
            if table is None:
                raise ValueError("Unsupported undo target.")
            target_id, kind = action["target_id"], action["action_type"]
            old = json.loads(action["old_data"]) if action["old_data"] else None
            new = json.loads(action["new_data"]) if action["new_data"] else None
            snapshot = new if redo else old
            remove = (kind == "delete" and redo) or (kind == "add" and not redo)
            restore = (kind == "add" and redo) or (kind == "delete" and not redo)
            if remove:
                cursor = conn.execute(f"DELETE FROM {table} WHERE id = ?", (target_id,))
                if cursor.rowcount != 1:
                    raise ValueError("The record is no longer available.")
            elif restore or kind in ("update", "move") or (kind == "toggle" and snapshot):
                if not snapshot:
                    raise ValueError("The action has no restorable snapshot.")
                columns = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
                values = {k: v for k, v in snapshot.items() if k in columns and k != "id"}
                if table == "events":
                    validate_schedule(values)
                if restore:
                    values["id"] = target_id
                    names = ", ".join(values)
                    placeholders = ", ".join("?" for _ in values)
                    conn.execute(f"INSERT INTO {table} ({names}) VALUES ({placeholders})", list(values.values()))
                else:
                    clause = ", ".join(f"{k} = ?" for k in values)
                    cursor = conn.execute(f"UPDATE {table} SET {clause} WHERE id = ?", [*values.values(), target_id])
                    if cursor.rowcount != 1:
                        raise ValueError("The record is no longer available.")
            elif kind == "toggle" and table == "checklist_items":
                cursor = conn.execute("UPDATE checklist_items SET is_completed = 1 - is_completed, "
                    "completed_at = CASE WHEN is_completed = 0 THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id = ?", (target_id,))
                if cursor.rowcount != 1:
                    raise ValueError("The task is no longer available.")
            else:
                raise ValueError("Unsupported history action.")
            if table == "events":
                conn.execute("DELETE FROM sent_reminders WHERE event_id = ?", (target_id,))
            conn.execute("UPDATE action_log SET is_undone = ? WHERE id = ?", (0 if redo else 1, action["id"]))
        self.invalidate_streak_cache()
        return action

    def log_action(self, action_type: str, target_type: str, target_id: int, old_data: str = None, new_data: str = None) -> int:
        conn = self._get_conn()
        try:
            with conn:
                # Clear redo history on new action
                conn.execute("DELETE FROM action_log WHERE is_undone = 1")
                cursor = conn.execute("""
                    INSERT INTO action_log (action_type, target_type, target_id, old_data, new_data)
                    VALUES (?, ?, ?, ?, ?)
                """, (action_type, target_type, target_id, old_data, new_data))
                # Keep log bounded
                conn.execute("DELETE FROM action_log WHERE id NOT IN (SELECT id FROM action_log ORDER BY id DESC LIMIT 50)")
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to log action: {e}")
            return -1

    def pop_last_undoable_action(self) -> dict | None:
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute("SELECT * FROM action_log WHERE is_undone = 0 ORDER BY id DESC LIMIT 1")
                row = cursor.fetchone()
                if row:
                    action = dict(row)
                    conn.execute("UPDATE action_log SET is_undone = 1 WHERE id = ?", (action["id"],))
                    return action
                return None
        except sqlite3.Error as e:
            logger.error(f"Failed to pop undo action: {e}")
            return None

    def pop_last_redoable_action(self) -> dict | None:
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute("SELECT * FROM action_log WHERE is_undone = 1 ORDER BY id ASC LIMIT 1")
                row = cursor.fetchone()
                if row:
                    action = dict(row)
                    conn.execute("UPDATE action_log SET is_undone = 0 WHERE id = ?", (action["id"],))
                    return action
                return None
        except sqlite3.Error as e:
            logger.error(f"Failed to pop redo action: {e}")
            return None

    # --- Exams CRUD ---

    def add_exam(self, title: str, date: str, time: str = "09:00", subject: str = "",
                 color: str = "#f85149", notes: str = "") -> int:
        validate_date(date)
        time_minutes(time)
        if not title.strip():
            raise ValueError("Enter an exam title.")
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute("""
                    INSERT INTO exams (title, date, time, subject, color, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (title, date, time, subject, color, notes))
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to add exam: {e}")
            return -1

    def get_all_exams(self) -> list[dict]:
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT * FROM exams ORDER BY date ASC, time ASC")
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get all exams: {e}")
            return []

    def get_upcoming_exams(self, limit: int = 5) -> list[dict]:
        conn = self._get_conn()
        today_str = datetime.now().strftime("%Y-%m-%d")
        try:
            cursor = conn.execute("SELECT * FROM exams WHERE date >= ? ORDER BY date ASC, time ASC LIMIT ?", (today_str, limit))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get upcoming exams: {e}")
            return []

    def delete_exam(self, exam_id: int) -> bool:
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to delete exam: {e}")
            return False

    def update_exam(self, exam_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
        self._validate_columns("exams", kwargs)
        if "title" in kwargs and not kwargs["title"].strip():
            raise ValueError("Enter an exam title.")
        if "date" in kwargs:
            validate_date(kwargs["date"])
        if "time" in kwargs:
            time_minutes(kwargs["time"])
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        values.append(exam_id)
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute(f"UPDATE exams SET {set_clause} WHERE id = ?", values)
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to update exam: {e}")
            return False

    # --- Analytics Queries ---

    def get_category_hours_summary(self, start_date_str: str, end_date_str: str,
                                       include_routines: bool = False) -> dict[str, float]:
        """Aggregate total hours spent per category across events (and optionally routines)."""
        cat_minutes = {}

        for events in self.get_events_for_range(start_date_str, end_date_str, include_routines).values():
            for ev in events:
                cat = ev.get("category") or "Other"
                try:
                    dur = time_minutes(ev["end_time"]) - time_minutes(ev["start_time"])
                    if dur > 0:
                        cat_minutes[cat] = cat_minutes.get(cat, 0) + dur
                except (ValueError, KeyError):
                    continue

        return {cat: round(mins / 60.0, 1) for cat, mins in cat_minutes.items()}

    def get_daily_hours_summary(self, start_date_str: str, end_date_str: str,
                                include_routines: bool = False) -> dict[str, float]:
        """Aggregate total scheduled hours for each day in range."""
        daily_hours = {}
        for day, events in self.get_events_for_range(start_date_str, end_date_str, include_routines).items():
            minutes = 0
            for ev in events:
                try:
                    minutes += max(0, time_minutes(ev["end_time"]) - time_minutes(ev["start_time"]))
                except (ValueError, KeyError):
                    continue
            daily_hours[day] = round(minutes / 60, 1)
        return daily_hours

    def get_heatmap_data(self, year: int, include_routines: bool = False) -> dict[str, float]:
        """Returns dict of YYYY-MM-DD -> total hours for every day in year."""
        start_d = date(year, 1, 1)
        end_d = date(year, 12, 31)
        return self.get_daily_hours_summary(
            start_d.strftime("%Y-%m-%d"), end_d.strftime("%Y-%m-%d"),
            include_routines=include_routines
        )

    def get_pomodoro_minutes_range(self, start_str: str, end_str: str) -> int:
        """Sum actual active work, excluding pauses/breaks, with legacy cycle fallback."""
        return int(sum(self.get_focus_seconds_by_date(start_str, end_str).values()) / 60)

    def invalidate_streak_cache(self):
        """Call after events/checklist/pomodoro changes to force recalculation."""
        self._streak_cache = None
        self._streak_cache_time = None

    def get_study_streak(self, min_minutes: int = None,
                         categories: list[str] | None = None,
                         include_pomo: bool = None,
                         include_checklist: bool = None) -> dict:
        """Returns current streak, best streak, today's progress, and goal.

        Args:
            min_minutes: Minimum recorded focus minutes per day to maintain streak.
            categories: Category names to count. None uses the saved selection.
            include_pomo: Compatibility override for counting recorded focus.
            include_checklist: Deprecated and ignored; tasks have no measured duration.

        Returns:
            dict with keys: current, best, today_minutes, goal_minutes
        """
        # Return cached result if < 30 seconds old
        now = datetime.now()
        min_minutes = min_minutes if min_minutes is not None else self.get_int_setting("streak_goal_minutes", 30, 1, 1440)
        if type(min_minutes) is not int or min_minutes <= 0:
            raise ValueError("Focus goal must be a positive integer.")
        if categories is None:
            categories = [c.strip() for c in self.get_setting("streak_categories", "Work,Study,Health,Personal").split(",") if c.strip()]
        if include_pomo is None:
            include_pomo = self.get_setting("streak_include_pomo", "1") == "1"
        cache_key = (now.date(), min_minutes, tuple(sorted(categories)), include_pomo, include_checklist, self.get_revision())
        if (self._streak_cache is not None
                and self._streak_cache_key == cache_key
                and self._streak_cache_time is not None
                and (now - self._streak_cache_time).total_seconds() < 30):
            return dict(self._streak_cache)

        today = now.date()
        current_streak = 0
        best_streak = 0
        temp_streak = 0
        end_str = today.isoformat()
        focus = self.get_focus_seconds_by_date("0001-01-01", end_str, categories) if include_pomo else {}
        today_minutes = int(focus.get(end_str, 0) / 60)
        qualifying = sorted(date.fromisoformat(day) for day, seconds in focus.items() if seconds >= min_minutes * 60)
        previous = None
        for day in qualifying:
            temp_streak = temp_streak + 1 if previous is not None and day - previous == timedelta(days=1) else 1
            best_streak = max(best_streak, temp_streak)
            previous = day
        active_day = today if today_minutes >= min_minutes else today - timedelta(days=1)
        qualified = set(qualifying)
        while active_day in qualified:
            current_streak += 1
            if active_day == date.min:
                break
            active_day -= timedelta(days=1)
        result = {
            "current": current_streak,
            "best": best_streak,
            "today_minutes": today_minutes,
            "goal_minutes": min_minutes,
        }
        self._streak_cache = result
        self._streak_cache_time = now
        self._streak_cache_key = cache_key
        return dict(result)

    @staticmethod
    def _event_duration(event):
        try:
            return max(0, time_minutes(event["end_time"]) - time_minutes(event["start_time"]))
        except (ValueError, KeyError, TypeError):
            return 0

    # --- Free Slot Finder (Auto-Scheduler) ---

    def find_free_slots(self, date_str: str, duration_minutes: int, min_hour: int = 8, max_hour: int = 22) -> list[dict]:
        """Find unoccupied time slots of at least duration_minutes on date_str."""
        if duration_minutes <= 0 or not 0 <= min_hour < max_hour <= 24:
            raise ValueError("Choose a positive duration and valid scheduling hours.")
        events = self.get_events_for_date(date_str, include_routines=True)
        busy_intervals = []
        for ev in events:
            try:
                sh, sm = map(int, ev["start_time"].split(":"))
                eh, em = map(int, ev["end_time"].split(":"))
                busy_intervals.append((sh * 60 + sm, eh * 60 + em))
            except Exception:
                continue
        busy_intervals.sort(key=lambda x: x[0])

        # Merge overlapping busy intervals
        merged_busy = []
        for b_start, b_end in busy_intervals:
            if not merged_busy:
                merged_busy.append([b_start, b_end])
            else:
                if b_start <= merged_busy[-1][1]:
                    merged_busy[-1][1] = max(merged_busy[-1][1], b_end)
                else:
                    merged_busy.append([b_start, b_end])

        # Find gaps within [min_hour*60, max_hour*60]
        day_start = min_hour * 60
        day_end = min(max_hour * 60, 1439)
        free_slots = []

        curr = day_start
        for b_start, b_end in merged_busy:
            if b_start > curr:
                gap = min(b_start, day_end) - curr
                if gap >= duration_minutes:
                    free_slots.append({
                        "start": f"{curr // 60:02d}:{curr % 60:02d}",
                        "end": f"{(curr + duration_minutes) // 60:02d}:{(curr + duration_minutes) % 60:02d}",
                        "max_end": f"{min(b_start, day_end) // 60:02d}:{min(b_start, day_end) % 60:02d}",
                        "available_minutes": gap
                    })
            curr = max(curr, b_end)

        if curr < day_end and (day_end - curr) >= duration_minutes:
            free_slots.append({
                "start": f"{curr // 60:02d}:{curr % 60:02d}",
                "end": f"{(curr + duration_minutes) // 60:02d}:{(curr + duration_minutes) % 60:02d}",
                "max_end": f"{day_end // 60:02d}:{day_end % 60:02d}",
                "available_minutes": day_end - curr
            })

        return free_slots


