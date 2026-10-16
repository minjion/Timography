"""Mini month calendar component for Google Calendar-style sidebar."""
import calendar
from datetime import datetime, timedelta
import customtkinter as ctk
from ui.controls import AppButton
from ui.theme import theme_color
from ui.theme import COLORS, FONTS, SIZES

class MiniCalendar(ctk.CTkFrame):
    def __init__(self, master, on_date_selected=None, current_date=None, db=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.on_date_selected = on_date_selected
        self.db = db
        self.week_start = db.get_setting("week_start", "monday") if db else "monday"

        now = datetime.now().date()
        self.selected_date = current_date.date() if isinstance(current_date, datetime) else (current_date or now)
        self.view_year = self.selected_date.year
        self.view_month = self.selected_date.month
        self.today = now

        self.day_buttons = []
        self._day_states = {}
        self._event_dates = set()  # dates that have events (for dot indicators)
        self._build_ui()
        self._load_event_dates()
        self.refresh()

    def _build_ui(self):
        # Header: Month Year and < > buttons
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=4, pady=(2, 6))

        self.lbl_month_year = ctk.CTkLabel(
            self.header_frame,
            text="",
            font=FONTS["body_bold"],
            text_color=theme_color("text_primary"),
            anchor="w"
        )
        self.lbl_month_year.pack(side="left", padx=4)

        btn_next = AppButton(
            self.header_frame,
            text=">",
            width=SIZES['mini_cal_nav_btn'],
            height=SIZES['mini_cal_nav_btn'],
            font=FONTS["small_bold"],
            fg_color="transparent",
            hover_color=theme_color("bg_tertiary"),
            text_color=theme_color("text_secondary"),
            command=self._next_month
        )
        btn_next.pack(side="right", padx=1)

        btn_prev = AppButton(
            self.header_frame,
            text="<",
            width=SIZES['mini_cal_nav_btn'],
            height=SIZES['mini_cal_nav_btn'],
            font=FONTS["small_bold"],
            fg_color="transparent",
            hover_color=theme_color("bg_tertiary"),
            text_color=theme_color("text_secondary"),
            command=self._prev_month
        )
        btn_prev.pack(side="right", padx=1)

        # Day of week labels (Mon -> Sun)
        self.dow_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.dow_frame.pack(fill="x", padx=2, pady=(0, 2))
        for i in range(7):
            self.dow_frame.columnconfigure(i, weight=1)

        days_names = ["M", "T", "W", "T", "F", "S", "S"]
        for i, name in enumerate(days_names):
            lbl = ctk.CTkLabel(
                self.dow_frame,
                text=name,
                font=FONTS["micro"],
                text_color=theme_color("text_muted"),
                width=1,
                height=SIZES['mini_cal_nav_btn']
            )
            lbl.grid(row=0, column=i, sticky="nsew", padx=1, pady=1)

        # Grid of days (6 rows x 7 cols)
        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_frame.pack(fill="x", padx=2, pady=0)
        for i in range(7):
            self.grid_frame.columnconfigure(i, weight=1, uniform="cal_col")

        for r in range(6):
            row_buttons = []
            for c in range(7):
                btn = AppButton(
                    self.grid_frame,
                    text="",
                    width=28,
                    height=28,
                    corner_radius=8,
                    font=("Segoe UI", 11),
                    fg_color="transparent",
                    text_color=theme_color("text_primary"),
                    hover_color=theme_color("bg_tertiary")
                )
                btn.grid(row=r, column=c, padx=1, pady=1, sticky="nsew")
                row_buttons.append(btn)
            self.day_buttons.append(row_buttons)

    def _prev_month(self):
        if self.view_month == 1:
            self.view_month = 12
            self.view_year -= 1
        else:
            self.view_month -= 1
        self.refresh()

    def _next_month(self):
        if self.view_month == 12:
            self.view_month = 1
            self.view_year += 1
        else:
            self.view_month += 1
        self.refresh()

    def set_date(self, target_date):
        if isinstance(target_date, datetime):
            target_date = target_date.date()
        self.selected_date = target_date
        self.view_year = target_date.year
        self.view_month = target_date.month
        self._load_event_dates()
        self.refresh()

    def _load_event_dates(self):
        """Load set of dates in current view month that have events."""
        self._event_dates.clear()
        if not self.db:
            return
        try:
            cal = calendar.Calendar(firstweekday=6 if self.week_start == "sunday" else 0)
            month_days = cal.monthdatescalendar(self.view_year, self.view_month)
            start = month_days[0][0]
            end = start + timedelta(days=41)
            events = self.db.get_events_for_range(start.isoformat(), end.isoformat(), False)
            self._event_dates = {datetime.strptime(day, "%Y-%m-%d").date()
                                 for day, items in events.items() if items}
        except Exception:
            pass

    def refresh(self):
        self.today = datetime.now().date()
        self._load_event_dates()
        key = (self.view_year, self.view_month, self.selected_date, self.week_start,
               self.today, frozenset(self._event_dates), tuple(COLORS.values()))
        if key == getattr(self, "_render_key", None):
            return
        self._render_key = key
        month_name = calendar.month_name[self.view_month]
        self.lbl_month_year.configure(text=f"{month_name} {self.view_year}")

        first = 6 if self.week_start == "sunday" else 0
        cal = calendar.Calendar(firstweekday=first)
        for idx, label in enumerate(self.dow_frame.winfo_children()):
            if isinstance(label, ctk.CTkLabel):
                label.configure(text=["M", "T", "W", "T", "F", "S", "S"][(first + idx) % 7])
        month_days = cal.monthdatescalendar(self.view_year, self.view_month)

        while len(month_days) < 6:
            last_date = month_days[-1][-1]
            extra_week = [last_date + timedelta(days=i) for i in range(1, 8)]
            month_days.append(extra_week)

        for r in range(6):
            week = month_days[r] if r < len(month_days) else []
            for c in range(7):
                btn = self.day_buttons[r][c]
                if c < len(week):
                    d = week[c]
                    has_events = d in self._event_dates
                    state = (d, d.month == self.view_month, d == self.today,
                             d == self.selected_date, has_events, tuple(COLORS.values()))
                    if self._day_states.get((r, c)) == state:
                        continue
                    self._day_states[r, c] = state
                    day_text = str(d.day)

                    btn.configure(text=day_text)

                    is_current_month = (d.month == self.view_month)
                    is_today = (d == self.today)
                    is_selected = (d == self.selected_date)

                    if is_selected:
                        btn.configure(
                            fg_color=theme_color("accent"),
                            text_color="#ffffff",
                            hover_color=theme_color("accent_hover"),
                            border_width=0,
                            font=("Segoe UI", 11, "bold")
                        )
                    elif is_today:
                        btn.configure(
                            fg_color=theme_color("today_bg"),
                            text_color=theme_color("today_accent"),
                            hover_color=theme_color("bg_tertiary"),
                            border_width=1,
                            border_color=theme_color("today_accent"),
                            font=("Segoe UI", 11, "bold")
                        )
                    elif is_current_month:
                        border_w = 1 if has_events else 0
                        border_c = COLORS["accent"] if has_events else COLORS["border"]
                        fnt = ("Segoe UI", 11, "bold") if has_events else ("Segoe UI", 11)
                        btn.configure(
                            fg_color="transparent",
                            text_color=theme_color("text_primary"),
                            hover_color=theme_color("bg_tertiary"),
                            border_width=border_w,
                            border_color=border_c,
                            font=fnt
                        )
                    else:
                        btn.configure(
                            fg_color="transparent",
                            text_color=theme_color("text_muted"),
                            hover_color=theme_color("bg_tertiary"),
                            border_width=0,
                            font=("Segoe UI", 11)
                        )

                    btn.configure(command=lambda dt=d: self._on_day_click(dt))
                else:
                    btn.configure(text="", fg_color="transparent", border_width=0, command=None)

    def _on_day_click(self, clicked_date):
        self.selected_date = clicked_date
        self.view_year = clicked_date.year
        self.view_month = clicked_date.month
        self.refresh()
        if self.on_date_selected:
            self.on_date_selected(clicked_date)
