"""Unified Tabbed Main Window for Timography — Calendar, Tasks, Focus, Analytics, Exams & Routines."""
from datetime import datetime, date, timedelta
import tkinter as tk
import tkinter.messagebox as messagebox
import customtkinter as ctk

from config import APP_VERSION
from ui.theme import COLORS, FONTS, CARD_CORNER_RADIUS, BUTTON_CORNER_RADIUS
from ui.mini_calendar import MiniCalendar
from ui.time_grid import TimeGrid
from ui.animations import fade_window
from ui.checklist_panel import ChecklistPanel
from ui.pomodoro import PomodoroView
from ui.analytics_dashboard import AnalyticsView
from ui.exam_countdown import ExamCountdownView
from ui.routines_dialog import RoutinesTemplatesView
from ui.quick_add import QuickAddDialog
from core.undo_manager import UndoManager
from core.hotkeys import bind_window_shortcuts


class MainWindow(ctk.CTkToplevel):
    def __init__(self, master, db, refresh_callback=None, on_checklist_stats_change=None,
                 undo_mgr: UndoManager = None, notifier=None):
        super().__init__(master)
        self.db = db
        self.refresh_callback = refresh_callback
        self.on_checklist_stats_change = on_checklist_stats_change
        self.undo_mgr = undo_mgr or UndoManager(db)
        self.notifier = notifier

        self.title(f"Timography v{APP_VERSION} — Productivity Platform")
        self.geometry("1180x760")
        self.minsize(980, 640)
        self.configure(fg_color=COLORS["bg_primary"])
        self.withdraw()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.current_date = datetime.now().date()
        self.view_mode = "week"
        self.active_tab = "calendar"
        self.category_vars = {}
        self.search_query = ""
        self._initial_scroll_done = False

        self._build_ui()
        self._setup_shortcuts()
        self.refresh()

    def _build_ui(self):
        # 1. Top Navigation Bar with Embedded Tabs
        self.top_bar = ctk.CTkFrame(self, height=56, fg_color=COLORS["bg_secondary"], corner_radius=0)
        self.top_bar.pack(fill="x", side="top")
        self.top_bar.pack_propagate(False)

        # Left: Branding + Tabs Selector
        left_top = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        left_top.pack(side="left", padx=14, pady=8)

        lbl_app = ctk.CTkLabel(left_top, text="Timography", font=FONTS["heading"], text_color=COLORS["accent"])
        lbl_app.pack(side="left", padx=(0, 16))

        # Main Segmented Tabs Bar
        self.tabs_bar = ctk.CTkFrame(left_top, fg_color=COLORS["bg_tertiary"], corner_radius=BUTTON_CORNER_RADIUS)
        self.tabs_bar.pack(side="left")

        self.tab_buttons = {}
        tab_defs = [
            ("calendar", "📅 Calendar"),
            ("tasks", "✓ Tasks"),
            ("focus", "⏱️ Focus"),
            ("analytics", "📊 Analytics"),
            ("exams", "📚 Exams"),
            ("routines", "🔁 Routines"),
        ]

        for tab_id, tab_label in tab_defs:
            btn = ctk.CTkButton(
                self.tabs_bar,
                text=tab_label,
                font=FONTS["small_bold"],
                height=30,
                width=86,
                fg_color=COLORS["accent"] if tab_id == "calendar" else "transparent",
                hover_color=COLORS["border"],
                text_color=COLORS["bg_primary"] if tab_id == "calendar" else COLORS["text_secondary"],
                corner_radius=BUTTON_CORNER_RADIUS,
                command=lambda t=tab_id: self.switch_tab(t)
            )
            btn.pack(side="left", padx=2, pady=2)
            self.tab_buttons[tab_id] = btn

        # Right: Contextual Controls Area
        self.right_top = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        self.right_top.pack(side="right", padx=14, pady=8)

        # Calendar Date Nav Box (Visible on Calendar & Tasks)
        self.date_nav_box = ctk.CTkFrame(self.right_top, fg_color="transparent")
        self.date_nav_box.pack(side="left", padx=(0, 8))

        btn_today = ctk.CTkButton(
            self.date_nav_box, text="Today", font=FONTS["small_bold"], width=56, height=30,
            fg_color=COLORS["bg_tertiary"], hover_color=COLORS["border"],
            text_color=COLORS["text_primary"], corner_radius=BUTTON_CORNER_RADIUS,
            command=self._go_today
        )
        btn_today.pack(side="left", padx=(0, 4))

        btn_prev = ctk.CTkButton(
            self.date_nav_box, text="<", width=28, height=30, font=FONTS["body_bold"],
            fg_color="transparent", hover_color=COLORS["bg_tertiary"],
            text_color=COLORS["text_secondary"], command=lambda: self._navigate(-1)
        )
        btn_prev.pack(side="left", padx=1)

        btn_next = ctk.CTkButton(
            self.date_nav_box, text=">", width=28, height=30, font=FONTS["body_bold"],
            fg_color="transparent", hover_color=COLORS["bg_tertiary"],
            text_color=COLORS["text_secondary"], command=lambda: self._navigate(1)
        )
        btn_next.pack(side="left", padx=(1, 10))

        self.lbl_title_range = ctk.CTkLabel(self.date_nav_box, text="", font=FONTS["small_bold"], text_color=COLORS["text_primary"])
        self.lbl_title_range.pack(side="left", padx=(0, 8))

        # Day / Week toggle (Visible on Calendar only)
        self.mode_frame = ctk.CTkFrame(self.right_top, fg_color=COLORS["bg_tertiary"], corner_radius=BUTTON_CORNER_RADIUS)
        self.mode_frame.pack(side="left", padx=(0, 8))

        self.btn_day_mode = ctk.CTkButton(
            self.mode_frame, text="Day", width=42, height=26, font=FONTS["small_bold"],
            fg_color="transparent", text_color=COLORS["text_secondary"], corner_radius=BUTTON_CORNER_RADIUS,
            command=lambda: self._set_mode("day")
        )
        self.btn_day_mode.pack(side="left", padx=2, pady=2)

        self.btn_week_mode = ctk.CTkButton(
            self.mode_frame, text="Week", width=46, height=26, font=FONTS["small_bold"],
            fg_color=COLORS["accent"], text_color=COLORS["bg_primary"], corner_radius=BUTTON_CORNER_RADIUS,
            command=lambda: self._set_mode("week")
        )
        self.btn_week_mode.pack(side="left", padx=2, pady=2)

        # Quick-Add ⚡ Button
        btn_quick = ctk.CTkButton(
            self.right_top, text="⚡ Quick", font=FONTS["small_bold"], width=72, height=32,
            fg_color=COLORS["bg_tertiary"], hover_color=COLORS["border"],
            text_color=COLORS["accent"], corner_radius=BUTTON_CORNER_RADIUS,
            command=self._open_quick_add
        )
        btn_quick.pack(side="left", padx=(0, 8))

        # + Event Button
        self.btn_create_event = ctk.CTkButton(
            self.right_top, text="+ Event", font=FONTS["body_bold"], width=80, height=32,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            text_color=COLORS["bg_primary"], corner_radius=BUTTON_CORNER_RADIUS,
            command=lambda: self._open_add_event()
        )
        self.btn_create_event.pack(side="left")

        # 2. Main Tab Container (Holds the 6 Views)
        self.tab_container = ctk.CTkFrame(self, fg_color="transparent")
        self.tab_container.pack(fill="both", expand=True)

        # Build View 1: Calendar View (Sidebar + TimeGrid)
        self.view_calendar = ctk.CTkFrame(self.tab_container, fg_color="transparent")
        self._build_calendar_view()

        # Build View 2: Tasks View (Full-Width ChecklistPanel)
        self.view_tasks = ChecklistPanel(
            self.tab_container,
            db=self.db,
            on_stats_change=self._on_checklist_stats_changed,
            undo_mgr=self.undo_mgr,
            is_full_tab=True
        )

        # Build View 3: Focus Room (Embedded PomodoroView)
        self.view_focus = PomodoroView(
            self.tab_container,
            db=self.db,
            notifier=self.notifier
        )

        # Build View 4: Analytics View (Embedded AnalyticsView)
        self.view_analytics = AnalyticsView(
            self.tab_container,
            db=self.db
        )

        # Build View 5: Exams & Deadlines (Embedded ExamCountdownView)
        self.view_exams = ExamCountdownView(
            self.tab_container,
            db=self.db,
            on_schedule_revision=self.refresh
        )

        # Build View 6: Routines & Templates (Embedded RoutinesTemplatesView)
        self.view_routines = RoutinesTemplatesView(
            self.tab_container,
            db=self.db,
            on_change_callback=self.refresh
        )

        # Initial Tab: Calendar
        self.view_calendar.pack(fill="both", expand=True)

    def _build_calendar_view(self):
        # Left Sidebar
        self.sidebar = ctk.CTkFrame(self.view_calendar, width=225, fg_color=COLORS["bg_secondary"], corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Mini Calendar in Sidebar
        self.mini_calendar = MiniCalendar(
            self.sidebar,
            on_date_selected=self._on_mini_calendar_date,
            current_date=self.current_date,
            db=self.db
        )
        self.mini_calendar.pack(fill="x", padx=10, pady=(12, 8))

        # Study Streak Pill in Sidebar
        self.streak_banner = ctk.CTkFrame(self.sidebar, fg_color=COLORS["bg_tertiary"], corner_radius=6, height=28)
        self.streak_banner.pack(fill="x", padx=10, pady=(0, 8))
        self.streak_banner.pack_propagate(False)

        self.lbl_streak_pill = ctk.CTkLabel(
            self.streak_banner, text="🔥 0 Day Streak", font=FONTS["micro"],
            text_color=COLORS["accent_orange"]
        )
        self.lbl_streak_pill.pack(expand=True)

        sep = ctk.CTkFrame(self.sidebar, height=1, fg_color=COLORS["border"])
        sep.pack(fill="x", padx=14, pady=4)

        # Categories list
        lbl_cats = ctk.CTkLabel(self.sidebar, text="MY CALENDARS", font=FONTS["micro"], text_color=COLORS["text_muted"])
        lbl_cats.pack(anchor="w", padx=16, pady=(4, 2))

        self.categories_scroll = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent", height=160)
        self.categories_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        btn_add_cat = ctk.CTkButton(
            self.sidebar, text="+ Add Category", font=FONTS["small"],
            fg_color="transparent", hover_color=COLORS["bg_tertiary"],
            text_color=COLORS["accent"], anchor="w", command=self._add_category
        )
        btn_add_cat.pack(fill="x", padx=14, pady=(0, 10))

        # Center Time Grid
        self.time_grid = TimeGrid(
            self.view_calendar,
            on_event_clicked=self._on_event_clicked,
            on_slot_clicked=self._on_slot_clicked,
            on_event_moved=self._on_event_moved
        )
        self.time_grid.pack(side="left", fill="both", expand=True)

    def switch_tab(self, tab_id: str):
        if self.active_tab == tab_id:
            return

        # Update tab buttons
        for t_id, btn in self.tab_buttons.items():
            if t_id == tab_id:
                btn.configure(fg_color=COLORS["accent"], text_color=COLORS["bg_primary"])
            else:
                btn.configure(fg_color="transparent", text_color=COLORS["text_secondary"])

        # Hide current view
        view_map = {
            "calendar": self.view_calendar,
            "tasks": self.view_tasks,
            "focus": self.view_focus,
            "analytics": self.view_analytics,
            "exams": self.view_exams,
            "routines": self.view_routines
        }
        current_view = view_map.get(self.active_tab)
        if current_view:
            current_view.pack_forget()

        # Show new view
        self.active_tab = tab_id
        new_view = view_map.get(tab_id)
        if new_view:
            new_view.pack(fill="both", expand=True)

        # Context-aware top bar updates
        if tab_id == "calendar":
            self.date_nav_box.pack(side="left", padx=(0, 8))
            self.mode_frame.pack(side="left", padx=(0, 8))
            self.btn_create_event.configure(text="+ Event")
            self._load_and_display_events()
        elif tab_id == "tasks":
            self.date_nav_box.pack(side="left", padx=(0, 8))
            self.mode_frame.pack_forget()
            self.btn_create_event.configure(text="+ Event")
            self.view_tasks.load_date(self.current_date.strftime("%Y-%m-%d"))
        else:
            self.date_nav_box.pack_forget()
            self.mode_frame.pack_forget()

        if tab_id == "analytics":
            self.view_analytics.refresh()
        elif tab_id == "exams":
            self.view_exams.refresh()
        elif tab_id == "routines":
            self.view_routines.refresh()

    def _setup_shortcuts(self):
        actions = {
            "<Key-1>": lambda: self.switch_tab("calendar"),
            "<Key-2>": lambda: self.switch_tab("tasks"),
            "<Key-3>": lambda: self.switch_tab("focus"),
            "<Key-4>": lambda: self.switch_tab("analytics"),
            "<Key-5>": lambda: self.switch_tab("exams"),
            "<Key-6>": lambda: self.switch_tab("routines"),
            "<Key-n>": self._open_add_event,
            "<Key-t>": self._go_today,
            "<Key-d>": lambda: self._set_mode("day"),
            "<Key-w>": lambda: self._set_mode("week"),
            "<Control-z>": self._undo,
            "<Control-y>": self._redo,
        }
        bind_window_shortcuts(self, actions)

    def show(self):
        self.attributes('-alpha', 0.0)
        self.deiconify()
        self.lift()
        self.focus_force()
        self.refresh()
        fade_window(self, target_alpha=1.0, duration_ms=200)
        if not self._initial_scroll_done:
            self.after(250, lambda: self.time_grid.scroll_to_hour(max(0, datetime.now().hour - 1)))
            self._initial_scroll_done = True

    def hide(self):
        self.withdraw()

    def _on_close(self):
        self.hide()

    def _go_today(self):
        self.current_date = datetime.now().date()
        self.refresh()
        if self.active_tab == "calendar":
            self.time_grid.scroll_to_hour(max(0, datetime.now().hour - 1))

    def _navigate(self, delta):
        if self.active_tab == "calendar" and self.view_mode == "week":
            self.current_date += timedelta(days=7 * delta)
        else:
            self.current_date += timedelta(days=delta)
        self.refresh()

    def _set_mode(self, mode):
        self.view_mode = mode
        if mode == "day":
            self.btn_day_mode.configure(fg_color=COLORS["accent"], text_color=COLORS["bg_primary"])
            self.btn_week_mode.configure(fg_color="transparent", text_color=COLORS["text_secondary"])
        else:
            self.btn_week_mode.configure(fg_color=COLORS["accent"], text_color=COLORS["bg_primary"])
            self.btn_day_mode.configure(fg_color="transparent", text_color=COLORS["text_secondary"])
        self.refresh()

    def _on_mini_calendar_date(self, selected_date):
        self.current_date = selected_date
        self.refresh()

    def _build_categories(self):
        for w in self.categories_scroll.winfo_children():
            w.destroy()

        categories = self.db.get_all_categories()
        for cat in categories:
            name = cat["name"]
            if name not in self.category_vars:
                self.category_vars[name] = tk.BooleanVar(value=True)
            var = self.category_vars[name]

            cb = ctk.CTkCheckBox(
                self.categories_scroll, text=name, variable=var,
                command=self._apply_filter,
                fg_color=cat.get("color", COLORS["accent"]),
                hover_color=cat.get("color", COLORS["accent"]),
                font=FONTS["small"]
            )
            cb.pack(pady=2, padx=4, anchor="w")

    def _apply_filter(self):
        self._load_and_display_events()

    def refresh(self):
        self._build_categories()
        self.mini_calendar.set_date(self.current_date)

        streak = self.db.get_study_streak()
        cur_strk = streak.get("current", 0)
        self.lbl_streak_pill.configure(text=f"🔥 {cur_strk} Day Study Streak")

        # Update Top Date Title
        if self.view_mode == "day" or self.active_tab == "tasks":
            title_str = self.current_date.strftime("%A, %B %d, %Y")
        else:
            start_of_week = self.current_date - timedelta(days=self.current_date.weekday())
            end_of_week = start_of_week + timedelta(days=6)
            if start_of_week.month == end_of_week.month:
                title_str = f"{start_of_week.strftime('%B %d')} - {end_of_week.strftime('%d, %Y')}"
            else:
                title_str = f"{start_of_week.strftime('%b %d')} - {end_of_week.strftime('%b %d, %Y')}"

        self.lbl_title_range.configure(text=title_str)

        if self.active_tab == "calendar":
            self._load_and_display_events()
        elif self.active_tab == "tasks":
            self.view_tasks.load_date(self.current_date.strftime("%Y-%m-%d"))

    def _load_and_display_events(self):
        active_cats = [name for name, var in self.category_vars.items() if var.get()]
        events_by_date = {}

        if self.view_mode == "day":
            d_str = self.current_date.strftime("%Y-%m-%d")
            all_evs = self.db.get_events_for_date(d_str, include_routines=True)
            events_by_date[d_str] = [
                e for e in all_evs
                if (e.get("category") in active_cats or not self.category_vars)
                and (not self.search_query or self.search_query in e.get("title", "").lower() or self.search_query in e.get("description", "").lower())
            ]
        else:
            start_of_week = self.current_date - timedelta(days=self.current_date.weekday())
            start_str = start_of_week.strftime("%Y-%m-%d")
            week_dict = self.db.get_events_for_week(start_str, include_routines=True)
            for d_str, ev_list in week_dict.items():
                events_by_date[d_str] = [
                    e for e in ev_list
                    if (e.get("category") in active_cats or not self.category_vars)
                    and (not self.search_query or self.search_query in e.get("title", "").lower() or self.search_query in e.get("description", "").lower())
                ]

        self.time_grid.set_data(self.view_mode, self.current_date, events_by_date)

    def _on_checklist_stats_changed(self, completed: int, total: int):
        """0ms lightweight notification to desktop widget without redrawing calendar."""
        if self.on_checklist_stats_change:
            self.on_checklist_stats_change(completed, total)

    def _undo(self):
        msg = self.undo_mgr.undo()
        if msg:
            self.refresh()
            if self.refresh_callback:
                self.refresh_callback()

    def _redo(self):
        msg = self.undo_mgr.redo()
        if msg:
            self.refresh()
            if self.refresh_callback:
                self.refresh_callback()

    def _on_event_clicked(self, event):
        if event.get("is_routine"):
            self.switch_tab("routines")
        else:
            self._open_edit_event(event)

    def _on_slot_clicked(self, date_str, start_time_str):
        self._open_add_event(default_date=date_str, default_time=start_time_str)

    def _on_event_moved(self, event, new_date, new_start, new_end):
        ev_id = event.get("id")
        if not ev_id or event.get("is_routine"):
            return
        old_data = self.db.get_event(ev_id)
        try:
            self.db.update_event(ev_id, date=new_date, start_time=new_start, end_time=new_end)
            new_data = self.db.get_event(ev_id)
            if self.undo_mgr:
                self.undo_mgr.record("move", "event", ev_id, old_data, new_data)
            self.refresh()
            if self.refresh_callback:
                self.refresh_callback()
        except Exception as e:
            import logging
            logging.error(f"Failed to move event: {e}")

    def _open_add_event(self, default_date=None, default_time=None):
        from ui.event_dialog import EventDialog
        target_d = default_date or self.current_date.strftime("%Y-%m-%d")
        dlg = EventDialog(
            self.master, self.db,
            on_save_callback=self._on_event_saved,
            default_date=target_d, default_time=default_time
        )
        try:
            dlg.attributes('-alpha', 0.0)
            dlg.after(50, lambda: fade_window(dlg, 1.0, 200))
        except Exception:
            pass

    def _open_edit_event(self, event):
        from ui.event_dialog import EventDialog
        dlg = EventDialog(self.master, self.db, event=event, on_save_callback=self._on_event_saved)
        try:
            dlg.attributes('-alpha', 0.0)
            dlg.after(50, lambda: fade_window(dlg, 1.0, 200))
        except Exception:
            pass

    def _open_quick_add(self):
        QuickAddDialog(self, self.db, on_created_callback=self._on_event_saved, undo_mgr=self.undo_mgr)

    def _on_event_saved(self):
        self.refresh()
        if self.refresh_callback:
            self.refresh_callback()

    def _add_category(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Add Category")
        dialog.geometry("300x200")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLORS["bg_primary"])
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Category Name", font=FONTS["body_bold"], text_color=COLORS["text_primary"]).pack(padx=20, pady=(15, 5), anchor="w")
        ent_name = ctk.CTkEntry(dialog, font=FONTS["body"], fg_color=COLORS["bg_tertiary"], border_color=COLORS["border"], text_color=COLORS["text_primary"])
        ent_name.pack(fill="x", padx=20)

        color_var = {"value": "#58a6ff"}
        ctk.CTkLabel(dialog, text="Color", font=FONTS["body_bold"], text_color=COLORS["text_primary"]).pack(padx=20, pady=(10, 5), anchor="w")
        color_row = ctk.CTkFrame(dialog, fg_color="transparent")
        color_row.pack(fill="x", padx=20)
        palette = ["#58a6ff", "#3fb950", "#f85149", "#bc8cff", "#f0883e", "#d29922"]
        c_btns = []
        for c in palette:
            b = ctk.CTkButton(color_row, text="", width=28, height=28, fg_color=c, hover_color=c,
                              corner_radius=14, border_width=2, border_color=COLORS["bg_primary"],
                              command=lambda col=c: _pick(col))
            b.pack(side="left", padx=2)
            c_btns.append(b)

        def _pick(col):
            color_var["value"] = col
            for b in c_btns:
                b.configure(border_color=COLORS["text_primary"] if b.cget("fg_color") == col else COLORS["bg_primary"])

        _pick("#58a6ff")

        def _save():
            name = ent_name.get().strip()
            if name:
                self.db.add_category(name, color_var["value"])
                dialog.destroy()
                self.refresh()
                if self.refresh_callback:
                    self.refresh_callback()

        ctk.CTkButton(dialog, text="Add ✓", font=FONTS["body_bold"], fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"], command=_save).pack(fill="x", padx=20, pady=15)
