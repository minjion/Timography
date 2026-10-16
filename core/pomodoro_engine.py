"""Pomodoro state machine with interruptible waits and safe phase transitions."""
import logging
import threading
import time
import math
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class PomodoroEngine:
    PHASE_IDLE = "IDLE"
    PHASE_WORK = "WORK"
    PHASE_SHORT_BREAK = "SHORT_BREAK"
    PHASE_LONG_BREAK = "LONG_BREAK"
    PHASE_PAUSED = "PAUSED"

    def __init__(self, on_tick=None, on_phase_change=None, on_complete=None, on_focus_checkpoint=None):
        self.on_tick = on_tick
        self.on_phase_change = on_phase_change
        self.on_complete = on_complete
        self.on_focus_checkpoint = on_focus_checkpoint
        self.phase = self.previous_phase = self.PHASE_IDLE
        self.work_minutes, self.break_minutes, self.long_break_minutes = 25, 5, 15
        self.target_cycles, self.current_cycle, self.cycles_completed = 4, 1, 0
        self.title, self.category = "Focus Session", "Study"
        self.event_id = self.session_id = None
        self.remaining_seconds = self.total_phase_seconds = 0
        self._running = False
        self._thread = None
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._deadline = None
        self.daily_focus_seconds = {}
        self._sample_time = self._sample_wall = None
        self._paused_remaining = 0
        self._checkpoint_time = 0
        self._last_checkpoint_snapshot = None

    @staticmethod
    def _notify(callback, *args):
        if callback:
            try:
                callback(*args)
            except Exception:
                logger.exception("Pomodoro callback failed")

    def start(self, title="Focus Session", category="Study", work_min=25,
              break_min=5, long_break_min=15, target_cycles=4,
              event_id=None, session_id=None):
        if any(type(v) is not int or v <= 0 for v in
               (work_min, break_min, long_break_min, target_cycles)):
            raise ValueError("Durations and cycles must be positive integers")
        self.stop()
        with self._lock:
            self.title, self.category = title, category
            self.work_minutes, self.break_minutes = work_min, break_min
            self.long_break_minutes, self.target_cycles = long_break_min, target_cycles
            self.current_cycle, self.cycles_completed = 1, 0
            self.event_id, self.session_id = event_id, session_id
            self.daily_focus_seconds = {}
            self._last_checkpoint_snapshot = None
            self._checkpoint_time = time.monotonic()
            self._stop_event = threading.Event()
            self._running = True
            self._start_phase(self.PHASE_WORK)
            self._thread = threading.Thread(target=self._run_loop, args=(self._stop_event,), daemon=True)
            self._thread.start()

    def _start_phase(self, phase):
        self.phase = phase
        minutes = {self.PHASE_WORK: self.work_minutes,
                   self.PHASE_SHORT_BREAK: self.break_minutes,
                   self.PHASE_LONG_BREAK: self.long_break_minutes}[phase]
        self.remaining_seconds = self.total_phase_seconds = minutes * 60
        self._deadline = time.monotonic() + self.remaining_seconds
        self._sample_time, self._sample_wall = time.monotonic(), datetime.now()
        self._notify(self.on_phase_change, phase, self.current_cycle)
        self._notify(self.on_tick, self.remaining_seconds, self.total_phase_seconds, phase, self.current_cycle)

    def pause(self):
        with self._lock:
            if self.phase not in (self.PHASE_IDLE, self.PHASE_PAUSED):
                self._sample_work()
                self._paused_remaining = max(0, self._deadline - time.monotonic())
                self.remaining_seconds = math.ceil(self._paused_remaining)
                self.previous_phase, self.phase = self.phase, self.PHASE_PAUSED
                self._checkpoint()
                self._notify(self.on_phase_change, self.phase, self.current_cycle)

    def resume(self):
        with self._lock:
            if self.phase == self.PHASE_PAUSED:
                self.phase = self.previous_phase
                self._deadline = time.monotonic() + self._paused_remaining
                self._sample_time, self._sample_wall = time.monotonic(), datetime.now()
                self._notify(self.on_phase_change, self.phase, self.current_cycle)

    def skip(self):
        with self._lock:
            self._sample_work()
            if self.phase == self.PHASE_PAUSED:
                self.phase = self.previous_phase
                self._sample_time, self._sample_wall = time.monotonic(), datetime.now()
                self._deadline = self._sample_time + self._paused_remaining
            if self.phase != self.PHASE_IDLE:
                self._handle_phase_end(credit_work=False)
                self._checkpoint()

    def stop(self):
        with self._lock:
            self._sample_work()
            self._checkpoint()
            self._running = False
            self._stop_event.set()
            self.phase = self.PHASE_IDLE
            thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=1)

    @property
    def focused_seconds(self):
        with self._lock:
            return sum(self.daily_focus_seconds.values())

    def _sample_work(self):
        """Charge active WORK only, bounded by its deadline, and divide at local midnight."""
        if self.phase != self.PHASE_WORK or self._sample_time is None:
            return
        until = min(time.monotonic(), self._deadline)
        seconds = max(0, until - self._sample_time)
        wall = self._sample_wall
        while seconds > 0:
            midnight = datetime.combine(wall.date() + timedelta(days=1), datetime.min.time())
            chunk = min(seconds, (midnight - wall).total_seconds())
            day = wall.date().isoformat()
            self.daily_focus_seconds[day] = self.daily_focus_seconds.get(day, 0) + chunk
            seconds -= chunk
            wall += timedelta(seconds=chunk)
        self._sample_time, self._sample_wall = max(self._sample_time, until), wall

    def _checkpoint(self):
        snapshot = (self.session_id, self.cycles_completed, tuple(sorted(self.daily_focus_seconds.items())))
        if (self.session_id is not None and self.on_focus_checkpoint
                and snapshot != self._last_checkpoint_snapshot):
            try:
                saved = self.on_focus_checkpoint(self.session_id,
                    dict(self.daily_focus_seconds), self.cycles_completed)
                if saved is not False:
                    self._last_checkpoint_snapshot = snapshot
            except Exception:
                logger.exception("Focus checkpoint failed; retained for retry")
        self._checkpoint_time = time.monotonic()

    def _handle_phase_end(self, credit_work=True):
        # Caller holds the reentrant lock; never join a worker under that lock.
        if self.phase == self.PHASE_WORK:
            self._sample_work()
            if credit_work:
                self.cycles_completed += 1
            self._checkpoint()
            phase = self.PHASE_LONG_BREAK if self.current_cycle >= self.target_cycles else self.PHASE_SHORT_BREAK
            self._start_phase(phase)
        elif self.phase == self.PHASE_SHORT_BREAK:
            self.current_cycle += 1
            self._start_phase(self.PHASE_WORK)
        elif self.phase == self.PHASE_LONG_BREAK:
            self._running = False
            self._stop_event.set()
            self.phase = self.PHASE_IDLE
            self._checkpoint()
            self._notify(self.on_complete)

    def _run_loop(self, stop_event):
        while not stop_event.wait(0.2):
            with self._lock:
                if stop_event.is_set():
                    return
                if self.phase in (self.PHASE_IDLE, self.PHASE_PAUSED):
                    continue
                self._sample_work()
                if time.monotonic() - self._checkpoint_time >= 5:
                    self._checkpoint()
                remaining = max(0, math.ceil(self._deadline - time.monotonic()))
                if remaining == 0:
                    self._handle_phase_end()
                elif remaining != self.remaining_seconds:
                    self.remaining_seconds = remaining
                    self._notify(self.on_tick, remaining, self.total_phase_seconds, self.phase, self.current_cycle)
