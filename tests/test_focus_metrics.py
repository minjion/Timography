"""Measured focus accounting and additive legacy migration regressions."""
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from core.analytics import calculate_focus_score
from core.database import TimographyDB
from core.pomodoro_engine import PomodoroEngine


class FocusDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = TimographyDB(":memory:")
        self.db.initialize()
        self.day = date.today().isoformat()

    def tearDown(self):
        self.db.close()

    def test_checkpoint_is_idempotent_and_keeps_partial_minutes(self):
        session = self.db.start_pomodoro("Write", tracked=True)
        self.assertTrue(self.db.checkpoint_pomodoro(session, {self.day: 125.5}, 0))
        self.db.checkpoint_pomodoro(session, {self.day: 125.5}, 0)
        self.db.checkpoint_pomodoro(session, {self.day: 30}, 0)
        self.assertEqual(self.db.get_today_pomodoro_minutes(self.day), 2)
        self.assertEqual(self.db.get_focus_seconds_by_date(self.day, self.day)[self.day], 125.5)
        self.assertEqual(self.db.get_pomodoro_history()[0]["tracked_seconds"], 125.5)

    def test_measured_cycles_are_not_counted_twice_and_dates_are_split(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        session = self.db.start_pomodoro("Read", work_minutes=25, tracked=True)
        self.db.checkpoint_pomodoro(session, {yesterday: 90, self.day: 150}, 1)
        self.assertEqual(self.db.get_today_pomodoro_minutes(yesterday), 1)
        self.assertEqual(self.db.get_today_pomodoro_minutes(self.day), 2)
        self.assertEqual(self.db.get_pomodoro_minutes_range(yesterday, self.day), 4)

    def test_legacy_cycle_credit_remains_and_recovery_does_not_invent_time(self):
        legacy = self.db.start_pomodoro("Legacy", work_minutes=25)
        self.db.update_pomodoro(legacy, cycles_completed=2)
        measured = self.db.start_pomodoro("Measured", tracked=True)
        self.db.checkpoint_pomodoro(measured, {self.day: 130}, 0)
        self.assertEqual(self.db.recover_interrupted_pomodoros(), 1)
        self.assertEqual(self.db.recover_interrupted_pomodoros(), 0)
        history = self.db.get_pomodoro_history()
        self.assertIsNotNone(history[0]["end_time"])
        self.assertIsNone(history[1]["end_time"])
        self.assertEqual(self.db.get_today_pomodoro_minutes(self.day), 52)

    def test_invalid_checkpoint_is_atomic(self):
        session = self.db.start_pomodoro("Write", tracked=True)
        for invalid in (float("nan"), float("inf"), -1, True, "60"):
            with self.assertRaises(ValueError):
                self.db.checkpoint_pomodoro(session, {self.day: 60, "2026-01-01": invalid}, 0)
        self.assertEqual(self.db.get_focus_seconds_by_date(self.day, self.day), {})
        self.assertFalse(self.db.checkpoint_pomodoro(999, {self.day: 60}, 0))

    def test_plans_and_tasks_cannot_create_focus_or_goal_progress(self):
        self.db.add_event("Tomorrow", "", "09:00", "23:00", self.day,
                          "#58a6ff", "Study", "daily", 10)
        task = self.db.add_checklist_item("Task", self.day)
        self.db.toggle_checklist_item(task)
        self.assertEqual(self.db.get_study_streak()["today_minutes"], 0)
        self.assertEqual(calculate_focus_score(self.db, self.day)["score"], 0)
        session = self.db.start_pomodoro("Read", tracked=True)
        self.db.checkpoint_pomodoro(session, {self.day: 900}, 0)
        self.assertEqual(calculate_focus_score(self.db, self.day)["score"], 50)
        self.assertEqual(self.db.get_study_streak()["today_minutes"], 15)

    def test_category_filter_and_all_history_best_streak(self):
        self.db.set_setting("streak_categories", "Study")
        study = self.db.start_pomodoro("Read", category="Study", tracked=True)
        health = self.db.start_pomodoro("Exercise", category="Health", tracked=True)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        old = date.today() - timedelta(days=300)
        days = {(old + timedelta(days=i)).isoformat(): 1800 for i in range(4)}
        days[yesterday] = 1800
        self.db.checkpoint_pomodoro(study, days, 0)
        self.db.checkpoint_pomodoro(health, {self.day: 3600}, 0)
        streak = self.db.get_study_streak()
        self.assertEqual((streak["current"], streak["best"], streak["today_minutes"]), (1, 4, 0))
        self.assertEqual(self.db.get_study_streak(categories=["HEALTH"])["today_minutes"], 60)

    def test_existing_database_migration_is_additive_and_once_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "legacy.db")
            with sqlite3.connect(path) as conn:
                conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
                conn.executemany("INSERT INTO settings VALUES (?, ?)",
                    [("defaults_seeded", "1"), ("streak_include_pomo", "0")])
                conn.execute("CREATE TABLE pomodoro_sessions (id INTEGER PRIMARY KEY, event_id INTEGER, "
                    "title TEXT, start_time TEXT, end_time TEXT, work_minutes INTEGER, break_minutes INTEGER, "
                    "cycles_completed INTEGER, cycles_target INTEGER, category TEXT, date TEXT)")
                conn.execute("INSERT INTO pomodoro_sessions VALUES (1,NULL,'Old','2026-01-01T09:00',"
                    "NULL,25,5,2,4,'Study','2026-01-01')")
            conn.close()
            migrated = TimographyDB(path)
            try:
                migrated.initialize()
                self.assertEqual(migrated.get_today_pomodoro_minutes("2026-01-01"), 50)
                self.assertEqual(migrated.get_setting("streak_include_pomo"), "1")
                migrated.set_setting("streak_include_pomo", "0")
                migrated.initialize()
                self.assertEqual(migrated.get_setting("streak_include_pomo"), "0")
                self.assertEqual(migrated.get_pomodoro_history()[0]["title"], "Old")
            finally:
                migrated.close()

    def test_recurrences_never_generate_before_origin_and_monthly_skips_short_month(self):
        self.db.add_event("Month end", "", "09:00", "10:00", "2026-01-31",
                          "#58a6ff", "Study", "monthly", 10)
        self.assertEqual(self.db.get_events_for_date("2025-12-31", False), [])
        self.assertEqual(self.db.get_events_for_date("2026-02-28", False), [])
        self.assertEqual(self.db.get_events_for_date("2026-03-31", False)[0]["occurrence_date"], "2026-03-31")


class FocusEngineTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.wall = datetime(2026, 10, 14, 12)
        self.monotonic_patch = patch("core.pomodoro_engine.time.monotonic", side_effect=lambda: self.now)
        self.datetime_patch = patch("core.pomodoro_engine.datetime", wraps=datetime)
        self.thread_patch = patch("core.pomodoro_engine.threading.Thread")
        self.monotonic_patch.start()
        self.clock = self.datetime_patch.start()
        self.clock.now.side_effect = lambda: self.wall
        self.thread_patch.start()
        self.checkpoint = Mock()
        self.engine = PomodoroEngine(on_focus_checkpoint=self.checkpoint)
        self.engine.start(work_min=1, break_min=1, target_cycles=2, session_id=1)

    def tearDown(self):
        self.engine.stop()
        self.thread_patch.stop()
        self.datetime_patch.stop()
        self.monotonic_patch.stop()

    def advance(self, seconds):
        self.now += seconds
        self.wall += timedelta(seconds=seconds)

    def test_pause_resume_does_not_charge_pause_or_round_duration_up(self):
        self.advance(10.25)
        self.engine.pause()
        self.advance(120)
        self.engine.resume()
        self.advance(4.25)
        self.engine.stop()
        self.assertEqual(self.engine.focused_seconds, 14.5)
        self.assertAlmostEqual(self.engine._deadline - self.now, 45.5)
        self.assertEqual(self.engine.cycles_completed, 0)

    def test_skip_while_paused_keeps_only_work_and_breaks_never_count(self):
        self.advance(12)
        self.engine.pause()
        self.advance(120)
        self.engine.skip()
        self.assertEqual(self.engine.focused_seconds, 12)
        self.assertEqual(self.engine.phase, self.engine.PHASE_SHORT_BREAK)
        self.advance(30)
        self.engine.stop()
        self.assertEqual(self.engine.focused_seconds, 12)
        self.assertEqual(self.engine.cycles_completed, 0)

    def test_midnight_divides_work_and_deadline_caps_delayed_worker(self):
        self.engine.stop()
        self.wall = datetime(2026, 10, 14, 23, 59, 45)
        self.engine.start(work_min=1, session_id=2)
        self.advance(100)
        self.engine.stop()
        self.assertEqual(self.engine.daily_focus_seconds, {"2026-10-14": 15, "2026-10-15": 45})
        self.assertEqual(self.engine.focused_seconds, 60)

    def test_completed_work_and_partial_next_cycle_are_both_measured(self):
        self.advance(60)
        self.engine._handle_phase_end()
        self.advance(60)
        self.engine._handle_phase_end()
        self.advance(11)
        self.engine.stop()
        self.assertEqual(self.engine.cycles_completed, 1)
        self.assertEqual(self.engine.focused_seconds, 71)
        self.assertEqual(self.checkpoint.call_args.args[2], 1)

    def test_failed_checkpoint_retries_cumulative_snapshot_without_break_writes(self):
        self.checkpoint.return_value = False
        self.advance(15)
        self.engine.pause()
        self.checkpoint.return_value = True
        self.engine._checkpoint()
        self.assertEqual(self.checkpoint.call_args.args[1], {"2026-10-14": 15})
        count = self.checkpoint.call_count
        self.advance(30)
        self.engine._checkpoint()
        self.assertEqual(self.checkpoint.call_count, count)


if __name__ == "__main__":
    unittest.main()
