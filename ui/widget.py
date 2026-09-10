"""Polished desktop widget with frosted glass, mini-cards, streak pill, checklist progress, and quick focus."""
import customtkinter as ctk
from datetime import datetime
import tkinter as tk

from config import DEFAULT_WIDGET_X, DEFAULT_WIDGET_Y, REFRESH_INTERVAL_MS
from ui.theme import COLORS, FONTS, WIDGET_CORNER_RADIUS, CARD_CORNER_RADIUS
from ui.animations import fade_window


class DesktopWidget(ctk.CTkToplevel):
    def __init__(self, master, db, on_add_event=None, on_open_main=None,
                 on_quick_add=None, on_open_pomodoro=None, on_open_exams=None):
        super().__init__(master)
        self.db = db
        self.on_add_event = on_add_event
        self.on_open_main = on_open_main
        self.on_quick_add = on_quick_add
        self.on_open_pomodoro = on_open_pomodoro
        self.on_open_exams = on_open_exams

        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.configure(fg_color=COLORS["transparent"])
        self.wm_attributes("-transparentcolor", COLORS["transparent"])

        # Frosted glass effect
        try:
            self.wm_attributes("-alpha", 0.95)
        except Exception:
            pass

        # Load saved position
        x = self.db.get_setting("widget_x", str(DEFAULT_WIDGET_X))
        y = self.db.get_setting("widget_y", str(DEFAULT_WIDGET_Y))
        try:
            x, y = int(x), int(y)
        except ValueError:
            x, y = DEFAULT_WIDGET_X, DEFAULT_WIDGET_Y

        self.geometry(f"300x460+{x}+{y}")
        self._offset_x = 0
        self._offset_y = 0

        # Outer container
        self.container = ctk.CTkFrame(self, fg_color=COLORS["bg_primary"], corner_radius=WIDGET_CORNER_RADIUS)
        self.container.pack(fill="both", expand=True, padx=5, pady=5)

        # Header row
        self.header_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=10, pady=(10, 4))

        self.header_frame.bind("<Button-1>", self._start_drag)
        self.header_frame.bind("<B1-Motion>", self._on_drag)
        self.header_frame.bind("<ButtonRelease-1>", self._stop_drag)

        self.date_label = ctk.CTkLabel(
            self.header_frame, text="Schedule",
            font=FONTS["widget_title"], text_color=COLORS["text_primary"]
        )
        self.date_label.pack(side="left")
        self.date_label.bind("<Button-1>", self._start_drag)
        self.date_label.bind("<B1-Motion>", self._on_drag)
        self.date_label.bind("<ButtonRelease-1>", self._stop_drag)

        # Streak indicator badge
        self.lbl_streak = ctk.CTkLabel(
            self.header_frame, text="🔥 0d", font=FONTS["micro"],
            text_color=COLORS["accent_orange"], fg_color=COLORS["bg_secondary"],
            corner_radius=6, width=38, height=20
        )
        self.lbl_streak.pack(side="left", padx=(8, 0))

        self.menu_btn = ctk.CTkButton(
            self.header_frame, text="≡", width=28, height=28,
            fg_color="transparent", hover_color=COLORS["bg_tertiary"],
            font=FONTS["subheading"], text_color=COLORS["text_secondary"],
            command=self._show_menu
        )
        self.menu_btn.pack(side="right", padx=(4, 0))

        self.hide_btn = ctk.CTkButton(
            self.header_frame, text="—", width=28, height=28,
            fg_color="transparent", hover_color=COLORS["bg_tertiary"],
            font=FONTS["small_bold"], text_color=COLORS["text_secondary"],
            command=self.hide_animated
        )
        self.hide_btn.pack(side="right")

        # Separator
        self.separator = ctk.CTkFrame(self.container, height=1, fg_color=COLORS["border"])
        self.separator.pack(fill="x", padx=10, pady=(4, 6))

        # Scrollable event area
        self.scroll_frame = ctk.CTkScrollableFrame(self.container, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=5, pady=2)

        # Checklist mini status bar
        self.checklist_bar = ctk.CTkFrame(self.container, fg_color=COLORS["bg_secondary"], corner_radius=6, height=26)
        self.checklist_bar.pack(fill="x", padx=10, pady=(4, 6))
        self.checklist_bar.pack_propagate(False)

        self.lbl_checklist_stats = ctk.CTkLabel(
            self.checklist_bar, text="✓ Checklist: 0/0", font=FONTS["micro"],
            text_color=COLORS["text_secondary"]
        )
        self.lbl_checklist_stats.pack(side="left", padx=8)

        self.chk_prog = ctk.CTkProgressBar(
            self.checklist_bar, height=6, corner_radius=3,
            progress_color=COLORS["accent_green"], fg_color=COLORS["bg_primary"],
            width=100
        )
        self.chk_prog.pack(side="right", padx=(0, 8))
        self.chk_prog.set(0.0)

        # Quick action row at bottom
        bottom_box = ctk.CTkFrame(self.container, fg_color="transparent")
        bottom_box.pack(fill="x", padx=10, pady=(0, 10))

        self.add_btn = ctk.CTkButton(
            bottom_box, text="+ Add", fg_color=COLORS["bg_tertiary"],
            hover_color=COLORS["border"], text_color=COLORS["text_primary"],
            font=FONTS["small_bold"], height=30, corner_radius=CARD_CORNER_RADIUS,
            command=self._add_event_click
        )
        self.add_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.focus_btn = ctk.CTkButton(
            bottom_box, text="⏱️ Focus", fg_color=COLORS["bg_tertiary"],
            hover_color=COLORS["border"], text_color=COLORS["accent_green"],
            font=FONTS["small_bold"], height=30, corner_radius=CARD_CORNER_RADIUS,
            command=self._open_focus
        )
        self.focus_btn.pack(side="right", fill="x", expand=True, padx=(4, 0))

        self.refresh()
        self._schedule_refresh()

    def _show_menu(self):
        menu = tk.Menu(self, tearoff=0, bg=COLORS["bg_secondary"], fg=COLORS["text_primary"])
        menu.add_command(label="Open Calendar", command=self._on_open_main_click)
        if self.on_quick_add:
            menu.add_command(label="Quick Add Event (Ctrl+Space)", command=self.on_quick_add)
        menu.add_command(label="Start Focus Timer", command=self._open_focus)
        if self.on_open_exams:
            menu.add_command(label="Exams & Deadlines", command=self.on_open_exams)
        menu.add_command(label="Manage Routines", command=self._open_routines_dialog)
        menu.add_separator()
        menu.add_command(label="Hide Widget", command=self.hide_animated)
        menu.post(self.winfo_pointerx(), self.winfo_pointery())

    def _open_routines_dialog(self):
        from ui.routines_dialog import RoutinesDialog
        RoutinesDialog(self.master, self.db, on_change_callback=self.refresh)

    def _on_open_main_click(self):
        if self.on_open_main:
            self.on_open_main()

    def _add_event_click(self):
        if self.on_add_event:
            self.on_add_event(default_date=datetime.now().strftime("%Y-%m-%d"))

    def _open_focus(self):
        if self.on_open_pomodoro:
            self.on_open_pomodoro()
        else:
            from ui.pomodoro import PomodoroDialog
            PomodoroDialog(self, self.db)

    def update_checklist_progress(self, completed: int, total: int):
        """Instant in-place update of widget checklist progress without reloading event cards."""
        try:
            self.lbl_checklist_stats.configure(text=f"✓ Checklist: {completed}/{total}")
            self.chk_prog.set(completed / max(1, total))
        except Exception:
            pass

    def refresh(self):
        now = datetime.now()
        self.date_label.configure(text=now.strftime("%a, %b %d"))

        # Streak pill
        streak = self.db.get_study_streak()
        cur_s = streak.get("current", 0)
        self.lbl_streak.configure(text=f"🔥 {cur_s}d")

        # Checklist mini stats
        today_str = now.strftime("%Y-%m-%d")
        stats = self.db.get_checklist_stats(today_str)
        self.lbl_checklist_stats.configure(text=f"✓ Checklist: {stats['completed']}/{stats['total']}")
        self.chk_prog.set(stats["completed"] / max(1, stats["total"]))

        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        events = self.db.get_events_for_date(today_str, include_routines=True)

        if not events:
            empty_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            empty_frame.pack(pady=30)
            ctk.CTkLabel(empty_frame, text="Nothing scheduled", font=FONTS["body"], text_color=COLORS["text_muted"]).pack()
            ctk.CTkLabel(empty_frame, text="Tap + to add an event", font=FONTS["small"], text_color=COLORS["text_muted"]).pack(pady=(4, 0))
            return

        events.sort(key=lambda x: x.get("start_time", ""))
        current_time = now.strftime("%H:%M")
        indicator_placed = False

        for event in events:
            start_time = event.get("start_time", "")
            end_time = event.get("end_time", "")
            is_routine = event.get("is_routine", False)
            color = event.get("color", COLORS["accent"])
            is_current = not indicator_placed and end_time >= current_time

            card = ctk.CTkFrame(
                self.scroll_frame,
                fg_color=COLORS["bg_tertiary"] if is_current else COLORS["bg_secondary"],
                corner_radius=CARD_CORNER_RADIUS,
                border_width=1,
                border_color=COLORS["accent"] if is_current else COLORS["border"]
            )
            card.pack(fill="x", pady=2, padx=4)

            if is_current:
                indicator_placed = True

            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=10, pady=7)

            accent_bar = ctk.CTkFrame(inner, width=4, corner_radius=2,
                                       fg_color=COLORS["routine_tag"] if is_routine else color)
            accent_bar.pack(side="left", fill="y", padx=(0, 8), pady=2)

            content = ctk.CTkFrame(inner, fg_color="transparent")
            content.pack(side="left", fill="both", expand=True)

            title_text = event.get("title", "")
            if is_routine:
                title_text = f"[R] {title_text}"

            title_lbl = ctk.CTkLabel(
                content, text=title_text, font=FONTS["widget_event"],
                text_color=COLORS["routine_tag"] if is_routine else COLORS["text_primary"],
                anchor="w"
            )
            title_lbl.pack(anchor="w")

            time_text = f"{start_time} - {end_time}"
            time_lbl = ctk.CTkLabel(content, text=time_text, font=FONTS["micro"], text_color=COLORS["text_secondary"], anchor="w")
            time_lbl.pack(anchor="w")

            if is_current:
                arrow = ctk.CTkLabel(inner, text="NOW", font=FONTS["micro"], text_color=COLORS["accent"])
                arrow.pack(side="right", padx=(4, 0))

            for w in [card, inner, content, title_lbl, time_lbl, accent_bar]:
                w.bind("<Button-1>", lambda e, ev=event: self._edit_event(ev))

    def _edit_event(self, event):
        if event.get("is_routine"):
            from ui.routines_dialog import RoutinesDialog
            RoutinesDialog(self.master, self.db, on_change_callback=self.refresh)
        else:
            from ui.event_dialog import EventDialog
            EventDialog(self.master, self.db, event=event, on_save_callback=self.refresh)

    def show(self):
        try:
            self.wm_attributes("-alpha", 0.0)
        except Exception:
            pass
        self.deiconify()
        fade_window(self, target_alpha=0.95, duration_ms=250)

    def hide_animated(self):
        def _do_hide():
            self.withdraw()
            try:
                self.wm_attributes("-alpha", 0.95)
            except Exception:
                pass
        fade_window(self, target_alpha=0.0, duration_ms=200)
        self.after(220, _do_hide)

    def hide(self):
        self.withdraw()

    def toggle(self):
        if self.state() == "withdrawn":
            self.show()
        else:
            self.hide_animated()

    def _start_drag(self, event):
        self._offset_x = event.x
        self._offset_y = event.y

    def _on_drag(self, event):
        x = self.winfo_x() - self._offset_x + event.x
        y = self.winfo_y() - self._offset_y + event.y
        self.geometry(f"+{x}+{y}")

    def _stop_drag(self, event):
        self.db.set_setting("widget_x", str(self.winfo_x()))
        self.db.set_setting("widget_y", str(self.winfo_y()))

    def _schedule_refresh(self):
        self.refresh()
        self.after(REFRESH_INTERVAL_MS, self._schedule_refresh)
