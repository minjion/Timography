"""Exam Countdown and Study Revision Scheduler View & Dialog for Timography."""
from datetime import datetime, date
import customtkinter as ctk
from ui.controls import AppButton, AppToplevel
from ui.scrolling import ScrollableFrame
from tkinter import messagebox
from ui.theme import theme_color
from ui.theme import COLORS, FONTS, CARD_CORNER_RADIUS, SIZES
from core.database import TimographyDB
from core.auto_scheduler import AutoScheduler


class ExamCountdownView(ctk.CTkFrame):
    """Embedded Exam Countdown view for Main Window Tab."""
    def __init__(self, master, db: TimographyDB, on_schedule_revision=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.db = db
        self.on_schedule_revision = on_schedule_revision
        self.auto_scheduler = AutoScheduler(db)

        self._build_ui()
        self.bind("<Map>", lambda event: self.refresh(), add="+")

    def _build_ui(self):
        self.container = ctk.CTkFrame(self, fg_color=theme_color("bg_secondary"), corner_radius=CARD_CORNER_RADIUS)
        self.container.pack(fill="both", expand=True, padx=20, pady=16)

        # Header
        top_row = ctk.CTkFrame(self.container, fg_color="transparent")
        top_row.pack(fill="x", padx=16, pady=(16, 10))

        ctk.CTkLabel(
            top_row, text="Exams & Deadlines Tracker", font=FONTS["heading"], text_color=theme_color("text_primary")
        ).pack(side="left")

        self.btn_add = AppButton(
            top_row,
            text="+ Add Exam / Deadline",
            font=FONTS["small_bold"],
            width=SIZES['exam_add_btn_w'],
            height=SIZES['exam_add_btn_h'],
            fg_color=theme_color("accent"),
            hover_color=theme_color("accent_hover"),
            text_color=theme_color("on_accent"),
            command=self._open_add_exam_dialog
        )
        self.btn_add.pack(side="right")

        self.scroll_frame = ScrollableFrame(self.container, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def reapply_theme(self):
        """Re-skin exam countdown view in-place when theme toggles."""
        try:
            if hasattr(self, "container"):
                self.container.configure(fg_color=theme_color("bg_secondary"))
            if hasattr(self, "btn_add"):
                self.btn_add.configure(
                    fg_color=theme_color("accent"),
                    hover_color=theme_color("accent_hover"),
                    text_color=theme_color("on_accent")
                )
        except Exception:
            pass
        self.refresh()

    def refresh(self):
        exams = self.db.get_all_exams()
        key = (exams, datetime.now().date(), tuple(COLORS.values()))
        if key == getattr(self, "_refresh_key", None):
            return
        self._refresh_key = key
        for w in self.scroll_frame.winfo_children():
            w.destroy()

        if not exams:
            ctk.CTkLabel(
                self.scroll_frame,
                text="No upcoming exams or deadlines added yet.\nTap '+ Add Exam / Deadline' above to start tracking countdowns!",
                font=FONTS["body"],
                text_color=theme_color("text_muted")
            ).pack(pady=40)
            return

        today = datetime.now().date()
        for ex in exams:
            self._render_exam_card(ex, today)

    def _render_exam_card(self, exam: dict, today: date):
        try:
            ex_date = datetime.strptime(exam["date"], "%Y-%m-%d").date()
            diff_days = (ex_date - today).days
        except Exception:
            diff_days = 0

        if diff_days < 0:
            badge_text = "PASSED"
            badge_color = COLORS["text_muted"]
        elif diff_days == 0:
            badge_text = "TODAY! ⚠️"
            badge_color = COLORS["accent_red"]
        elif diff_days <= 3:
            badge_text = f"In {diff_days} day{'s' if diff_days > 1 else ''}! 🚨"
            badge_color = COLORS["accent_red"]
        elif diff_days <= 7:
            badge_text = f"{diff_days} days left ⏳"
            badge_color = COLORS["accent_yellow"]
        else:
            badge_text = f"{diff_days} days left"
            badge_color = COLORS["accent_green"]

        card = ctk.CTkFrame(self.scroll_frame, fg_color=theme_color("bg_tertiary"), corner_radius=8)
        card.pack(fill="x", pady=6, padx=4)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)

        # Left stripe
        strip = ctk.CTkFrame(inner, width=4, corner_radius=2, fg_color=exam.get("color", theme_color("accent_red")))
        strip.pack(side="left", fill="y", padx=(0, 12))

        # Main details
        info = ctk.CTkFrame(inner, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(info, text=exam["title"], font=FONTS["body_bold"], text_color=theme_color("text_primary"), anchor="w").pack(anchor="w")
        dt_str = f"📅 {exam['date']} at {exam.get('time', '09:00')}"
        if exam.get("subject"):
            dt_str += f"  •  {exam['subject']}"
        ctk.CTkLabel(info, text=dt_str, font=FONTS["small"], text_color=theme_color("text_secondary"), anchor="w").pack(anchor="w")

        # Right status & actions
        right_col = ctk.CTkFrame(inner, fg_color="transparent")
        right_col.pack(side="right")

        ctk.CTkLabel(
            right_col,
            text=badge_text,
            font=FONTS["small_bold"],
            text_color="#ffffff",
            fg_color=badge_color,
            corner_radius=8,
            width=SIZES['exam_badge_w'],
            height=SIZES['exam_badge_h']
        ).pack(pady=(0, 6))

        action_row = ctk.CTkFrame(right_col, fg_color="transparent")
        action_row.pack()

        if diff_days >= 0:
            btn_rev = AppButton(
                action_row,
                text="+ Revision Slot ⚡",
                font=FONTS["small_bold"],
                width=SIZES['exam_badge_w'] + 10,
                height=SIZES['exam_badge_h'],
                fg_color=theme_color("accent"),
                hover_color=theme_color("accent_hover"),
                text_color=theme_color("on_accent"),
                command=lambda ex_t=exam: self._auto_schedule_revision(ex_t)
            )
            btn_rev.pack(side="left", padx=(0, 6))

        btn_del = AppButton(
            action_row,
            text="✕",
            font=FONTS["small"],
            width=SIZES['routine_small_btn'],
            height=SIZES['routine_small_btn'],
            fg_color="transparent",
            hover_color=theme_color("bg_secondary"),
            text_color=theme_color("text_muted"),
            command=lambda ex_id=exam["id"]: self._delete_exam(ex_id)
        )
        btn_del.pack(side="left")

    def _auto_schedule_revision(self, exam: dict):
        today_str = datetime.now().strftime("%Y-%m-%d")
        slot = self.auto_scheduler.suggest_best_slot(today_str, duration_minutes=90, category="Study")
        if not slot:
            messagebox.showinfo("No free slot", "No 90-minute revision slot is available today.", parent=self)
            return
        start, end = slot["start"], slot["end"]

        rev_title = f"Exam Prep: {exam['title']}"
        self.db.add_event(
            title=rev_title,
            description=f"Revision for {exam['title']} ({exam.get('date', '')})",
            start_time=start,
            end_time=end,
            date=today_str,
            color="#bc8cff",
            category="Study",
            recurring="none",
            reminder_minutes=10
        )
        if self.on_schedule_revision:
            self.on_schedule_revision()
        self.refresh()

    def _delete_exam(self, exam_id: int):
        self.db.delete_exam(exam_id)
        self.refresh()

    def _open_add_exam_dialog(self):
        d = AppToplevel(self)
        d.title("Add Exam / Deadline")
        d.geometry("360x400")
        d.resizable(False, False)
        d.configure(fg_color=theme_color("bg_primary"))
        d.transient(self)
        d.grab_set()

        ctk.CTkLabel(d, text="Exam / Deadline Title", font=FONTS["small_bold"], text_color=theme_color("text_primary")).pack(padx=20, pady=(15, 2), anchor="w")
        ent_title = ctk.CTkEntry(d, placeholder_text="e.g. Physics Midterm", font=FONTS["small"])
        ent_title.pack(fill="x", padx=20)

        ctk.CTkLabel(d, text="Date (YYYY-MM-DD)", font=FONTS["small_bold"], text_color=theme_color("text_primary")).pack(padx=20, pady=(10, 2), anchor="w")
        ent_date = ctk.CTkEntry(d, placeholder_text="YYYY-MM-DD", font=FONTS["small"])
        ent_date.pack(fill="x", padx=20)
        ent_date.insert(0, datetime.now().strftime("%Y-%m-%d"))

        ctk.CTkLabel(d, text="Time (HH:MM)", font=FONTS["small_bold"], text_color=theme_color("text_primary")).pack(padx=20, pady=(10, 2), anchor="w")
        ent_time = ctk.CTkEntry(d, placeholder_text="09:00", font=FONTS["small"])
        ent_time.pack(fill="x", padx=20)
        ent_time.insert(0, "09:00")

        ctk.CTkLabel(d, text="Subject / Course", font=FONTS["small_bold"], text_color=theme_color("text_primary")).pack(padx=20, pady=(10, 2), anchor="w")
        ent_subj = ctk.CTkEntry(d, placeholder_text="e.g. PHYS 201", font=FONTS["small"])
        ent_subj.pack(fill="x", padx=20)

        def _save():
            title = ent_title.get().strip()
            d_str = ent_date.get().strip()
            t_str = ent_time.get().strip() or "09:00"
            subj = ent_subj.get().strip()
            if not title or not d_str:
                return
            try:
                if self.db.add_exam(title=title, date=d_str, time=t_str, subject=subj) == -1:
                    raise ValueError("The countdown could not be saved.")
            except ValueError as exc:
                messagebox.showerror("Check countdown details", str(exc), parent=d)
                return
            d.destroy()
            self.refresh()

        AppButton(
            d, text="Save Countdown", font=FONTS["body_bold"],
            fg_color=theme_color("accent"), hover_color=theme_color("accent_hover"),
            text_color=theme_color("on_accent"), command=_save
        ).pack(fill="x", padx=20, pady=20)


class ExamCountdownDialog(AppToplevel):
    """Standalone popup wrapper for Exam Countdown."""
    def __init__(self, master, db: TimographyDB, on_schedule_revision=None):
        super().__init__(master)
        self.title("Exam & Deadline Countdowns")
        self.geometry("520x580")
        self.configure(fg_color=theme_color("bg_primary"))
        self.wm_attributes("-topmost", True)

        view = ExamCountdownView(self, db, on_schedule_revision=on_schedule_revision)
        view.pack(fill="both", expand=True)
