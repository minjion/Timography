"""Independent Qt bridge and preview safety checks with disposable databases."""
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

try:
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtTest import QSignalSpy
except ImportError as exc:
    raise unittest.SkipTest("Install the Qt preview requirements to run bridge tests") from exc

from core.database import TimographyDB
from core.backups import BackupManager
from desktop_qt.controller import PlannerController
from main_qt import prepare_database
import main_qt


class QtControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.db = TimographyDB(":memory:")
        self.db.initialize()
        for routine in self.db.get_all_routines():
            self.db.delete_routine(routine["id"])
        self.controller = PlannerController(self.db, preview_mode=True)
        self.today = date.today().isoformat()

    def tearDown(self):
        self.controller.close()
        self.app.processEvents()
        self.db.close()

    def create(self, title="Read chapter", category="Study", estimate=25):
        before = {task["id"] for task in self.controller.tasks}
        self.assertTrue(self.controller.createTask(title, category, estimate))
        return next(task["id"] for task in self.controller.tasks if task["id"] not in before)

    def test_task_schedule_edit_complete_and_remove_flow(self):
        changes = QSignalSpy(self.controller.changed)
        task_id = self.create()
        self.assertEqual(self.controller.taskCount, 1)
        self.assertEqual(self.controller.completedCount, 0)
        self.assertTrue(self.controller.scheduleTask(task_id, self.today, "09:00", "10:00"))
        task = next(task for task in self.controller.tasks if task["id"] == task_id)
        self.assertEqual(len(task["blocks"]), 1)
        block_id = task["blocks"][0]["id"]
        matching = [block for block in self.controller.agenda if block["task_id"] == task_id]
        self.assertEqual(len(matching), 1)
        self.assertTrue(self.controller.editTask(task_id, "Revised chapter", "Work", "日本語 notes", 40))
        task = next(task for task in self.controller.tasks if task["id"] == task_id)
        self.assertEqual((task["title"], task["category"], task["notes"], task["estimate_minutes"]),
                         ("Revised chapter", "Work", "日本語 notes", 40))
        self.assertEqual(next(block for block in self.controller.agenda if block["task_id"] == task_id)["title"], "Revised chapter")
        self.assertTrue(self.controller.toggleTask(task_id))
        self.assertEqual(self.controller.completedCount, 1)
        self.assertTrue(self.controller.toggleTask(task_id))
        self.assertEqual(self.controller.completedCount, 0)
        self.assertTrue(self.controller.removeBlock(block_id))
        self.assertFalse(next(task for task in self.controller.tasks if task["id"] == task_id)["blocks"])
        self.assertTrue(self.controller.deleteTask(task_id))
        self.assertEqual(self.controller.taskCount, 0)
        self.assertGreater(changes.count(), 3)

    def test_bad_input_is_reported_without_partial_schedule_or_task_writes(self):
        errors = QSignalSpy(self.controller.errorChanged)
        self.assertFalse(self.controller.createTask("  ", "Study", 25))
        self.assertTrue(self.controller.errorMessage)
        self.assertEqual(self.controller.taskCount, 0)
        self.controller.clearError()
        self.assertEqual(self.controller.errorMessage, "")
        task_id = self.create()
        for day, start, end in (("2026-02-30", "09:00", "10:00"),
                                (self.today, "11:00", "10:00"),
                                (self.today, "29:00", "30:00")):
            self.assertFalse(self.controller.scheduleTask(task_id, day, start, end))
            self.assertTrue(self.controller.errorMessage)
            self.assertFalse(next(task for task in self.controller.tasks if task["id"] == task_id)["blocks"])
        self.assertGreater(errors.count(), 0)

    def test_theme_persists_and_preview_properties_are_explicit(self):
        self.assertTrue(self.controller.previewMode)
        self.assertEqual(self.controller.selectedDate, self.today)
        self.assertTrue(self.controller.dateLabel)
        self.assertTrue(self.controller.setDarkMode(False))
        self.assertFalse(self.controller.darkMode)
        self.assertEqual(self.db.get_setting("theme"), "light")
        self.controller.close()
        self.controller = PlannerController(self.db, preview_mode=True)
        self.assertFalse(self.controller.darkMode)
        self.assertTrue(self.controller.setDarkMode(True))
        self.assertEqual(self.db.get_setting("theme"), "dark")

    def test_focus_keeps_task_identity_and_partial_work_through_pause_stop(self):
        first = self.create("First focus task", "Work")
        second = self.create("Other focus task", "Health")
        self.assertTrue(self.controller.startFocus(first))
        self.assertEqual(self.controller.activeTaskId, first)
        self.assertTrue(self.controller.focusRunning)
        self.assertEqual(self.controller.engine.title, "First focus task")
        self.assertEqual(self.controller.engine.category, "Work")
        session_id = self.controller.engine.session_id
        self.assertTrue(self.controller.startFocus(second))
        self.assertEqual(self.controller.activeTaskId, first)
        self.assertEqual(self.controller.engine.session_id, session_id)
        time.sleep(0.25)
        self.assertTrue(self.controller.pauseResumeFocus())
        self.assertEqual(self.controller.engine.phase, self.controller.engine.PHASE_PAUSED)
        focused = self.controller.engine.focused_seconds
        time.sleep(0.1)
        self.assertAlmostEqual(self.controller.engine.focused_seconds, focused, places=3)
        self.assertTrue(self.controller.stopFocus())
        self.assertFalse(self.controller.focusRunning)
        self.assertGreater(self.controller.service.task_focus_seconds(first), 0)
        self.assertEqual(self.controller.service.task_focus_seconds(second), 0)
        history = next(session for session in self.db.get_pomodoro_history() if session["id"] == session_id)
        self.assertIsNotNone(history["end_time"])
        self.assertEqual(history["cycles_completed"], 0)
        self.assertGreater(history["tracked_seconds"], 0)

    def test_delete_focused_task_refuses_until_stopped_and_preserves_recorded_history(self):
        task_id = self.create()
        self.assertTrue(self.controller.startFocus(task_id))
        session_id = self.controller.engine.session_id
        time.sleep(0.1)
        self.assertFalse(self.controller.deleteTask(task_id))
        self.assertTrue(self.controller.focusRunning)
        self.assertTrue(any(task["id"] == task_id for task in self.controller.tasks))
        self.assertTrue(self.controller.stopFocus())
        self.assertTrue(self.controller.deleteTask(task_id))
        self.assertFalse(self.controller.focusRunning)
        self.assertFalse(any(task["id"] == task_id for task in self.controller.tasks))
        history = next(session for session in self.db.get_pomodoro_history() if session["id"] == session_id)
        self.assertIsNotNone(history["end_time"])
        self.assertGreater(history["tracked_seconds"], 0)

    def test_completing_active_task_flushes_focus_before_changing_completion(self):
        task_id = self.create()
        self.assertTrue(self.controller.startFocus(task_id), self.controller.errorMessage)
        session_id = self.controller.engine.session_id
        time.sleep(0.1)
        self.assertTrue(self.controller.toggleTask(task_id))
        self.assertFalse(self.controller.focusRunning)
        self.assertEqual(self.controller.completedCount, 1)
        saved = next(session for session in self.db.get_pomodoro_history() if session["id"] == session_id)
        self.assertIsNotNone(saved["end_time"])
        self.assertGreater(saved["tracked_seconds"], 0)

    def test_close_is_idempotent_and_flushes_active_work(self):
        task_id = self.create()
        self.assertTrue(self.controller.startFocus(task_id), self.controller.errorMessage)
        session_id = self.controller.engine.session_id
        time.sleep(0.1)
        self.controller.close()
        self.controller.close()
        self.assertFalse(self.controller.engine._thread.is_alive())
        saved = next(session for session in self.db.get_pomodoro_history() if session["id"] == session_id)
        self.assertIsNotNone(saved["end_time"])
        self.assertGreater(saved["tracked_seconds"], 0)

    def test_failed_close_can_retry_final_focus_write_without_losing_session(self):
        task_id = self.create()
        self.assertTrue(self.controller.startFocus(task_id), self.controller.errorMessage)
        session_id = self.controller.engine.session_id
        time.sleep(0.1)
        with patch.object(self.db, "checkpoint_pomodoro", return_value=False):
            self.assertFalse(self.controller.close())
            self.assertEqual(self.controller.engine.session_id, session_id)
        self.assertTrue(self.controller.close())
        saved = next(session for session in self.db.get_pomodoro_history() if session["id"] == session_id)
        self.assertIsNotNone(saved["end_time"])
        self.assertGreater(saved["tracked_seconds"], 0)

    def test_recurring_agenda_links_the_task_for_this_occurrence(self):
        self.controller.close()
        self.db.close()
        self.db = TimographyDB(":memory:")
        self.db.initialize()
        for routine in self.db.get_all_routines():
            self.db.delete_routine(routine["id"])
        origin = (date.today() - timedelta(days=7)).isoformat()
        event = self.db.add_event("Weekly review", "", "09:00", "10:00", origin,
                                  "#58a6ff", "Study", "weekly", 10)
        self.db.add_checklist_item("Last week's review", origin, event_id=event)
        today_task = self.db.add_checklist_item("This week's review", self.today, event_id=event)
        future = (date.today() + timedelta(days=7)).isoformat()
        self.db.add_checklist_item("Next week's review", future, event_id=event)
        self.controller = PlannerController(self.db, preview_mode=True)
        block = next(block for block in self.controller.agenda if block["id"] == event)
        self.assertEqual(block["task_id"], today_task)

    def test_completed_agenda_task_has_no_start_focus_action_until_reopened(self):
        task_id = self.create()
        self.assertTrue(self.controller.scheduleTask(task_id, self.today, "09:00", "10:00"))
        self.assertEqual(self.controller.agenda[0]["task_id"], task_id)
        self.assertTrue(self.controller.toggleTask(task_id))
        self.assertEqual(self.controller.agenda[0]["task_id"], -1)
        self.assertTrue(self.controller.toggleTask(task_id))
        self.assertEqual(self.controller.agenda[0]["task_id"], task_id)

    def test_ambiguous_legacy_agenda_does_not_choose_an_arbitrary_task(self):
        event = self.db.add_event("Shared occurrence", "", "09:00", "10:00", self.today,
                                  "#58a6ff", "Study", "none", 10)
        self.db.add_checklist_item("First duplicate", self.today, event_id=event)
        self.db.add_checklist_item("Second duplicate", self.today, event_id=event)
        self.controller.refresh()
        self.assertEqual(self.controller.agenda[0]["task_id"], -1)

    def test_file_url_export_and_restore_keep_unified_tasks_blocks_and_focus(self):
        task_id = self.create("Unified task", "Work")
        self.assertTrue(self.controller.scheduleTask(task_id, self.today, "09:00", "10:00"))
        self.assertTrue(self.controller.startFocus(task_id), self.controller.errorMessage)
        time.sleep(0.1)
        self.assertTrue(self.controller.stopFocus())
        original = self.controller.tasks
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "日本語 task backup.db"
            self.assertTrue(self.controller.exportBackup(target.as_uri()), self.controller.errorMessage)
            self.create("Not present in export")
            manager = BackupManager(self.db, Path(folder) / "safety")
            manager.restore_backup(target)
            self.assertTrue(self.controller.refresh())
            self.assertEqual(self.controller.tasks, original)
            self.assertGreater(self.controller.service.task_focus_seconds(task_id), 0)

    def test_backup_rejects_malformed_optional_task_tables(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = BackupManager(self.db, Path(folder) / "backups")
            for table in ("task_details", "task_blocks", "task_session_links"):
                with self.subTest(table=table):
                    target = manager.create_backup(Path(folder) / f"{table}.db")
                    with closing(sqlite3.connect(target)) as connection:
                        connection.execute(f'DROP TABLE "{table}"')
                        connection.execute(f'CREATE TABLE "{table}" (invalid_column TEXT)')
                        connection.commit()
                    with self.assertRaises(ValueError):
                        manager.validate_backup(target)


class QtPreviewTests(unittest.TestCase):
    def test_second_instance_is_rejected_before_copy_or_database_open(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "preview.db"
            with patch("main_qt.InstanceLock") as lock, patch("main_qt.prepare_database") as prepare, \
                    patch("main_qt.TimographyDB") as database, \
                    patch("PySide6.QtWidgets.QMessageBox.information") as notification:
                lock.return_value.acquire.return_value = False
                self.assertEqual(main_qt.main(["--preview-database", str(target)]), 0)
                prepare.assert_not_called()
                database.assert_not_called()
                notification.assert_called_once()
            self.assertFalse(target.exists())

    def test_preview_snapshots_wal_source_once_and_keeps_source_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            source_path = Path(folder) / "original.db"
            preview_path = Path(folder) / "preview" / "planner.db"
            source = TimographyDB(str(source_path))
            source.initialize()
            source._get_conn().execute("PRAGMA journal_mode=WAL")
            event_id = source.add_event("Original source event", "", "09:00", "10:00",
                date.today().isoformat(), "#58a6ff", "Study", "none", 10)
            original_changes = source._get_conn().total_changes
            source_bytes = source_path.read_bytes()
            wal_path = Path(str(source_path) + "-wal")
            wal_bytes = wal_path.read_bytes()
            prepared = prepare_database(source_path, preview_path)
            self.assertEqual(Path(prepared).resolve(), preview_path.resolve())
            self.assertEqual(source._get_conn().total_changes, original_changes)
            self.assertEqual(source_path.read_bytes(), source_bytes)
            self.assertEqual(wal_path.read_bytes(), wal_bytes)
            preview = TimographyDB(str(preview_path))
            try:
                preview.initialize()
                self.assertEqual(preview.get_event(event_id)["title"], "Original source event")
                preview.update_event(event_id, title="Preview-only change")
                prepare_database(source_path, preview_path)
                self.assertEqual(preview.get_event(event_id)["title"], "Preview-only change")
                self.assertEqual(source.get_event(event_id)["title"], "Original source event")
                with closing(sqlite3.connect(preview_path)) as connection:
                    self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            finally:
                preview.close()
                source.close()

    def test_preview_refuses_alias_of_source_without_modifying_it(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "original.db"
            source.write_bytes(b"Unmodified existing file")
            with self.assertRaises(ValueError):
                prepare_database(source, source.parent / "." / source.name)
            self.assertEqual(source.read_bytes(), b"Unmodified existing file")

    def test_missing_source_does_not_create_or_touch_source_and_corrupt_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "original.db"
            target = Path(folder) / "preview" / "planner.db"
            self.assertEqual(Path(prepare_database(source, target)), target)
            self.assertFalse(source.exists())
            self.assertFalse(target.exists())
            source.write_bytes(b"Corrupt source data must be preserved")
            with self.assertRaises((ValueError, sqlite3.DatabaseError)):
                prepare_database(source, target)
            self.assertEqual(source.read_bytes(), b"Corrupt source data must be preserved")
            self.assertFalse(target.exists())
            self.assertEqual(list(target.parent.glob(".preview-*.db")), [])


if __name__ == "__main__":
    unittest.main()
