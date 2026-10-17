"""Qt adapter for shared task services and the measured focus engine.

QML owns presentation. Task rules live in TaskService and timer accounting stays
in PomodoroEngine; no Tk objects or worker-thread UI calls are involved here.
"""
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, unquote
import logging

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot, Qt

from core.backups import BackupManager
from core.pomodoro_engine import PomodoroEngine
from core.task_service import TaskService
from core.validation import validate_date, time_minutes

logger = logging.getLogger(__name__)


class PlannerController(QObject):
    changed = Signal()
    tasksChanged = Signal()
    timerChanged = Signal()
    errorChanged = Signal()
    _completed = Signal()
    _checkpointError = Signal(str)

    def __init__(self, db, preview_mode=True, parent=None):
        super().__init__(parent)
        self.db = db
        self.service = TaskService(db)
        self._preview_mode = preview_mode
        self._tasks, self._agenda, self._sessions = [], [], []
        self._categories = []
        self._focused_minutes = 0.0
        self._status = "Ready"
        self._error = ""
        self._dark = db.get_setting("theme", "dark") == "dark"
        self._date = datetime.now().date().isoformat()
        self._date_label = ""
        self._next_title, self._next_time = "Room to focus", "No more events today"
        self._active_task_id = -1
        self._focus_title, self._phase, self._remaining = "Choose a task to focus on", "IDLE", 0
        self._last_timer_snapshot = None
        self._closed = False
        self._last_stats_refresh = datetime.now()
        self.engine = PomodoroEngine(on_focus_checkpoint=self._checkpoint,
                                     on_complete=self._completed.emit)
        self._completed.connect(self._finish_automatically, Qt.ConnectionType.QueuedConnection)
        self._checkpointError.connect(self._show_checkpoint_error, Qt.ConnectionType.QueuedConnection)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self.refresh()

    @Property("QVariantList", notify=tasksChanged)
    def tasks(self):
        return self._tasks

    @Property("QVariantList", notify=changed)
    def agenda(self):
        return self._agenda

    @Property("QVariantList", notify=changed)
    def recentSessions(self):
        return self._sessions

    @Property("QStringList", notify=changed)
    def categories(self):
        return self._categories

    @Property(int, notify=changed)
    def taskCount(self):
        return len(self._tasks)

    @Property(int, notify=changed)
    def completedCount(self):
        return sum(bool(task["is_completed"]) for task in self._tasks)

    @Property(float, notify=changed)
    def focusedMinutes(self):
        return self._focused_minutes

    @Property(str, notify=changed)
    def dateLabel(self):
        return self._date_label

    @Property(str, notify=changed)
    def selectedDate(self):
        return self._date

    @Property(str, notify=changed)
    def nextTitle(self):
        return self._next_title

    @Property(str, notify=changed)
    def nextTime(self):
        return self._next_time

    @Property(str, notify=changed)
    def statusMessage(self):
        return self._status

    @Property(str, notify=errorChanged)
    def errorMessage(self):
        return self._error

    @Property(bool, notify=changed)
    def darkMode(self):
        return self._dark

    @Property(str, notify=timerChanged)
    def focusTitle(self):
        return self._focus_title

    @Property(str, notify=timerChanged)
    def focusPhase(self):
        return self._phase

    @Property(int, notify=timerChanged)
    def remainingSeconds(self):
        return self._remaining

    @Property(int, notify=timerChanged)
    def activeTaskId(self):
        return self._active_task_id

    @Property(bool, notify=timerChanged)
    def focusRunning(self):
        return self._phase != "IDLE"

    @Property(str, constant=True)
    def databasePath(self):
        return str(Path(self.db.db_path).resolve()) if self.db.db_path != ":memory:" else ":memory:"

    @Property(bool, constant=True)
    def previewMode(self):
        return self._preview_mode

    def _fail(self, exc):
        self._error = str(exc) or "This action could not be saved. Try again."
        self.errorChanged.emit()
        return False

    def _success(self, message):
        self._error = ""
        self._status = message
        self.errorChanged.emit()
        self.changed.emit()
        return True

    def _mutate(self, action, message):
        if self._closed:
            return False
        try:
            if action() is False:
                raise ValueError("This item is no longer available. Refresh your planner.")
            self._reload()
            return self._success(message)
        except Exception as exc:
            logger.exception("Planner action failed")
            return self._fail(exc)

    def _reload(self):
        now = datetime.now()
        self._date = now.date().isoformat()
        self._date_label = now.strftime("%A, %B %d").replace(" 0", " ")
        tasks = self.service.list_tasks()
        if tasks != self._tasks:
            self._tasks = tasks
            self.tasksChanged.emit()
        # Service reads task focus totals in a batch, keeping this adapter cheap.
        self._categories = [row["name"] for row in self.db.get_all_categories()]
        self._categories = list(dict.fromkeys(self._categories + [task["category"] for task in self._tasks]))
        if not self._categories:
            self._categories = ["Study", "Work", "Personal"]
        linked_tasks = {}
        for task in self._tasks:
            if task["is_completed"]:
                continue
            for block in task["blocks"]:
                if block.get("event_id") is not None and block["start"][:10] == self._date:
                    linked_tasks.setdefault(block["event_id"], set()).add(task["id"])
        event_tasks = {event_id: next(iter(task_ids)) for event_id, task_ids in linked_tasks.items()
                       if len(task_ids) == 1}
        events = self.db.get_events_for_date(self._date)
        self._agenda = [{"id": event["id"],
                         "task_id": event_tasks.get(event["id"], -1) if not event.get("is_routine") else -1,
                         "title": event["title"], "category": event["category"],
                         "start": event["start_time"], "end": event["end_time"]} for event in events]
        self._agenda.sort(key=lambda event: (event["start"], event["end"], event["title"]))
        upcoming = next((event for event in self._agenda if event["end"] > now.strftime("%H:%M")), None)
        self._next_title = upcoming["title"] if upcoming else "Room to focus"
        self._next_time = f'{upcoming["start"]} – {upcoming["end"]}' if upcoming else "No more events today"
        self._focused_minutes = self.db.get_focus_seconds_by_date(self._date, self._date).get(self._date, 0) / 60
        self._sessions = [{"id": item["id"], "title": item["title"], "category": item["category"],
                           "date": item["date"], "estimated": item.get("tracked_seconds") is None,
                           "minutes": (item["tracked_seconds"] if item.get("tracked_seconds") is not None
                                       else item["cycles_completed"] * item["work_minutes"] * 60) / 60}
                          for item in self.db.get_pomodoro_history(30)]
        self._last_stats_refresh = now

    @Slot(result=bool)
    def refresh(self):
        if self._closed:
            return False
        try:
            self._reload()
            self.changed.emit()
            return True
        except Exception as exc:
            return self._fail(exc)

    @Slot(str, str, int, result=bool)
    def createTask(self, title, category, estimate):
        return self._mutate(lambda: self.service.create_task(title, category=category,
                             estimate_minutes=estimate), "Task captured. Schedule it when you are ready.")

    @Slot(int, str, str, str, int, result=bool)
    def editTask(self, task_id, title, category, notes, estimate):
        return self._mutate(lambda: self.service.update_task(task_id, title=title,
                             category=category, notes=notes, estimate_minutes=estimate), "Task updated.")

    @Slot(int, result=bool)
    def toggleTask(self, task_id):
        try:
            task = self.service.get_task(task_id)
            if task is None:
                raise ValueError("This task no longer exists. Refresh your planner.")
            completing = not bool(task["is_completed"])
            if completing and task_id == self._active_task_id and self.engine.session_id is not None:
                if not self.stopFocus():
                    return False
            return self._mutate(lambda: self.service.set_completed(task_id, completing),
                                "Task completed." if completing else "Task reopened.")
        except Exception as exc:
            return self._fail(exc)

    @Slot(int, result=bool)
    def deleteTask(self, task_id):
        if task_id == self._active_task_id and self.engine.session_id is not None:
            return self._fail(ValueError("Stop and save the active focus session before deleting this task."))
        return self._mutate(lambda: self.service.delete_task(task_id), "Task removed. Recorded focus history is retained.")

    @Slot(int, str, str, str, result=bool)
    def scheduleTask(self, task_id, day, start, end):
        try:
            validate_date(day)
            time_minutes(start)
            time_minutes(end)
            if end <= start:
                raise ValueError("End time must be after start time on the same day.")
            begin, finish = f"{day}T{start}:00", f"{day}T{end}:00"
            conflicts = self.service.conflicts(begin, finish)
            return self._mutate(lambda: self.service.schedule_task(task_id, begin, finish),
                "Block scheduled. It overlaps another calendar entry." if conflicts else "Time block added to your calendar.")
        except Exception as exc:
            return self._fail(exc)

    @Slot(int, result=bool)
    def removeBlock(self, block_id):
        block = next((block for task in self._tasks for block in task["blocks"] if block["id"] == block_id), None)
        message = ("Task detached from its original calendar entry. The original event or recurring series is retained."
                   if block and not block.get("owns_event", True)
                   else "Time block removed; the task is retained.")
        return self._mutate(lambda: self.service.unschedule_block(block_id), message)

    @Slot(int, result=bool)
    def startFocus(self, task_id):
        if self._closed:
            return False
        try:
            if self.engine.phase != PomodoroEngine.PHASE_IDLE:
                return self._success("Your existing focus session is still active.")
            if self.engine.session_id is not None and not self.stopFocus():
                return False  # An unsaved final checkpoint must never be replaced.
            task = self.service.get_task(task_id)
            if task is None or task["is_completed"]:
                raise ValueError("Choose an unfinished task to begin focus.")
            work = self.db.get_int_setting("pomo_work", 25, 1, 180)
            pause = self.db.get_int_setting("pomo_short_break", 5, 1, 60)
            long_pause = self.db.get_int_setting("pomo_long_break", 15, 1, 120)
            cycles = self.db.get_int_setting("pomo_cycles", 4, 1, 12)
            session_id = self.service.start_focus(task_id, work_minutes=work,
                                                  break_minutes=pause, cycles_target=cycles)
            self._active_task_id = task_id
            self.engine.start(title=task["title"], category=task["category"], work_min=work,
                              break_min=pause, long_break_min=long_pause, target_cycles=cycles,
                              session_id=session_id)
            self._sync_timer()
            self._reload()
            return self._success("Focus started. Only active work earns minutes.")
        except Exception as exc:
            logger.exception("Could not start focus")
            return self._fail(exc)

    def _checkpoint(self, session_id, seconds, cycles):
        saved = self.db.checkpoint_pomodoro(session_id, seconds, cycles)
        if not saved:
            self._checkpointError.emit("Focus could not be saved. Work remains in memory and will be retried.")
        return saved

    @Slot(str)
    def _show_checkpoint_error(self, message):
        if not self._closed:
            self._fail(ValueError(message))

    @Slot(result=bool)
    def pauseResumeFocus(self):
        try:
            if self.engine.phase == PomodoroEngine.PHASE_IDLE:
                raise ValueError("Start a focus session first.")
            if self.engine.phase == PomodoroEngine.PHASE_PAUSED:
                self.engine.resume()
                message = "Focus resumed."
            else:
                self.engine.pause()
                message = "Paused. Paused time will not earn focus minutes."
            self._sync_timer()
            return self._success(message)
        except Exception as exc:
            return self._fail(exc)

    @Slot(result=bool)
    def stopFocus(self):
        try:
            self.engine.stop()
            session_id = self.engine.session_id
            if session_id is not None:
                with self.engine._lock:
                    saved = self.db.checkpoint_pomodoro(session_id, dict(self.engine.daily_focus_seconds),
                        self.engine.cycles_completed, end_time=datetime.now().isoformat())
                if not saved:
                    self._sync_timer()
                    raise RuntimeError("Could not save the session. Please retry Stop before starting another task.")
            self.engine.session_id = None
            self._active_task_id = -1
            self._sync_timer()
            self._reload()
            return self._success("Session saved, including partial work.")
        except Exception as exc:
            logger.exception("Could not finish focus")
            return self._fail(exc)

    @Slot()
    def _finish_automatically(self):
        if not self._closed:
            self.stopFocus()

    def _sync_timer(self):
        with self.engine._lock:
            idle = self.engine.phase == "IDLE" and self.engine.session_id is None
            snapshot = (self.engine.phase, 0 if idle else self.engine.remaining_seconds,
                        "Choose a task to focus on" if idle else self.engine.title, self._active_task_id)
        if snapshot != self._last_timer_snapshot:
            self._last_timer_snapshot = snapshot
            self._phase, self._remaining, self._focus_title = snapshot[:3]
            self.timerChanged.emit()

    @Slot()
    def _tick(self):
        if self._closed:
            return
        self._sync_timer()
        if (datetime.now() - self._last_stats_refresh).total_seconds() >= 5:
            self.refresh()

    @Slot(bool, result=bool)
    def setDarkMode(self, enabled):
        def save():
            self.db.set_setting("theme", "dark" if enabled else "light")
            self._dark = enabled
        return self._mutate(save, "Appearance saved.")

    @Slot()
    def clearError(self):
        self._error = ""
        self.errorChanged.emit()

    @Slot(str, result=bool)
    def exportBackup(self, path):
        try:
            if not path.strip():
                raise ValueError("Choose a location for the backup.")
            # FileDialog.selectedFile arrives as a local file URL.
            if path.startswith("file:"):
                parsed = urlparse(path)
                path = unquote(parsed.path)
                if len(path) > 2 and path[0] == "/" and path[2] == ":":
                    path = path[1:]
                if parsed.netloc:
                    path = "//" + parsed.netloc + path
            target = BackupManager(self.db).create_backup(path)
            return self._success(f"Backup saved to {target}")
        except Exception as exc:
            return self._fail(exc)

    @Slot(result=bool)
    def requestClose(self):
        return self.close()

    def close(self):
        if self._closed:
            return True
        self._timer.stop()
        saved = self.stopFocus() if self.engine.session_id is not None else True
        self.engine.stop()
        self._closed = saved
        return saved
