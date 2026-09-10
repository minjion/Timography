"""Pomodoro Focus Timer View & Dialog for Timography."""
from datetime import datetime
import customtkinter as ctk
from ui.theme import COLORS, FONTS, CARD_CORNER_RADIUS, BUTTON_CORNER_RADIUS
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

        self.engine = PomodoroEngine(
            on_tick=self._on_tick_threadsafe,
            on_phase_change=self._on_phase_change_threadsafe,
            on_complete=self._on_complete_threadsafe
        )

        self._build_ui()

    def _build_ui(self):
        # Center container
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.pack(expand=True, fill="both", padx=20, pady=20)

        self.card = ctk.CTkFrame(outer, fg_color=COLORS["bg_secondary"], corner_radius=CARD_CORNER_RADIUS, width=440)
        self.card.pack(expand=True, pady=10)

        # Header / Title row
        ctk.CTkLabel(
            self.card, text="Focus Room", font=FONTS["heading"], text_color=COLORS["accent_green"]
        ).pack(pady=(20, 6))

        # Task Selector Entry
        self.task_entry = ctk.CTkEntry(
            self.card,
            placeholder_text="What are you focusing on? (e.g. Study Math Ch 4)...",
            font=FONTS["body"],
            width=320,
            height=36,
            fg_color=COLORS["bg_tertiary"],
            border_color=COLORS["border"]
        )
        self.task_entry.pack(pady=(0, 12))
        self.task_entry.insert(0, "Deep Work Session")

        # Phase Badge
        self.lbl_phase = ctk.CTkLabel(
            self.card,
            text="READY TO FOCUS",
            font=FONTS["small_bold"],
            text_color=COLORS["bg_primary"],
            fg_color=COLORS["accent"],
            corner_radius=10,
            width=130,
            height=26
        )
        self.lbl_phase.pack(pady=(0, 15))

        # Giant Timer Display
        self.lbl_timer = ctk.CTkLabel(
            self.card,
            text="25:00",
            font=("Consolas", 64, "bold"),
            text_color=COLORS["text_primary"]
        )
        self.lbl_timer.pack(pady=(0, 10))

        # Progress bar
        self.prog_bar = ctk.CTkProgressBar(
            self.card,
            height=10,
            corner_radius=5,
            progress_color=COLORS["accent_green"],
            fg_color=COLORS["bg_tertiary"],
            width=320
        )
        self.prog_bar.pack(pady=(0, 14))
        self.prog_bar.set(1.0)

        # Cycle dots
        self.lbl_cycles = ctk.CTkLabel(
            self.card,
            text="○ ○ ○ ○   (Cycle 1 of 4)",
            font=FONTS["body_bold"],
            text_color=COLORS["text_secondary"]
        )
        self.lbl_cycles.pack(pady=(0, 18))

        # Buttons Row
        btn_box = ctk.CTkFrame(self.card, fg_color="transparent")
        btn_box.pack(pady=(0, 16))

        self.btn_main = ctk.CTkButton(
            btn_box,
            text="▶ Start Focus",
            font=FONTS["body_bold"],
            width=120,
            height=38,
            fg_color=COLORS["accent_green"],
            hover_color="#2ea043",
            text_color=COLORS["bg_primary"],
            command=self._on_main_button_click
        )
        self.btn_main.pack(side="left", padx=5)

        self.btn_skip = ctk.CTkButton(
            btn_box,
            text="Skip ❯",
            font=FONTS["body_bold"],
            width=80,
            height=38,
            fg_color=COLORS["bg_tertiary"],
            hover_color=COLORS["border"],
            text_color=COLORS["text_secondary"],
            command=self.engine.skip
        )
        self.btn_skip.pack(side="left", padx=5)

        self.btn_reset = ctk.CTkButton(
            btn_box,
            text="Reset",
            font=FONTS["body_bold"],
            width=80,
            height=38,
            fg_color=COLORS["bg_tertiary"],
            hover_color=COLORS["border"],
            text_color=COLORS["accent_red"],
            command=self._reset_timer
        )
        self.btn_reset.pack(side="left", padx=5)

        # Bottom stat banner
        self.lbl_today_pomo = ctk.CTkLabel(
            self.card,
            text="⏱️ 0 min focused today",
            font=FONTS["small"],
            text_color=COLORS["text_muted"]
        )
        self.lbl_today_pomo.pack(pady=(0, 18))
        self._update_today_pomo_label()

    def _update_today_pomo_label(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        mins = self.db.get_today_pomodoro_minutes(today_str)
        self.lbl_today_pomo.configure(text=f"⏱️ {mins} min focused today")

    def _on_main_button_click(self):
        if self.engine.phase == PomodoroEngine.PHASE_IDLE:
            task_name = self.task_entry.get().strip() or "Focus Session"
            self.db_session_id = self.db.start_pomodoro(title=task_name)
            self.engine.start(
                title=task_name,
                session_id=self.db_session_id
            )
            self.btn_main.configure(text="❚❚ Pause", fg_color=COLORS["accent_yellow"], text_color=COLORS["bg_primary"])
        elif self.engine.phase == PomodoroEngine.PHASE_PAUSED:
            self.engine.resume()
            self.btn_main.configure(text="❚❚ Pause", fg_color=COLORS["accent_yellow"])
        else:
            self.engine.pause()
            self.btn_main.configure(text="▶ Resume", fg_color=COLORS["accent_green"])

    def _reset_timer(self):
        self.engine.stop()
        self.lbl_timer.configure(text="25:00")
        self.lbl_phase.configure(text="READY TO FOCUS", fg_color=COLORS["accent"])
        self.btn_main.configure(text="▶ Start Focus", fg_color=COLORS["accent_green"], text_color=COLORS["bg_primary"])
        self.prog_bar.set(1.0)
        self.lbl_cycles.configure(text="○ ○ ○ ○   (Cycle 1 of 4)")
        self._update_today_pomo_label()

    def _on_tick_threadsafe(self, remaining, total, phase, cycle):
        self.after(0, lambda: self._update_timer_ui(remaining, total, phase, cycle))

    def _update_timer_ui(self, remaining, total, phase, cycle):
        if not self.winfo_exists():
            return
        m = remaining // 60
        s = remaining % 60
        self.lbl_timer.configure(text=f"{m:02d}:{s:02d}")
        frac = remaining / max(1, total)
        self.prog_bar.set(frac)

    def _on_phase_change_threadsafe(self, new_phase, cycle):
        self.after(0, lambda: self._update_phase_ui(new_phase, cycle))

    def _update_phase_ui(self, new_phase, cycle):
        if not self.winfo_exists():
            return
        target = self.engine.target_cycles
        completed = self.engine.cycles_completed
        dots = " ".join(["●" if i < completed else "○" for i in range(target)])
        self.lbl_cycles.configure(text=f"{dots}   (Cycle {min(cycle, target)} of {target})")

        if new_phase == PomodoroEngine.PHASE_WORK:
            self.lbl_phase.configure(text="FOCUS TIME", fg_color=COLORS["accent_green"])
            self.prog_bar.configure(progress_color=COLORS["accent_green"])
            self.btn_main.configure(text="❚❚ Pause", fg_color=COLORS["accent_yellow"])
            if self.notifier:
                self.notifier.send_simple("Focus Session Started", f"Focusing on: {self.task_entry.get().strip()} (25 min)")
        elif new_phase == PomodoroEngine.PHASE_SHORT_BREAK:
            self.lbl_phase.configure(text="SHORT BREAK", fg_color=COLORS["accent_orange"])
            self.prog_bar.configure(progress_color=COLORS["accent_orange"])
            if self.notifier:
                self.notifier.send_simple("Break Time!", "Great focus sprint! Take 5 minutes to stretch.")
        elif new_phase == PomodoroEngine.PHASE_LONG_BREAK:
            self.lbl_phase.configure(text="LONG BREAK", fg_color=COLORS["accent_purple"])
            self.prog_bar.configure(progress_color=COLORS["accent_purple"])
            if self.notifier:
                self.notifier.send_simple("Long Break!", "Awesome work completing 4 cycles! Enjoy a 15-min rest.")

        if self.db_session_id:
            self.db.update_pomodoro(self.db_session_id, cycles_completed=completed)
        self._update_today_pomo_label()

    def _on_complete_threadsafe(self):
        self.after(0, self._on_complete_ui)

    def _on_complete_ui(self):
        self.lbl_timer.configure(text="DONE! 🎉")
        self.lbl_phase.configure(text="COMPLETED", fg_color=COLORS["accent_green"])
        self.btn_main.configure(text="▶ Start New", fg_color=COLORS["accent_green"])
        self._update_today_pomo_label()


class PomodoroDialog(ctk.CTkToplevel):
    """Standalone popup wrapper for Pomodoro."""
    def __init__(self, master, db: TimographyDB, notifier: NotificationManager = None,
                 title: str = "Focus Session", **kwargs):
        super().__init__(master)
        self.title("Pomodoro Focus Timer")
        self.geometry("460x520")
        self.configure(fg_color=COLORS["bg_primary"])
        self.wm_attributes("-topmost", True)

        view = PomodoroView(self, db, notifier=notifier)
        view.task_entry.delete(0, "end")
        view.task_entry.insert(0, title)
        view.pack(fill="both", expand=True)
