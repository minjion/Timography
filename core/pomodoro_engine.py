"""Pomodoro state machine and timer engine for Timography."""
import threading
import time
from datetime import datetime


class PomodoroEngine:
    PHASE_IDLE = "IDLE"
    PHASE_WORK = "WORK"
    PHASE_SHORT_BREAK = "SHORT_BREAK"
    PHASE_LONG_BREAK = "LONG_BREAK"
    PHASE_PAUSED = "PAUSED"

    def __init__(self, on_tick=None, on_phase_change=None, on_complete=None):
        self.on_tick = on_tick
        self.on_phase_change = on_phase_change
        self.on_complete = on_complete

        self.phase = self.PHASE_IDLE
        self.previous_phase = self.PHASE_IDLE
        self.work_minutes = 25
        self.break_minutes = 5
        self.long_break_minutes = 15
        self.target_cycles = 4
        self.current_cycle = 1

        self.title = "Focus Session"
        self.category = "Study"
        self.event_id = None
        self.session_id = None

        self.remaining_seconds = 0
        self.total_phase_seconds = 0
        self.cycles_completed = 0

        self._running = False
        self._thread = None
        self._lock = threading.Lock()

    def start(self, title: str = "Focus Session", category: str = "Study",
              work_min: int = 25, break_min: int = 5, long_break_min: int = 15,
              target_cycles: int = 4, event_id: int = None, session_id: int = None):
        self.stop()
        self.title = title
        self.category = category
        self.work_minutes = work_min
        self.break_minutes = break_min
        self.long_break_minutes = long_break_min
        self.target_cycles = target_cycles
        self.current_cycle = 1
        self.cycles_completed = 0
        self.event_id = event_id
        self.session_id = session_id

        self._start_phase(self.PHASE_WORK)

    def _start_phase(self, new_phase: str):
        with self._lock:
            self.phase = new_phase
            if new_phase == self.PHASE_WORK:
                self.remaining_seconds = self.work_minutes * 60
            elif new_phase == self.PHASE_SHORT_BREAK:
                self.remaining_seconds = self.break_minutes * 60
            elif new_phase == self.PHASE_LONG_BREAK:
                self.remaining_seconds = self.long_break_minutes * 60
            else:
                self.remaining_seconds = 0
            self.total_phase_seconds = self.remaining_seconds

        if self.on_phase_change:
            try:
                self.on_phase_change(self.phase, self.current_cycle)
            except Exception:
                pass

        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def pause(self):
        with self._lock:
            if self.phase != self.PHASE_PAUSED:
                self.previous_phase = self.phase
                self.phase = self.PHASE_PAUSED
                if self.on_phase_change:
                    self.on_phase_change(self.phase, self.current_cycle)

    def resume(self):
        with self._lock:
            if self.phase == self.PHASE_PAUSED:
                self.phase = self.previous_phase
                if self.on_phase_change:
                    self.on_phase_change(self.phase, self.current_cycle)

    def skip(self):
        """Skip current phase and transition to next."""
        self._handle_phase_end()

    def stop(self):
        self._running = False
        with self._lock:
            self.phase = self.PHASE_IDLE
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

    def _handle_phase_end(self):
        if self.phase == self.PHASE_WORK:
            self.cycles_completed += 1
            if self.current_cycle >= self.target_cycles:
                self._start_phase(self.PHASE_LONG_BREAK)
            else:
                self._start_phase(self.PHASE_SHORT_BREAK)
        elif self.phase in (self.PHASE_SHORT_BREAK, self.PHASE_LONG_BREAK):
            if self.phase == self.PHASE_LONG_BREAK:
                # All cycles done
                self.stop()
                if self.on_complete:
                    try:
                        self.on_complete()
                    except Exception:
                        pass
                return
            else:
                self.current_cycle += 1
                self._start_phase(self.PHASE_WORK)

    def _run_loop(self):
        while self._running:
            time.sleep(1)
            with self._lock:
                if not self._running:
                    break
                if self.phase == self.PHASE_PAUSED:
                    continue

                if self.remaining_seconds > 0:
                    self.remaining_seconds -= 1
                else:
                    self._handle_phase_end()
                    continue

                rem = self.remaining_seconds
                tot = self.total_phase_seconds
                ph = self.phase
                cyc = self.current_cycle

            if self.on_tick:
                try:
                    self.on_tick(rem, tot, ph, cyc)
                except Exception:
                    pass
