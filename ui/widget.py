"""Polished desktop widget with frosted glass, mini-cards, streak pill, checklist progress, and quick focus."""
import customtkinter as ctk
from ui.controls import AppButton, AppToplevel
from ui.scrolling import ScrollableFrame
from datetime import datetime
import tkinter as tk
from tkinter import font as tkfont

from config import DEFAULT_WIDGET_X, DEFAULT_WIDGET_Y, REFRESH_INTERVAL_MS
from ui.theme import theme_color
from ui.theme import COLORS, FONTS, WIDGET_CORNER_RADIUS, CARD_CORNER_RADIUS, SIZES
from ui.animations import fade_window
from core.undo_manager import UndoManager


class DesktopWidget(AppToplevel):
    def __init__(self, master, db, on_add_event=None, on_open_main=None,
                 on_quick_add=None, on_open_pomodoro=None, on_open_exams=None):
        super().__init__(master)
        self.db = db
        self.undo_mgr = UndoManager(db)
        self.on_add_event = on_add_event
        self.on_open_main = on_open_main
        self.on_quick_add = on_quick_add
        self.on_open_pomodoro = on_open_pomodoro
        self.on_open_exams = on_open_exams
        self._visibility_animation = None
        self._hide_after_id = None
        self._task_font = tkfont.Font(self, font=("Segoe UI", -11))

        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.configure(fg_color=theme_color("transparent"))
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

        self.geometry(f"{SIZES['widget_width']}x{SIZES['widget_height']}+{x}+{y}")
        self._offset_x = 0
        self._offset_y = 0

        # Outer container
        self.container = ctk.CTkFrame(self, fg_color=theme_color("bg_primary"), corner_radius=WIDGET_CORNER_RADIUS)
        self.container.pack(fill="both", expand=True, padx=5, pady=5)

        # Header row
        self.header_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=10, pady=(10, 4))

        self.header_frame.bind("<Button-1>", self._start_drag)
        self.header_frame.bind("<B1-Motion>", self._on_drag)
        self.header_frame.bind("<ButtonRelease-1>", self._stop_drag)

        self.date_label = ctk.CTkLabel(
            self.header_frame, text="Schedule",
            font=FONTS["widget_title"], text_color=theme_color("text_primary")
        )
        self.date_label.pack(side="left")
        self.date_label.bind("<Button-1>", self._start_drag)
        self.date_label.bind("<B1-Motion>", self._on_drag)
        self.date_label.bind("<ButtonRelease-1>", self._stop_drag)

        # Streak indicator badge
        self.lbl_streak = ctk.CTkLabel(
            self.header_frame, text="0 days", font=FONTS["micro"],
            text_color=theme_color("accent_orange"), fg_color=theme_color("bg_secondary"),
            corner_radius=6, width=38, height=20
        )
        self.lbl_streak.pack(side="left", padx=(8, 0))

        self.menu_btn = AppButton(
            self.header_frame, text="≡", width=SIZES['widget_btn_size'], height=SIZES['widget_btn_size'],
            fg_color="transparent", hover_color=theme_color("bg_tertiary"),
            font=FONTS["subheading"], text_color=theme_color("text_secondary"),
            command=self._show_menu
        )
        self.menu_btn.pack(side="right", padx=(4, 0))

        self.hide_btn = AppButton(
            self.header_frame, text="—", width=SIZES['widget_btn_size'], height=SIZES['widget_btn_size'],
            fg_color="transparent", hover_color=theme_color("bg_tertiary"),
            font=FONTS["small_bold"], text_color=theme_color("text_secondary"),
            command=self.hide_animated
        )
        self.hide_btn.pack(side="right")

        # Separator
        self.separator = ctk.CTkFrame(self.container, height=1, fg_color=theme_color("border"))
        self.separator.pack(fill="x", padx=10, pady=(4, 6))

        # Quick action row pinned to bottom
        bottom_box = ctk.CTkFrame(self.container, fg_color="transparent")
        bottom_box.pack(side="bottom", fill="x", padx=10, pady=(0, 10))

        self.add_btn = AppButton(
            bottom_box, text="+ Add", fg_color=theme_color("bg_tertiary"),
            hover_color=theme_color("border"), text_color=theme_color("text_primary"),
            font=FONTS["small_bold"], height=30, corner_radius=CARD_CORNER_RADIUS,
            command=self._add_event_click
        )
        self.add_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.focus_btn = AppButton(
            bottom_box, text="Focus", fg_color=theme_color("bg_tertiary"),
            hover_color=theme_color("border"), text_color=theme_color("accent_green"),
            font=FONTS["small_bold"], height=30, corner_radius=CARD_CORNER_RADIUS,
            command=self._open_focus
        )
        self.focus_btn.pack(side="right", fill="x", expand=True, padx=(4, 0))

        # Checklist mini status bar pinned above bottom buttons
        self.checklist_bar = ctk.CTkFrame(self.container, fg_color=theme_color("bg_secondary"), corner_radius=6, height=26)
        self.checklist_bar.pack(side="bottom", fill="x", padx=10, pady=(4, 6))
        self.checklist_bar.pack_propagate(False)

        self.lbl_checklist_stats = ctk.CTkLabel(
            self.checklist_bar, text="Tasks: 0/0", font=FONTS["micro"],
            text_color=theme_color("text_secondary")
        )
        self.lbl_checklist_stats.pack(side="left", padx=8)

        self.chk_prog = ctk.CTkProgressBar(
            self.checklist_bar, height=6, corner_radius=3,
            progress_color=theme_color("accent_green"), fg_color=theme_color("bg_primary"),
            width=100
        )
        self.chk_prog.pack(side="right", padx=(0, 8))
        self.chk_prog.set(0.0)

        # Mini Checklist Items Section pinned above status bar
        self.checklist_section = ctk.CTkFrame(self.container, fg_color="transparent")
        self.checklist_section.pack(side="bottom", fill="x", padx=10, pady=(2, 0))

        self.checklist_items_frame = ctk.CTkFrame(self.checklist_section, fg_color="transparent")
        self.checklist_items_frame.pack(fill="x")

        self._checklist_widgets = []  # Store checkbox references
        self.refresh_callback = None

        # Scrollable event area fills remaining space
        self.scroll_frame = ScrollableFrame(self.container, fg_color="transparent")
        self.scroll_frame.pack(side="top", fill="both", expand=True, padx=5, pady=2)

        self._schedule_refresh()

    def _show_menu(self):
        menu = tk.Menu(
            self, tearoff=0,
            bg=COLORS["bg_secondary"],
            fg=COLORS["text_primary"],
            activebackground=COLORS["bg_tertiary"],
            activeforeground=COLORS["text_primary"],
        )
        menu.add_command(label="Open Planner", command=self._on_open_main_click)
        if self.on_quick_add:
            menu.add_command(label="Quick Add Event (Ctrl+Space)", command=self.on_quick_add)
        menu.add_command(label="Start Focus Timer", command=self._open_focus)
        if self.on_open_exams:
            menu.add_command(label="Exams & Deadlines", command=self.on_open_exams)
        menu.add_command(label="Manage Routines", command=self._open_routines_dialog)
        menu.add_separator()
        menu.add_command(label="Hide Widget", command=self.hide_animated)
        menu.post(self.winfo_pointerx(), self.winfo_pointery())

    def reapply_theme(self):
        """Re-skin desktop widget in-place when theme toggles."""
        try:
            self.configure(fg_color=theme_color("transparent"))
            self.wm_attributes("-transparentcolor", COLORS["transparent"])
            self.container.configure(fg_color=theme_color("bg_primary"))
            self.date_label.configure(text_color=theme_color("text_primary"))
            self.lbl_streak.configure(fg_color=theme_color("bg_secondary"))
            self.menu_btn.configure(hover_color=theme_color("bg_tertiary"), text_color=theme_color("text_secondary"))
            self.hide_btn.configure(hover_color=theme_color("bg_tertiary"), text_color=theme_color("text_secondary"))
            self.separator.configure(fg_color=theme_color("border"))
            self.add_btn.configure(fg_color=theme_color("bg_tertiary"), hover_color=theme_color("border"), text_color=theme_color("text_primary"))
            self.focus_btn.configure(fg_color=theme_color("bg_tertiary"), hover_color=theme_color("border"), text_color=theme_color("accent_green"))
            self.checklist_bar.configure(fg_color=theme_color("bg_secondary"))
            self.lbl_checklist_stats.configure(text_color=theme_color("text_secondary"))
            self.chk_prog.configure(progress_color=theme_color("accent_green"), fg_color=theme_color("bg_primary"))
        except Exception:
            pass
        self.refresh()

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

    def _render_checklist_items(self):
        """Render up to 5 checklist items as interactive checkboxes."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        items = self.db.get_checklist(today_str)[:5]
        key = (today_str, items, tuple(COLORS.values()))
        if key == getattr(self, "_checklist_snapshot", None):
            return
        old = getattr(self, "_checklist_snapshot", None)
        if (old and old[0] == today_str and old[2] == key[2]
                and [(item["id"], item["title"]) for item in old[1]]
                == [(item["id"], item["title"]) for item in items]):
            for previous, item in zip(old[1], items):
                if previous["is_completed"] != item["is_completed"]:
                    checkbox = self._checklist_controls[item["id"]]
                    checkbox.select() if item["is_completed"] else checkbox.deselect()
                    checkbox.configure(text_color=theme_color("text_muted" if item["is_completed"] else "text_secondary"))
            self._checklist_snapshot = key
            return
        self._checklist_snapshot = key
        self._checklist_controls = {}
        for w in self._checklist_widgets:
            try:
                w.destroy()
            except Exception:
                pass
        self._checklist_widgets.clear()

        # Show up to 5 items
        for item in items[:5]:
            is_done = bool(item.get("is_completed", 0))
            item_id = item["id"]

            row = ctk.CTkFrame(self.checklist_items_frame, fg_color="transparent", height=24)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            cb = ctk.CTkCheckBox(
                row,
                text=self._compact_task_title(item.get("title", "")),
                font=FONTS["micro"],
                text_color=theme_color("text_muted") if is_done else theme_color("text_secondary"),
                fg_color=theme_color("accent_green"),
                border_color=theme_color("border"),
                hover_color=theme_color("bg_tertiary"),
                checkbox_width=16, checkbox_height=16,
                corner_radius=4,
                command=lambda iid=item_id: self._toggle_checklist(iid)
            )
            if is_done:
                cb.select()
            self._checklist_controls[item_id] = cb
            cb.pack(side="left", padx=4)
            self._checklist_widgets.append(row)

    def _compact_task_title(self, title):
        title = " ".join(title.split())
        width = SIZES["widget_width"] - 76
        if self._task_font.measure(title) <= width:
            return title
        while title and self._task_font.measure(title + "…") > width:
            title = title[:-1]
        return title + "…"

    def _toggle_checklist(self, item_id: int):
        """Toggle a checklist item and refresh."""
        try:
            old = self.db.get_checklist_item(item_id)
            if not self.db.toggle_checklist_item(item_id):
                self._checklist_snapshot = None
                self._render_checklist_items()
                return
            self.undo_mgr.record("toggle", "checklist", item_id, old, self.db.get_checklist_item(item_id))
            self._render_checklist_items()
            # Update progress bar
            today_str = datetime.now().strftime("%Y-%m-%d")
            stats = self.db.get_checklist_stats(today_str)
            self.lbl_checklist_stats.configure(text=f"Tasks: {stats['completed']}/{stats['total']}")
            self.chk_prog.set(stats["completed"] / max(1, stats["total"]))
            # Notify main window
            if self.refresh_callback:
                self.refresh_callback()
        except Exception:
            pass

    def update_checklist_progress(self, completed: int, total: int):
        """Instant in-place update of widget checklist progress without reloading event cards."""
        try:
            self.lbl_checklist_stats.configure(text=f"Tasks: {completed}/{total}")
            self.chk_prog.set(completed / max(1, total))
            self._render_checklist_items()
        except Exception:
            pass

    def refresh(self):
        now = datetime.now()
        self.db.generate_checklist_for_date(now.date().isoformat())
        self.date_label.configure(text=now.strftime("%a, %b %d"))

        # Streak pill with color coding
        streak = self.db.get_study_streak()
        cur_s = streak.get("current", 0)
        self.lbl_streak.configure(text=f"{cur_s} days")
        if cur_s == 0:
            self.lbl_streak.configure(text_color=theme_color("text_muted"))
        elif streak.get("today_minutes", 0) >= streak.get("goal_minutes", 30):
            self.lbl_streak.configure(text_color=theme_color("accent_green"))
        else:
            self.lbl_streak.configure(text_color=theme_color("accent_orange"))

        # Checklist mini stats
        today_str = now.strftime("%Y-%m-%d")
        stats = self.db.get_checklist_stats(today_str)
        self.lbl_checklist_stats.configure(text=f"Tasks: {stats['completed']}/{stats['total']}")
        self.chk_prog.set(stats["completed"] / max(1, stats["total"]))

        self._render_checklist_items()

        events = self.db.get_events_for_date(today_str, include_routines=True)
        current_time = now.strftime("%H:%M")
        active = next((event["id"] for event in events
                       if event["start_time"] <= current_time < event["end_time"]), None)
        key = (today_str, events, active, tuple(COLORS.values()))
        if key == getattr(self, "_schedule_snapshot", None):
            return
        self._schedule_snapshot = key
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        if not events:
            empty_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            empty_frame.pack(pady=30)
            ctk.CTkLabel(empty_frame, text="Nothing scheduled", font=FONTS["body"], text_color=theme_color("text_muted")).pack()
            ctk.CTkLabel(empty_frame, text="Tap + to add an event", font=FONTS["small"], text_color=theme_color("text_muted")).pack(pady=(4, 0))
            return

        events.sort(key=lambda x: x.get("start_time", ""))
        current_time = now.strftime("%H:%M")
        indicator_placed = False

        for event in events:
            start_time = event.get("start_time", "")
            end_time = event.get("end_time", "")
            is_routine = event.get("is_routine", False)
            color = event.get("color", COLORS["accent"])
            is_current = not indicator_placed and start_time <= current_time < end_time

            card = ctk.CTkFrame(
                self.scroll_frame,
                fg_color=theme_color("bg_tertiary") if is_current else theme_color("bg_secondary"),
                corner_radius=CARD_CORNER_RADIUS,
                border_width=1,
                border_color=theme_color("accent") if is_current else theme_color("border")
            )
            card.pack(fill="x", pady=2, padx=4)

            if is_current:
                indicator_placed = True

            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=10, pady=7)

            accent_bar = ctk.CTkFrame(inner, width=4, corner_radius=2,
                                       fg_color=theme_color("routine_tag") if is_routine else color)
            accent_bar.pack(side="left", fill="y", padx=(0, 8), pady=2)

            content = ctk.CTkFrame(inner, fg_color="transparent")
            content.pack(side="left", fill="both", expand=True)

            title_text = event.get("title", "")
            if is_routine:
                title_text = f"[R] {title_text}"

            title_lbl = ctk.CTkLabel(
                content, text=title_text, font=FONTS["widget_event"],
                text_color=theme_color("routine_tag") if is_routine else theme_color("text_primary"),
                anchor="w", wraplength=180, justify="left"
            )
            title_lbl.pack(anchor="w")
            def wrap_title(event, label=title_lbl):
                if not label.winfo_viewable():
                    return
                width = max(80, round(event.width / label._get_widget_scaling()))
                if label.cget("wraplength") != width:
                    label.configure(wraplength=width)
            content.bind("<Configure>", wrap_title)

            time_text = f"{start_time} - {end_time}"
            time_lbl = ctk.CTkLabel(content, text=time_text, font=FONTS["micro"], text_color=theme_color("text_secondary"), anchor="w")
            time_lbl.pack(anchor="w")

            if is_current:
                arrow = ctk.CTkLabel(inner, text="NOW", font=FONTS["micro"], text_color=theme_color("accent"))
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
        self._cancel_visibility_transition()
        if self.state() == "withdrawn":
            try:
                self.wm_attributes("-alpha", 0.0)
            except Exception:
                pass
        self.deiconify()
        self._visibility_animation = fade_window(self, target_alpha=0.95, duration_ms=180)

    def hide_animated(self):
        self._cancel_visibility_transition()
        def _do_hide():
            self._hide_after_id = None
            self.withdraw()
            try:
                self.wm_attributes("-alpha", 0.95)
            except Exception:
                pass
        self._visibility_animation = fade_window(self, target_alpha=0.0, duration_ms=160)
        self._hide_after_id = self.after(180, _do_hide)

    def hide(self):
        self._cancel_visibility_transition()
        self.withdraw()

    def _cancel_visibility_transition(self):
        if self._visibility_animation:
            self._visibility_animation.stop()
            self._visibility_animation = None
        if self._hide_after_id:
            self.after_cancel(self._hide_after_id)
            self._hide_after_id = None

    def toggle(self):
        if self.state() == "withdrawn" or self._hide_after_id:
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
        self._refresh_id = self.after(REFRESH_INTERVAL_MS, self._schedule_refresh)

    def destroy(self):
        self._cancel_visibility_transition()
        if hasattr(self, "_refresh_id"):
            self.after_cancel(self._refresh_id)
        super().destroy()
