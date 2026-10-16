"""Unified Tabbed Main Window for Timography — Calendar, Tasks, Focus, Analytics, Exams & Routines."""
from datetime import datetime, timedelta
import tkinter as tk
import customtkinter as ctk
from ui.controls import AppButton, AppToplevel
from ui.scrolling import ScrollableFrame

from config import APP_VERSION
from ui.theme import theme_color
from ui.theme import COLORS, FONTS, BUTTON_CORNER_RADIUS, SIZES
from ui.mini_calendar import MiniCalendar
from ui.time_grid import TimeGrid
from ui.checklist_panel import ChecklistPanel
from ui.pomodoro import PomodoroView
from ui.analytics_dashboard import AnalyticsView
from ui.exam_countdown import ExamCountdownView
from ui.routines_dialog import RoutinesTemplatesView
from ui.quick_add import QuickAddDialog
from core.undo_manager import UndoManager
from core.hotkeys import bind_window_shortcuts
from ui.settings_dialog import SettingsDialog
from ui.theme import apply_theme
from ui.layout import fit_window
from ui.today_view import TodayView


class MainWindow(AppToplevel):
    def __init__(self, master, db, refresh_callback=None, on_checklist_stats_change=None,
                 undo_mgr: UndoManager = None, notifier=None, settings_callback=None,
                 restore_callback=None):
        super().__init__(master)
        self.db = db
        self.refresh_callback = refresh_callback
        self.on_checklist_stats_change = on_checklist_stats_change
        self.undo_mgr = undo_mgr or UndoManager(db)
        self.notifier = notifier
        self.settings_callback = settings_callback
        self.restore_callback = restore_callback

        self.title(f"Timography v{APP_VERSION}")
        fit_window(self, SIZES['window_width'], SIZES['window_height'],
                   SIZES['window_min_w'], SIZES['window_min_h'])
        self.configure(fg_color=theme_color("bg_primary"))
        self.withdraw()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.current_date = datetime.now().date()
        self.view_mode = "week"
        self.active_tab = "today"
        self.category_vars = {}
        self.search_query = ""
        self._search_after_id = None
        self._status_after_id = None
        self._closing = False
        self._initial_scroll_done = False

        self._build_ui()
        self._setup_shortcuts()
        self.refresh()

    def _build_ui(self):
        # 1. Top Navigation Bar with Embedded Tabs
        self.top_bar = ctk.CTkFrame(self, height=SIZES['top_bar_height'], fg_color=theme_color("bg_secondary"), corner_radius=0)
        self.top_bar.pack(fill="x", side="top")
        self.top_bar.pack_propagate(False)

        # Left: Branding + Tabs Selector
        left_top = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        left_top.pack(side="left", padx=14, pady=8)

        self.lbl_app = ctk.CTkLabel(left_top, text="Timography", font=FONTS["heading"], text_color=theme_color("accent"))
        self.lbl_app.pack(side="left", padx=(0, 12))

        # Main Segmented Tabs Bar
        self.tabs_bar = ctk.CTkFrame(left_top, fg_color=theme_color("bg_tertiary"), corner_radius=BUTTON_CORNER_RADIUS)
        self.tabs_bar.pack(side="left")

        self.tab_buttons = {}
        tab_defs = [
            ("today", "Today"),
            ("calendar", "Calendar"),
            ("tasks", "Tasks"),
            ("focus", "Focus"),
            ("analytics", "Insights"),
            ("exams", "Exams"),
            ("routines", "Routines"),
        ]

        for tab_id, tab_label in tab_defs:
            btn = AppButton(
                self.tabs_bar,
                text=tab_label,
                font=FONTS["body_bold"],
                height=SIZES['tab_btn_height'],
                width=76,
                fg_color=theme_color("accent") if tab_id == self.active_tab else "transparent",
                hover_color=theme_color("border"),
                text_color=theme_color("on_accent") if tab_id == self.active_tab else theme_color("text_secondary"),
                corner_radius=BUTTON_CORNER_RADIUS,
                command=lambda t=tab_id: self.switch_tab(t)
            )
            btn.pack(side="left", padx=2, pady=2)
            self.tab_buttons[tab_id] = btn

        # Right: Contextual Controls Area
        self.right_top = ctk.CTkFrame(self, fg_color=theme_color("bg_secondary"), corner_radius=0)
        self.right_top.pack(fill="x", padx=0, pady=0)

        # Calendar Date Nav Box (Visible on Calendar & Tasks)
        self.date_nav_box = ctk.CTkFrame(self.right_top, fg_color="transparent")
        self.date_nav_box.pack(side="left", padx=(14, 8), pady=8)

        self.btn_today = AppButton(
            self.date_nav_box, text="Today", font=FONTS["body_bold"], width=SIZES['today_btn_width'], height=SIZES['nav_btn_size'],
            fg_color=theme_color("bg_tertiary"), hover_color=theme_color("border"),
            text_color=theme_color("text_primary"), corner_radius=BUTTON_CORNER_RADIUS,
            command=self._go_today
        )
        self.btn_today.pack(side="left", padx=(0, 4))

        self.btn_prev = AppButton(
            self.date_nav_box, text="<", width=SIZES['nav_btn_size'], height=SIZES['nav_btn_size'], font=FONTS["body_bold"],
            fg_color="transparent", hover_color=theme_color("bg_tertiary"),
            text_color=theme_color("text_secondary"), command=lambda: self._navigate(-1)
        )
        self.btn_prev.pack(side="left", padx=1)

        self.btn_next = AppButton(
            self.date_nav_box, text=">", width=SIZES['nav_btn_size'], height=SIZES['nav_btn_size'], font=FONTS["body_bold"],
            fg_color="transparent", hover_color=theme_color("bg_tertiary"),
            text_color=theme_color("text_secondary"), command=lambda: self._navigate(1)
        )
        self.btn_next.pack(side="left", padx=(1, 10))

        # Date range label
        self.lbl_date_range = ctk.CTkLabel(self.date_nav_box, text="", font=FONTS["body_bold"], text_color=theme_color("text_primary"))
        self.lbl_date_range.pack(side="left", padx=(0, 8))
        self.lbl_title_range = self.lbl_date_range

        # Day / Week Segmented Mode Toggle
        self.mode_frame = ctk.CTkFrame(self.right_top, fg_color=theme_color("bg_tertiary"), corner_radius=BUTTON_CORNER_RADIUS)
        self.mode_frame.pack(side="left", padx=(0, 8), pady=8)

        self.btn_day_mode = AppButton(
            self.mode_frame, text="Day", width=SIZES['mode_btn_width'], height=SIZES['mode_btn_height'], font=FONTS["small_bold"],
            fg_color="transparent", text_color=theme_color("text_secondary"), corner_radius=BUTTON_CORNER_RADIUS,
            command=lambda: self._set_mode("day")
        )
        self.btn_day_mode.pack(side="left", padx=2, pady=2)

        self.btn_week_mode = AppButton(
            self.mode_frame, text="Week", width=SIZES['mode_btn_width'], height=SIZES['mode_btn_height'], font=FONTS["small_bold"],
            fg_color=theme_color("accent"), text_color=theme_color("on_accent"), corner_radius=BUTTON_CORNER_RADIUS,
            command=lambda: self._set_mode("week")
        )
        self.btn_week_mode.pack(side="left", padx=2, pady=2)

        # Quick-Add ⚡ Button
        self.btn_quick = AppButton(
            self.right_top, text="Quick add", font=FONTS["small_bold"], width=82, height=SIZES['nav_btn_size'],
            fg_color=theme_color("bg_tertiary"), hover_color=theme_color("border"),
            text_color=theme_color("accent"), corner_radius=BUTTON_CORNER_RADIUS,
            command=self._open_quick_add
        )
        self.btn_quick.pack(side="right", padx=(8, 14), pady=8)

        # + Event Button
        self.btn_create_event = AppButton(
            self.right_top, text="+ Event", font=FONTS["body_bold"], width=SIZES['create_btn_width'], height=SIZES['nav_btn_size'],
            fg_color=theme_color("accent"), hover_color=theme_color("accent_hover"),
            text_color=theme_color("on_accent"), corner_radius=BUTTON_CORNER_RADIUS,
            command=lambda: self._open_add_event()
        )
        self.btn_create_event.pack(side="right", pady=8)

        # ⚙️ Settings Button
        self.btn_settings = AppButton(
            self.top_bar, text="Settings", font=FONTS["small"], width=64, height=SIZES['nav_btn_size'],
            fg_color="transparent", hover_color=theme_color("bg_tertiary"),
            text_color=theme_color("text_secondary"), corner_radius=BUTTON_CORNER_RADIUS,
            command=self._open_settings
        )
        self.btn_settings.pack(side="right", padx=14, pady=8)

        self.status_bar = ctk.CTkFrame(self, fg_color=theme_color("bg_secondary"), corner_radius=0, height=26)
        self.status_bar.pack(side="bottom", fill="x")
        self.status_label = ctk.CTkLabel(self.status_bar, text="Ready", font=FONTS["micro"],
                                       text_color=theme_color("text_secondary"), anchor="w", height=24)
        self.status_label.pack(fill="x", padx=16)

        # Main view container.
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

        self.view_today = TodayView(
            self.tab_container, self.db, self.undo_mgr,
            on_event=self._on_event_clicked,
            on_add_event=lambda: self._open_add_event(default_date=datetime.now().date().isoformat()),
            on_calendar=lambda: self._open_today_tab("calendar"),
            on_tasks=lambda: self._open_today_tab("tasks"),
            on_focus=self._start_focus_for_event,
            on_change=self._on_event_saved,
        )
        self.date_nav_box.pack_forget()
        self.mode_frame.pack_forget()
        self.view_today.pack(fill="both", expand=True)

    def _build_calendar_view(self):
        # Left Sidebar
        self.sidebar = ctk.CTkFrame(self.view_calendar, width=SIZES['sidebar_width'], fg_color=theme_color("bg_secondary"), corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.btn_add_cat = AppButton(
            self.sidebar, text="+ Add Category", font=FONTS["small"],
            fg_color="transparent", hover_color=theme_color("bg_tertiary"),
            text_color=theme_color("accent"), anchor="w", command=self._add_category
        )
        self.btn_add_cat.pack(side="bottom", fill="x", padx=14, pady=(0, 10))

        # Mini Calendar in Sidebar
        self.mini_calendar = MiniCalendar(
            self.sidebar,
            on_date_selected=self._on_mini_calendar_date,
            current_date=self.current_date,
            db=self.db
        )
        self.mini_calendar.pack(fill="x", padx=10, pady=(12, 8))

        # Study Streak Banner with progress
        self.streak_banner = ctk.CTkFrame(self.sidebar, fg_color=theme_color("bg_tertiary"), corner_radius=6)
        self.streak_banner.pack(fill="x", padx=10, pady=(0, 8))

        streak_top = ctk.CTkFrame(self.streak_banner, fg_color="transparent")
        streak_top.pack(fill="x", padx=8, pady=(6, 2))

        self.lbl_streak_pill = ctk.CTkLabel(
            streak_top, text="🔥 0 Day Streak", font=FONTS["micro"],
            text_color=theme_color("accent_orange")
        )
        self.lbl_streak_pill.pack(side="left")

        self.lbl_streak_progress = ctk.CTkLabel(
            streak_top, text="0/30 min", font=FONTS["micro"],
            text_color=theme_color("text_muted")
        )
        self.lbl_streak_progress.pack(side="right")

        self.streak_progress_bar = ctk.CTkProgressBar(
            self.streak_banner, height=4, corner_radius=2,
            fg_color=theme_color("bg_secondary"), progress_color=theme_color("accent_orange")
        )
        self.streak_progress_bar.pack(fill="x", padx=8, pady=(0, 6))
        self.streak_progress_bar.set(0)

        self.sidebar_sep = ctk.CTkFrame(self.sidebar, height=1, fg_color=theme_color("border"))
        self.sidebar_sep.pack(fill="x", padx=14, pady=4)
        self.search_entry = ctk.CTkEntry(self.sidebar, placeholder_text="Search events (Ctrl+F)",
            font=FONTS["small"], fg_color=theme_color("bg_tertiary"),
            border_color=theme_color("border"), text_color=theme_color("text_primary"))
        self.search_entry.pack(fill="x", padx=14, pady=(4, 6))
        self.search_entry.bind("<KeyRelease>", self._search_changed)

        # Categories list
        self.lbl_cats = ctk.CTkLabel(self.sidebar, text="MY CALENDARS", font=FONTS["micro"], text_color=theme_color("text_muted"))
        self.lbl_cats.pack(anchor="w", padx=16, pady=(4, 2))

        self.categories_scroll = ScrollableFrame(self.sidebar, fg_color="transparent", height=160)
        self.categories_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        # Center Time Grid
        self.time_grid = TimeGrid(
            self.view_calendar,
            on_event_clicked=self._on_event_clicked,
            on_slot_clicked=self._on_slot_clicked,
            on_event_moved=self._on_event_moved
        )
        self.time_grid.pack(side="left", fill="both", expand=True)

    def switch_tab(self, tab_id: str):
        if self.active_tab == tab_id or tab_id not in self.tab_buttons:
            return

        # Update tab buttons
        for t_id in (self.active_tab, tab_id):
            btn = self.tab_buttons[t_id]
            if t_id == tab_id:
                btn.configure(fg_color=theme_color("accent"), text_color=theme_color("on_accent"))
            else:
                btn.configure(fg_color="transparent", text_color=theme_color("text_secondary"))

        # Hide current view
        view_map = {
            "today": self.view_today,
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
            self.date_nav_box.pack(side="left", padx=(14, 8), pady=8)
            self.mode_frame.pack(side="left", padx=(0, 8), pady=8)
            self.btn_create_event.configure(text="+ Event")
        elif tab_id == "tasks":
            self.date_nav_box.pack(side="left", padx=(14, 8), pady=8)
            self.mode_frame.pack_forget()
            self.btn_create_event.configure(text="+ Event")
        else:
            self.date_nav_box.pack_forget()
            self.mode_frame.pack_forget()

        self.refresh()
        if tab_id == "calendar" and not self._initial_scroll_done:
            self.after_idle(self._scroll_calendar_today)

    def _setup_shortcuts(self):
        actions = {
            "<Key-1>": lambda: self.switch_tab("calendar"),
            "<Key-2>": lambda: self.switch_tab("tasks"),
            "<Key-3>": lambda: self.switch_tab("focus"),
            "<Key-4>": lambda: self.switch_tab("analytics"),
            "<Key-5>": lambda: self.switch_tab("exams"),
            "<Key-6>": lambda: self.switch_tab("routines"),
            "<Key-7>": lambda: self.switch_tab("today"),
            "<Key-n>": self._open_add_event,
            "<Key-t>": self._go_today,
            "<Key-d>": lambda: self._set_mode("day"),
            "<Key-w>": lambda: self._set_mode("week"),
            "<Control-z>": self._undo,
            "<Control-y>": self._redo,
            "<Control-f>": self._focus_search,
            "<Key-c>": lambda: self.switch_tab("tasks"),
            "<Key-p>": self._start_focus,
        }
        bind_window_shortcuts(self, actions)

    def show(self):
        self.attributes('-alpha', 1.0)
        self.deiconify()
        self.lift()
        self.focus_force()
        self.refresh()
        if self.active_tab == "calendar" and not self._initial_scroll_done:
            self.after_idle(self._scroll_calendar_today)

    def _scroll_calendar_today(self):
        if not self._closing:
            self.time_grid.scroll_to_hour(max(0, datetime.now().hour - 1), animate=False)
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

    def _open_today_tab(self, tab_id):
        self.current_date = datetime.now().date()
        if self.active_tab == tab_id:
            self.refresh()
        else:
            self.switch_tab(tab_id)

    def _navigate(self, delta):
        if self.active_tab == "calendar" and self.view_mode == "week":
            self.current_date += timedelta(days=7 * delta)
        else:
            self.current_date += timedelta(days=delta)
        self.refresh()

    def _set_mode(self, mode):
        self.view_mode = mode
        if mode == "day":
            self.btn_day_mode.configure(fg_color=theme_color("accent"), text_color=theme_color("on_accent"))
            self.btn_week_mode.configure(fg_color="transparent", text_color=theme_color("text_secondary"))
        else:
            self.btn_week_mode.configure(fg_color=theme_color("accent"), text_color=theme_color("on_accent"))
            self.btn_day_mode.configure(fg_color="transparent", text_color=theme_color("text_secondary"))
        self.refresh()

    def _on_mini_calendar_date(self, selected_date):
        self.current_date = selected_date
        self.refresh()

    def _build_categories(self):
        categories = self.db.get_all_categories()
        if categories == getattr(self, "_categories_snapshot", None):
            return
        self._categories_snapshot = categories
        for w in self.categories_scroll.winfo_children():
            w.destroy()

        names = {cat["name"] for cat in categories}
        self.category_vars = {name: var for name, var in self.category_vars.items() if name in names}
        for cat in categories:
            name = cat["name"]
            if name not in self.category_vars:
                self.category_vars[name] = tk.BooleanVar(value=True)
            var = self.category_vars[name]

            cb = ctk.CTkCheckBox(
                self.categories_scroll, text=name, variable=var,
                command=self._apply_filter,
                fg_color=cat.get("color", theme_color("accent")),
                hover_color=cat.get("color", theme_color("accent")),
                font=FONTS["small"]
            )
            cb.pack(pady=2, padx=4, anchor="w")

    def _apply_filter(self):
        self._load_and_display_events()

    def refresh(self):
        if self.active_tab not in ("calendar", "tasks"):
            view = getattr(self, f"view_{self.active_tab}")
            if hasattr(view, "refresh"):
                view.refresh()
            return
        if self.active_tab == "tasks":
            self.lbl_title_range.configure(text=self.current_date.strftime("%A, %B %d, %Y"))
            self.view_tasks.load_date(self.current_date.isoformat())
            return
        self._build_categories()
        self.mini_calendar.set_date(self.current_date)

        streak = self.db.get_study_streak()
        cur_strk = streak.get("current", 0)
        today_mins = streak.get("today_minutes", 0)
        goal_mins = streak.get("goal_minutes", 30)

        streak_text = f"{cur_strk} day focus streak" if cur_strk > 0 else "Daily focus goal"
        self.lbl_streak_pill.configure(text=streak_text)

        self.lbl_streak_progress.configure(text=f"{today_mins}/{goal_mins} min")
        progress = min(1.0, today_mins / max(1, goal_mins))
        self.streak_progress_bar.set(progress)
        # Color: gray when 0, yellow < 50%, green >= 100%
        if progress >= 1.0:
            self.streak_progress_bar.configure(progress_color=theme_color("accent_green"))
        elif progress >= 0.5:
            self.streak_progress_bar.configure(progress_color=theme_color("accent_yellow"))
        else:
            self.streak_progress_bar.configure(progress_color=theme_color("accent_orange"))

        # Update Top Date Title
        if self.view_mode == "day" or self.active_tab == "tasks":
            title_str = self.current_date.strftime("%A, %B %d, %Y")
        else:
            start_of_week = self._week_start()
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
            start_of_week = self._week_start()
            start_str = start_of_week.strftime("%Y-%m-%d")
            week_dict = self.db.get_events_for_week(start_str, include_routines=True)
            for d_str, ev_list in week_dict.items():
                events_by_date[d_str] = [
                    e for e in ev_list
                    if (e.get("category") in active_cats or not self.category_vars)
                    and (not self.search_query or self.search_query in e.get("title", "").lower() or self.search_query in e.get("description", "").lower())
                ]

        self.time_grid.week_start = self.db.get_setting("week_start", "monday")
        self.time_grid.set_data(self.view_mode, self.current_date, events_by_date)

    def _week_start(self):
        first = 6 if self.db.get_setting("week_start", "monday") == "sunday" else 0
        return self.current_date - timedelta(days=(self.current_date.weekday() - first) % 7)

    def _on_checklist_stats_changed(self, completed: int, total: int):
        """0ms lightweight notification to desktop widget without redrawing calendar."""
        if self.on_checklist_stats_change:
            today = datetime.now().date().isoformat()
            stats = self.db.get_checklist_stats(today)
            self.on_checklist_stats_change(stats["completed"], stats["total"])

    def _focus_search(self):
        self.switch_tab("calendar")
        self.search_entry.focus_set()

    def _search_changed(self, event=None):
        if self._search_after_id:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(150, self._run_search)

    def _run_search(self):
        self._search_after_id = None
        self.search_query = self.search_entry.get().strip().lower()
        self._load_and_display_events()

    def _start_focus(self):
        self.switch_tab("focus")
        if self.view_focus.engine.phase == self.view_focus.engine.PHASE_IDLE:
            self.view_focus._on_main_button_click()

    def _start_focus_for_event(self, event=None):
        self.switch_tab("focus")
        if hasattr(self.view_focus, "start_focus"):
            started = self.view_focus.start_focus(
                event["title"] if event else "Focus session",
                event.get("category", "Study") if event else "Study",
                event.get("id") if event and not event.get("is_routine") else None,
            )
            self.set_status("Focus session started." if started else "Continue your current focus session or reset it to start another.")
        elif self.view_focus.engine.phase == self.view_focus.engine.PHASE_IDLE:
            self.view_focus._on_main_button_click()

    def _undo(self):
        msg = self.undo_mgr.undo()
        if msg:
            self._on_event_saved()
            self.set_status(msg)
        else:
            self.set_status("No action available to undo.")

    def _redo(self):
        msg = self.undo_mgr.redo()
        if msg:
            self._on_event_saved()
            self.set_status(msg)
        else:
            self.set_status("No action available to redo.")

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
            if not self.db.update_event(ev_id, date=new_date, start_time=new_start, end_time=new_end):
                raise ValueError("The event could not be moved.")
            new_data = self.db.get_event(ev_id)
            if self.undo_mgr:
                self.undo_mgr.record("move", "event", ev_id, old_data, new_data)
            self._on_event_saved()
        except Exception as e:
            import logging
            logging.error(f"Failed to move event: {e}")
            self.set_status(str(e), error=True)

    def _open_add_event(self, default_date=None, default_time=None):
        from ui.event_dialog import EventDialog
        target_date = datetime.now().date() if self.active_tab == "today" else self.current_date
        target_d = default_date or target_date.isoformat()
        EventDialog(
            self, self.db,
            on_save_callback=self._on_event_saved,
            default_date=target_d, default_time=default_time, undo_mgr=self.undo_mgr
        )

    def _open_edit_event(self, event):
        from ui.event_dialog import EventDialog
        EventDialog(self, self.db, event=event, on_save_callback=self._on_event_saved, undo_mgr=self.undo_mgr)

    def _open_quick_add(self):
        QuickAddDialog(self, self.db, on_created_callback=self._on_event_saved, undo_mgr=self.undo_mgr)

    def _open_settings(self):
        SettingsDialog(
            self, self.db,
            on_save_callback=self._on_settings_saved,
            on_theme_change=self._on_theme_change,
            on_restore=self.restore_callback,
        )

    def set_status(self, message, error=False):
        """Brief feedback for completed actions and actionable adapter failures."""
        if self._closing:
            return
        if self._status_after_id:
            self.after_cancel(self._status_after_id)
            self._status_after_id = None
        self.status_label.configure(text=message,
                                    text_color=theme_color("accent_red" if error else "text_secondary"))
        if not error:
            self._status_after_id = self.after(6000, self._clear_status)

    def _clear_status(self):
        self._status_after_id = None
        self.status_label.configure(text="Ready", text_color=theme_color("text_secondary"))

    def _reapply_theme(self):
        """Re-skin all structural components to reflect the current theme."""
        self.configure(fg_color=theme_color("bg_primary"))
        if hasattr(self, "top_bar"):
            self.top_bar.configure(fg_color=theme_color("bg_secondary"))
        if hasattr(self, "tabs_bar"):
            self.tabs_bar.configure(fg_color=theme_color("bg_tertiary"))
        if hasattr(self, "lbl_app"):
            self.lbl_app.configure(text_color=theme_color("accent"))
        if hasattr(self, "lbl_date_range"):
            self.lbl_date_range.configure(text_color=theme_color("text_primary"))
        if hasattr(self, "btn_today"):
            self.btn_today.configure(fg_color=theme_color("bg_tertiary"), text_color=theme_color("text_primary"), hover_color=theme_color("border"))
        if hasattr(self, "btn_prev"):
            self.btn_prev.configure(hover_color=theme_color("bg_tertiary"), text_color=theme_color("text_secondary"))
        if hasattr(self, "btn_next"):
            self.btn_next.configure(hover_color=theme_color("bg_tertiary"), text_color=theme_color("text_secondary"))
        if hasattr(self, "mode_frame"):
            self.mode_frame.configure(fg_color=theme_color("bg_tertiary"))
        if hasattr(self, "btn_day_mode") and hasattr(self, "btn_week_mode"):
            if self.view_mode == "day":
                self.btn_day_mode.configure(fg_color=theme_color("accent"), text_color=theme_color("on_accent"))
                self.btn_week_mode.configure(fg_color="transparent", text_color=theme_color("text_secondary"))
            else:
                self.btn_week_mode.configure(fg_color=theme_color("accent"), text_color=theme_color("on_accent"))
                self.btn_day_mode.configure(fg_color="transparent", text_color=theme_color("text_secondary"))
        if hasattr(self, "btn_quick"):
            self.btn_quick.configure(fg_color=theme_color("bg_tertiary"), hover_color=theme_color("border"), text_color=theme_color("accent"))
        if hasattr(self, "btn_create_event"):
            self.btn_create_event.configure(fg_color=theme_color("accent"), hover_color=theme_color("accent_hover"), text_color=theme_color("on_accent"))
        if hasattr(self, "btn_settings"):
            self.btn_settings.configure(hover_color=theme_color("bg_tertiary"), text_color=theme_color("text_secondary"))

        # Update tab buttons
        if hasattr(self, "tab_buttons"):
            for t_id, btn in self.tab_buttons.items():
                if t_id == self.active_tab:
                    btn.configure(fg_color=theme_color("accent"), text_color=theme_color("on_accent"), hover_color=theme_color("accent_hover"))
                else:
                    btn.configure(fg_color="transparent", text_color=theme_color("text_secondary"), hover_color=theme_color("bg_tertiary"))

        # Sidebar and Calendar
        if hasattr(self, "sidebar"):
            self.sidebar.configure(fg_color=theme_color("bg_secondary"))
        if hasattr(self, "streak_banner"):
            self.streak_banner.configure(fg_color=theme_color("bg_tertiary"))
        if hasattr(self, "lbl_streak_pill"):
            self.lbl_streak_pill.configure(text_color=theme_color("accent_orange"))
        if hasattr(self, "lbl_streak_progress"):
            self.lbl_streak_progress.configure(text_color=theme_color("text_muted"))
        if hasattr(self, "streak_progress_bar"):
            self.streak_progress_bar.configure(fg_color=theme_color("bg_secondary"))
        if hasattr(self, "sidebar_sep"):
            self.sidebar_sep.configure(fg_color=theme_color("border"))
        if hasattr(self, "lbl_cats"):
            self.lbl_cats.configure(text_color=theme_color("text_muted"))
        if hasattr(self, "btn_add_cat"):
            self.btn_add_cat.configure(hover_color=theme_color("bg_tertiary"), text_color=theme_color("accent"))
        if hasattr(self, "mini_calendar"):
            self.mini_calendar.refresh()
        if hasattr(self, "time_grid"):
            self.time_grid.configure(fg_color=theme_color("bg_primary"))
            if hasattr(self.time_grid, "header_frame"):
                self.time_grid.header_frame.configure(fg_color=theme_color("bg_secondary"), height=SIZES['header_height'])
            if hasattr(self.time_grid, "body_frame"):
                self.time_grid.body_frame.configure(fg_color=theme_color("bg_primary"))
            if hasattr(self.time_grid, "canvas"):
                self.time_grid.canvas.configure(bg=COLORS["bg_primary"])
            self.time_grid.render()

        # Cascade theme update to all other tabs
        if hasattr(self, "view_tasks") and hasattr(self.view_tasks, "reapply_theme"):
            self.view_tasks.reapply_theme()
        if hasattr(self, "view_focus") and hasattr(self.view_focus, "reapply_theme"):
            self.view_focus.reapply_theme()
        if hasattr(self, "view_analytics") and hasattr(self.view_analytics, "reapply_theme"):
            self.view_analytics.reapply_theme()
        if hasattr(self, "view_exams") and hasattr(self.view_exams, "reapply_theme"):
            self.view_exams.reapply_theme()
        if hasattr(self, "view_routines") and hasattr(self.view_routines, "reapply_theme"):
            self.view_routines.reapply_theme()

        # Re-build category sidebar checkboxes
        self._build_categories()

        # Refresh active view
        self.refresh()

    def _on_theme_change(self, mode):
        """Live theme preview — rebuild UI with new colors."""
        if self._closing:
            return
        apply_theme(mode)
        self._reapply_theme()
        if self.refresh_callback:
            self.refresh_callback()

    def _on_settings_saved(self):
        """Called after settings dialog saves — refresh everything."""
        self.db.invalidate_streak_cache()
        self.mini_calendar.week_start = self.db.get_setting("week_start", "monday")
        self.view_focus.reload_settings()
        if self.settings_callback:
            self.settings_callback()
        self._reapply_theme()
        if self.refresh_callback:
            self.refresh_callback()

    def _on_event_saved(self):
        if self.refresh_callback:
            self.refresh_callback()
        else:
            self.refresh()

    def _add_category(self):
        dialog = AppToplevel(self)
        dialog.title("Add Category")
        dialog.geometry("320x260")
        dialog.resizable(False, False)
        dialog.configure(fg_color=theme_color("bg_primary"))
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="Category Name", font=FONTS["body_bold"], text_color=theme_color("text_primary")).pack(padx=20, pady=(15, 5), anchor="w")
        ent_name = ctk.CTkEntry(dialog, font=FONTS["body"], fg_color=theme_color("bg_tertiary"), border_color=theme_color("border"), text_color=theme_color("text_primary"))
        ent_name.pack(fill="x", padx=20)

        color_var = {"value": "#58a6ff"}
        ctk.CTkLabel(dialog, text="Color", font=FONTS["body_bold"], text_color=theme_color("text_primary")).pack(padx=20, pady=(10, 5), anchor="w")
        color_row = ctk.CTkFrame(dialog, fg_color="transparent")
        color_row.pack(fill="x", padx=20)
        palette = ["#58a6ff", "#3fb950", "#f85149", "#bc8cff", "#f0883e", "#d29922"]
        c_btns = []
        for c in palette:
            b = AppButton(color_row, text="", width=28, height=28, fg_color=c, hover_color=c,
                              corner_radius=14, border_width=2, border_color=theme_color("bg_primary"),
                              command=lambda col=c: _pick(col))
            b.pack(side="left", padx=2)
            c_btns.append(b)

        def _pick(col):
            color_var["value"] = col
            for b in c_btns:
                b.configure(border_color=theme_color("text_primary") if b.cget("fg_color") == col else theme_color("bg_primary"))

        _pick("#58a6ff")

        error_label = ctk.CTkLabel(dialog, text="", font=FONTS["small"], text_color=theme_color("accent_red"))
        error_label.pack(fill="x", padx=20, pady=(6, 0))

        def _save():
            name = ent_name.get().strip()
            if not name:
                error_label.configure(text="Enter a category name.")
                ent_name.focus_set()
                return
            if self.db.add_category(name, color_var["value"]) == -1:
                error_label.configure(text="Could not add category. Use a unique name.")
                return
            dialog.destroy()
            self._on_event_saved()

        AppButton(dialog, text="Add category", font=FONTS["body_bold"], fg_color=theme_color("accent"),
                      hover_color=theme_color("accent_hover"), text_color=theme_color("on_accent"),
                      command=_save).pack(fill="x", padx=20, pady=(6, 15))

    def destroy(self):
        self._closing = True
        if self._search_after_id:
            self.after_cancel(self._search_after_id)
        if self._status_after_id:
            self.after_cancel(self._status_after_id)
        super().destroy()
