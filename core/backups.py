"""Validated SQLite snapshots and recoverable, transaction-safe restoration."""
from contextlib import closing
from datetime import datetime
from pathlib import Path
import os
import sqlite3
import tempfile
import time
import logging

logger = logging.getLogger(__name__)


REQUIRED_COLUMNS = {
    "events": {"id", "title", "description", "start_time", "end_time", "date", "color", "category", "recurring", "reminder_minutes"},
    "categories": {"id", "name", "color"},
    "settings": {"key", "value"},
    "routines": {"id", "title", "description", "start_time", "end_time", "days_of_week", "is_active", "color", "category", "reminder_minutes"},
    "checklist_items": {"id", "title", "date", "is_completed", "completed_at", "sort_order", "event_id", "routine_id"},
    "pomodoro_sessions": {"id", "title", "date", "work_minutes", "cycles_completed", "cycles_target", "break_minutes", "start_time", "end_time", "category", "event_id"},
    "event_templates": {"id", "name", "title", "description", "duration_minutes", "color", "category", "reminder_minutes"},
    "exams": {"id", "title", "date", "time", "subject", "color", "notes"},
    "action_log": {"id", "action_type", "target_type", "target_id", "old_data", "new_data", "is_undone"},
    "sent_reminders": {"event_id", "reminder_date"},
}
OPTIONAL_COLUMNS = {"pomodoro_focus_days": {"session_id", "date", "seconds"}}


class BackupManager:
    """Uses the database's lock; never copies an active database file directly.

    Stop application services and active timers before restoring. Idle database
    clients may keep their Python connection; SQLite replaces its content atomically.
    """
    def __init__(self, db, backup_dir=None):
        self.db = db
        parent = Path(db.db_path).resolve().parent if db.db_path != ":memory:" else Path.cwd() / "data"
        self.backup_dir = Path(backup_dir).resolve() if backup_dir else parent / "backups"

    @staticmethod
    def _copy(source, destination):
        deadline = time.monotonic() + 15

        def progress(status, remaining, total):
            if time.monotonic() > deadline:
                raise TimeoutError("The database is busy. Close other Timography windows and try again.")

        source.backup(destination, pages=128, progress=progress, sleep=0.05)

    @staticmethod
    def _read_only(path):
        return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)

    def validate_backup(self, path):
        candidate = Path(path).resolve()
        if not candidate.is_file():
            raise ValueError("Choose an existing Timography backup file.")
        try:
            with closing(self._read_only(candidate)) as connection:
                if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("This backup failed its database integrity check.")
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
                for table, required in REQUIRED_COLUMNS.items():
                    if table not in tables:
                        raise ValueError("This file is not a complete Timography backup.")
                    columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
                    if not required <= columns:
                        raise ValueError(f"The backup has an unsupported {table} schema.")
                for table, required in OPTIONAL_COLUMNS.items():
                    if table in tables:
                        columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
                        if not required <= columns:
                            raise ValueError(f"The backup has an unsupported {table} schema.")
                counts = {table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                          for table in ("events", "routines", "checklist_items", "pomodoro_sessions")}
                return {"path": str(candidate), "counts": counts, "size_bytes": candidate.stat().st_size}
        except sqlite3.Error as exc:
            raise ValueError("The selected file is not a readable SQLite backup.") from exc

    def create_backup(self, destination=None):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = Path(destination).resolve() if destination else self.backup_dir / f"timography-{stamp}.db"
        if self.db.db_path != ":memory:" and target == Path(self.db.db_path).resolve():
            raise ValueError("Choose a backup location different from the working database.")
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=".timography-snapshot-", suffix=".db", dir=target.parent)
        os.close(handle)
        temporary = Path(temporary)
        try:
            with self.db._lock:
                source = self.db._get_conn()
                if source.in_transaction:
                    raise ValueError("Finish the pending database transaction before making a backup.")
                with closing(sqlite3.connect(str(temporary))) as copy:
                    self._copy(source, copy)
            self.validate_backup(temporary)
            temporary.replace(target)
            return target
        finally:
            temporary.unlink(missing_ok=True)

    def create_automatic_backup(self, retain=7):
        """At most one automatic snapshot per day, before startup migrations."""
        if self.db.db_path == ":memory:" or not Path(self.db.db_path).is_file():
            return None
        if Path(self.db.db_path).stat().st_size == 0:
            return None
        target = self.backup_dir / f"automatic-{datetime.now():%Y%m%d}.db"
        if target.exists():
            try:
                self.validate_backup(target)
                return None
            except ValueError:
                quarantine = target.with_name(f"{target.stem}-corrupt-{datetime.now():%H%M%S-%f}.db")
                target.rename(quarantine)
                logger.warning("Retained unreadable automatic backup at %s; creating a fresh snapshot", quarantine)
        result = self.create_backup(target)
        snapshots = sorted((path for path in self.backup_dir.glob("automatic-*.db")
                            if len(path.stem) == len("automatic-20261014")), reverse=True)
        for old in snapshots[max(1, retain):]:
            try:
                old.unlink()
            except OSError:
                logger.warning("Could not remove older automatic backup %s", old, exc_info=True)
        return result

    def restore_backup(self, path):
        """Validate, save a safety snapshot, restore, then run additive migrations.

        SQLite's backup transaction leaves the original database intact if copying
        fails. A migration failure is rolled back from the safety snapshot.
        """
        source_path = Path(path).resolve()
        if self.db.db_path != ":memory:" and source_path == Path(self.db.db_path).resolve():
            raise ValueError("The working database cannot be restored onto itself.")
        self.validate_backup(source_path)
        with self.db._lock:
            safety = self.create_backup(self.backup_dir / f"before-restore-{datetime.now():%Y%m%d-%H%M%S-%f}.db")
            target = self.db._get_conn()
            try:
                with closing(self._read_only(source_path)) as source:
                    self._copy(source, target)
                self._clear_caches()
                self.db.initialize()
                if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("The restored database failed its integrity check.")
            except Exception:
                if target.in_transaction:
                    target.rollback()
                with closing(self._read_only(safety)) as original:
                    self._copy(original, target)
                self._clear_caches()
                raise
            self._clear_caches()
            return safety

    def _clear_caches(self):
        self.db.invalidate_streak_cache()
        self.db._range_cache.clear()
        self.db._range_cache_changes = -1
