import customtkinter as ctk
from ui.controls import AppButton, AppToplevel
from ui.scrolling import ScrollableFrame
from tkinter import messagebox
from tkinter import filedialog
from datetime import datetime
from pathlib import Path
from queue import SimpleQueue, Empty
import threading
from core.backups import BackupManager
from core.database import TimographyDB
from ui.theme import theme_color
from ui.theme import FONTS, SIZES, BUTTON_CORNER_RADIUS, CARD_CORNER_RADIUS, get_current_theme, apply_theme
from ui.layout import fit_window

class SettingsDialog(AppToplevel):
    def __init__(self, master, db: TimographyDB, on_save_callback=None, on_theme_change=None,
                 on_restore=None, backup_manager=None):
        super().__init__(master)
        self.db = db
        self.on_save_callback = on_save_callback
        self.on_theme_change = on_theme_change
        self.on_restore = on_restore
        self.backup_manager = backup_manager or BackupManager(db)
        self._data_results = SimpleQueue()
        self._data_poll_id = None
        self._data_busy = False
        self._destroyed = False
        self._original_theme = get_current_theme()
        self._saved = False

        self.title("Settings")
        fit_window(self, SIZES['dialog_width'], SIZES['dialog_height'], SIZES['dialog_min_w'], SIZES['dialog_min_h'])
        self.transient(master)
        self.grab_set()

        # Center on screen
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"+{x}+{y}")

        self.bind("<Escape>", lambda e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.configure(fg_color=theme_color("bg_primary"))

        self._cards = []
        self._labels = []
        self._section_labels = []
        self._entries = []
        self._menus = []
        self._checkboxes = []

        # Main scrollable container
        self.scroll_frame = ScrollableFrame(self, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Build UI Sections
        self._build_appearance_section()
        self._build_focus_section()
        self._build_streak_section()
        self._build_notifications_section()
        self._build_data_section()

        # Save Button
        self.save_btn = AppButton(
            self,
            text="Save Settings",
            font=FONTS["body_bold"],
            fg_color=theme_color("accent"),
            hover_color=theme_color("accent_hover"),
            text_color="#ffffff",
            corner_radius=BUTTON_CORNER_RADIUS,
            height=SIZES["action_btn_height"],
            command=self._save_settings
        )
        self.save_btn.pack(fill="x", padx=20, pady=(0, 20))

    def _create_section_label(self, parent, text):
        lbl = ctk.CTkLabel(
            parent,
            text=text,
            font=FONTS["micro"],
            text_color=theme_color("text_muted")
        )
        lbl.pack(anchor="w", pady=(20 if parent.winfo_children() else 0, 5))
        self._section_labels.append(lbl)
        return lbl

    def _create_card(self, parent):
        card = ctk.CTkFrame(
            parent,
            fg_color=theme_color("bg_secondary"),
            corner_radius=CARD_CORNER_RADIUS
        )
        card.pack(fill="x", pady=(0, 10))
        self._cards.append(card)
        return card

    def _build_appearance_section(self):
        self._create_section_label(self.scroll_frame, "APPEARANCE")
        card = self._create_card(self.scroll_frame)

        # Theme
        theme_frame = ctk.CTkFrame(card, fg_color="transparent")
        theme_frame.pack(fill="x", padx=15, pady=10)
        lbl_th = ctk.CTkLabel(theme_frame, text="Theme", font=FONTS["body"], text_color=theme_color("text_primary"))
        lbl_th.pack(side="left")
        self._labels.append(lbl_th)

        self.theme_var = ctk.StringVar(value=get_current_theme())
        self.theme_seg = ctk.CTkSegmentedButton(
            theme_frame,
            values=["Light", "Dark"],
            command=self._on_theme_preview,
            font=FONTS["small"]
        )
        self.theme_seg.pack(side="right")
        current_theme_str = "Light" if self.theme_var.get() == "light" else "Dark"
        self.theme_seg.set(current_theme_str)

        # UI Scale
        scale_frame = ctk.CTkFrame(card, fg_color="transparent")
        scale_frame.pack(fill="x", padx=15, pady=10)
        lbl_sc = ctk.CTkLabel(scale_frame, text="Display scaling", font=FONTS["body"], text_color=theme_color("text_primary"))
        lbl_sc.pack(side="left")
        self._labels.append(lbl_sc)
        lbl_sc_v = ctk.CTkLabel(scale_frame, text="Windows automatic", font=FONTS["small"], text_color=theme_color("text_secondary"))
        lbl_sc_v.pack(side="right")
        self._labels.append(lbl_sc_v)

        # Start Week On
        week_frame = ctk.CTkFrame(card, fg_color="transparent")
        week_frame.pack(fill="x", padx=15, pady=10)
        lbl_wk = ctk.CTkLabel(week_frame, text="Start Week On", font=FONTS["body"], text_color=theme_color("text_primary"))
        lbl_wk.pack(side="left")
        self._labels.append(lbl_wk)

        self.week_var = ctk.StringVar(value=self.db.get_setting("week_start", "monday").capitalize())
        self.week_menu = ctk.CTkOptionMenu(
            week_frame,
            values=["Monday", "Sunday"],
            variable=self.week_var,
            font=FONTS["small"],
            fg_color=theme_color("bg_tertiary"),
            text_color=theme_color("text_primary"),
            button_color=theme_color("bg_tertiary"),
            button_hover_color=theme_color("border"),
            dropdown_fg_color=theme_color("bg_secondary"),
            dropdown_hover_color=theme_color("bg_tertiary"),
            dropdown_text_color=theme_color("text_primary")
        )
        self.week_menu.pack(side="right")
        self._menus.append(self.week_menu)
        self.start_widget_var = ctk.BooleanVar(value=self.db.get_setting("start_in_widget_mode", "0") == "1")
        self._add_checkbox_row(card, "Start with desktop widget only", self.start_widget_var)

    def reapply_theme(self):
        """Re-skin SettingsDialog in-place when toggling theme."""
        self.configure(fg_color=theme_color("bg_primary"))
        for card in self._cards:
            try:
                card.configure(fg_color=theme_color("bg_secondary"))
            except Exception:
                pass
        for lbl in self._labels:
            try:
                lbl.configure(text_color=theme_color("text_primary"))
            except Exception:
                pass
        for lbl in self._section_labels:
            try:
                lbl.configure(text_color=theme_color("text_muted"))
            except Exception:
                pass
        for entry in self._entries:
            try:
                entry.configure(fg_color=theme_color("bg_primary"), border_color=theme_color("border"), text_color=theme_color("text_primary"))
            except Exception:
                pass
        for menu in self._menus:
            try:
                menu.configure(
                    fg_color=theme_color("bg_tertiary"),
                    text_color=theme_color("text_primary"),
                    button_color=theme_color("bg_tertiary"),
                    button_hover_color=theme_color("border"),
                    dropdown_fg_color=theme_color("bg_secondary"),
                    dropdown_hover_color=theme_color("bg_tertiary"),
                    dropdown_text_color=theme_color("text_primary")
                )
            except Exception:
                pass
        for cb in self._checkboxes:
            try:
                cb.configure(text_color=theme_color("text_primary"), fg_color=theme_color("accent"))
            except Exception:
                pass
        try:
            self.save_btn.configure(fg_color=theme_color("accent"), hover_color=theme_color("accent_hover"), text_color="#ffffff")
        except Exception:
            pass

    def _on_theme_preview(self, value):
        mode = "light" if "Light" in value else "dark"
        self.theme_var.set(mode)
        apply_theme(mode)
        self.reapply_theme()
        if self.on_theme_change:
            self.on_theme_change(mode)

    def _build_focus_section(self):
        self._create_section_label(self.scroll_frame, "FOCUS & PRODUCTIVITY")
        card = self._create_card(self.scroll_frame)

        self.pomo_work_var = ctk.StringVar(value=self.db.get_setting("pomo_work", "25"))
        self._add_entry_row(card, "Pomodoro Work (min)", self.pomo_work_var)

        self.pomo_short_var = ctk.StringVar(value=self.db.get_setting("pomo_short_break", "5"))
        self._add_entry_row(card, "Short Break (min)", self.pomo_short_var)

        self.pomo_long_var = ctk.StringVar(value=self.db.get_setting("pomo_long_break", "15"))
        self._add_entry_row(card, "Long Break (min)", self.pomo_long_var)

        self.pomo_cycles_var = ctk.StringVar(value=self.db.get_setting("pomo_cycles", "4"))
        self._add_entry_row(card, "Cycles Before Long Break", self.pomo_cycles_var)

    def _add_entry_row(self, parent, label, variable):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=10)
        lbl = ctk.CTkLabel(row, text=label, font=FONTS["body"], text_color=theme_color("text_primary"))
        lbl.pack(side="left")
        self._labels.append(lbl)
        entry = ctk.CTkEntry(
            row,
            textvariable=variable,
            font=FONTS["body"],
            width=60,
            justify="center",
            fg_color=theme_color("bg_primary"),
            border_color=theme_color("border"),
            text_color=theme_color("text_primary")
        )
        entry.pack(side="right")
        self._entries.append(entry)

    def _build_streak_section(self):
        self._create_section_label(self.scroll_frame, "RECORDED FOCUS GOAL")
        card = self._create_card(self.scroll_frame)

        self.streak_goal_var = ctk.StringVar(value=self.db.get_setting("streak_goal_minutes", "30"))
        self._add_entry_row(card, "Daily Goal (min)", self.streak_goal_var)
        explanation = ctk.CTkLabel(card,
            text="Your goal and streak count timer work in the selected categories. Scheduled events and task checkmarks do not add minutes. Pauses and breaks are excluded; older sessions keep their completed-cycle estimates.",
            font=FONTS["small"], text_color=theme_color("text_secondary"),
            wraplength=360, justify="left", anchor="w")
        explanation.pack(fill="x", padx=15, pady=(0, 8))
        self._labels.append(explanation)

        # Categories
        cat_frame = ctk.CTkFrame(card, fg_color="transparent")
        cat_frame.pack(fill="x", padx=15, pady=10)
        lbl_cats = ctk.CTkLabel(cat_frame, text="Focus categories", font=FONTS["body"], text_color=theme_color("text_primary"))
        lbl_cats.pack(anchor="w", pady=(0, 5))
        self._labels.append(lbl_cats)

        saved_cats = self.db.get_setting("streak_categories", "Work,Study,Health,Personal").split(",")
        self.cat_vars = {}

        cats = self.db.get_all_categories()
        for cat in cats:
            cat_name = cat.get("name", "")
            if not cat_name:
                continue
            var = ctk.BooleanVar(value=(cat_name in saved_cats))
            self.cat_vars[cat_name] = var
            cb = ctk.CTkCheckBox(
                cat_frame,
                text=cat_name,
                variable=var,
                font=FONTS["body"],
                text_color=theme_color("text_secondary"),
                fg_color=theme_color("accent"),
                checkbox_height=SIZES["checkbox_size"],
                checkbox_width=SIZES["checkbox_size"]
            )
            cb.pack(anchor="w", padx=10, pady=2)
            self._checkboxes.append(cb)

        # Include Pomo & Checklist
        self.streak_pomo_var = ctk.BooleanVar(value=True)
        self.streak_check_var = ctk.BooleanVar(value=False)

    def _add_checkbox_row(self, parent, label, variable):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=10)
        cb = ctk.CTkCheckBox(
            row,
            text=label,
            variable=variable,
            font=FONTS["body"],
            text_color=theme_color("text_primary"),
            fg_color=theme_color("accent"),
            checkbox_height=SIZES["checkbox_size"],
            checkbox_width=SIZES["checkbox_size"]
        )
        cb.pack(side="left")
        self._checkboxes.append(cb)

    def _build_notifications_section(self):
        self._create_section_label(self.scroll_frame, "NOTIFICATIONS")
        card = self._create_card(self.scroll_frame)

        # Default reminder
        rem_frame = ctk.CTkFrame(card, fg_color="transparent")
        rem_frame.pack(fill="x", padx=15, pady=10)
        lbl_rem = ctk.CTkLabel(rem_frame, text="Default Reminder (min)", font=FONTS["body"], text_color=theme_color("text_primary"))
        lbl_rem.pack(side="left")
        self._labels.append(lbl_rem)
        self.default_rem_var = ctk.StringVar(value=self.db.get_setting("default_reminder", "10"))
        rem_menu = ctk.CTkOptionMenu(
            rem_frame,
            values=["5", "10", "15", "30", "60"],
            variable=self.default_rem_var,
            font=FONTS["small"],
            fg_color=theme_color("bg_tertiary"),
            text_color=theme_color("text_primary"),
            button_color=theme_color("bg_tertiary"),
            button_hover_color=theme_color("border"),
            dropdown_fg_color=theme_color("bg_secondary"),
            dropdown_hover_color=theme_color("bg_tertiary"),
            dropdown_text_color=theme_color("text_primary"),
            width=80
        )
        rem_menu.pack(side="right")
        self._menus.append(rem_menu)

        # Morning briefing
        mb_frame = ctk.CTkFrame(card, fg_color="transparent")
        mb_frame.pack(fill="x", padx=15, pady=10)
        self.mb_var = ctk.BooleanVar(value=self.db.get_setting("morning_briefing", "1") == "1")
        mb_cb = ctk.CTkCheckBox(
            mb_frame,
            text="Morning Briefing",
            variable=self.mb_var,
            font=FONTS["body"],
            text_color=theme_color("text_primary"),
            fg_color=theme_color("accent"),
            checkbox_height=SIZES["checkbox_size"],
            checkbox_width=SIZES["checkbox_size"]
        )
        mb_cb.pack(side="left")
        self._checkboxes.append(mb_cb)
        self.mb_hour_var = ctk.StringVar(value=self.db.get_setting("morning_briefing_hour", "8"))
        mb_entry = ctk.CTkEntry(
            mb_frame,
            textvariable=self.mb_hour_var,
            font=FONTS["body"],
            width=40,
            justify="center",
            fg_color=theme_color("bg_primary"),
            border_color=theme_color("border"),
            text_color=theme_color("text_primary")
        )
        mb_entry.pack(side="right")
        self._entries.append(mb_entry)
        ctk.CTkLabel(mb_frame, text="Hour:", font=FONTS["small"], text_color=theme_color("text_secondary")).pack(side="right", padx=(0, 5))

        # Warnings & Recap
        self.warnings_var = ctk.BooleanVar(value=self.db.get_setting("streak_warnings", "1") == "1")
        self._add_checkbox_row(card, "Streak Warnings", self.warnings_var)

        self.recap_var = ctk.BooleanVar(value=self.db.get_setting("weekly_recap", "1") == "1")
        self._add_checkbox_row(card, "Weekly Recap", self.recap_var)

    def _save_settings(self):
        active_cats = [name for name, var in self.cat_vars.items() if var.get()]
        settings = {
            "start_in_widget_mode": "1" if self.start_widget_var.get() else "0",
            "theme": self.theme_var.get(), "week_start": self.week_var.get().lower(),
            "pomo_work": self.pomo_work_var.get(), "pomo_short_break": self.pomo_short_var.get(),
            "pomo_long_break": self.pomo_long_var.get(), "pomo_cycles": self.pomo_cycles_var.get(),
            "streak_goal_minutes": self.streak_goal_var.get(), "streak_categories": ",".join(active_cats),
            "streak_include_pomo": "1" if self.streak_pomo_var.get() else "0",
            "streak_include_checklist": "1" if self.streak_check_var.get() else "0",
            "default_reminder": self.default_rem_var.get(), "morning_briefing": "1" if self.mb_var.get() else "0",
            "morning_briefing_hour": self.mb_hour_var.get(), "streak_warnings": "1" if self.warnings_var.get() else "0",
            "weekly_recap": "1" if self.recap_var.get() else "0",
        }
        try:
            self.db.set_settings(settings)
        except Exception as exc:
            messagebox.showerror("Settings could not be saved", str(exc), parent=self)
            return
        self._saved = True
        apply_theme(self.theme_var.get())
        if self.on_save_callback:
            self.on_save_callback()

        self.destroy()

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        if self._data_poll_id:
            self.after_cancel(self._data_poll_id)
            self._data_poll_id = None
        if not self._saved and get_current_theme() != self._original_theme:
            apply_theme(self._original_theme)
            if self.on_theme_change:
                self.on_theme_change(self._original_theme)
        super().destroy()

    def _build_data_section(self):
        self._create_section_label(self.scroll_frame, "DATA & RECOVERY")
        card = self._create_card(self.scroll_frame)
        location = "Temporary session database" if self.db.db_path == ":memory:" else str(Path(self.db.db_path).resolve())
        for text in (f"Saved data: {location}",
                     "Automatic daily backups keep the 7 most recent snapshots. Export a separate backup before moving this app to another computer. Restoring restarts the app and keeps a safety copy of current data.",
                     "Reminders require Timography to remain running. Closing the planner hides it; Quit from the tray ends the app."):
            label = ctk.CTkLabel(card, text=text, font=FONTS["small"],
                                 text_color=theme_color("text_secondary"), wraplength=360, justify="left", anchor="w")
            label.pack(fill="x", padx=15, pady=(8, 0))
            self._labels.append(label)
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=15, pady=12)
        self.backup_btn = AppButton(actions, text="Back up data", font=FONTS["small_bold"],
            width=130, command=self._export_backup, fg_color=theme_color("accent"), text_color=theme_color("on_accent"))
        self.backup_btn.pack(side="left", padx=(0, 8))
        self.restore_btn = AppButton(actions, text="Restore backup", font=FONTS["small_bold"],
            width=130, command=self._select_restore, fg_color=theme_color("bg_tertiary"), text_color=theme_color("text_primary"),
            state="normal" if self.on_restore else "disabled")
        self.restore_btn.pack(side="left")
        self.data_status = ctk.CTkLabel(card, text="Backups include saved tasks, events, focus history and settings.",
            font=FONTS["small"], text_color=theme_color("text_secondary"), wraplength=360, justify="left", anchor="w")
        self.data_status.pack(fill="x", padx=15, pady=(0, 12))
        self._labels.append(self.data_status)

    def _run_data_job(self, operation, on_success):
        if self._data_busy:
            return
        self._data_busy = True
        self.backup_btn.configure(state="disabled")
        self.restore_btn.configure(state="disabled")
        self.data_status.configure(text="Working…", text_color=theme_color("text_secondary"))

        def work():
            try:
                self._data_results.put((on_success, operation(), None))
            except Exception as exc:
                self._data_results.put((None, None, str(exc)))

        threading.Thread(target=work, name="Timography backup", daemon=True).start()
        self._data_poll_id = self.after(80, self._poll_data_job)

    def _poll_data_job(self):
        self._data_poll_id = None
        try:
            callback, result, error = self._data_results.get_nowait()
        except Empty:
            self._data_poll_id = self.after(80, self._poll_data_job)
            return
        self._data_busy = False
        self.backup_btn.configure(state="normal")
        self.restore_btn.configure(state="normal" if self.on_restore else "disabled")
        if error:
            self.data_status.configure(text=error, text_color=theme_color("accent_red"))
        else:
            callback(result)

    def _export_backup(self):
        if self._data_busy:
            return
        destination = filedialog.asksaveasfilename(parent=self, title="Back up Timography data", defaultextension=".db",
            initialfile=f"timography-{datetime.now():%Y%m%d-%H%M%S}.db", filetypes=[("Timography database", "*.db")])
        if destination:
            self._run_data_job(lambda: self.backup_manager.create_backup(destination),
                               lambda path: self.data_status.configure(text=f"Backup saved: {path}", text_color=theme_color("accent_green")))

    def _select_restore(self):
        if self._data_busy or not self.on_restore:
            return
        source = filedialog.askopenfilename(parent=self, title="Choose a Timography backup", filetypes=[("Timography database", "*.db"), ("All files", "*.*")])
        if source:
            self._run_data_job(lambda: self.backup_manager.validate_backup(source), self._confirm_restore)

    def _confirm_restore(self, info):
        counts = info["counts"]
        message = (f"Restore {counts['events']} events, {counts['checklist_items']} tasks and "
                   f"{counts['pomodoro_sessions']} focus sessions from this backup?\n\n"
                   "Timography will finish your active focus session, make a safety copy of current data and restart. Unsaved settings will be discarded.")
        if messagebox.askyesno("Restore backup", message, parent=self):
            callback, path = self.on_restore, info["path"]
            self.destroy()
            callback(path)
        else:
            self.data_status.configure(text="Restore cancelled. Current data is unchanged.")
