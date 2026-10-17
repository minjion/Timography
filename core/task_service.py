"""Frontend-independent task operations over the preserved checklist identity.

Tasks, calendar blocks and source events commit together. Measured focus remains
historical data even when the corresponding task or calendar block is removed.
"""
from contextlib import contextmanager
from datetime import datetime
import re

from core.task_migrations import migrate_tasks
from core.validation import validate_date


class TaskService:
    def __init__(self, db):
        self.db = db
        with db._lock:
            migrate_tasks(db._get_conn())

    @contextmanager
    def _write(self):
        with self.db._lock:
            connection = self.db._get_conn()
            if connection.in_transaction:
                raise RuntimeError("Finish the current transaction before changing tasks.")
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            self.db.invalidate_streak_cache()

    @staticmethod
    def _text(value, name, maximum, required=False):
        if not isinstance(value, str):
            raise ValueError(f"{name} must be text.")
        value = value.strip()
        if required and not value:
            raise ValueError(f"Enter a {name.lower()}.")
        if len(value) > maximum:
            raise ValueError(f"{name} must be at most {maximum} characters.")
        return value

    @staticmethod
    def _estimate(value):
        if type(value) is not int or not 1 <= value <= 1440:
            raise ValueError("Task estimate must be from 1 to 1440 minutes.")
        return value

    @staticmethod
    def _period(start, end):
        parsed = []
        for value in (start, end):
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::00)?", value):
                raise ValueError("Use local date and time, for example 2026-10-17T09:00.")
            try:
                parsed.append(datetime.fromisoformat(value))
            except ValueError as exc:
                raise ValueError("Enter a valid calendar date and time.") from exc
        first, last = parsed
        if first.date() != last.date() or last <= first:
            raise ValueError("A block must end after its start on the same day.")
        return first, last

    @staticmethod
    def _require(connection, task_id):
        TaskService._id(task_id)
        row = connection.execute("SELECT * FROM checklist_items WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise ValueError("This task is no longer available.")
        return row

    @staticmethod
    def _id(value):
        if type(value) is not int or value <= 0:
            raise ValueError("Choose a valid task or block identifier.")
        return value

    @staticmethod
    def _focus_totals(connection, task_id=None):
        where = " WHERE l.task_id = ?" if task_id is not None else ""
        values = (task_id,) if task_id is not None else ()
        return dict(connection.execute("""SELECT l.task_id,
            SUM(CASE WHEN p.tracked_seconds IS NULL
                THEN MAX(0, p.work_minutes * p.cycles_completed * 60)
                ELSE MAX(0, p.tracked_seconds) END)
            FROM task_session_links l JOIN pomodoro_sessions p ON p.id = l.session_id"""
            + where + " GROUP BY l.task_id", values))

    def _list(self, connection, day=None, include_completed=True, task_id=None):
        conditions, values = [], []
        if task_id is not None:
            conditions.append("c.id = ?")
            values.append(task_id)
        if day is not None:
            if day:
                validate_date(day)
                conditions.append("(c.date = ? OR EXISTS (SELECT 1 FROM task_blocks b "
                                  "WHERE b.task_id = c.id AND substr(b.start, 1, 10) = ?))")
                values.extend((day, day))
            else:
                conditions.append("c.date = '' AND NOT EXISTS (SELECT 1 FROM task_blocks b WHERE b.task_id = c.id)")
        if not include_completed:
            conditions.append("c.is_completed = 0")
        clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = connection.execute("""SELECT c.*,
            COALESCE(d.category, e.category, r.category, 'Study') AS task_category,
            COALESCE(d.notes, e.description, r.description, '') AS task_notes,
            d.estimate_minutes AS task_estimate,
            COALESCE(e.start_time, r.start_time) AS source_start,
            COALESCE(e.end_time, r.end_time) AS source_end
            FROM checklist_items c LEFT JOIN task_details d ON d.task_id = c.id
            LEFT JOIN events e ON e.id = c.event_id LEFT JOIN routines r ON r.id = c.routine_id"""
            + clause + " ORDER BY c.is_completed, c.date, c.sort_order, c.id", values).fetchall()
        if not rows:
            return []
        selected = {row["id"] for row in rows}
        blocks = {}
        for row in connection.execute("SELECT id, task_id, start, end, event_id, owns_event, source_routine_id "
                                      "FROM task_blocks ORDER BY start, id"):
            if row["task_id"] in selected:
                block = {key: row[key] for key in ("id", "start", "end", "event_id", "source_routine_id")}
                block["owns_event"] = bool(row["owns_event"])
                blocks.setdefault(row["task_id"], []).append(block)
        totals = self._focus_totals(connection, task_id)
        result = []
        for row in rows:
            estimate = row["task_estimate"]
            if estimate is None:
                try:
                    start = datetime.strptime(row["source_start"], "%H:%M")
                    end = datetime.strptime(row["source_end"], "%H:%M")
                    estimate = max(1, int((end - start).total_seconds() / 60))
                except (ValueError, TypeError):
                    estimate = 25
            result.append({"id": row["id"], "title": row["title"], "category": row["task_category"],
                "notes": row["task_notes"], "estimate_minutes": estimate,
                "is_completed": bool(row["is_completed"]), "date": row["date"],
                "blocks": blocks.get(row["id"], []), "focus_seconds": float(totals.get(row["id"], 0))})
        return result

    def list_tasks(self, day=None, include_completed=True):
        """None lists all tasks; an empty date lists the unscheduled inbox."""
        with self.db._lock:
            return self._list(self.db._get_conn(), day, include_completed)

    def get_task(self, task_id):
        self._id(task_id)
        with self.db._lock:
            tasks = self._list(self.db._get_conn(), task_id=task_id)
            return tasks[0] if tasks else None

    def create_task(self, title, category="Study", notes="", estimate_minutes=25):
        title = self._text(title, "Title", 500, True)
        category = self._text(category, "Category", 100, True)
        notes = self._text(notes, "Notes", 10000)
        estimate_minutes = self._estimate(estimate_minutes)
        with self._write() as connection:
            order = connection.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM checklist_items WHERE date = ''").fetchone()[0]
            task_id = connection.execute("INSERT INTO checklist_items (title, date, sort_order) VALUES (?, '', ?)",
                                         (title, order)).lastrowid
            connection.execute("INSERT INTO task_details VALUES (?, ?, ?, ?)",
                               (task_id, category, notes, estimate_minutes))
        return task_id

    def update_task(self, task_id, **changes):
        unknown = set(changes) - {"title", "category", "notes", "estimate_minutes"}
        if unknown:
            raise ValueError("Unsupported task fields: " + ", ".join(sorted(unknown)))
        validators = {"title": lambda value: self._text(value, "Title", 500, True),
                      "category": lambda value: self._text(value, "Category", 100, True),
                      "notes": lambda value: self._text(value, "Notes", 10000),
                      "estimate_minutes": self._estimate}
        changes = {key: validators[key](value) for key, value in changes.items()}
        with self._write() as connection:
            self._require(connection, task_id)
            if "title" in changes:
                connection.execute("UPDATE checklist_items SET title = ? WHERE id = ?", (changes["title"], task_id))
            details = {key: value for key, value in changes.items() if key != "title"}
            if details:
                connection.execute("INSERT OR IGNORE INTO task_details (task_id) VALUES (?)", (task_id,))
                connection.execute("UPDATE task_details SET " + ", ".join(key + " = ?" for key in details)
                                   + " WHERE task_id = ?", [*details.values(), task_id])
            source = {"title": "title", "category": "category", "notes": "description"}
            source_changes = {source[key]: value for key, value in changes.items() if key in source}
            if "category" in changes:
                color = connection.execute("SELECT color FROM categories WHERE name = ?", (changes["category"],)).fetchone()
                source_changes["color"] = color[0] if color else "#58a6ff"
            if source_changes:
                connection.execute("UPDATE events SET " + ", ".join(key + " = ?" for key in source_changes)
                    + " WHERE id IN (SELECT event_id FROM task_blocks WHERE task_id = ? AND owns_event = 1)",
                    [*source_changes.values(), task_id])
        return True

    def set_completed(self, task_id, completed):
        if type(completed) is not bool:
            raise ValueError("Completion must be true or false.")
        with self._write() as connection:
            task = self._require(connection, task_id)
            if bool(task["is_completed"]) != completed:
                connection.execute("UPDATE checklist_items SET is_completed = ?, completed_at = ? WHERE id = ?",
                    (int(completed), datetime.now().isoformat() if completed else None, task_id))
        return True

    def schedule_task(self, task_id, start, end):
        first, last = self._period(start, end)
        with self._write() as connection:
            self._require(connection, task_id)
            task = self._list(connection, task_id=task_id)[0]
            category = connection.execute("SELECT color FROM categories WHERE name = ?", (task["category"],)).fetchone()
            color = category[0] if category else "#58a6ff"
            event_id = connection.execute("INSERT INTO events "
                "(title, description, start_time, end_time, date, color, category, recurring, reminder_minutes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'none', 10)",
                (task["title"], task["notes"], first.strftime("%H:%M"), last.strftime("%H:%M"),
                 first.date().isoformat(), color, task["category"])).lastrowid
            block_id = connection.execute("INSERT INTO task_blocks (task_id, start, end, event_id, owns_event) "
                "VALUES (?, ?, ?, ?, 1)", (task_id, first.isoformat(), last.isoformat(), event_id)).lastrowid
        return block_id

    def conflicts(self, start, end, exclude_task_id=None):
        """Return overlap warnings against fixed events/routines; scheduling remains an explicit choice."""
        first, last = self._period(start, end)
        with self.db._lock:
            owned = set()
            if exclude_task_id is not None:
                self._id(exclude_task_id)
                owned = {row[0] for row in self.db._get_conn().execute(
                    "SELECT event_id FROM task_blocks WHERE task_id = ? AND event_id IS NOT NULL", (exclude_task_id,))}
            result = []
            for event in self.db.get_events_for_date(first.date().isoformat()):
                if event["id"] in owned:
                    continue
                try:
                    event_start = datetime.fromisoformat(f"{first.date().isoformat()}T{event['start_time']}:00")
                    event_end = datetime.fromisoformat(f"{first.date().isoformat()}T{event['end_time']}:00")
                except ValueError:
                    continue
                if event_start < last and first < event_end:
                    result.append({"event_id": event["id"], "title": event["title"],
                                   "start": event_start.isoformat(), "end": event_end.isoformat()})
            return result

    def unschedule_block(self, block_id):
        self._id(block_id)
        with self._write() as connection:
            block = connection.execute("SELECT * FROM task_blocks WHERE id = ?", (block_id,)).fetchone()
            if block is None:
                return False
            if block["owns_event"] and block["event_id"] is not None:
                connection.execute("DELETE FROM sent_reminders WHERE event_id = ?", (block["event_id"],))
                connection.execute("DELETE FROM events WHERE id = ?", (block["event_id"],))
            connection.execute("DELETE FROM task_blocks WHERE id = ?", (block_id,))
        return True

    def delete_task(self, task_id):
        self._id(task_id)
        with self._write() as connection:
            if not connection.execute("SELECT 1 FROM checklist_items WHERE id = ?", (task_id,)).fetchone():
                return False
            events = [row[0] for row in connection.execute(
                "SELECT event_id FROM task_blocks WHERE task_id = ? AND owns_event = 1", (task_id,))]
            for event_id in events:
                connection.execute("DELETE FROM sent_reminders WHERE event_id = ?", (event_id,))
                connection.execute("DELETE FROM events WHERE id = ?", (event_id,))
            connection.execute("DELETE FROM task_blocks WHERE task_id = ?", (task_id,))
            connection.execute("DELETE FROM task_details WHERE task_id = ?", (task_id,))
            connection.execute("DELETE FROM checklist_items WHERE id = ?", (task_id,))
            # Session links are retained as historical attribution; session/ledger rows survive.
        return True

    def link_session(self, session_id, task_id):
        self._id(session_id)
        with self._write() as connection:
            self._require(connection, task_id)
            if not connection.execute("SELECT 1 FROM pomodoro_sessions WHERE id = ?", (session_id,)).fetchone():
                raise ValueError("This focus session is no longer available.")
            old = connection.execute("SELECT task_id FROM task_session_links WHERE session_id = ?", (session_id,)).fetchone()
            if old and old[0] != task_id:
                raise ValueError("This focus session already belongs to another task.")
            connection.execute("INSERT OR IGNORE INTO task_session_links VALUES (?, ?)", (session_id, task_id))
        return True

    def start_focus(self, task_id, work_minutes=25, break_minutes=5, cycles_target=4):
        """Create measured focus plus task attribution as a single committed operation."""
        for value, maximum in ((work_minutes, 180), (break_minutes, 120), (cycles_target, 12)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("Choose valid focus durations and cycle count.")
        with self._write() as connection:
            self._require(connection, task_id)
            task = self._list(connection, task_id=task_id)[0]
            if task["is_completed"]:
                raise ValueError("Reopen this task before starting a focus session.")
            now = datetime.now()
            today_blocks = [block for block in task["blocks"] if block["start"][:10] == now.date().isoformat()]
            active = next((block for block in today_blocks if block["start"] <= now.isoformat() < block["end"]), None)
            upcoming = next((block for block in today_blocks if block["start"] > now.isoformat()), None)
            selected = active or upcoming or (today_blocks[-1] if today_blocks else None)
            event_id = selected["event_id"] if selected else None
            session_id = connection.execute("INSERT INTO pomodoro_sessions "
                "(event_id, title, start_time, work_minutes, break_minutes, cycles_target, category, date, tracked_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)", (event_id, task["title"], now.isoformat(), work_minutes,
                break_minutes, cycles_target, task["category"], now.date().isoformat())).lastrowid
            connection.execute("INSERT INTO task_session_links VALUES (?, ?)", (session_id, task_id))
        return session_id

    def task_focus_seconds(self, task_id):
        self._id(task_id)
        with self.db._lock:
            return float(self._focus_totals(self.db._get_conn(), task_id).get(task_id, 0))
