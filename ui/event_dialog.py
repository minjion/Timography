"""Event dialog for creating and editing events with guaranteed visible Create/Save buttons."""
import customtkinter as ctk
from ui.controls import AppButton, AppToplevel
from ui.scrolling import ScrollableFrame
from datetime import datetime
from tkinter import messagebox
from core.database import TimographyDB
from ui.theme import theme_color
from ui.theme import COLORS, CATEGORY_COLORS, FONTS, BUTTON_CORNER_RADIUS, SIZES
from ui.layout import fit_window
from core.undo_manager import UndoManager

REMINDER_OPTIONS = {"None": 0, "5 min": 5, "10 min": 10, "15 min": 15, "30 min": 30, "1 hour": 60}
RECURRING_OPTIONS = {"None": "none", "Daily": "daily", "Weekly": "weekly", "Monthly": "monthly"}


class EventDialog(AppToplevel):
    def __init__(self, master, db: TimographyDB, event: dict | None = None,
                 on_save_callback=None, default_date: str | None = None, default_time: str | None = None, undo_mgr=None):
        super().__init__(master)

        self.db = db
        self.event = event
        self.on_save_callback = on_save_callback
        self.default_time = default_time
        self.is_edit = event is not None
        self.undo_mgr = undo_mgr or UndoManager(db)

        dlg_title = "Edit Event" if self.is_edit else "✚ Create New Event"
        self.title(dlg_title)

        w, h = fit_window(self, SIZES['dialog_width'], SIZES['dialog_height'], SIZES['dialog_min_w'], SIZES['dialog_min_h'])
        self.configure(fg_color=theme_color("bg_primary"))
        self.transient(master)

        self._selected_color = COLORS["accent"]
        self.color_buttons = []
        self.default_date = default_date or datetime.now().strftime("%Y-%m-%d")

        self._setup_ui()
        self._populate_fields()

        # Center the dialog on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

        self.grab_set()
        self.focus_force()
        self.ent_title.focus_set()

        # Keyboard shortcuts
        self.bind("<Escape>", lambda e: self.destroy())

    def _setup_ui(self):
        # 1. Header (Top)
        header_frame = ctk.CTkFrame(self, fg_color="transparent", height=44)
        header_frame.pack(fill="x", padx=20, pady=(16, 6), side="top")

        series = self.is_edit and self.event.get("recurring", "none") != "none"
        header_text = "Edit recurring series" if series else "Edit Event" if self.is_edit else "Create New Event"
        self.lbl_header = ctk.CTkLabel(
            header_frame, text=header_text, font=FONTS["heading"], text_color=theme_color("text_primary")
        )
        self.lbl_header.pack(side="left")
        if series:
            ctk.CTkLabel(self, text="Changes apply to every occurrence. The date is the series start.",
                         font=FONTS["small"], text_color=theme_color("text_secondary"),
                         wraplength=350, justify="left").pack(fill="x", padx=20, pady=(0, 6))

        # 2. Bottom Action Bar (Pinned with side="bottom" so it is ALWAYS 100% visible!)
        self.bottom_bar = ctk.CTkFrame(self, fg_color=theme_color("bg_secondary"), height=SIZES['action_bar_height'], corner_radius=0)
        self.bottom_bar.pack(fill="x", side="bottom")

        btn_box = ctk.CTkFrame(self.bottom_bar, fg_color="transparent")
        btn_box.pack(fill="both", expand=True, padx=20, pady=12)

        self.btn_cancel = AppButton(
            btn_box, text="Cancel", font=FONTS["body_bold"], width=90, height=SIZES['action_btn_height'],
            fg_color=theme_color("bg_tertiary"), hover_color=theme_color("border"),
            text_color=theme_color("text_secondary"), corner_radius=BUTTON_CORNER_RADIUS,
            command=self.destroy
        )
        self.btn_cancel.pack(side="left", padx=(0, 8))

        if self.is_edit:
            self.btn_delete = AppButton(
                btn_box, text="Delete", font=FONTS["body_bold"], width=80, height=SIZES['action_btn_height'],
                fg_color=theme_color("accent_red"), hover_color="#d73a49",
                text_color="#ffffff", corner_radius=BUTTON_CORNER_RADIUS,
                command=self._delete_event
            )
            self.btn_delete.pack(side="left", padx=(0, 8))

        # Prominent CREATE / SAVE button
        btn_text = "Save Changes ✓" if self.is_edit else "Create Event ✓"
        self.btn_save = AppButton(
            btn_box, text=btn_text, font=FONTS["body_bold"], height=SIZES['action_btn_height'],
            fg_color=theme_color("accent"), hover_color=theme_color("accent_hover"),
            text_color=theme_color("on_accent"), corner_radius=BUTTON_CORNER_RADIUS,
            command=self._save
        )
        self.btn_save.pack(side="right", fill="x", expand=True)

        # 3. Middle Scrollable Form Body
        self.scroll_body = ScrollableFrame(self, fg_color="transparent")
        self.scroll_body.pack(fill="both", expand=True, padx=20, pady=(4, 6))

        # Title
        ctk.CTkLabel(self.scroll_body, text="Event Title *", font=FONTS["body_bold"], text_color=theme_color("text_primary")).pack(anchor="w", pady=(4, 4))
        self.ent_title = ctk.CTkEntry(
            self.scroll_body, placeholder_text="e.g. Math Lecture, Team Sync, Gym Workout",
            font=FONTS["body"], fg_color=theme_color("bg_secondary"), border_color=theme_color("border"),
            text_color=theme_color("text_primary"), height=SIZES['field_height']
        )
        self.ent_title.pack(fill="x", pady=(0, 10))
        self.ent_title.bind("<Return>", lambda e: self._save())

        # Description
        ctk.CTkLabel(self.scroll_body, text="Description", font=FONTS["body_bold"], text_color=theme_color("text_primary")).pack(anchor="w", pady=(0, 4))
        self.txt_desc = ctk.CTkTextbox(
            self.scroll_body, font=FONTS["body"], height=64,
            fg_color=theme_color("bg_secondary"), border_color=theme_color("border"), border_width=1,
            text_color=theme_color("text_primary")
        )
        self.txt_desc.pack(fill="x", pady=(0, 10))

        # Date & Category row
        row1 = ctk.CTkFrame(self.scroll_body, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 10))
        row1.columnconfigure((0, 1), weight=1)

        # Date
        date_frame = ctk.CTkFrame(row1, fg_color="transparent")
        date_frame.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkLabel(date_frame, text="Date (YYYY-MM-DD)", font=FONTS["small_bold"], text_color=theme_color("text_primary")).pack(anchor="w", pady=(0, 4))
        self.ent_date = ctk.CTkEntry(
            date_frame, font=FONTS["body"], fg_color=theme_color("bg_secondary"),
            border_color=theme_color("border"), text_color=theme_color("text_primary"), height=SIZES['field_height']
        )
        self.ent_date.pack(fill="x")

        # Category
        cat_frame = ctk.CTkFrame(row1, fg_color="transparent")
        cat_frame.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ctk.CTkLabel(cat_frame, text="Category", font=FONTS["small_bold"], text_color=theme_color("text_primary")).pack(anchor="w", pady=(0, 4))

        categories = self.db.get_all_categories()
        cat_names = [c['name'] for c in categories] if categories else ["Work", "Study", "Health", "Social", "Personal"]
        self.opt_category = ctk.CTkOptionMenu(
            cat_frame, values=cat_names, font=FONTS["body"], height=SIZES['field_height'],
            text_color=theme_color("text_primary"), fg_color=theme_color("bg_secondary"), button_color=theme_color("bg_tertiary"),
            button_hover_color=theme_color("accent"),
            dropdown_fg_color=theme_color("bg_secondary"), dropdown_hover_color=theme_color("bg_tertiary"),
            dropdown_text_color=theme_color("text_primary")
        )
        self.opt_category.pack(fill="x")

        # Time Row
        row2 = ctk.CTkFrame(self.scroll_body, fg_color="transparent")
        row2.pack(fill="x", pady=(0, 10))
        row2.columnconfigure((0, 1), weight=1)

        hours = [f"{i:02d}" for i in range(24)]
        minutes = [f"{i:02d}" for i in range(0, 60, 5)]

        # Start Time
        start_frame = ctk.CTkFrame(row2, fg_color="transparent")
        start_frame.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkLabel(start_frame, text="Start Time", font=FONTS["small_bold"], text_color=theme_color("text_primary")).pack(anchor="w", pady=(0, 4))

        start_time_inner = ctk.CTkFrame(start_frame, fg_color="transparent")
        start_time_inner.pack(fill="x")
        self.opt_start_h = ctk.CTkOptionMenu(
            start_time_inner, values=hours, width=SIZES['time_menu_width'], height=SIZES['field_height'],
            font=FONTS["body"], text_color=theme_color("text_primary"), fg_color=theme_color("bg_secondary"), button_color=theme_color("bg_tertiary"),
            dropdown_fg_color=theme_color("bg_secondary"), dropdown_hover_color=theme_color("bg_tertiary"),
            dropdown_text_color=theme_color("text_primary")
        )
        self.opt_start_h.pack(side="left", padx=(0, 2))
        ctk.CTkLabel(start_time_inner, text=":", font=FONTS["body_bold"], text_color=theme_color("text_primary")).pack(side="left", padx=2)
        self.opt_start_m = ctk.CTkOptionMenu(
            start_time_inner, values=minutes, width=SIZES['time_menu_width'], height=SIZES['field_height'],
            font=FONTS["body"], text_color=theme_color("text_primary"), fg_color=theme_color("bg_secondary"), button_color=theme_color("bg_tertiary"),
            dropdown_fg_color=theme_color("bg_secondary"), dropdown_hover_color=theme_color("bg_tertiary"),
            dropdown_text_color=theme_color("text_primary")
        )
        self.opt_start_m.pack(side="left", padx=(2, 0))

        # End Time
        end_frame = ctk.CTkFrame(row2, fg_color="transparent")
        end_frame.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ctk.CTkLabel(end_frame, text="End Time", font=FONTS["small_bold"], text_color=theme_color("text_primary")).pack(anchor="w", pady=(0, 4))

        end_time_inner = ctk.CTkFrame(end_frame, fg_color="transparent")
        end_time_inner.pack(fill="x")
        self.opt_end_h = ctk.CTkOptionMenu(
            end_time_inner, values=hours, width=SIZES['time_menu_width'], height=SIZES['field_height'],
            font=FONTS["body"], text_color=theme_color("text_primary"), fg_color=theme_color("bg_secondary"), button_color=theme_color("bg_tertiary"),
            dropdown_fg_color=theme_color("bg_secondary"), dropdown_hover_color=theme_color("bg_tertiary"),
            dropdown_text_color=theme_color("text_primary")
        )
        self.opt_end_h.pack(side="left", padx=(0, 2))
        ctk.CTkLabel(end_time_inner, text=":", font=FONTS["body_bold"], text_color=theme_color("text_primary")).pack(side="left", padx=2)
        self.opt_end_m = ctk.CTkOptionMenu(
            end_time_inner, values=minutes, width=SIZES['time_menu_width'], height=SIZES['field_height'],
            font=FONTS["body"], text_color=theme_color("text_primary"), fg_color=theme_color("bg_secondary"), button_color=theme_color("bg_tertiary"),
            dropdown_fg_color=theme_color("bg_secondary"), dropdown_hover_color=theme_color("bg_tertiary"),
            dropdown_text_color=theme_color("text_primary")
        )
        self.opt_end_m.pack(side="left", padx=(2, 0))

        # Reminder & Recurring row
        row3 = ctk.CTkFrame(self.scroll_body, fg_color="transparent")
        row3.pack(fill="x", pady=(0, 10))
        row3.columnconfigure((0, 1), weight=1)

        # Reminder
        rem_frame = ctk.CTkFrame(row3, fg_color="transparent")
        rem_frame.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkLabel(rem_frame, text="Reminder Alert", font=FONTS["small_bold"], text_color=theme_color("text_primary")).pack(anchor="w", pady=(0, 4))
        self.opt_reminder = ctk.CTkOptionMenu(
            rem_frame, values=list(REMINDER_OPTIONS.keys()), font=FONTS["body"], height=SIZES['field_height'],
            text_color=theme_color("text_primary"), fg_color=theme_color("bg_secondary"), button_color=theme_color("bg_tertiary"),
            dropdown_fg_color=theme_color("bg_secondary"), dropdown_hover_color=theme_color("bg_tertiary"),
            dropdown_text_color=theme_color("text_primary")
        )
        self.opt_reminder.pack(fill="x")

        # Recurring
        rec_frame = ctk.CTkFrame(row3, fg_color="transparent")
        rec_frame.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ctk.CTkLabel(rec_frame, text="Repeat", font=FONTS["small_bold"], text_color=theme_color("text_primary")).pack(anchor="w", pady=(0, 4))
        self.opt_recurring = ctk.CTkOptionMenu(
            rec_frame, values=list(RECURRING_OPTIONS.keys()), font=FONTS["body"], height=SIZES['field_height'],
            text_color=theme_color("text_primary"), fg_color=theme_color("bg_secondary"), button_color=theme_color("bg_tertiary"),
            dropdown_fg_color=theme_color("bg_secondary"), dropdown_hover_color=theme_color("bg_tertiary"),
            dropdown_text_color=theme_color("text_primary")
        )
        self.opt_recurring.pack(fill="x")

        # Color picker row
        ctk.CTkLabel(self.scroll_body, text="Accent Color", font=FONTS["small_bold"], text_color=theme_color("text_primary")).pack(anchor="w", pady=(0, 6))
        color_frame = ctk.CTkFrame(self.scroll_body, fg_color="transparent")
        color_frame.pack(fill="x", pady=(0, 10))

        colors = ["#58a6ff", "#3fb950", "#f85149", "#bc8cff", "#f0883e", "#d29922"]
        for c in colors:
            btn = AppButton(
                color_frame, text="", width=SIZES['color_dot_size'], height=SIZES['color_dot_size'], fg_color=c, hover_color=c,
                corner_radius=SIZES['color_dot_size'] // 2, border_width=2, border_color=theme_color("transparent"),
                command=lambda col=c: self._select_color(col)
            )
            btn.pack(side="left", padx=(0, 10))
            self.color_buttons.append(btn)

    def _select_color(self, color):
        self._selected_color = color
        for btn in self.color_buttons:
            if btn.cget("fg_color") == color:
                btn.configure(border_color=theme_color("text_primary"))
            else:
                btn.configure(border_color=theme_color("transparent"))

    def _populate_fields(self):
        if self.event:
            self.ent_title.insert(0, self.event.get('title', ''))
            desc = self.event.get('description', '')
            if desc:
                self.txt_desc.insert("1.0", desc)

            self.ent_date.insert(0, self.event.get('date', self.default_date))

            if 'category' in self.event:
                self.opt_category.set(self.event['category'])

            if 'start_time' in self.event:
                try:
                    sh, sm = self.event['start_time'].split(':')
                    self.opt_start_h.set(sh)
                    self.opt_start_m.set(sm)
                except ValueError:
                    pass

            if 'end_time' in self.event:
                try:
                    eh, em = self.event['end_time'].split(':')
                    self.opt_end_h.set(eh)
                    self.opt_end_m.set(em)
                except ValueError:
                    pass

            rem_val = self.event.get('reminder_minutes', 10)
            for k, v in REMINDER_OPTIONS.items():
                if v == rem_val:
                    self.opt_reminder.set(k)
                    break

            rec_val = self.event.get('recurring', 'none')
            for k, v in RECURRING_OPTIONS.items():
                if v == rec_val:
                    self.opt_recurring.set(k)
                    break

            color = self.event.get('color', CATEGORY_COLORS.get("Work", "#58a6ff"))
            self._select_color(color)
        else:
            self.ent_date.insert(0, self.default_date)
            now = datetime.now()
            start_h = f"{now.hour:02d}"
            start_m = "00"
            if self.default_time:
                try:
                    parts = self.default_time.split(":")
                    start_h = f"{int(parts[0]):02d}"
                    start_m = f"{int(parts[1]):02d}" if len(parts) > 1 else "00"
                except (ValueError, IndexError):
                    pass
            end_minutes = min(1439, int(start_h) * 60 + int(start_m) + 60)
            if end_minutes <= int(start_h) * 60 + int(start_m):
                start_h, start_m = "23", "00"
            end_h, end_m = f"{end_minutes // 60:02d}", f"{end_minutes % 60:02d}"
            self.opt_start_h.set(start_h)
            self.opt_start_m.set(start_m)
            self.opt_end_h.set(end_h)
            self.opt_end_m.set(end_m)
            reminder = self.db.get_int_setting("default_reminder", 10, 0, 120)
            self.opt_reminder.set(next((k for k, v in REMINDER_OPTIONS.items() if v == reminder), "10 min"))
            self._select_color(CATEGORY_COLORS.get("Work", "#58a6ff"))

    def _delete_event(self):
        if self.is_edit and self.event:
            old_data = self.db.get_event(self.event["id"])
            if not self.db.delete_event(self.event["id"]):
                messagebox.showerror("Delete failed", "The event could not be deleted.", parent=self)
                return
            self.undo_mgr.record("delete", "event", self.event["id"], old_data, None)
            if self.on_save_callback:
                self.on_save_callback()
            self.destroy()

    def _save(self):
        title = self.ent_title.get().strip()
        if not title:
            self.ent_title.configure(border_color=COLORS.get("accent_red", "red"))
            self.ent_title.focus_set()
            return

        desc = self.txt_desc.get("1.0", "end-1c").strip()
        date_str = self.ent_date.get().strip()
        category = self.opt_category.get()

        start_time = f"{self.opt_start_h.get()}:{self.opt_start_m.get()}"
        end_time = f"{self.opt_end_h.get()}:{self.opt_end_m.get()}"

        reminder_min = REMINDER_OPTIONS[self.opt_reminder.get()]
        recurring = RECURRING_OPTIONS[self.opt_recurring.get()]
        color = self._selected_color

        try:
            if self.is_edit:
                old = self.db.get_event(self.event['id'])
                if not self.db.update_event(self.event['id'], title=title, description=desc,
                    date=date_str, category=category, start_time=start_time, end_time=end_time,
                    reminder_minutes=reminder_min, recurring=recurring, color=color):
                    raise ValueError("The event could not be saved.")
                self.undo_mgr.record("update", "event", self.event['id'], old, self.db.get_event(self.event['id']))
            else:
                event_id = self.db.add_event(title, desc, start_time, end_time, date_str,
                    color, category, recurring, reminder_min)
                if event_id == -1:
                    raise ValueError("The event could not be created.")
                self.undo_mgr.record("add", "event", event_id, None, self.db.get_event(event_id))
        except ValueError as exc:
            messagebox.showerror("Check event details", str(exc), parent=self)
            return

        if self.on_save_callback:
            self.on_save_callback()

        self.destroy()
