"""Pomodoro Focus Timer View & Dialog for Timography."""
from datetime import datetime
from queue import SimpleQueue, Empty
import customtkinter as ctk
from ui.controls import AppButton, AppToplevel
from ui.scrolling import ScrollableFrame
from ui.theme import theme_color
from ui.theme import FONTS, CARD_CORNER_RADIUS, SIZES
from core.pomodoro_engine import PomodoroEngine
from core.database import TimographyDB
from core.notifications import NotificationManager


class PomodoroView(ctk.CTkFrame):
    """Embedded Pomodoro Focus Room for Main Window Tab."""
    def __init__(self, master, db: TimographyDB, notifier: NotificationManager = None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.db = db
        self.notifier = notifier
        self.db_session_id = None
        self.source_event_id = None
        self._prefilling_source = False
        self._context_traces = []
        self._updates = SimpleQueue()

        self.engine = PomodoroEngine(
            on_tick=self._on_tick_threadsafe,
            on_phase_change=self._on_phase_change_threadsafe,
            on_complete=self._on_complete_threadsafe,
            on_focus_checkpoint=self._persist_focus
        )

        self._build_ui()
        self._context_traces = [
            (variable, variable.trace_add("write", self._on_context_edited))
            for variable in (self._task_title_var, self._category_var)
        ]
        self.reload_settings()
        self._poll_id = self.after(100, self._drain_updates)

    def _build_ui(self):
        # Center container
        outer = ScrollableFrame(self, fg_color="transparent")
        outer.pack(expand=True, fill="both", padx=20, pady=20)

        self.card = ctk.CTkFrame(outer, fg_color=theme_color("bg_secondary"), corner_radius=CARD_CORNER_RADIUS, width=440)
        self.card.pack(expand=True, pady=10)

        # Header / Title row
        ctk.CTkLabel(
            self.card, text="Focus Room", font=FONTS["heading"], text_color=theme_color("accent_green")
        ).pack(pady=(20, 6))

        # Task Selector Entry
        self._task_title_var = ctk.StringVar(value="Deep Work Session")
        self.task_entry = ctk.CTkEntry(
            self.card,
            placeholder_text="What are you focusing on? (e.g. Study Math Ch 4)...",
            font=FONTS["body"],
            textvariable=self._task_title_var,
            width=320,
            height=36,
            fg_color=theme_color("bg_tertiary"),
            border_color=theme_color("border")
        )
        self.task_entry.pack(pady=(0, 12))
        self._category_var = ctk.StringVar(value="Study")
        self.category_menu = ctk.CTkOptionMenu(self.card,
            values=[c["name"] for c in self.db.get_all_categories()] or ["Study"],
            variable=self._category_var, width=200)
        self.category_menu.pack(pady=(0, 12))

        # Phase Badge
        self.lbl_phase = ctk.CTkLabel(
            self.card,
            text="READY TO FOCUS",
            font=FONTS["small_bold"],
            text_color=theme_color("on_accent"),
            fg_color=theme_color("accent"),
            corner_radius=10,
            width=130,
            height=26
        )
        self.lbl_phase.pack(pady=(0, 15))

        # Giant Timer Display
        self.lbl_timer = ctk.CTkLabel(
            self.card,
            text="25:00",
            font=("Consolas", SIZES['timer_font_size'], "bold"),
            text_color=theme_color("text_primary")
        )
        self.lbl_timer.pack(pady=(0, 10))

        # Progress bar
        self.prog_bar = ctk.CTkProgressBar(
            self.card,
            height=10,
            corner_radius=5,
            progress_color=theme_color("accent_green"),
            fg_color=theme_color("bg_tertiary"),
            width=320
        )
        self.prog_bar.pack(pady=(0, 14))
        self.prog_bar.set(1.0)

        # Cycle dots
        self.lbl_cycles = ctk.CTkLabel(
            self.card,
            text="○ ○ ○ ○   (Cycle 1 of 4)",
            font=FONTS["body_bold"],
            text_color=theme_color("text_secondary")
        )
        self.lbl_cycles.pack(pady=(0, 18))

        # Buttons Row
        btn_box = ctk.CTkFrame(self.card, fg_color="transparent")
        btn_box.pack(pady=(0, 16))

        self.btn_main = AppButton(
            btn_box,
            text="▶ Start Focus",
            font=FONTS["body_bold"],
            width=SIZES['pomo_btn_width'],
            height=SIZES['pomo_btn_height'],
            fg_color=theme_color("accent_green"),
            hover_color="#2ea043",
            text_color=theme_color("on_accent"),
            command=self._on_main_button_click
        )
        self.btn_main.pack(side="left", padx=5)

        self.btn_skip = AppButton(
            btn_box,
            text="Skip ❯",
            font=FONTS["body_bold"],
            width=SIZES['pomo_btn_width'] * 2 // 3,
            height=SIZES['pomo_btn_height'],
            fg_color=theme_color("bg_tertiary"),
            hover_color=theme_color("border"),
            text_color=theme_color("text_secondary"),
            command=self.engine.skip
        )
        self.btn_skip.pack(side="left", padx=5)

        self.btn_reset = AppButton(
            btn_box,
            text="Reset",
            font=FONTS["body_bold"],
            width=SIZES['pomo_btn_width'] * 2 // 3,
            height=SIZES['pomo_btn_height'],
            fg_color=theme_color("bg_tertiary"),
            hover_color=theme_color("border"),
            text_color=theme_color("accent_red"),
            command=self._reset_timer
        )
        self.btn_reset.pack(side="left", padx=5)

        # Bottom stat banner
        self.lbl_today_pomo = ctk.CTkLabel(
            self.card,
            text="⏱️ 0 min focused today",
            font=FONTS["small"],
            text_color=theme_color("text_muted")
        )
        self.lbl_today_pomo.pack(pady=(0, 18))
        self._update_today_pomo_label()

    def reapply_theme(self):
        """Re-skin PomodoroView in-place when theme toggles."""
        try:
            self.card.configure(fg_color=theme_color("bg_secondary"))
            self.task_entry.configure(
                fg_color=theme_color("bg_tertiary"),
                border_color=theme_color("border"),
                text_color=theme_color("text_primary")
            )
            self.lbl_timer.configure(text_color=theme_color("text_primary"))
            self.prog_bar.configure(fg_color=theme_color("bg_tertiary"))
            self.lbl_cycles.configure(text_color=theme_color("text_secondary"))
            self.btn_skip.configure(
                fg_color=theme_color("bg_tertiary"),
                hover_color=theme_color("border"),
                text_color=theme_color("text_secondary")
            )
            self.btn_reset.configure(
                fg_color=theme_color("bg_tertiary"),
                hover_color=theme_color("border"),
                text_color=theme_color("accent_red")
            )
            self.lbl_today_pomo.configure(text_color=theme_color("text_muted"))
            if self.engine.phase == PomodoroEngine.PHASE_IDLE:
                self.lbl_phase.configure(text_color=theme_color("on_accent"), fg_color=theme_color("accent"))
                self.btn_main.configure(fg_color=theme_color("accent_green"), text_color=theme_color("on_accent"))
        except Exception:
            pass
        self._update_today_pomo_label()

    def _update_today_pomo_label(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        mins = self.db.get_today_pomodoro_minutes(today_str)
        self.lbl_today_pomo.configure(text=f"⏱️ {mins} min focused today")

    def refresh(self):
        self._update_today_pomo_label()

    def _on_main_button_click(self):
        if self.engine.phase == PomodoroEngine.PHASE_IDLE:
            self.start_focus(self.task_entry.get(), self.category_menu.get(), self.source_event_id)
        elif self.engine.phase == PomodoroEngine.PHASE_PAUSED:
            self.engine.resume()
            self.btn_main.configure(text="❚❚ Pause", fg_color=theme_color("accent_yellow"))
        else:
            self.engine.pause()
            self.btn_main.configure(text="▶ Resume", fg_color=theme_color("accent_green"))

    def _on_context_edited(self, *_):
        if not self._prefilling_source and self.engine.phase == PomodoroEngine.PHASE_IDLE:
            self.source_event_id = None

    def start_focus(self, title, category="Study", event_id=None):
        """Start a selected task while preserving any timer already in progress."""
        if self.engine.phase != PomodoroEngine.PHASE_IDLE:
            return False
        self._drain_updates(reschedule=False)
        if self.db_session_id and not self._finish_session():
            return False
        title = title.strip() or "Focus Session"
        session = self.db.start_pomodoro(title=title, category=category, event_id=event_id,
            work_minutes=self.work_min, break_minutes=self.break_min,
            cycles_target=self.target_cycles, tracked=True)
        if session == -1:
            self.lbl_today_pomo.configure(text="Could not save session. Please try again.")
            return False
        self.db_session_id, self.source_event_id = session, event_id
        self._prefilling_source = True
        try:
            self._task_title_var.set(title)
            self._category_var.set(category)
        finally:
            self._prefilling_source = False
        self.engine.start(title=title, category=category, event_id=event_id,
            work_min=self.work_min, break_min=self.break_min, long_break_min=self.long_break_min,
            target_cycles=self.target_cycles, session_id=session)
        self.task_entry.configure(state="disabled")
        self.category_menu.configure(state="disabled")
        self.btn_main.configure(text="❚❚ Pause", fg_color=theme_color("accent_yellow"), text_color=theme_color("on_accent"))
        return True

    def _persist_focus(self, session_id, daily_seconds, cycles_completed):
        # Runs on the timer worker; the DB serializes writes and Tk updates stay queued.
        saved = self.db.checkpoint_pomodoro(session_id, daily_seconds, cycles_completed)
        if saved:
            self._updates.put((self._update_today_pomo_label, ()))
        else:
            self._updates.put((self._show_save_error, ()))
        return saved

    def _show_save_error(self):
        self.lbl_today_pomo.configure(text="Focus could not be saved; retrying…")

    def _reset_timer(self):
        self.engine.stop()
        self._drain_updates(reschedule=False)
        self._finish_session()
        self.task_entry.configure(state="normal")
        self.category_menu.configure(state="normal")
        self.lbl_timer.configure(text=f"{self.work_min:02d}:00")
        self.lbl_phase.configure(text="READY TO FOCUS", fg_color=theme_color("accent"))
        self.btn_main.configure(text="▶ Start Focus", fg_color=theme_color("accent_green"), text_color=theme_color("on_accent"))
        self.prog_bar.set(1.0)
        self.lbl_cycles.configure(text=f"Cycle 1 of {self.target_cycles}")
        self._update_today_pomo_label()

    def _on_tick_threadsafe(self, remaining, total, phase, cycle):
        self._updates.put((self._update_timer_ui, (remaining, total, phase, cycle)))

    def _update_timer_ui(self, remaining, total, phase, cycle):
        if not self.winfo_exists():
            return
        m = remaining // 60
        s = remaining % 60
        self.lbl_timer.configure(text=f"{m:02d}:{s:02d}")
        frac = remaining / max(1, total)
        self.prog_bar.set(frac)

    def _on_phase_change_threadsafe(self, new_phase, cycle):
        self._updates.put((self._update_phase_ui, (new_phase, cycle)))

    def _update_phase_ui(self, new_phase, cycle):
        if not self.winfo_exists():
            return
        target = self.engine.target_cycles
        completed = self.engine.cycles_completed
        dots = " ".join(["●" if i < completed else "○" for i in range(target)])
        self.lbl_cycles.configure(text=f"{dots}   (Cycle {min(cycle, target)} of {target})")

        if new_phase == PomodoroEngine.PHASE_WORK:
            self.lbl_phase.configure(text="FOCUS TIME", fg_color=theme_color("accent_green"))
            self.prog_bar.configure(progress_color=theme_color("accent_green"))
            self.btn_main.configure(text="❚❚ Pause", fg_color=theme_color("accent_yellow"))
            if self.notifier:
                self.notifier.send_simple("Focus Session Started", f"Focusing on: {self.engine.title} ({self.engine.work_minutes} min)")
        elif new_phase == PomodoroEngine.PHASE_SHORT_BREAK:
            self.lbl_phase.configure(text="SHORT BREAK", fg_color=theme_color("accent_orange"))
            self.prog_bar.configure(progress_color=theme_color("accent_orange"))
            if self.notifier:
                self.notifier.send_simple("Break Time!", f"Take {self.engine.break_minutes} minutes to stretch.")
        elif new_phase == PomodoroEngine.PHASE_LONG_BREAK:
            self.lbl_phase.configure(text="LONG BREAK", fg_color=theme_color("accent_purple"))
            self.prog_bar.configure(progress_color=theme_color("accent_purple"))
            if self.notifier:
                self.notifier.send_simple("Long Break!", f"Completed {completed} work cycles. Rest for {self.engine.long_break_minutes} minutes.")

        self._update_today_pomo_label()

    def _on_complete_threadsafe(self):
        self._updates.put((self._on_complete_ui, ()))

    def _on_complete_ui(self):
        self._finish_session()
        self.task_entry.configure(state="normal")
        self.category_menu.configure(state="normal")
        self.lbl_timer.configure(text="DONE! 🎉")
        self.lbl_phase.configure(text="COMPLETED", fg_color=theme_color("accent_green"))
        self.btn_main.configure(text="▶ Start New", fg_color=theme_color("accent_green"))
        self._update_today_pomo_label()

    def reload_settings(self):
        self.work_min = self.db.get_int_setting("pomo_work", 25, 1, 180)
        self.break_min = self.db.get_int_setting("pomo_short_break", 5, 1, 60)
        self.long_break_min = self.db.get_int_setting("pomo_long_break", 15, 1, 120)
        self.target_cycles = self.db.get_int_setting("pomo_cycles", 4, 1, 12)
        if self.engine.phase == PomodoroEngine.PHASE_IDLE:
            self.lbl_timer.configure(text=f"{self.work_min:02d}:00")
            self.lbl_cycles.configure(text=f"Cycle 1 of {self.target_cycles}")

    def _finish_session(self):
        if self.db_session_id:
            if not self.db.checkpoint_pomodoro(self.db_session_id, self.engine.daily_focus_seconds,
                cycles_completed=self.engine.cycles_completed, end_time=datetime.now().isoformat()):
                self.lbl_today_pomo.configure(text="Could not save focus; retry before starting a new session.")
                return False
            self.db_session_id = None
        return True

    def _drain_updates(self, reschedule=True):
        while True:
            try:
                callback, args = self._updates.get_nowait()
            except Empty:
                break
            callback(*args)
        if reschedule:
            self._poll_id = self.after(100, self._drain_updates)

    def destroy(self):
        self.engine.stop()
        self._drain_updates(reschedule=False)
        self._finish_session()
        if hasattr(self, "_poll_id"):
            self.after_cancel(self._poll_id)
        for variable, trace in self._context_traces:
            variable.trace_remove("write", trace)
        super().destroy()


class PomodoroDialog(AppToplevel):
    """Standalone popup wrapper for Pomodoro."""
    def __init__(self, master, db: TimographyDB, notifier: NotificationManager = None,
                 title: str = "Focus Session", **kwargs):
        super().__init__(master)
        self.title("Pomodoro Focus Timer")
        self.geometry("460x520")
        self.configure(fg_color=theme_color("bg_primary"))
        self.wm_attributes("-topmost", True)

        view = PomodoroView(self, db, notifier=notifier)
        view.task_entry.delete(0, "end")
        view.task_entry.insert(0, title)
        view.pack(fill="both", expand=True)
