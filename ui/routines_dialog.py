"""Routines & Templates Manager View & Dialog for Timography."""
import tkinter as tk
import tkinter.messagebox as messagebox
import customtkinter as ctk
from core.database import TimographyDB
from ui.theme import COLORS, FONTS, CARD_CORNER_RADIUS, BUTTON_CORNER_RADIUS

DAYS_MAP = [
    ("Mon", "1"),
    ("Tue", "2"),
    ("Wed", "3"),
    ("Thu", "4"),
    ("Fri", "5"),
    ("Sat", "6"),
    ("Sun", "0"),
]


class RoutinesTemplatesView(ctk.CTkFrame):
    """Embedded Routines & Event Templates View for Main Window Tab."""
    def __init__(self, master, db: TimographyDB, on_change_callback=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.db = db
        self.on_change_callback = on_change_callback
        self.current_subtab = "routines"  # "routines" or "templates"

        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        container = ctk.CTkFrame(self, fg_color=COLORS["bg_secondary"], corner_radius=CARD_CORNER_RADIUS)
        container.pack(fill="both", expand=True, padx=20, pady=16)

        # Top Header
        top_bar = ctk.CTkFrame(container, fg_color="transparent")
        top_bar.pack(fill="x", padx=20, pady=(16, 10))

        self.seg_subtab = ctk.CTkSegmentedButton(
            top_bar,
            values=["Weekly Routines", "Event Templates"],
            font=FONTS["small_bold"],
            command=self._on_subtab_switch
        )
        self.seg_subtab.set("Weekly Routines")
        self.seg_subtab.pack(side="left")

        self.btn_action = ctk.CTkButton(
            top_bar,
            text="+ Add Routine",
            font=FONTS["small_bold"],
            width=130,
            height=32,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["bg_primary"],
            command=self._on_action_click
        )
        self.btn_action.pack(side="right")

        # Scrollable items area
        self.scroll_frame = ctk.CTkScrollableFrame(container, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _on_subtab_switch(self, value):
        if value == "Weekly Routines":
            self.current_subtab = "routines"
            self.btn_action.configure(text="+ Add Routine")
        else:
            self.current_subtab = "templates"
            self.btn_action.configure(text="+ Add Template")
        self.refresh()

    def _on_action_click(self):
        if self.current_subtab == "routines":
            self._open_add_routine_dialog()
        else:
            self._open_add_template_dialog()

    def refresh(self):
        for w in self.scroll_frame.winfo_children():
            w.destroy()

        if self.current_subtab == "routines":
            self._render_routines_list()
        else:
            self._render_templates_list()

    def _render_routines_list(self):
        routines = self.db.get_all_routines()
        if not routines:
            ctk.CTkLabel(
                self.scroll_frame,
                text="No routines configured.\nAdd recurring blocks (School, Gym, Lunch) to auto-fill your weekly schedule.",
                font=FONTS["body"],
                text_color=COLORS["text_muted"]
            ).pack(pady=40)
            return

        for r in routines:
            self._render_routine_card(r)

    def _render_routine_card(self, r: dict):
        card = ctk.CTkFrame(self.scroll_frame, fg_color=COLORS["bg_tertiary"], corner_radius=8)
        card.pack(fill="x", pady=5, padx=4)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)

        # Color strip
        strip = ctk.CTkFrame(inner, width=4, corner_radius=2, fg_color=r.get("color", COLORS["accent"]))
        strip.pack(side="left", fill="y", padx=(0, 12))

        # Main details
        info = ctk.CTkFrame(inner, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)

        title_row = ctk.CTkFrame(info, fg_color="transparent")
        title_row.pack(fill="x", anchor="w")

        ctk.CTkLabel(title_row, text=r["title"], font=FONTS["body_bold"], text_color=COLORS["text_primary"]).pack(side="left")
        ctk.CTkLabel(title_row, text=f"• {r.get('category', 'Routine')}", font=FONTS["micro"], text_color=COLORS["text_secondary"]).pack(side="left", padx=(8, 0))

        # Days badges
        days = [d.strip() for d in r.get("days_of_week", "").split(",") if d.strip()]
        days_txt = []
        for day_name, day_num in DAYS_MAP:
            if day_num in days:
                days_txt.append(day_name)
        days_str = ", ".join(days_txt) if days_txt else "No days"

        sub_str = f"⏰ {r['start_time']} - {r['end_time']}  •  Days: {days_str}"
        ctk.CTkLabel(info, text=sub_str, font=FONTS["small"], text_color=COLORS["text_secondary"], anchor="w").pack(anchor="w", pady=(2, 0))

        # Actions on right
        actions = ctk.CTkFrame(inner, fg_color="transparent")
        actions.pack(side="right")

        # Toggle Switch
        is_active = bool(r.get("is_active", 1))
        switch_var = tk.BooleanVar(value=is_active)

        def _on_toggle(r_id=r["id"], var=switch_var):
            self.db.toggle_routine(r_id, var.get())
            if self.on_change_callback:
                self.on_change_callback()

        sw = ctk.CTkSwitch(
            actions, text="Active", variable=switch_var, font=FONTS["small"],
            progress_color=COLORS["accent_green"], command=_on_toggle
        )
        sw.pack(side="left", padx=(0, 12))

        btn_edit = ctk.CTkButton(
            actions, text="Edit", font=FONTS["small"], width=50, height=26,
            fg_color=COLORS["bg_secondary"], hover_color=COLORS["border"],
            text_color=COLORS["text_primary"], command=lambda rt=r: self._open_edit_routine_dialog(rt)
        )
        btn_edit.pack(side="left", padx=(0, 6))

        btn_del = ctk.CTkButton(
            actions, text="✕", font=FONTS["small"], width=26, height=26,
            fg_color="transparent", hover_color=COLORS["bg_secondary"],
            text_color=COLORS["text_muted"], command=lambda r_id=r["id"]: self._delete_routine(r_id)
        )
        btn_del.pack(side="left")

    def _delete_routine(self, routine_id: int):
        self.db.delete_routine(routine_id)
        self.refresh()
        if self.on_change_callback:
            self.on_change_callback()

    def _render_templates_list(self):
        templates = self.db.get_all_templates()
        if not templates:
            ctk.CTkLabel(
                self.scroll_frame,
                text="No templates configured.\nAdd event templates for quick 1-click scheduling.",
                font=FONTS["body"],
                text_color=COLORS["text_muted"]
            ).pack(pady=40)
            return

        for t in templates:
            self._render_template_card(t)

    def _render_template_card(self, t: dict):
        card = ctk.CTkFrame(self.scroll_frame, fg_color=COLORS["bg_tertiary"], corner_radius=8)
        card.pack(fill="x", pady=5, padx=4)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)

        strip = ctk.CTkFrame(inner, width=4, corner_radius=2, fg_color=t.get("color", COLORS["accent"]))
        strip.pack(side="left", fill="y", padx=(0, 12))

        info = ctk.CTkFrame(inner, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(info, text=t["name"], font=FONTS["body_bold"], text_color=COLORS["text_primary"], anchor="w").pack(anchor="w")
        dur = t.get("duration_minutes", 60)
        cat = t.get("category", "Work")
        subtext = f"{dur} min  •  Category: {cat}"
        ctk.CTkLabel(info, text=subtext, font=FONTS["small"], text_color=COLORS["text_secondary"], anchor="w").pack(anchor="w", pady=(2, 0))

        btn_del = ctk.CTkButton(
            inner, text="✕", font=FONTS["small"], width=28, height=28,
            fg_color="transparent", hover_color=COLORS["bg_secondary"],
            text_color=COLORS["text_muted"], command=lambda t_id=t["id"]: self._delete_template(t_id)
        )
        btn_del.pack(side="right")

    def _delete_template(self, template_id: int):
        self.db.delete_template(template_id)
        self.refresh()
        if self.on_change_callback:
            self.on_change_callback()

    def _open_add_routine_dialog(self):
        RoutineEditDialog(self, self.db, on_save=self._on_saved_routine)

    def _open_edit_routine_dialog(self, routine: dict):
        RoutineEditDialog(self, self.db, routine=routine, on_save=self._on_saved_routine)

    def _on_saved_routine(self):
        self.refresh()
        if self.on_change_callback:
            self.on_change_callback()

    def _open_add_template_dialog(self):
        d = ctk.CTkToplevel(self)
        d.title("New Template")
        d.geometry("340x360")
        d.resizable(False, False)
        d.configure(fg_color=COLORS["bg_primary"])
        d.transient(self)
        d.grab_set()

        ctk.CTkLabel(d, text="Template Name", font=FONTS["small_bold"], text_color=COLORS["text_primary"]).pack(padx=20, pady=(15, 2), anchor="w")
        ent_name = ctk.CTkEntry(d, placeholder_text="e.g. Math Revision", font=FONTS["small"])
        ent_name.pack(fill="x", padx=20)

        ctk.CTkLabel(d, text="Duration (minutes)", font=FONTS["small_bold"], text_color=COLORS["text_primary"]).pack(padx=20, pady=(10, 2), anchor="w")
        ent_dur = ctk.CTkEntry(d, placeholder_text="60", font=FONTS["small"])
        ent_dur.pack(fill="x", padx=20)
        ent_dur.insert(0, "60")

        ctk.CTkLabel(d, text="Category", font=FONTS["small_bold"], text_color=COLORS["text_primary"]).pack(padx=20, pady=(10, 2), anchor="w")
        cats = [c["name"] for c in self.db.get_all_categories()] or ["Study", "Work", "Health", "Social", "Personal"]
        opt_cat = ctk.CTkOptionMenu(d, values=cats, font=FONTS["small"])
        opt_cat.pack(fill="x", padx=20)

        def _save():
            name = ent_name.get().strip()
            if not name:
                return
            try:
                dur = int(ent_dur.get().strip())
            except ValueError:
                dur = 60
            cat = opt_cat.get()
            self.db.add_template(name=name, title=name, duration_minutes=dur, category=cat)
            d.destroy()
            self.refresh()

        ctk.CTkButton(
            d, text="Save Template", font=FONTS["body_bold"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            text_color=COLORS["bg_primary"], command=_save
        ).pack(fill="x", padx=20, pady=20)


class RoutineEditDialog(ctk.CTkToplevel):
    """Modal dialog for adding or editing a routine."""
    def __init__(self, master, db: TimographyDB, routine: dict = None, on_save=None):
        super().__init__(master)
        self.db = db
        self.routine = routine
        self.is_edit = routine is not None
        self.on_save = on_save

        self.title("Edit Routine" if self.is_edit else "Add Routine")
        self.geometry("440x520")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg_primary"])
        self.transient(master)
        self.grab_set()

        self._day_vars = {}
        self._selected_color = routine.get("color", "#58a6ff") if routine else "#58a6ff"
        self._setup_form()

    def _setup_form(self):
        pad_x = 24
        ctk.CTkLabel(self, text="Routine Title", font=FONTS["small_bold"], text_color=COLORS["text_primary"]).pack(padx=pad_x, pady=(16, 2), anchor="w")
        self.ent_title = ctk.CTkEntry(self, placeholder_text="e.g. Morning Classes", font=FONTS["body"])
        self.ent_title.pack(fill="x", padx=pad_x)
        if self.is_edit:
            self.ent_title.insert(0, self.routine.get("title", ""))

        # Time Pickers
        time_row = ctk.CTkFrame(self, fg_color="transparent")
        time_row.pack(fill="x", padx=pad_x, pady=(12, 2))

        # Start Time
        sh_col = ctk.CTkFrame(time_row, fg_color="transparent")
        sh_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(sh_col, text="Start Time", font=FONTS["small_bold"], text_color=COLORS["text_primary"]).pack(anchor="w")
        st_box = ctk.CTkFrame(sh_col, fg_color="transparent")
        st_box.pack(anchor="w", pady=(2, 0))
        hours = [f"{h:02d}" for h in range(24)]
        minutes = [f"{m:02d}" for m in range(0, 60, 5)]
        self.opt_sh = ctk.CTkOptionMenu(st_box, values=hours, width=65)
        self.opt_sh.pack(side="left", padx=(0, 4))
        self.opt_sm = ctk.CTkOptionMenu(st_box, values=minutes, width=65)
        self.opt_sm.pack(side="left")

        # End Time
        eh_col = ctk.CTkFrame(time_row, fg_color="transparent")
        eh_col.pack(side="right", fill="x", expand=True)
        ctk.CTkLabel(eh_col, text="End Time", font=FONTS["small_bold"], text_color=COLORS["text_primary"]).pack(anchor="w")
        et_box = ctk.CTkFrame(eh_col, fg_color="transparent")
        et_box.pack(anchor="w", pady=(2, 0))
        self.opt_eh = ctk.CTkOptionMenu(et_box, values=hours, width=65)
        self.opt_eh.pack(side="left", padx=(0, 4))
        self.opt_em = ctk.CTkOptionMenu(et_box, values=minutes, width=65)
        self.opt_em.pack(side="left")

        if self.is_edit:
            st = self.routine.get("start_time", "08:00")
            et = self.routine.get("end_time", "09:00")
            sh, sm = st.split(":") if ":" in st else ("08", "00")
            eh, em = et.split(":") if ":" in et else ("09", "00")
            self.opt_sh.set(sh)
            self.opt_sm.set(sm)
            self.opt_eh.set(eh)
            self.opt_em.set(em)
        else:
            self.opt_sh.set("08")
            self.opt_sm.set("00")
            self.opt_eh.set("09")
            self.opt_em.set("00")

        # Days of week checkboxes
        ctk.CTkLabel(self, text="Active Days", font=FONTS["small_bold"], text_color=COLORS["text_primary"]).pack(padx=pad_x, pady=(12, 4), anchor="w")
        days_box = ctk.CTkFrame(self, fg_color="transparent")
        days_box.pack(fill="x", padx=pad_x)

        active_days = self.routine.get("days_of_week", "").split(",") if self.is_edit else ["1", "2", "3", "4", "5"]
        for name, num in DAYS_MAP:
            var = tk.BooleanVar(value=num in active_days)
            self._day_vars[num] = var
            cb = ctk.CTkCheckBox(days_box, text=name, variable=var, width=50, font=FONTS["micro"])
            cb.pack(side="left", padx=2)

        # Category
        ctk.CTkLabel(self, text="Category", font=FONTS["small_bold"], text_color=COLORS["text_primary"]).pack(padx=pad_x, pady=(12, 2), anchor="w")
        cats = [c["name"] for c in self.db.get_all_categories()] or ["Study", "Work", "Health", "Social", "Routine", "Personal"]
        self.opt_cat = ctk.CTkOptionMenu(self, values=cats)
        self.opt_cat.pack(fill="x", padx=pad_x)
        if self.is_edit and self.routine.get("category"):
            self.opt_cat.set(self.routine["category"])
        else:
            self.opt_cat.set("Routine")

        # Color picker row
        ctk.CTkLabel(self, text="Accent Color", font=FONTS["small_bold"], text_color=COLORS["text_primary"]).pack(padx=pad_x, pady=(12, 4), anchor="w")
        color_box = ctk.CTkFrame(self, fg_color="transparent")
        color_box.pack(fill="x", padx=pad_x)

        palette = ["#58a6ff", "#3fb950", "#f85149", "#bc8cff", "#f0883e", "#d29922"]
        self._color_btns = []
        for c in palette:
            b = ctk.CTkButton(
                color_box, text="", width=28, height=28, fg_color=c, hover_color=c,
                corner_radius=14, border_width=2, border_color=COLORS["bg_primary"],
                command=lambda col=c: self._select_color(col)
            )
            b.pack(side="left", padx=3)
            self._color_btns.append(b)

        self._select_color(self._selected_color)

        # Save Button
        ctk.CTkButton(
            self, text="Save Routine", font=FONTS["body_bold"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            text_color=COLORS["bg_primary"], command=self._save
        ).pack(fill="x", padx=pad_x, pady=(20, 10))

    def _select_color(self, color):
        self._selected_color = color
        for b in self._color_btns:
            b.configure(border_color=COLORS["text_primary"] if b.cget("fg_color") == color else COLORS["bg_primary"])

    def _save(self):
        title = self.ent_title.get().strip()
        if not title:
            return

        st = f"{self.opt_sh.get()}:{self.opt_sm.get()}"
        et = f"{self.opt_eh.get()}:{self.opt_em.get()}"
        selected_days = [num for num, var in self._day_vars.items() if var.get()]
        if not selected_days:
            selected_days = ["1", "2", "3", "4", "5"]
        days_str = ",".join(selected_days)
        category = self.opt_cat.get()
        color = self._selected_color

        if self.is_edit:
            self.db.update_routine(
                self.routine["id"],
                title=title,
                start_time=st,
                end_time=et,
                days_of_week=days_str,
                category=category,
                color=color
            )
        else:
            self.db.add_routine(
                title=title,
                description="",
                start_time=st,
                end_time=et,
                days_of_week=days_str,
                color=color,
                category=category,
                reminder_minutes=10,
                is_active=1
            )

        if self.on_save:
            self.on_save()
        self.destroy()


class RoutinesDialog(ctk.CTkToplevel):
    """Standalone popup wrapper for Routines."""
    def __init__(self, master, db: TimographyDB, on_change_callback=None):
        super().__init__(master)
        self.title("Manage Routines & Templates")
        self.geometry("580x640")
        self.configure(fg_color=COLORS["bg_primary"])
        self.transient(master)

        view = RoutinesTemplatesView(self, db, on_change_callback=on_change_callback)
        view.pack(fill="both", expand=True)
