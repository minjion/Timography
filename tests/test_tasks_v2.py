"""Application-service contracts shared by the Qt and legacy task frontends."""
import sqlite3
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from core.database import TimographyDB
from core.task_migrations import migrate_tasks
from core.task_service import TaskService


class TaskServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = TimographyDB(":memory:")
        self.db.initialize()
        self.service = TaskService(self.db)
        self.day = date.today().isoformat()

    def tearDown(self):
        self.db.close()

    def event(self, recurring="none", day=None):
        return self.db.add_event("Read chapter", "Original notes", "09:00", "10:00", day or self.day,
                                 "#bc8cff", "Study", recurring, 10)

    def counts(self):
        return tuple(self.db._get_conn().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("checklist_items", "task_details", "task_blocks", "events", "pomodoro_sessions", "task_session_links"))

    def test_inbox_create_edit_complete_reopen_keeps_canonical_identity(self):
        task_id = self.service.create_task("  Outline  ", "Work", "Notes", 45)
        task = self.service.get_task(task_id)
        self.assertEqual((task["title"], task["category"], task["date"], task["blocks"]), ("Outline", "Work", "", []))
        self.assertEqual(self.service.list_tasks("")[0]["id"], task_id)
        self.service.update_task(task_id, title="Draft", notes="Next step", estimate_minutes=60)
        self.service.set_completed(task_id, True)
        completed = self.db.get_checklist_item(task_id)["completed_at"]
        self.service.set_completed(task_id, True)
        self.assertEqual(self.db.get_checklist_item(task_id)["completed_at"], completed)
        self.assertEqual(self.service.list_tasks(include_completed=False), [])
        self.service.set_completed(task_id, False)
        self.assertIsNone(self.db.get_checklist_item(task_id)["completed_at"])
        self.assertEqual(self.service.get_task(task_id)["title"], "Draft")
        self.assertFalse(self.db._get_conn().in_transaction)

    def test_multiple_blocks_project_earliest_date_and_do_not_duplicate_legacy_tasks(self):
        task_id = self.service.create_task("Write")
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        later = self.service.schedule_task(task_id, tomorrow + "T10:00", tomorrow + "T11:00")
        earlier = self.service.schedule_task(task_id, self.day + "T09:00", self.day + "T09:30")
        task = self.service.get_task(task_id)
        self.assertEqual(task["date"], self.day)
        self.assertEqual([block["id"] for block in task["blocks"]], [earlier, later])
        self.assertEqual(self.service.list_tasks(tomorrow)[0]["id"], task_id)
        for day in (self.day, tomorrow):
            self.db.sync_checklist_for_date(day)
        matches = [item for item in self.service.list_tasks() if item["title"] == "Write"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(self.db.get_checklist(self.day)[0]["id"], task_id)
        self.service.unschedule_block(earlier)
        self.assertEqual(self.service.get_task(task_id)["date"], tomorrow)
        self.service.unschedule_block(later)
        self.assertEqual(self.service.get_task(task_id)["date"], "")
        self.assertEqual(self.service.get_task(task_id)["blocks"], [])

    def test_owned_events_follow_task_metadata_and_category_color(self):
        task_id = self.service.create_task("Read")
        self.service.schedule_task(task_id, self.day + "T09:00", self.day + "T10:00")
        event_id = self.service.get_task(task_id)["blocks"][0]["event_id"]
        self.service.update_task(task_id, title="Plan", category="Work", notes="Details")
        event = self.db.get_event(event_id)
        work_color = next(category["color"] for category in self.db.get_all_categories() if category["name"] == "Work")
        self.assertEqual((event["title"], event["category"], event["description"], event["color"]),
                         ("Plan", "Work", "Details", work_color))
        self.db.sync_checklist_for_date(self.day)
        self.assertEqual(self.service.get_task(task_id)["title"], "Plan")

    def test_legacy_inserts_are_visible_and_metadata_derives_until_explicitly_edited(self):
        event_id = self.event()
        task_id = self.db.add_checklist_item("Legacy task", self.day, event_id=event_id)
        task = self.service.get_task(task_id)
        self.assertEqual((task["category"], task["notes"], task["estimate_minutes"]), ("Study", "Original notes", 60))
        self.assertEqual(task["blocks"][0]["event_id"], event_id)
        self.assertFalse(task["blocks"][0]["owns_event"])
        self.db.update_event(event_id, category="Work", description="Changed source")
        self.assertEqual(self.service.get_task(task_id)["category"], "Work")
        self.service.update_task(task_id, category="Health", notes="", estimate_minutes=10)
        self.db.update_event(event_id, category="Study")
        task = self.service.get_task(task_id)
        self.assertEqual((task["category"], task["notes"], task["estimate_minutes"]), ("Health", "", 10))
        self.assertEqual(self.db.get_event(event_id)["category"], "Study")

    def test_unscheduling_shared_legacy_recurrence_does_not_delete_series(self):
        event_id = self.event("daily")
        task_id = self.db.add_checklist_item("Occurrence", self.day, event_id=event_id)
        block = self.service.get_task(task_id)["blocks"][0]
        self.service.unschedule_block(block["id"])
        self.assertIsNotNone(self.db.get_event(event_id))
        self.assertEqual(self.service.get_task(task_id)["blocks"], [])
        self.assertEqual(len(self.db.get_events_for_date(self.day, False)), 1)

    def test_legacy_calendar_retiming_and_deletion_update_task_projection(self):
        task_id = self.service.create_task("Read")
        self.service.schedule_task(task_id, self.day + "T09:00", self.day + "T10:00")
        event_id = self.service.get_task(task_id)["blocks"][0]["event_id"]
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        self.db.update_event(event_id, date=tomorrow, start_time="11:00", end_time="12:00")
        task = self.service.get_task(task_id)
        self.assertEqual(task["date"], tomorrow)
        self.assertEqual(task["blocks"][0]["start"], tomorrow + "T11:00:00")
        self.db.delete_event(event_id)
        self.assertEqual(self.service.get_task(task_id)["date"], "")
        self.assertEqual(self.service.get_task(task_id)["blocks"], [])

    def test_scheduling_failure_rolls_back_calendar_event_and_task_projection(self):
        task_id = self.service.create_task("Read")
        before = self.counts()
        self.db._get_conn().execute("CREATE TRIGGER fail_block BEFORE INSERT ON task_blocks "
            "WHEN NEW.owns_event = 1 BEGIN SELECT RAISE(ABORT, 'simulated disk write failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.schedule_task(task_id, self.day + "T09:00", self.day + "T10:00")
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.service.get_task(task_id)["date"], "")
        self.assertFalse(self.db._get_conn().in_transaction)

    def test_create_and_edit_failures_cannot_partially_update_tasks(self):
        connection = self.db._get_conn()
        before = self.counts()
        connection.execute("CREATE TRIGGER fail_details BEFORE INSERT ON task_details "
                           "BEGIN SELECT RAISE(ABORT, 'simulated failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.create_task("Read")
        self.assertEqual(self.counts(), before)
        connection.execute("DROP TRIGGER fail_details")
        task_id = self.service.create_task("Original")
        self.service.schedule_task(task_id, self.day + "T09:00", self.day + "T10:00")
        connection.execute("CREATE TRIGGER fail_event_edit BEFORE UPDATE ON events "
                           "BEGIN SELECT RAISE(ABORT, 'simulated failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.update_task(task_id, title="Wrong", notes="Wrong")
        task = self.service.get_task(task_id)
        self.assertEqual((task["title"], task["notes"]), ("Original", ""))
        self.assertFalse(connection.in_transaction)

    def test_delete_task_preserves_focus_history_and_unrelated_events(self):
        unrelated = self.event("weekly")
        task_id = self.service.create_task("Tracked")
        self.service.schedule_task(task_id, self.day + "T13:00", self.day + "T14:00")
        owned = self.service.get_task(task_id)["blocks"][0]["event_id"]
        session_id = self.service.start_focus(task_id)
        self.db.checkpoint_pomodoro(session_id, {self.day: 87.5}, 0)
        self.assertEqual(self.service.get_task(task_id)["focus_seconds"], 87.5)
        self.service.delete_task(task_id)
        self.assertIsNone(self.service.get_task(task_id))
        self.assertIsNone(self.db.get_event(owned))
        self.assertIsNotNone(self.db.get_event(unrelated))
        self.assertEqual(self.db.get_focus_seconds_by_date(self.day, self.day)[self.day], 87.5)
        self.assertEqual(self.service.task_focus_seconds(task_id), 87.5)
        self.assertEqual(self.db.get_pomodoro_history()[0]["id"], session_id)

    def test_link_is_idempotent_and_never_steals_another_tasks_focus(self):
        first = self.service.create_task("First")
        second = self.service.create_task("Second")
        session = self.db.start_pomodoro("Legacy", work_minutes=25)
        self.db.update_pomodoro(session, cycles_completed=2)
        self.service.link_session(session, first)
        self.service.link_session(session, first)
        self.assertEqual(self.service.get_task(first)["focus_seconds"], 3000)
        with self.assertRaises(ValueError):
            self.service.link_session(session, second)
        self.assertEqual(self.service.get_task(second)["focus_seconds"], 0)

    def test_start_focus_uses_current_task_category_and_active_today_block(self):
        task_id = self.service.create_task("Read", category="Work")
        past = (date.today() - timedelta(days=1)).isoformat()
        self.service.schedule_task(task_id, past + "T09:00", past + "T10:00")
        self.service.schedule_task(task_id, self.day + "T13:00", self.day + "T14:00")
        self.service.schedule_task(task_id, self.day + "T15:00", self.day + "T16:00")
        with patch("core.task_service.datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime.combine(date.today(), datetime.min.time()).replace(hour=13, minute=15)
            session = self.service.start_focus(task_id)
        row = self.db.get_pomodoro_history()[0]
        active = self.service.get_task(task_id)["blocks"][1]
        self.assertEqual((row["id"], row["event_id"], row["category"], row["tracked_seconds"]),
                         (session, active["event_id"], "Work", 0))
        self.service.set_completed(task_id, True)
        before = self.counts()
        with self.assertRaises(ValueError):
            self.service.start_focus(task_id)
        self.assertEqual(self.counts(), before)

    def test_start_focus_failure_cannot_leave_unlinked_session(self):
        task_id = self.service.create_task("Read")
        self.db._get_conn().execute("CREATE TRIGGER fail_link BEFORE INSERT ON task_session_links "
                                   "BEGIN SELECT RAISE(ABORT, 'simulated failure'); END")
        before = self.counts()
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.start_focus(task_id)
        self.assertEqual(self.counts(), before)
        self.assertFalse(self.db._get_conn().in_transaction)

    def test_conflicts_are_warnings_and_touching_boundaries_do_not_overlap(self):
        for routine in self.db.get_all_routines():
            self.db.delete_routine(routine["id"])
        event_id = self.event()
        task_id = self.service.create_task("Parallel")
        warnings = self.service.conflicts(self.day + "T09:30", self.day + "T10:30")
        self.assertEqual([warning["event_id"] for warning in warnings], [event_id])
        self.assertEqual(self.service.conflicts(self.day + "T10:00", self.day + "T11:00"), [])
        self.service.schedule_task(task_id, self.day + "T09:30", self.day + "T10:30")
        self.assertEqual(len(self.service.conflicts(self.day + "T09:45", self.day + "T10:00", task_id)), 1)

    def test_invalid_values_are_rejected_without_any_writes(self):
        before = self.counts()
        for changes in ({"title": " "}, {"title": "Read", "estimate_minutes": 0},
                        {"title": "Read", "estimate_minutes": True}, {"title": "Read", "category": ""}):
            with self.assertRaises(ValueError):
                self.service.create_task(**changes)
        self.assertEqual(self.counts(), before)
        task_id = self.service.create_task("Read")
        before = self.counts()
        for start, end in (("invalid", self.day + "T10:00"), (self.day + "T10:00", self.day + "T09:00"),
                           (self.day + "T23:00", "2099-01-01T00:00"),
                           (self.day + "T09:00Z", self.day + "T10:00Z"),
                           (self.day + "T09:00:10", self.day + "T10:00:10")):
            with self.assertRaises(ValueError):
                self.service.schedule_task(task_id, start, end)
        with self.assertRaises(ValueError):
            self.service.update_task(task_id, is_completed=True)
        with self.assertRaises(ValueError):
            self.service.set_completed(task_id, 1)
        with self.assertRaises(ValueError):
            self.service.delete_task(True)
        self.assertEqual(self.counts(), before)
        self.assertFalse(self.db._get_conn().in_transaction)

    def test_operations_do_not_commit_an_unrelated_pending_transaction(self):
        connection = self.db._get_conn()
        connection.execute("INSERT INTO settings VALUES ('pending', 'uncommitted')")
        with self.assertRaises(RuntimeError):
            self.service.create_task("Read")
        self.assertTrue(connection.in_transaction)
        connection.rollback()
        self.assertIsNone(self.db.get_setting("pending"))

    def test_list_uses_batched_focus_and_block_reads(self):
        for index in range(30):
            self.service.create_task(f"Task {index}")
        statements = []
        self.db._get_conn().set_trace_callback(statements.append)
        try:
            tasks = self.service.list_tasks()
        finally:
            self.db._get_conn().set_trace_callback(None)
        self.assertEqual(len(tasks), 30)
        self.assertEqual(len([statement for statement in statements if statement.lstrip().startswith("SELECT")]), 3)


class TaskMigrationTests(unittest.TestCase):
    def setUp(self):
        self.db = TimographyDB(":memory:")
        self.db.initialize()

    def tearDown(self):
        self.db.close()

    def remove_v2_schema(self):
        connection = self.db._get_conn()
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'task_%'").fetchall():
            connection.execute(f'DROP TRIGGER "{row[0]}"')
        for table in ("task_blocks", "task_details", "task_session_links"):
            connection.execute(f"DROP TABLE {table}")
        with connection:
            connection.execute("DELETE FROM settings WHERE key = 'task_schema_version'")

    def test_additive_migration_preserves_every_legacy_task_and_focus_row(self):
        day = date.today().isoformat()
        event = self.db.add_event("Read", "Notes", "09:00", "10:00", day, "#bc8cff", "Study", "daily", 10)
        task = self.db.add_checklist_item("Unchanged title", day, event_id=event)
        self.db.toggle_checklist_item(task)
        session = self.db.start_pomodoro("Original focus", event_id=event, tracked=True)
        self.db.checkpoint_pomodoro(session, {day: 94}, 0)
        original_task = self.db.get_checklist_item(task)
        original_focus = self.db.get_pomodoro_history()
        self.remove_v2_schema()
        migrate_tasks(self.db._get_conn())
        self.assertEqual(self.db.get_checklist_item(task), original_task)
        self.assertEqual(self.db.get_pomodoro_history(), original_focus)
        service = TaskService(self.db)
        self.assertEqual(service.get_task(task)["focus_seconds"], 94)
        self.assertEqual(service.get_task(task)["blocks"][0]["event_id"], event)
        self.assertFalse(service.get_task(task)["blocks"][0]["owns_event"])
        before = self.db._get_conn().total_changes
        migrate_tasks(self.db._get_conn())
        self.assertEqual(self.db._get_conn().total_changes, before)

    def test_migration_failure_rolls_back_schema_as_well_as_data(self):
        self.remove_v2_schema()
        connection = self.db._get_conn()

        def deny_blocks(action, name, *_):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_CREATE_TABLE and name == "task_blocks" else sqlite3.SQLITE_OK

        connection.set_authorizer(deny_blocks)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                migrate_tasks(connection)
        finally:
            connection.set_authorizer(None)
        self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'task_details'").fetchone())
        self.assertIsNone(self.db.get_setting("task_schema_version"))
        self.assertFalse(connection.in_transaction)
        migrate_tasks(connection)
        self.assertEqual(self.db.get_setting("task_schema_version"), "1")

    def test_ambiguous_old_event_sessions_remain_unattributed(self):
        day = date.today().isoformat()
        event = self.db.add_event("Read", "", "09:00", "10:00", day, "#bc8cff", "Study", "none", 10)
        self.db.add_checklist_item("First", day, event_id=event)
        self.db.add_checklist_item("Duplicate", day, event_id=event)
        self.db.start_pomodoro("Old", event_id=event)
        self.remove_v2_schema()
        migrate_tasks(self.db._get_conn())
        self.assertEqual(self.db._get_conn().execute("SELECT COUNT(*) FROM task_session_links").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
