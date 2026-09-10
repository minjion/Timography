"""Exam Countdown and Study Revision Scheduler View & Dialog for Timography."""
from datetime import datetime, date
import customtkinter as ctk
from ui.theme import COLORS, FONTS, CARD_CORNER_RADIUS, BUTTON_CORNER_RADIUS
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
        self.refresh()

    def _build_ui(self):
        container = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], corner_radius=CARD_CORNER_RADIUS)
        container.pack(fill="both", expand=True, padx=20, pady=16)

        # Header
        top_row = ctk.CTkFrame(container, fg_color="transparent")
        top_row.pack(fill="x", padx=16, pady=(16, 10))

        ctk.CTkLabel(
            top_row, text="Exams & Deadlines Tracker", font=FONTS["heading"], text_color=COLORS["text_primary"]
        ).pack(side="left")

        btn_add = ctk.CTkButton(
            top_row,
            text="+ Add Exam / Deadline",
            font=FONTS["small_bold"],
            width=150,
            height=32,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["bg_primary"],
            command=self._open_add_exam_dialog
        )
        btn_add.pack(side="right")

        self.scroll_frame = ctk.CTkScrollableFrame(container, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def refresh(self):
        for w in self.scroll_frame.winfo_children():
            w.destroy()

        exams = self.db.get_all_exams()
        if not exams:
            ctk.CTkLabel(
                self.scroll_frame,
                text="No upcoming exams or deadlines added yet.\nTap '+ Add Exam / Deadline' above to start tracking countdowns!",
                font=FONTS["body"],
                text_color=COLORS["text_muted"]
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

        card = ctk.CTkFrame(self.scroll_frame, fg_color=COLORS["bg_tertiary"], corner_radius=8)
        card.pack(fill="x", pady=6, padx=4)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)

        # Left stripe
        strip = ctk.CTkFrame(inner, width=4, corner_radius=2, fg_color=exam.get("color", COLORS["accent_red"]))
        strip.pack(side="left", fill="y", padx=(0, 12))

        # Main details
        info = ctk.CTkFrame(inner, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(info, text=exam["title"], font=FONTS["body_bold"], text_color=COLORS["text_primary"], anchor="w").pack(anchor="w")
        dt_str = f"📅 {exam['date']} at {exam.get('time', '09:00')}"
        if exam.get("subject"):
            dt_str += f"  •  {exam['subject']}"
        ctk.CTkLabel(info, text=dt_str, font=FONTS["small"], text_color=COLORS["text_secondary"], anchor="w").pack(anchor="w")

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
            width=100,
            height=26
        ).pack(pady=(0, 6))

        action_row = ctk.CTkFrame(right_col, fg_color="transparent")
        action_row.pack()

        if diff_days >= 0:
            btn_rev = ctk.CTkButton(
                action_row,
                text="+ Revision Slot ⚡",
                font=FONTS["small_bold"],
                width=110,
                height=26,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                text_color=COLORS["bg_primary"],
                command=lambda ex_t=exam: self._auto_schedule_revision(ex_t)
            )
            btn_rev.pack(side="left", padx=(0, 6))

        btn_del = ctk.CTkButton(
            action_row,
            text="✕",
            font=FONTS["small"],
            width=26,
            height=26,
            fg_color="transparent",
            hover_color=COLORS["bg_secondary"],
            text_color=COLORS["text_muted"],
            command=lambda ex_id=exam["id"]: self._delete_exam(ex_id)
        )
        btn_del.pack(side="left")

    def _auto_schedule_revision(self, exam: dict):
        today_str = datetime.now().strftime("%Y-%m-%d")
        slot = self.auto_scheduler.suggest_best_slot(today_str, duration_minutes=90, category="Study")
        start = slot["start"] if slot else "16:00"
        end = slot["end"] if slot else "17:30"

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
        d = ctk.CTkToplevel(self)
        d.title("Add Exam / Deadline")
        d.geometry("360x400")
        d.resizable(False, False)
        d.configure(fg_color=COLORS["bg_primary"])
        d.transient(self)
        d.grab_set()

        ctk.CTkLabel(d, text="Exam / Deadline Title", font=FONTS["small_bold"], text_color=COLORS["text_primary"]).pack(padx=20, pady=(15, 2), anchor="w")
        ent_title = ctk.CTkEntry(d, placeholder_text="e.g. Physics Midterm", font=FONTS["small"])
        ent_title.pack(fill="x", padx=20)

        ctk.CTkLabel(d, text="Date (YYYY-MM-DD)", font=FONTS["small_bold"], text_color=COLORS["text_primary"]).pack(padx=20, pady=(10, 2), anchor="w")
        ent_date = ctk.CTkEntry(d, placeholder_text="YYYY-MM-DD", font=FONTS["small"])
        ent_date.pack(fill="x", padx=20)
        ent_date.insert(0, datetime.now().strftime("%Y-%m-%d"))

        ctk.CTkLabel(d, text="Time (HH:MM)", font=FONTS["small_bold"], text_color=COLORS["text_primary"]).pack(padx=20, pady=(10, 2), anchor="w")
        ent_time = ctk.CTkEntry(d, placeholder_text="09:00", font=FONTS["small"])
        ent_time.pack(fill="x", padx=20)
        ent_time.insert(0, "09:00")

        ctk.CTkLabel(d, text="Subject / Course", font=FONTS["small_bold"], text_color=COLORS["text_primary"]).pack(padx=20, pady=(10, 2), anchor="w")
        ent_subj = ctk.CTkEntry(d, placeholder_text="e.g. PHYS 201", font=FONTS["small"])
        ent_subj.pack(fill="x", padx=20)

        def _save():
            title = ent_title.get().strip()
            d_str = ent_date.get().strip()
            t_str = ent_time.get().strip() or "09:00"
            subj = ent_subj.get().strip()
            if not title or not d_str:
                return
            self.db.add_exam(title=title, date=d_str, time=t_str, subject=subj)
            d.destroy()
            self.refresh()

        ctk.CTkButton(
            d, text="Save Countdown", font=FONTS["body_bold"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            text_color=COLORS["bg_primary"], command=_save
        ).pack(fill="x", padx=20, pady=20)


class ExamCountdownDialog(ctk.CTkToplevel):
    """Standalone popup wrapper for Exam Countdown."""
    def __init__(self, master, db: TimographyDB, on_schedule_revision=None):
        super().__init__(master)
        self.title("Exam & Deadline Countdowns")
        self.geometry("520x580")
        self.configure(fg_color=COLORS["bg_primary"])
        self.wm_attributes("-topmost", True)

        view = ExamCountdownView(self, db, on_schedule_revision=on_schedule_revision)
        view.pack(fill="both", expand=True)
