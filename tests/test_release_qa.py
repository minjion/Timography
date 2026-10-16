"""Release integration checks; every writable database lives in a temporary folder."""
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from core.database import TimographyDB
from core.undo_manager import UndoManager


class ReleaseFixture(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "planner.db"
        self.db = TimographyDB(str(self.path))
        self.db.initialize()
        self.undo = UndoManager(self.db)
        self.today = date.today().isoformat()

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def event(self, title="Study", day=None, recurring="none"):
        return self.db.add_event(title, "日本語 · Notes", "09:00", "10:00",
                                 day or self.today, "#58a6ff", "Study", recurring, 10)


class ReleasePersistenceTests(ReleaseFixture):
    def test_full_user_workflow_survives_reopen_and_repeat_undo(self):
        event_id = self.event()
        self.undo.record("add", "event", event_id)
        task = next(item for item in self.db.generate_checklist_for_date(self.today)
                    if item["event_id"] == event_id)
        before = self.db.get_checklist_item(task["id"])
        self.db.toggle_checklist_item(task["id"])
        completed = self.db.get_checklist_item(task["id"])
        self.undo.record("toggle", "checklist", task["id"], before, completed)
        session_id = self.db.start_pomodoro("Read notes", tracked=True, event_id=event_id)
        self.assertTrue(self.db.checkpoint_pomodoro(session_id, {self.today: 95.5}, 0))
        self.db.set_settings({"theme": "light", "week_start": "sunday"})
        self.db.close()
        self.db = TimographyDB(str(self.path))
        self.db.initialize()
        self.undo = UndoManager(self.db)
        self.assertEqual(self.db.get_event(event_id)["description"], "日本語 · Notes")
        self.assertEqual(self.db.get_setting("theme"), "light")
        self.assertEqual(self.db.get_setting("week_start"), "sunday")
        self.assertEqual(self.db.get_checklist_item(task["id"]), completed)
        self.assertEqual(self.db.get_focus_seconds_by_date(self.today, self.today), {self.today: 95.5})
        for _ in range(2):
            self.assertTrue(self.undo.undo())
            self.assertEqual(self.db.get_checklist_item(task["id"]), before)
            self.assertTrue(self.undo.redo())
            self.assertEqual(self.db.get_checklist_item(task["id"]), completed)

    def test_new_action_after_undo_discards_redo_branch_without_touching_other_days(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        scheduled = self.event(day=tomorrow, recurring="weekly")
        self.undo.record("add", "event", scheduled)
        self.assertTrue(self.undo.undo())
        task_id = self.db.add_checklist_item("Replacement action", self.today)
        self.undo.record("add", "checklist", task_id)
        self.assertIsNone(self.undo.redo())
        self.assertIsNone(self.db.get_event(scheduled))
        self.assertIsNotNone(self.db.get_checklist_item(task_id))
        self.assertFalse(self.db.get_events_for_date(tomorrow, include_routines=False))

    def test_deleted_scheduled_task_stays_deleted_on_normal_visit_and_restart(self):
        event_id = self.event()
        tasks = self.db.generate_checklist_for_date(self.today)
        target = next(item for item in tasks if item["event_id"] == event_id)
        self.assertTrue(self.db.delete_checklist_item(target["id"]))
        self.db.close()
        self.db = TimographyDB(str(self.path))
        self.db.initialize()
        items = self.db.generate_checklist_for_date(self.today)
        self.assertFalse(any(item["event_id"] == event_id for item in items))
        restored = self.db.sync_checklist_for_date(self.today)
        self.assertEqual(sum(item["event_id"] == event_id for item in restored), 1)


class ReleaseBackupTests(ReleaseFixture):
    def setUp(self):
        super().setUp()
        from core.backups import BackupManager
        self.manager = BackupManager(self.db, Path(self.folder.name) / "backups")

    def test_backup_restore_keeps_every_table_and_invalidates_warm_views(self):
        event_id = self.event("Original plan")
        self.undo.record("add", "event", event_id)
        task_id = self.db.add_checklist_item("Original task", self.today, event_id=event_id)
        self.db.toggle_checklist_item(task_id)
        session = self.db.start_pomodoro("Original work", tracked=True)
        self.db.checkpoint_pomodoro(session, {self.today: 122.75}, 0)
        self.db.add_exam("Original exam", self.today)
        self.db.set_settings({"theme": "light", "week_start": "sunday"})
        original = self.snapshot()
        backup = self.manager.create_backup(Path(self.folder.name) / "export.db")
        self.assertEqual(Path(backup).resolve(), (Path(self.folder.name) / "export.db").resolve())
        self.assertIsInstance(self.manager.validate_backup(backup), dict)
        self.db.update_event(event_id, title="Changed plan")
        self.db.delete_checklist_item(task_id)
        self.db.checkpoint_pomodoro(session, {self.today: 300}, 0)
        self.db.set_setting("theme", "dark")
        changed = self.snapshot()
        self.assertEqual(self.db.get_events_for_date(self.today, False)[0]["title"], "Changed plan")
        self.db.get_study_streak()  # Warm computed snapshots before restore.
        safety = self.manager.restore_backup(backup)
        self.assertTrue(Path(safety).is_file())
        self.assertEqual(self.snapshot(), original)
        self.assertEqual(self.db.get_events_for_date(self.today, False)[0]["title"], "Original plan")
        self.assertEqual(self.db.get_focus_seconds_by_date(self.today, self.today), {self.today: 122.75})
        with closing(sqlite3.connect(safety)) as conn:
            recovered = {table: sorted((tuple(row) for row in conn.execute(f'SELECT * FROM "{table}"')), key=repr)
                         for table in changed}
        self.assertEqual(recovered, changed)

    def test_corrupt_or_unrelated_backup_is_rejected_without_changing_live_data(self):
        self.event()
        original = self.snapshot()
        corrupt = Path(self.folder.name) / "corrupt.db"
        corrupt.write_bytes(b"This is not SQLite data")
        unrelated = Path(self.folder.name) / "unrelated.db"
        with closing(sqlite3.connect(unrelated)) as conn:
            conn.execute("CREATE TABLE other (value TEXT)")
            conn.commit()
        for candidate in (corrupt, unrelated):
            with self.subTest(candidate=candidate.name):
                with self.assertRaises((ValueError, sqlite3.DatabaseError)):
                    self.manager.restore_backup(candidate)
                self.assertEqual(self.snapshot(), original)

    def test_backup_captures_committed_wal_data(self):
        self.db._get_conn().execute("PRAGMA journal_mode = WAL")
        event_id = self.event("Stored in WAL")
        backup = self.manager.create_backup(Path(self.folder.name) / "wal-export.db")
        with closing(sqlite3.connect(backup)) as conn:
            self.assertEqual(conn.execute("SELECT title FROM events WHERE id = ?", (event_id,)).fetchone()[0], "Stored in WAL")
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_failed_migration_rolls_back_live_database_and_keeps_safety_backup(self):
        event_id = self.event("Before backup")
        backup = self.manager.create_backup()
        self.db.update_event(event_id, title="Keep this latest change")
        original = self.snapshot()
        self.db.get_events_for_date(self.today, False)
        with patch.object(self.db, "initialize", side_effect=ValueError("Simulated migration failure")):
            with self.assertRaisesRegex(ValueError, "Simulated migration failure"):
                self.manager.restore_backup(backup)
        self.assertEqual(self.snapshot(), original)
        self.assertEqual(self.db.get_events_for_date(self.today, False)[0]["title"], "Keep this latest change")
        self.assertEqual(len(list(self.manager.backup_dir.glob("before-restore-*.db"))), 1)

    def test_failed_export_preserves_previous_destination_and_cleans_temporary_file(self):
        target = Path(self.folder.name) / "existing-export.db"
        target.write_bytes(b"Previously exported file")
        with patch.object(self.manager, "validate_backup", side_effect=ValueError("Simulated validation failure")):
            with self.assertRaisesRegex(ValueError, "Simulated validation failure"):
                self.manager.create_backup(target)
        self.assertEqual(target.read_bytes(), b"Previously exported file")
        self.assertEqual(list(Path(self.folder.name).glob(".timography-snapshot-*")), [])

    def test_backup_cannot_overwrite_or_restore_working_database(self):
        original = self.snapshot()
        with self.assertRaises(ValueError):
            self.manager.create_backup(self.path)
        with self.assertRaises(ValueError):
            self.manager.restore_backup(self.path)
        self.assertEqual(self.snapshot(), original)

    def test_present_but_invalid_focus_ledger_is_rejected_before_restore(self):
        backup = self.manager.create_backup()
        with closing(sqlite3.connect(backup)) as conn:
            conn.execute("DROP TABLE pomodoro_focus_days")
            conn.execute("CREATE TABLE pomodoro_focus_days (wrong_column TEXT)")
            conn.commit()
        original = self.snapshot()
        with self.assertRaises(ValueError):
            self.manager.restore_backup(backup)
        self.assertEqual(self.snapshot(), original)

    def test_automatic_backups_are_daily_and_retention_preserves_manual_exports(self):
        manual = self.manager.create_backup()
        for day in (1, 2, 3):
            with patch("core.backups.datetime") as clock:
                clock.now.return_value = datetime(2026, 10, day, 12)
                created = self.manager.create_automatic_backup(retain=2)
                self.assertTrue(created.is_file())
                self.assertIsNone(self.manager.create_automatic_backup(retain=2))
        self.assertEqual(sorted(path.name for path in self.manager.backup_dir.glob("automatic-*.db")),
                         ["automatic-20261002.db", "automatic-20261003.db"])
        self.assertTrue(manual.is_file())

    def test_legacy_backup_restores_with_additive_focus_migration(self):
        session = self.db.start_pomodoro("Historical focus", work_minutes=25)
        self.db.update_pomodoro(session, cycles_completed=2)
        backup = self.manager.create_backup()
        with closing(sqlite3.connect(backup)) as conn:
            conn.execute("DROP TABLE pomodoro_focus_days")
            conn.execute("ALTER TABLE pomodoro_sessions DROP COLUMN tracked_seconds")
            conn.execute("DELETE FROM settings WHERE key='focus_metrics_version'")
            conn.commit()
        self.manager.validate_backup(backup)
        self.manager.restore_backup(backup)
        restored = next(item for item in self.db.get_pomodoro_history() if item["id"] == session)
        self.assertEqual(restored["title"], "Historical focus")
        self.assertIsNone(restored["tracked_seconds"])
        self.assertEqual(self.db.get_today_pomodoro_minutes(self.today), 50)
        measured = self.db.start_pomodoro("New measured work", tracked=True)
        self.assertTrue(self.db.checkpoint_pomodoro(measured, {self.today: 120}, 0))
        self.assertEqual(self.db.get_today_pomodoro_minutes(self.today), 52)

    def test_corrupt_todays_automatic_backup_does_not_block_healthy_working_database(self):
        self.event("Healthy current plan")
        original = self.snapshot()
        automatic = self.manager.create_automatic_backup()
        automatic.write_bytes(b"Corrupted automatic snapshot")
        replacement = self.manager.create_automatic_backup()
        self.assertIsNotNone(replacement)
        info = self.manager.validate_backup(replacement)
        self.assertEqual(info["counts"]["events"], 1)
        self.assertEqual(self.snapshot(), original)

    def snapshot(self):
        conn = self.db._get_conn()
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {table: sorted((tuple(row) for row in conn.execute(f'SELECT * FROM "{table}"')), key=repr)
                for table in tables}


class ReleaseInstanceTests(unittest.TestCase):
    def test_two_locks_exclude_second_instance_and_can_be_reacquired(self):
        from core.instance_lock import InstanceLock
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "planner.db"
            first, second = InstanceLock(path), InstanceLock(path)
            try:
                self.assertTrue(first.acquire())
                self.assertTrue(first.acquire())  # The owning client is idempotent.
                self.assertFalse(second.acquire())
                first.release()
                first.release()
                self.assertTrue(second.acquire())
                self.assertFalse(first.acquire())
            finally:
                second.release()
                first.release()

    def test_process_exit_releases_os_lock_without_deleting_lock_file(self):
        from core.instance_lock import InstanceLock
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "planner.db"
            code = ("from core.instance_lock import InstanceLock; import sys; "
                    "lock=InstanceLock(sys.argv[1]); print(lock.acquire(), flush=True)")
            result = subprocess.run([sys.executable, "-c", code, str(path)],
                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=5, check=True)
            self.assertEqual(result.stdout.strip(), "True")
            self.assertTrue(path.with_suffix(".lock").is_file())
            next_owner = InstanceLock(path)
            try:
                self.assertTrue(next_owner.acquire())
                denied = subprocess.run([sys.executable, "-c", code, str(path)],
                    cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=5, check=True)
                self.assertEqual(denied.stdout.strip(), "False")
            finally:
                next_owner.release()


if __name__ == "__main__":
    unittest.main()
