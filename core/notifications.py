"""Windows toast notification manager for Timography."""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class NotificationManager:
    def __init__(self):
        """Initialize the notification manager."""
        self._toaster = None
        self._init_toaster()
    
    def _init_toaster(self):
        try:
            from windows_toasts import WindowsToaster
            self._toaster = WindowsToaster('Timography')
        except Exception as e:
            logger.warning(f"Could not initialize toaster: {e}")
            self._toaster = None
    
    def send_event_reminder(self, event: dict) -> None:
        """Send a toast notification for an upcoming event."""
        if not self._toaster:
            return
        
        try:
            from windows_toasts import Toast
            toast = Toast()
            
            title = f"⏰ {event.get('title', 'Upcoming Event')}"
            start_time = event.get('start_time', '')
            category = event.get('category', 'Uncategorized')
            
            body = f"Starting at {start_time} | {category}"
            if 'description' in event and event['description']:
                body += f"\n{event['description']}"
                
            toast.text_fields = [title, body]
            self._toaster.show_toast(toast)
        except Exception as e:
            logger.error(f"Failed to send event reminder toast: {e}")
    
    def send_daily_summary(self, events: list[dict]) -> None:
        """Send morning summary toast."""
        if not self._toaster:
            return
            
        try:
            from windows_toasts import Toast
            toast = Toast()
            
            if not events:
                toast.text_fields = ["Timography Daily Summary", "No events scheduled today. Enjoy your free day! 🎉"]
            else:
                count = len(events)
                first_event = events[0]
                title = first_event.get('title', 'Unknown')
                time = first_event.get('start_time', 'Unknown time')
                
                toast.text_fields = ["Timography Daily Summary", f"You have {count} event(s) today. First up: {title} at {time}"]
            
            self._toaster.show_toast(toast)
        except Exception as e:
            logger.error(f"Failed to send daily summary toast: {e}")
    
    def send_simple(self, title: str, message: str) -> None:
        """Send a simple toast notification."""
        if not self._toaster:
            return
            
        try:
            from windows_toasts import Toast
            toast = Toast()
            toast.text_fields = [title, message]
            self._toaster.show_toast(toast)
        except Exception as e:
            logger.error(f"Failed to send simple toast: {e}")

    def send_morning_briefing(self, events: list[dict], checklist_stats: dict, upcoming_exams: list[dict], streak: dict) -> None:
        """Send rich morning briefing notification."""
        if not self._toaster:
            return
        try:
            from windows_toasts import Toast
            toast = Toast()
            title = "☀️ Good Morning! Your Daily Briefing"
            
            lines = []
            ev_count = len(events)
            if ev_count > 0:
                first_ev = events[0]
                lines.append(f"📅 {ev_count} events today (First: {first_ev.get('title')} at {first_ev.get('start_time')})")
            else:
                lines.append("📅 Free schedule today!")

            # Checklist
            tot = checklist_stats.get("total", 0)
            if tot > 0:
                lines.append(f"✓ {tot} tasks on your checklist")

            # Streak
            cur_streak = streak.get("current", 0)
            if cur_streak > 0:
                lines.append(f"🔥 {cur_streak}-day study streak active!")

            # Urgent exam
            if upcoming_exams:
                ex = upcoming_exams[0]
                lines.append(f"📚 Next exam: {ex.get('title')} on {ex.get('date')}")

            toast.text_fields = [title, "\n".join(lines[:3])]
            self._toaster.show_toast(toast)
        except Exception as e:
            logger.error(f"Failed to send morning briefing toast: {e}")

    def send_weekly_recap(self, total_hours: float, top_category: str, streak: int) -> None:
        """Send Sunday evening weekly productivity recap toast."""
        if not self._toaster:
            return
        try:
            from windows_toasts import Toast
            toast = Toast()
            title = "📊 Sunday Weekly Productivity Recap"
            msg = f"You scheduled {total_hours:.1f}h this week! Top focus: {top_category}."
            if streak > 0:
                msg += f" 🔥 Study streak: {streak} days."
            toast.text_fields = [title, msg]
            self._toaster.show_toast(toast)
        except Exception as e:
            logger.error(f"Failed to send weekly recap toast: {e}")

    def send_streak_warning(self, streak_days: int) -> None:
        """Alert user before end of day if study streak is about to break."""
        self.send_simple("🔥 Study Streak at Risk!", f"Don't lose your {streak_days}-day study streak! Log 30 minutes of study today.")

