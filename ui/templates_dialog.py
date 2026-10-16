"""Event Templates manager dialog for Timography."""
import customtkinter as ctk
from ui.controls import AppButton, AppToplevel
from ui.scrolling import ScrollableFrame
from tkinter import messagebox
from ui.theme import theme_color
from ui.theme import FONTS, CARD_CORNER_RADIUS
from core.database import TimographyDB


class TemplatesDialog(AppToplevel):
    def __init__(self, master, db: TimographyDB, on_use_template=None):
        super().__init__(master)
        self.db = db
        self.on_use_template = on_use_template

        self.title("Event Templates")
        self.geometry("460x480")
        self.resizable(False, False)
        self.configure(fg_color=theme_color("bg_primary"))
        self.wm_attributes("-topmost", True)

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        container = ctk.CTkFrame(self, fg_color=theme_color("bg_secondary"), corner_radius=CARD_CORNER_RADIUS)
        container.pack(fill="both", expand=True, padx=16, pady=16)

        # Header
        top_row = ctk.CTkFrame(container, fg_color="transparent")
        top_row.pack(fill="x", padx=16, pady=(16, 10))

        ctk.CTkLabel(top_row, text="Event Templates", font=FONTS["heading"], text_color=theme_color("text_primary")).pack(side="left")

        btn_new = AppButton(
            top_row,
            text="+ New Template",
            font=FONTS["small_bold"],
            width=110,
            height=30,
            fg_color=theme_color("accent"),
            hover_color=theme_color("accent_hover"),
            text_color=theme_color("on_accent"),
            command=self._open_new_template_dialog
        )
        btn_new.pack(side="right")

        # Scroll area for templates
        self.scroll_frame = ScrollableFrame(container, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def refresh(self):
        for w in self.scroll_frame.winfo_children():
            w.destroy()

        templates = self.db.get_all_templates()
        if not templates:
            ctk.CTkLabel(self.scroll_frame, text="No templates saved yet.", font=FONTS["body"], text_color=theme_color("text_muted")).pack(pady=30)
            return

        for t in templates:
            self._render_template_card(t)

    def _render_template_card(self, t: dict):
        card = ctk.CTkFrame(self.scroll_frame, fg_color=theme_color("bg_tertiary"), corner_radius=8)
        card.pack(fill="x", pady=4, padx=4)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)

        # Left color strip
        strip = ctk.CTkFrame(inner, width=4, corner_radius=2, fg_color=t.get("color", theme_color("accent")))
        strip.pack(side="left", fill="y", padx=(0, 10))

        # Info column
        info = ctk.CTkFrame(inner, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(info, text=t["name"], font=FONTS["body_bold"], text_color=theme_color("text_primary"), anchor="w").pack(anchor="w")
        dur = t.get("duration_minutes", 60)
        cat = t.get("category", "Work")
        subtext = f"{dur} min  •  {cat}"
        ctk.CTkLabel(info, text=subtext, font=FONTS["micro"], text_color=theme_color("text_secondary"), anchor="w").pack(anchor="w")

        # Actions
        btn_use = AppButton(
            inner,
            text="Use ⚡",
            font=FONTS["small_bold"],
            width=65,
            height=28,
            fg_color=theme_color("accent"),
            hover_color=theme_color("accent_hover"),
            text_color=theme_color("on_accent"),
            command=lambda tmpl=t: self._use_template(tmpl)
        )
        btn_use.pack(side="right", padx=(8, 0))

        btn_del = AppButton(
            inner,
            text="✕",
            font=FONTS["micro"],
            width=26,
            height=28,
            fg_color="transparent",
            hover_color=theme_color("bg_secondary"),
            text_color=theme_color("text_muted"),
            command=lambda t_id=t["id"]: self._delete_template(t_id)
        )
        btn_del.pack(side="right")

    def _use_template(self, template: dict):
        self.destroy()
        if self.on_use_template:
            self.on_use_template(template)

    def _delete_template(self, template_id: int):
        self.db.delete_template(template_id)
        self.refresh()

    def _open_new_template_dialog(self):
        d = AppToplevel(self)
        d.title("New Template")
        d.geometry("340x360")
        d.resizable(False, False)
        d.configure(fg_color=theme_color("bg_primary"))
        d.transient(self)
        d.grab_set()

        ctk.CTkLabel(d, text="Template Name", font=FONTS["small_bold"], text_color=theme_color("text_primary")).pack(padx=20, pady=(15, 2), anchor="w")
        ent_name = ctk.CTkEntry(d, placeholder_text="e.g. Math Revision", font=FONTS["small"])
        ent_name.pack(fill="x", padx=20)

        ctk.CTkLabel(d, text="Duration (minutes)", font=FONTS["small_bold"], text_color=theme_color("text_primary")).pack(padx=20, pady=(10, 2), anchor="w")
        ent_dur = ctk.CTkEntry(d, placeholder_text="60", font=FONTS["small"])
        ent_dur.pack(fill="x", padx=20)
        ent_dur.insert(0, "60")

        ctk.CTkLabel(d, text="Category", font=FONTS["small_bold"], text_color=theme_color("text_primary")).pack(padx=20, pady=(10, 2), anchor="w")
        cats = [c["name"] for c in self.db.get_all_categories()] or ["Work"]
        opt_cat = ctk.CTkOptionMenu(
            d, values=cats, font=FONTS["small"],
            fg_color=theme_color("bg_secondary"),
            button_color=theme_color("bg_tertiary"),
            text_color=theme_color("text_primary"),
            dropdown_fg_color=theme_color("bg_secondary"),
            dropdown_hover_color=theme_color("bg_tertiary"),
            dropdown_text_color=theme_color("text_primary")
        )
        opt_cat.pack(fill="x", padx=20)

        def _save():
            name = ent_name.get().strip()
            if not name:
                return
            try:
                dur = int(ent_dur.get().strip())
                cat = opt_cat.get()
                if self.db.add_template(name=name, title=name, duration_minutes=dur, category=cat) == -1:
                    raise ValueError("The template could not be saved.")
            except ValueError as exc:
                messagebox.showerror("Check template details", str(exc), parent=d)
                return
            d.destroy()
            self.refresh()

        AppButton(d, text="Save Template", font=FONTS["body_bold"], fg_color=theme_color("accent"), hover_color=theme_color("accent_hover"), command=_save).pack(fill="x", padx=20, pady=20)
