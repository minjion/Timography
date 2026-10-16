import threading
import time
import unittest
import tempfile
from pathlib import Path
from datetime import date, timedelta
from unittest.mock import Mock

from core.database import TimographyDB
from core.undo_manager import UndoManager
from core.nlp_parser import parse_natural_event
from core.pomodoro_engine import PomodoroEngine
from core.scheduler import ReminderScheduler
from core.auto_scheduler import AutoScheduler
from unittest.mock import patch
from datetime import datetime
from core.analytics import calculate_focus_score, get_weekly_insights
from ui.scrolling import WheelAccumulator


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = TimographyDB(":memory:")
        self.db.initialize()
        self.undo = UndoManager(self.db)

    def tearDown(self):
        self.db.close()

    def event(self, **overrides):
        values = dict(title="Study", description="Notes", start_time="09:00", end_time="10:00",
            date=date.today().isoformat(), color="#58a6ff", category="Study", recurring="none", reminder_minutes=10)
        values.update(overrides)
        return self.db.add_event(**values)

    def test_invalid_schedule_does_not_write(self):
        for fields in ({"date": "2026-02-30"}, {"start_time": "29:00"}, {"end_time": "08:00"},
                       {"title": " "}, {"color": "invalid"}):
            with self.assertRaises(ValueError):
                self.event(**fields)
        self.assertEqual(self.db.get_events_for_date(date.today().isoformat(), False), [])

    def test_repeat_undo_redo_preserves_id_and_all_fields(self):
        event_id = self.event()
        original = self.db.get_event(event_id)
        self.undo.record("add", "event", event_id, None, original)
        for _ in range(3):
            self.assertIsNotNone(self.undo.undo())
            self.assertIsNone(self.db.get_event(event_id))
            self.assertIsNotNone(self.undo.redo())
            self.assertEqual(self.db.get_event(event_id), original)
        self.db.update_event(event_id, description="Updated notes", recurring="weekly", reminder_minutes=30)
        updated = self.db.get_event(event_id)
        self.undo.record("update", "event", event_id, original, updated)
        self.undo.undo()
        self.assertEqual(self.db.get_event(event_id), original)
        self.undo.redo()
        self.assertEqual(self.db.get_event(event_id), updated)
        self.db.delete_event(event_id)
        self.undo.record("delete", "event", event_id, updated)
        self.undo.undo()
        self.assertEqual(self.db.get_event(event_id), updated)
        self.undo.redo()
        self.assertIsNone(self.db.get_event(event_id))

    def test_checklist_undo_restores_completion_and_links(self):
        event_id = self.event()
        item_id = self.db.add_checklist_item("Review", date.today().isoformat(), event_id=event_id)
        self.db.toggle_checklist_item(item_id)
        original = self.db.get_checklist_item(item_id)
        self.db.delete_checklist_item(item_id)
        self.undo.record("delete", "checklist", item_id, original)
        self.undo.undo()
        self.assertEqual(self.db.get_checklist_item(item_id), original)
        self.undo.redo()
        self.assertIsNone(self.db.get_checklist_item(item_id))

    def test_failed_undo_does_not_consume_history(self):
        event_id = self.event()
        self.undo.record("add", "event", event_id)
        self.db.delete_event(event_id)
        with self.assertRaises(ValueError):
            self.db.apply_history_action()
        self.assertEqual(self.db._get_conn().execute("SELECT is_undone FROM action_log").fetchone()[0], 0)

    def test_streak_survives_unfinished_today_and_updates_immediately(self):
        def record(day):
            session = self.db.start_pomodoro("Recorded study", work_minutes=60, tracked=True)
            self.db.checkpoint_pomodoro(session, {day: 3600}, 1, end_time=f"{day}T10:00:00")

        record((date.today() - timedelta(days=1)).isoformat())
        record((date.today() - timedelta(days=2)).isoformat())
        self.assertEqual(self.db.get_study_streak()["current"], 2)
        self.event()
        self.assertEqual(self.db.get_study_streak()["current"], 2, "A plan must not earn completed focus")
        record(date.today().isoformat())
        self.assertEqual(self.db.get_study_streak()["current"], 3)
        self.db.set_settings({"streak_goal_minutes": "90", "streak_include_checklist": "0"})
        self.assertEqual(self.db.get_study_streak()["current"], 0)
        self.assertEqual(self.db.get_study_streak(min_minutes=30)["current"], 3)

    def test_settings_validation_is_atomic(self):
        with self.assertRaises(ValueError):
            self.db.set_settings({"theme": "light", "pomo_work": "zero"})
        self.assertIsNone(self.db.get_setting("theme"))
        self.db.set_setting("pomo_work", "corrupt")
        self.assertEqual(self.db.get_int_setting("pomo_work", 25, 1, 180), 25)

    def test_deleted_defaults_do_not_reappear_on_restart(self):
        for routine in self.db.get_all_routines():
            self.db.delete_routine(routine["id"])
        for template in self.db.get_all_templates():
            self.db.delete_template(template["id"])
        self.db.initialize()
        self.assertEqual(self.db.get_all_routines(), [])
        self.assertEqual(self.db.get_all_templates(), [])

    def test_database_can_serve_workers_and_ui(self):
        failures = []
        def write(index):
            try:
                for item in range(20):
                    self.db.set_setting(f"worker-{index}-{item}", str(item))
                    self.event(title=f"Worker {index}: {item}")
            except Exception as exc:
                failures.append(exc)
        threads = [threading.Thread(target=write, args=(i,)) for i in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertFalse(failures)
        self.assertEqual(len(self.db.get_events_for_date(date.today().isoformat(), False)), 80)

    def test_notification_settings_apply(self):
        self.db.set_settings({"morning_briefing_hour": "11", "morning_briefing": "0", "weekly_recap": "0"})
        notifier = Mock()
        scheduler = ReminderScheduler(self.db, notifier)
        self.assertIn("hour='11'", str(scheduler.scheduler.get_job("daily_summary").trigger))
        scheduler.send_daily_summary()
        scheduler.send_weekly_recap()
        notifier.send_morning_briefing.assert_not_called()
        notifier.send_weekly_recap.assert_not_called()
        scheduler.stop()

    def test_reminders_can_fire_before_midnight_and_are_deduplicated(self):
        event_id = self.event(date="2026-10-10", start_time="00:05", end_time="01:00")
        due = self.db.get_upcoming_reminders(datetime(2026, 10, 9, 23, 57))
        matching = [event for event in due if event["id"] == event_id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["occurrence_date"], "2026-10-10")
        self.db.mark_reminder_sent(event_id, "2026-10-10")
        self.assertFalse(any(event["id"] == event_id for event in self.db.get_upcoming_reminders(datetime(2026, 10, 10, 0, 0))))

    def test_failed_notification_remains_eligible_for_retry(self):
        event_id = self.event(date="2026-10-10", start_time="00:05", end_time="01:00")
        notifier = Mock()
        notifier.send_event_reminder.return_value = False
        scheduler = ReminderScheduler(self.db, notifier)
        try:
            with patch("core.scheduler.datetime") as clock:
                clock.now.return_value = datetime(2026, 10, 9, 23, 57)
                scheduler.check_reminders()
                self.assertTrue(any(ev["id"] == event_id for ev in self.db.get_upcoming_reminders(clock.now())))
                notifier.send_event_reminder.return_value = True
                scheduler.check_reminders()
                self.assertFalse(any(ev["id"] == event_id for ev in self.db.get_upcoming_reminders(clock.now())))
        finally:
            scheduler.stop()

    def test_auto_schedule_does_not_choose_a_time_in_the_past(self):
        with patch("core.auto_scheduler.datetime") as clock:
            clock.now.return_value = datetime(2026, 10, 9, 19, 7)
            slot = AutoScheduler(self.db).suggest_best_slot("2026-10-09", 60)
        self.assertIsNotNone(slot)
        self.assertGreaterEqual(slot["start"], "19:15")

    def test_range_expands_recurrence_and_batches_queries(self):
        monthly = self.event(date="2024-01-31", recurring="monthly")
        weekly = self.event(date="2024-02-01", recurring="weekly")
        daily = self.event(date="2024-02-27", recurring="daily")
        future = self.event(date="2024-04-01", recurring="daily")
        queries = []
        self.db._get_conn().set_trace_callback(queries.append)
        result = self.db.get_events_for_range("2024-02-01", "2024-03-31", True)
        self.assertEqual(sum(q.startswith("SELECT") for q in queries), 2)
        self.assertEqual(len(result), 60)
        self.assertFalse(any(ev["id"] == monthly for ev in result["2024-02-29"]))
        self.assertTrue(any(ev["id"] == monthly for ev in result["2024-03-31"]))
        self.assertTrue(any(ev["id"] == weekly for ev in result["2024-02-29"]))
        self.assertTrue(any(ev["id"] == daily for ev in result["2024-02-29"]))
        self.assertFalse(any(ev["id"] == future for events in result.values() for ev in events))
        self.assertTrue(all(ev["occurrence_date"] == day for day, events in result.items() for ev in events))

    def test_range_cache_isolated_and_invalidated_by_mutations_and_history(self):
        day = date.today().isoformat()
        event_id = self.event()
        original = self.db.get_event(event_id)
        result = self.db.get_events_for_date(day, False)
        result[0]["title"] = "Corrupted caller copy"
        self.assertEqual(self.db.get_events_for_date(day, False)[0]["title"], "Study")
        self.db.update_event(event_id, title="Changed")
        self.undo.record("update", "event", event_id, original, self.db.get_event(event_id))
        self.assertEqual(self.db.get_events_for_date(day, False)[0]["title"], "Changed")
        self.undo.undo()
        self.assertEqual(self.db.get_events_for_date(day, False)[0]["title"], "Study")

    def test_checklist_seeds_once_even_with_manual_tasks_and_respects_deletion(self):
        day = date.today().isoformat()
        event_id = self.event()
        manual = self.db.add_checklist_item("Custom task", day)
        items = self.db.generate_checklist_for_date(day)
        scheduled = next(item for item in items if item["event_id"] == event_id)
        self.assertTrue(any(item["id"] == manual for item in items))
        self.db.delete_checklist_item(scheduled["id"])
        before = self.db._get_conn().total_changes
        again = self.db.generate_checklist_for_date(day)
        self.assertFalse(any(item["event_id"] == event_id for item in again))
        self.assertEqual(self.db._get_conn().total_changes, before)
        self.assertTrue(any(item["event_id"] == event_id for item in self.db.sync_checklist_for_date(day)))

    def test_checklist_sync_updates_titles_preserves_completion_and_custom_tasks(self):
        day = date.today().isoformat()
        event_id = self.event()
        item = next(it for it in self.db.generate_checklist_for_date(day) if it["event_id"] == event_id)
        self.db.toggle_checklist_item(item["id"])
        completed_at = self.db.get_checklist_item(item["id"])["completed_at"]
        manual = self.db.add_checklist_item("Keep my task", day)
        self.db.update_event(event_id, title="Updated study", start_time="11:00", end_time="12:00")
        items = self.db.sync_checklist_for_date(day)
        updated = next(it for it in items if it["id"] == item["id"])
        self.assertEqual(updated["title"], "Updated study (11:00 - 12:00)")
        self.assertEqual(updated["completed_at"], completed_at)
        self.assertEqual(updated["is_completed"], 1)
        self.db.delete_event(event_id)
        synced = self.db.sync_checklist_for_date(day)
        self.assertTrue(any(it["id"] == manual for it in synced))
        retained = next(it for it in synced if it["id"] == item["id"])
        self.assertIsNone(retained["event_id"])
        self.assertEqual(retained["is_completed"], 1)

    def test_sync_removes_obsolete_pending_schedule_items(self):
        day = date.today().isoformat()
        event_id = self.event()
        self.db.generate_checklist_for_date(day)
        self.db.delete_event(event_id)
        items = self.db.sync_checklist_for_date(day)
        self.assertFalse(any(it["event_id"] == event_id for it in items))

    def test_checklist_toggle_history_restores_exact_completion_timestamp(self):
        item_id = self.db.add_checklist_item("Task", date.today().isoformat())
        old = self.db.get_checklist_item(item_id)
        self.db.toggle_checklist_item(item_id)
        new = self.db.get_checklist_item(item_id)
        self.undo.record("toggle", "checklist", item_id, old, new)
        self.undo.undo()
        self.assertEqual(self.db.get_checklist_item(item_id), old)
        self.undo.redo()
        self.assertEqual(self.db.get_checklist_item(item_id), new)

    def test_invalid_routine_update_is_rejected(self):
        routine = self.db.get_all_routines()[0]
        for fields in ({"days_of_week": "9"}, {"days_of_week": ""}, {"is_active": 5}):
            with self.assertRaises(ValueError):
                self.db.update_routine(routine["id"], **fields)
        self.assertEqual(self.db.get_routine(routine["id"]), routine)

    def test_nested_event_does_not_shorten_fatigue_warning(self):
        for routine in self.db.get_all_routines():
            self.db.delete_routine(routine["id"])
        day = "2026-10-20"
        self.event(date=day, start_time="09:00", end_time="13:00")
        self.event(date=day, start_time="10:00", end_time="11:00")
        warnings = [s for s in AutoScheduler(self.db).get_smart_suggestions(day) if s["type"] == "fatigue_warning"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("09:00 - 13:00", warnings[0]["message"])
        self.assertIn("4h+", warnings[0]["message"])

    def test_scheduler_can_choose_preferred_time_inside_a_large_gap(self):
        for routine in self.db.get_all_routines():
            self.db.delete_routine(routine["id"])
        with patch("core.auto_scheduler.datetime") as clock:
            clock.now.return_value = datetime(2026, 10, 9, 12)
            slot = AutoScheduler(self.db).suggest_best_slot("2026-10-10", 60, "Study")
            self.assertIsNone(AutoScheduler(self.db).suggest_best_slot("2026-10-08", 60))
        self.assertEqual(slot["start"], "14:00")

    def test_focus_score_counts_recorded_work_without_scheduled_events(self):
        for routine in self.db.get_all_routines():
            self.db.delete_routine(routine["id"])
        day = date.today().isoformat()
        self.assertEqual(calculate_focus_score(self.db, day)["score"], 0)
        session = self.db.start_pomodoro("Read", work_minutes=25)
        self.db.update_pomodoro(session, cycles_completed=2)
        self.assertEqual(calculate_focus_score(self.db, day)["score"], 100)
        self.assertEqual(calculate_focus_score(self.db, day)["pomodoro_mins"], 50)

    def test_weekly_insights_respect_sunday_start(self):
        self.db.set_setting("week_start", "sunday")
        self.event(date="2026-10-11", category="Study")
        self.event(date="2026-10-10", category="Work")
        insights = get_weekly_insights(self.db, date(2026, 10, 11))
        self.assertIn("1.0 hours this week", insights[0])
        self.assertIn("Study", insights[1])

    def test_external_instance_write_invalidates_range_and_streak_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            first = TimographyDB(str(Path(folder) / "fixture.db"))
            second = TimographyDB(first.db_path)
            try:
                first.initialize()
                day = date.today().isoformat()
                self.assertEqual(first.get_events_for_date(day, False), [])
                self.assertEqual(first.get_study_streak()["today_minutes"], 0)
                second.add_event("New study", "", "09:00", "10:00", day, "#58a6ff", "Study", "none", 10)
                self.assertEqual(len(first.get_events_for_date(day, False)), 1)
                self.assertEqual(first.get_study_streak()["today_minutes"], 0)
                session = second.start_pomodoro("External recorded work", work_minutes=60, tracked=True)
                second.checkpoint_pomodoro(session, {day: 3600}, 1)
                self.assertEqual(first.get_study_streak()["today_minutes"], 60)
            finally:
                second.close()
                first.close()

    def test_invalid_legacy_time_does_not_break_streak(self):
        event_id = self.event()
        with self.db._get_conn() as conn:
            conn.execute("UPDATE events SET start_time = 'invalid' WHERE id = ?", (event_id,))
        self.assertEqual(self.db.get_study_streak()["today_minutes"], 0)


class ScrollingTests(unittest.TestCase):
    @patch("ui.scrolling.sys.platform", "win32")
    def test_precision_deltas_accumulate_and_direction_change_is_immediate(self):
        wheel = WheelAccumulator()
        self.assertEqual([wheel.steps(-1) for _ in range(6)], [0, 0, 0, 0, 0, 1])
        self.assertEqual(wheel.steps(120), -20)
        self.assertEqual(wheel.steps(-120), 20)
        self.assertEqual([wheel.steps(1) for _ in range(6)], [0, 0, 0, 0, 0, -1])


class ParserTests(unittest.TestCase):
    def test_documented_examples(self):
        reference = date(2026, 10, 9)
        result = parse_natural_event("study math tomorrow 2pm for 90m", reference)
        self.assertEqual((result["date"], result["start_time"], result["end_time"], result["category"]),
                         ("2026-10-10", "14:00", "15:30", "Study"))
        self.assertEqual(parse_natural_event("gym tonight", reference)["start_time"], "18:00")

    def test_invalid_input_rejected(self):
        for value in ("", "study at 29:99", "meeting february 30 at 9am", "gym at 11pm for 2h", "study for 0m"):
            with self.assertRaises(ValueError, msg=value):
                parse_natural_event(value)


class TimerTests(unittest.TestCase):
    def test_automatic_transitions_and_completion_do_not_deadlock(self):
        completed = threading.Event()
        engine = PomodoroEngine(on_complete=completed.set)
        try:
            engine.start(target_cycles=1)
            with engine._lock:
                engine._deadline = time.monotonic() - 1
            limit = time.monotonic() + 2
            while engine.phase != engine.PHASE_LONG_BREAK and time.monotonic() < limit:
                time.sleep(0.02)
            self.assertEqual(engine.phase, engine.PHASE_LONG_BREAK)
            self.assertEqual(engine.cycles_completed, 1)
            with engine._lock:
                engine._deadline = time.monotonic() - 1
            self.assertTrue(completed.wait(2))
            self.assertEqual(engine.phase, engine.PHASE_IDLE)
        finally:
            engine.stop()

    def test_restart_pause_skip_and_stop(self):
        engine = PomodoroEngine()
        try:
            engine.start()
            old_worker = engine._thread
            engine.pause()
            remaining = engine.remaining_seconds
            time.sleep(0.3)
            self.assertEqual(engine.remaining_seconds, remaining)
            engine.resume()
            engine.skip()
            self.assertEqual(engine.phase, engine.PHASE_SHORT_BREAK)
            self.assertEqual(engine.cycles_completed, 0)
            engine.start(work_min=10)
            self.assertFalse(old_worker.is_alive())
            self.assertEqual(engine.remaining_seconds, 600)
        finally:
            engine.stop()
        self.assertFalse(engine._thread.is_alive())


if __name__ == "__main__":
    unittest.main()
