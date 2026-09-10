import sqlite3
import logging
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

class TimographyDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None

    def _get_conn(self) -> sqlite3.Connection:
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
        return self.conn

    def initialize(self):
        conn = self._get_conn()
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
                if cursor.fetchone()[0] == 0:
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
                if cursor.fetchone()[0] == 0:
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
                if cursor.fetchone()[0] == 0:
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
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database: {e}")

    def add_event(self, title: str, description: str, start_time: str, end_time: str, date: str, color: str, category: str, recurring: str, reminder_minutes: int) -> int:
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
        
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values())
        values.append(event_id)
        
        conn = self._get_conn()
        try:
            with conn:
                cursor = conn.execute(f"UPDATE events SET {set_clause} WHERE id = ?", values)
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
        conn = self._get_conn()
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d")
            weekday = target_date.strftime("%w")
            day_of_month = target_date.strftime("%d")
            
            query = """
                SELECT * FROM events 
                WHERE (date = ? AND recurring = 'none')
                   OR (recurring = 'daily' AND date <= ?)
                   OR (recurring = 'weekly' AND date <= ? AND strftime('%w', date) = ?)
                   OR (recurring = 'monthly' AND date <= ? AND strftime('%d', date) = ?)
                ORDER BY start_time ASC
            """
            cursor = conn.execute(query, (date_str, date_str, date_str, weekday, date_str, day_of_month))
            events = [dict(row) for row in cursor.fetchall()]
            for ev in events:
                ev["is_routine"] = False

            if include_routines:
                routines = self.get_active_routines_for_weekday(weekday)
                for r in routines:
                    routine_ev = {
                        "id": -r["id"],  # Negative ID indicates virtual routine instance
                        "routine_id": r["id"],
                        "title": r["title"],
                        "description": r["description"],
                        "start_time": r["start_time"],
                        "end_time": r["end_time"],
                        "date": date_str,
                        "color": r["color"],
                        "category": r["category"],
                        "recurring": "routine",
                        "reminder_minutes": r["reminder_minutes"],
                        "is_routine": True,
                        "days_of_week": r["days_of_week"],
                        "created_at": r.get("created_at", "")
                    }
                    events.append(routine_ev)
                events.sort(key=lambda x: x.get("start_time", ""))

            return events
        except (sqlite3.Error, ValueError) as e:
            logger.error(f"Failed to get events for date: {e}")
            return []

    def get_events_for_week(self, start_date_str: str, include_routines: bool = True) -> dict[str, list[dict]]:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            week_events = {}
            for i in range(7):
                current_date = start_date + timedelta(days=i)
                current_date_str = current_date.strftime("%Y-%m-%d")
                week_events[current_date_str] = self.get_events_for_date(current_date_str, include_routines=include_routines)
            return week_events
        except ValueError as e:
            logger.error(f"Failed to get events for week: {e}")
            return {}

    def get_upcoming_reminders(self, now_datetime: datetime) -> list[dict]:
        today_str = now_datetime.strftime("%Y-%m-%d")
        events = self.get_events_for_date(today_str)
        upcoming = []
        
        conn = self._get_conn()
        try:
            for event in events:
                start_time_str = event["start_time"]
                reminder_minutes = event["reminder_minutes"]
                
                try:
                    event_dt = datetime.strptime(f"{today_str} {start_time_str}", "%Y-%m-%d %H:%M")
                    reminder_dt = event_dt - timedelta(minutes=reminder_minutes)
                    
                    if reminder_dt <= now_datetime < event_dt:
                        cursor = conn.execute("SELECT 1 FROM sent_reminders WHERE event_id = ? AND reminder_date = ?", (event["id"], today_str))
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
        """Generate checklist from today's schedule if none exists yet."""
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM checklist_items WHERE date = ?", (date_str,))
            if cursor.fetchone()[0] == 0:
                events = self.get_events_for_date(date_str, include_routines=True)
                items_to_insert = []
                for idx, ev in enumerate(events):
                    title = ev.get("title", "Task")
                    time_info = f"({ev.get('start_time', '')} - {ev.get('end_time', '')})"
                    full_title = f"{title} {time_info}"
                    if ev.get("is_routine"):
                        items_to_insert.append((full_title, None, ev.get("routine_id"), date_str, idx))
                    else:
                        items_to_insert.append((full_title, ev.get("id"), None, date_str, idx))
                
                if items_to_insert:
                    with conn:
                        conn.executemany("""
                            INSERT INTO checklist_items (title, event_id, routine_id, date, sort_order)
                            VALUES (?, ?, ?, ?, ?)
                        """, items_to_insert)
            return self.get_checklist(date_str)
        except sqlite3.Error as e:
            logger.error(f"Failed to generate checklist: {e}")
            return []

    def get_checklist(self, date_str: str) -> list[dict]:
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT * FROM checklist_items WHERE date = ? ORDER BY sort_order ASC, id ASC", (date_str,))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get checklist: {e}")
            return []

    def add_checklist_item(self, title: str, date_str: str, event_id: int = None, routine_id: int = None) -> int:
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
                       work_minutes: int = 25, break_minutes: int = 5, cycles_target: int = 4) -> int:
        conn = self._get_conn()
        today_str = datetime.now().strftime("%Y-%m-%d")
        start_time_iso = datetime.now().isoformat()
        try:
            with conn:
                cursor = conn.execute("""
                    INSERT INTO pomodoro_sessions (event_id, title, start_time, work_minutes, break_minutes, cycles_target, category, date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (event_id, title, start_time_iso, work_minutes, break_minutes, cycles_target, category, today_str))
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to start pomodoro: {e}")
            return -1

    def update_pomodoro(self, session_id: int, **kwargs) -> bool:
        if not kwargs:
            return False
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
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT SUM(work_minutes * cycles_completed) FROM pomodoro_sessions WHERE date = ?", (date_str,))
            res = cursor.fetchone()[0]
            return int(res or 0)
        except sqlite3.Error as e:
            logger.error(f"Failed to get pomodoro minutes: {e}")
            return 0

    # --- Event Templates ---

    def add_template(self, name: str, title: str, description: str = "", duration_minutes: int = 60,
                     color: str = "#58a6ff", category: str = "Work", reminder_minutes: int = 10) -> int:
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

    def get_category_hours_summary(self, start_date_str: str, end_date_str: str) -> dict[str, float]:
        """Aggregate total hours spent per category across events and routines."""
        start_d = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_d = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        cat_minutes = {}

        curr = start_d
        while curr <= end_d:
            d_str = curr.strftime("%Y-%m-%d")
            evs = self.get_events_for_date(d_str, include_routines=True)
            for ev in evs:
                cat = ev.get("category") or "Other"
                try:
                    sh, sm = map(int, ev["start_time"].split(":"))
                    eh, em = map(int, ev["end_time"].split(":"))
                    dur = (eh * 60 + em) - (sh * 60 + sm)
                    if dur > 0:
                        cat_minutes[cat] = cat_minutes.get(cat, 0) + dur
                except Exception:
                    continue
            curr += timedelta(days=1)

        return {cat: round(mins / 60.0, 1) for cat, mins in cat_minutes.items()}

    def get_daily_hours_summary(self, start_date_str: str, end_date_str: str) -> dict[str, float]:
        """Aggregate total scheduled hours for each day in range."""
        start_d = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_d = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        daily_hours = {}

        curr = start_d
        while curr <= end_d:
            d_str = curr.strftime("%Y-%m-%d")
            evs = self.get_events_for_date(d_str, include_routines=True)
            tot_min = 0
            for ev in evs:
                try:
                    sh, sm = map(int, ev["start_time"].split(":"))
                    eh, em = map(int, ev["end_time"].split(":"))
                    dur = (eh * 60 + em) - (sh * 60 + sm)
                    if dur > 0:
                        tot_min += dur
                except Exception:
                    continue
            daily_hours[d_str] = round(tot_min / 60.0, 1)
            curr += timedelta(days=1)

        return daily_hours

    def get_heatmap_data(self, year: int) -> dict[str, float]:
        """Returns dict of YYYY-MM-DD -> total hours for every day in year."""
        start_d = date(year, 1, 1)
        end_d = date(year, 12, 31)
        return self.get_daily_hours_summary(start_d.strftime("%Y-%m-%d"), end_d.strftime("%Y-%m-%d"))

    def get_study_streak(self, min_minutes: int = 30) -> dict:
        """Returns current streak and best streak of days with >= min_minutes of study."""
        today = datetime.now().date()
        current_streak = 0
        best_streak = 0
        temp_streak = 0

        # Scan back 180 days
        for i in range(180):
            d = today - timedelta(days=i)
            d_str = d.strftime("%Y-%m-%d")
            evs = self.get_events_for_date(d_str, include_routines=True)
            study_mins = 0
            for ev in evs:
                if (ev.get("category") or "").lower() == "study":
                    try:
                        sh, sm = map(int, ev["start_time"].split(":"))
                        eh, em = map(int, ev["end_time"].split(":"))
                        dur = (eh * 60 + em) - (sh * 60 + sm)
                        if dur > 0:
                            study_mins += dur
                    except Exception:
                        continue
            study_mins += self.get_today_pomodoro_minutes(d_str)

            if study_mins >= min_minutes:
                temp_streak += 1
                if i == current_streak:
                    current_streak += 1
            else:
                if i == 0:
                    # Today not completed yet is fine, check starting from yesterday
                    pass
                else:
                    if temp_streak > best_streak:
                        best_streak = temp_streak
                    temp_streak = 0

        best_streak = max(best_streak, current_streak, temp_streak)
        return {"current": current_streak, "best": best_streak}

    # --- Free Slot Finder (Auto-Scheduler) ---

    def find_free_slots(self, date_str: str, duration_minutes: int, min_hour: int = 8, max_hour: int = 22) -> list[dict]:
        """Find unoccupied time slots of at least duration_minutes on date_str."""
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
        day_end = max_hour * 60
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


