"""Background scheduler for event reminders."""
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from core.database import TimographyDB
from core.notifications import NotificationManager

logger = logging.getLogger(__name__)

class ReminderScheduler:
    def __init__(self, db: TimographyDB, notifier: NotificationManager):
        self.db = db
        self.notifier = notifier
        self.scheduler = BackgroundScheduler(daemon=True)
        self._setup_jobs()
    
    def _setup_jobs(self):
        # Job 1: Check reminders every 30 seconds
        self.scheduler.add_job(
            self.check_reminders, 'interval', seconds=30, id='reminder_check',
            max_instances=1, coalesce=True
        )
        # Job 2: Morning Briefing at 07:30
        self.scheduler.add_job(
            self.send_daily_summary, 'cron', hour=7, minute=30, id='daily_summary',
            max_instances=1, coalesce=True
        )
        # Job 3: Sunday Weekly Recap at 20:00
        self.scheduler.add_job(
            self.send_weekly_recap, 'cron', day_of_week='sun', hour=20, minute=0, id='weekly_recap',
            max_instances=1, coalesce=True
        )
    
    def start(self):
        self.scheduler.start()
        logger.info("Reminder scheduler started")
    
    def stop(self):
        self.scheduler.shutdown(wait=False)
        logger.info("Reminder scheduler stopped")
    
    def check_reminders(self):
        """Check for events that need reminders fired now."""
        try:
            now = datetime.now()
            due = self.db.get_upcoming_reminders(now)
            for event in due:
                self.notifier.send_event_reminder(event)
                self.db.mark_reminder_sent(event['id'], now.strftime('%Y-%m-%d'))
                logger.info(f"Sent reminder for event: {event.get('title')}")
        except Exception as e:
            logger.error(f"Reminder check error: {e}")
    
    def send_daily_summary(self):
        try:
            today_str = datetime.now().strftime('%Y-%m-%d')
            events = self.db.get_events_for_date(today_str, include_routines=True)
            stats = self.db.get_checklist_stats(today_str)
            exams = self.db.get_upcoming_exams(limit=2)
            streak = self.db.get_study_streak()
            self.notifier.send_morning_briefing(events, stats, exams, streak)
        except Exception as e:
            logger.error(f"Daily summary error: {e}")

    def send_weekly_recap(self):
        try:
            from datetime import timedelta
            today = datetime.now().date()
            start_of_week = today - timedelta(days=6)
            cat_hours = self.db.get_category_hours_summary(start_of_week.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d'))
            total_hours = sum(cat_hours.values())
            top_cat = max(cat_hours.items(), key=lambda x: x[1])[0] if cat_hours else "Study"
            streak = self.db.get_study_streak().get("current", 0)
            self.notifier.send_weekly_recap(total_hours, top_cat, streak)
        except Exception as e:
            logger.error(f"Weekly recap error: {e}")

