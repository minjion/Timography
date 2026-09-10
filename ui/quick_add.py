"""Raycast/Spotlight-style floating Quick-Add bar with real-time NLP parsing."""
from datetime import datetime
import customtkinter as ctk
from ui.theme import COLORS, FONTS, CARD_CORNER_RADIUS, BUTTON_CORNER_RADIUS
from core.nlp_parser import parse_natural_event
from core.auto_scheduler import AutoScheduler
from core.database import TimographyDB
from core.undo_manager import UndoManager


class QuickAddDialog(ctk.CTkToplevel):
    def __init__(self, master, db: TimographyDB, on_created_callback=None, undo_mgr: UndoManager = None):
        super().__init__(master)
        self.db = db
        self.on_created_callback = on_created_callback
        self.undo_mgr = undo_mgr
        self.auto_scheduler = AutoScheduler(db)

        self.title("Quick Add Event")
        self.geometry("520x260")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg_primary"])
        self.wm_attributes("-topmost", True)

        # Center on screen
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w - 520) // 2
        y = (screen_h - 260) // 3
        self.geometry(f"+{x}+{y}")

        self.parsed_data = {}
        self._build_ui()

        # Focus input and bind Escape
        self.bind("<Escape>", lambda e: self.destroy())
        self.entry_input.focus_force()

    def _build_ui(self):
        container = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], corner_radius=CARD_CORNER_RADIUS)
        container.pack(fill="both", expand=True, padx=12, pady=12)

        # Top Bar: Icon + Input
        top_row = ctk.CTkFrame(container, fg_color="transparent")
        top_row.pack(fill="x", padx=16, pady=(16, 10))

        icon_lbl = ctk.CTkLabel(top_row, text="⚡", font=FONTS["heading"], text_color=COLORS["accent"])
        icon_lbl.pack(side="left", padx=(0, 10))

        self.entry_input = ctk.CTkEntry(
            top_row,
            placeholder_text="Type event (e.g. 'Study math tomorrow 2pm for 90m')...",
            font=FONTS["body"],
            fg_color=COLORS["bg_tertiary"],
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            height=38
        )
        self.entry_input.pack(side="left", fill="x", expand=True)
        self.entry_input.bind("<KeyRelease>", self._on_text_change)
        self.entry_input.bind("<Return>", lambda e: self._save_event())

        # Live NLP Preview Box
        self.preview_frame = ctk.CTkFrame(container, fg_color=COLORS["bg_tertiary"], corner_radius=8, height=90)
        self.preview_frame.pack(fill="x", padx=16, pady=(0, 12))
        self.preview_frame.pack_propagate(False)

        self.lbl_preview_title = ctk.CTkLabel(
            self.preview_frame,
            text="Type above to preview event...",
            font=FONTS["body_bold"],
            text_color=COLORS["text_primary"],
            anchor="w"
        )
        self.lbl_preview_title.pack(fill="x", padx=14, pady=(10, 4))

        meta_row = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        meta_row.pack(fill="x", padx=14)

        self.lbl_preview_datetime = ctk.CTkLabel(
            meta_row,
            text="",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"]
        )
        self.lbl_preview_datetime.pack(side="left")

        self.pill_category = ctk.CTkLabel(
            meta_row,
            text="Work",
            font=FONTS["micro"],
            text_color=COLORS["bg_primary"],
            fg_color=COLORS["accent"],
            corner_radius=8,
            width=65,
            height=20
        )
        self.pill_category.pack(side="right")

        # Bottom Actions
        bottom_row = ctk.CTkFrame(container, fg_color="transparent")
        bottom_row.pack(fill="x", padx=16, pady=(0, 12))

        btn_auto = ctk.CTkButton(
            bottom_row,
            text="Auto-Schedule Slot ⚡",
            font=FONTS["small_bold"],
            fg_color=COLORS["bg_tertiary"],
            hover_color=COLORS["border"],
            text_color=COLORS["accent_purple"],
            height=34,
            command=self._auto_schedule_slot
        )
        btn_auto.pack(side="left")

        btn_cancel = ctk.CTkButton(
            bottom_row,
            text="Cancel [Esc]",
            font=FONTS["small"],
            fg_color="transparent",
            hover_color=COLORS["bg_tertiary"],
            text_color=COLORS["text_muted"],
            width=80,
            height=34,
            command=self.destroy
        )
        btn_cancel.pack(side="right", padx=(8, 0))

        btn_create = ctk.CTkButton(
            bottom_row,
            text="Create [Enter]",
            font=FONTS["body_bold"],
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["bg_primary"],
            width=110,
            height=34,
            command=self._save_event
        )
        btn_create.pack(side="right")

    def _on_text_change(self, event=None):
        text = self.entry_input.get().strip()
        if not text:
            self.lbl_preview_title.configure(text="Type above to preview event...")
            self.lbl_preview_datetime.configure(text="")
            self.parsed_data = {}
            return

        self.parsed_data = parse_natural_event(text)
        title = self.parsed_data["title"]
        dt = self.parsed_data["date"]
        st = self.parsed_data["start_time"]
        et = self.parsed_data["end_time"]
        cat = self.parsed_data["category"]
        color = self.parsed_data["color"]

        self.lbl_preview_title.configure(text=title)
        self.lbl_preview_datetime.configure(text=f"📅 {dt}    ⏰ {st} - {et}")
        self.pill_category.configure(text=cat, fg_color=color)

    def _auto_schedule_slot(self):
        text = self.entry_input.get().strip()
        if not text:
            return
        parsed = parse_natural_event(text)
        sh, sm = map(int, parsed["start_time"].split(":"))
        eh, em = map(int, parsed["end_time"].split(":"))
        dur = max(30, (eh * 60 + em) - (sh * 60 + sm))

        slot = self.auto_scheduler.suggest_best_slot(parsed["date"], duration_minutes=dur, category=parsed["category"])
        if slot:
            parsed["start_time"] = slot["start"]
            parsed["end_time"] = slot["end"]
            self.parsed_data = parsed
            self.lbl_preview_datetime.configure(text=f"📅 {parsed['date']}    ⏰ {slot['start']} - {slot['end']} (Optimal Slot ✨)")
        else:
            self.lbl_preview_datetime.configure(text=f"📅 {parsed['date']}    ⚠️ No open slot found for {dur}m")

    def _save_event(self):
        if not self.parsed_data:
            text = self.entry_input.get().strip()
            if not text:
                return
            self.parsed_data = parse_natural_event(text)

        ev_id = self.db.add_event(
            title=self.parsed_data["title"],
            description="Created via Quick-Add",
            start_time=self.parsed_data["start_time"],
            end_time=self.parsed_data["end_time"],
            date=self.parsed_data["date"],
            color=self.parsed_data["color"],
            category=self.parsed_data["category"],
            recurring="none",
            reminder_minutes=10
        )

        if self.undo_mgr and ev_id != -1:
            self.undo_mgr.record("add", "event", ev_id, None, self.parsed_data)

        self.destroy()
        if self.on_created_callback:
            self.on_created_callback()
