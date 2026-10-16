"""Full Analytics View & Dashboard with Interactive Period Filters, Real Calculations, and Donut/Bar Charts."""
from datetime import datetime, date, timedelta
import tkinter as tk
import customtkinter as ctk
from ui.controls import AppToplevel
from ui.scrolling import ScrollableFrame
from ui.theme import theme_color
from ui.theme import COLORS, FONTS, CATEGORY_COLORS, CARD_CORNER_RADIUS, SIZES
from core.database import TimographyDB
from core.analytics import get_weekly_insights, calculate_focus_score
from ui.heatmap import ActivityHeatmap


class AnalyticsView(ctk.CTkFrame):
    def __init__(self, master, db: TimographyDB, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.db = db
        self.current_date = datetime.now().date()
        self.period_mode = "week"  # "week", "month", "30d", "year"

        self._build_ui()
        self._refresh_key = None

    def _build_ui(self):
        # Top Header & Period Selector
        top_bar = ctk.CTkFrame(self, fg_color="transparent", height=44)
        top_bar.pack(fill="x", padx=20, pady=(14, 8))

        self.top_title = ctk.CTkLabel(
            top_bar,
            text="Productivity & Time Analytics",
            font=FONTS["heading"],
            text_color=theme_color("text_primary")
        )
        self.top_title.pack(side="left")

        self.seg_period = ctk.CTkSegmentedButton(
            top_bar,
            values=["This Week", "This Month", "Past 30 Days", "Year to Date"],
            font=FONTS["small_bold"],
            command=self._on_period_change
        )
        self.seg_period.set("This Week")
        self.seg_period.pack(side="right")

        self.include_routines_var = ctk.BooleanVar(value=False)
        self.switch_routines = ctk.CTkSwitch(
            top_bar,
            text="Include Routines",
            font=FONTS["small"],
            variable=self.include_routines_var,
            command=self.refresh,
            progress_color=theme_color("accent")
        )
        self.switch_routines.pack(side="right", padx=(0, 16))

        # Scrollable dashboard body
        self.scroll_body = ScrollableFrame(self, fg_color="transparent")
        self.scroll_body.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        # 1. 4 Metric Cards in a Grid
        cards_grid = ctk.CTkFrame(self.scroll_body, fg_color="transparent")
        cards_grid.pack(fill="x", pady=(0, 12))
        for i in range(4):
            cards_grid.columnconfigure(i, weight=1)

        # Card 1: Total Hours
        self.card_hours = self._create_kpi_card(cards_grid, 0, "TOTAL SCHEDULED", "-- hrs", "Across events & routines", COLORS["accent"])

        # Card 2: Focus Time (Real dynamic calculation: Study + Work + Pomodoro across period)
        self.card_focus = self._create_kpi_card(cards_grid, 1, "FOCUS TIME", "-- hrs", "Deep work & study", COLORS["accent_green"])

        # Card 3: Focus Score (Dynamic focus rating across period)
        self.card_pomo = self._create_kpi_card(cards_grid, 2, "TODAY'S FOCUS GOAL", "-- %", "Recorded minutes / goal", COLORS["accent_purple"])

        # Card 4: Study Streak
        self.card_streak = self._create_kpi_card(cards_grid, 3, "FOCUS GOAL STREAK", "🔥 0 Days", "Recorded focus", COLORS["accent_orange"])

        self.kpi_cards = [self.card_hours, self.card_focus, self.card_pomo, self.card_streak]

        # 2. Charts Row: Donut Chart on Left, Daily Bar Chart on Right
        charts_row = ctk.CTkFrame(self.scroll_body, fg_color="transparent")
        charts_row.pack(fill="x", pady=(0, 12))
        charts_row.columnconfigure(0, weight=1)
        charts_row.columnconfigure(1, weight=1)

        # Left: Donut Chart Card
        self.pie_frame = ctk.CTkFrame(charts_row, fg_color=theme_color("bg_secondary"), corner_radius=CARD_CORNER_RADIUS)
        self.pie_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.lbl_pie_title = ctk.CTkLabel(
            self.pie_frame,
            text="CATEGORY DISTRIBUTION (THIS WEEK)",
            font=FONTS["micro"],
            text_color=theme_color("text_muted")
        )
        self.lbl_pie_title.pack(anchor="w", padx=16, pady=(12, 4))

        self.canvas_pie = tk.Canvas(self.pie_frame, bg=COLORS["bg_secondary"], bd=0, highlightthickness=0, height=220)
        self.canvas_pie.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        # Right: Bar Chart Card
        self.bar_frame = ctk.CTkFrame(charts_row, fg_color=theme_color("bg_secondary"), corner_radius=CARD_CORNER_RADIUS)
        self.bar_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        self.lbl_bar_title = ctk.CTkLabel(
            self.bar_frame,
            text="DAILY WORKLOAD (HOURS PER DAY)",
            font=FONTS["micro"],
            text_color=theme_color("text_muted")
        )
        self.lbl_bar_title.pack(anchor="w", padx=16, pady=(12, 4))

        self.canvas_bar = tk.Canvas(self.bar_frame, bg=COLORS["bg_secondary"], bd=0, highlightthickness=0, height=220)
        self.canvas_bar.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self._chart_data = None
        self.canvas_pie.bind("<Configure>", self._redraw_charts)
        self.canvas_bar.bind("<Configure>", self._redraw_charts)

        # 3. Heatmap & Insights Row (2 columns)
        bottom_row = ctk.CTkFrame(self.scroll_body, fg_color="transparent")
        bottom_row.pack(fill="x", pady=(0, 12))
        bottom_row.columnconfigure(0, weight=3)
        bottom_row.columnconfigure(1, weight=2)

        # Left: Heatmap Container
        self.heatmap_container = ctk.CTkFrame(bottom_row, fg_color=theme_color("bg_secondary"), corner_radius=CARD_CORNER_RADIUS)
        self.heatmap_container.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.lbl_heatmap_title = ctk.CTkLabel(
            self.heatmap_container,
            text="ANNUAL ACTIVITY HEATMAP (PAST 28 WEEKS)",
            font=FONTS["micro"],
            text_color=theme_color("text_muted")
        )
        self.lbl_heatmap_title.pack(anchor="w", padx=16, pady=(12, 4))

        self.heatmap = ActivityHeatmap(self.heatmap_container, weeks=28)
        self.heatmap.pack(fill="x", padx=12, pady=(0, 12))

        # Right: Productivity Insights Card
        self.insights_frame = ctk.CTkFrame(bottom_row, fg_color=theme_color("bg_secondary"), corner_radius=CARD_CORNER_RADIUS)
        self.insights_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        self.lbl_insights_title = ctk.CTkLabel(
            self.insights_frame,
            text="PRODUCTIVITY INSIGHTS & HIGHLIGHTS",
            font=FONTS["micro"],
            text_color=theme_color("text_muted")
        )
        self.lbl_insights_title.pack(anchor="w", padx=16, pady=(12, 4))

        self.insights_body = ctk.CTkFrame(self.insights_frame, fg_color="transparent")
        self.insights_body.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    def _create_kpi_card(self, parent, col, title, initial_val, subtitle, color):
        f = ctk.CTkFrame(parent, fg_color=theme_color("bg_secondary"), corner_radius=CARD_CORNER_RADIUS)
        f.grid(row=0, column=col, sticky="nsew", padx=4)

        lbl_title = ctk.CTkLabel(f, text=title, font=FONTS["micro"], text_color=theme_color("text_muted"))
        lbl_title.pack(anchor="w", padx=14, pady=(10, 2))
        lbl_val = ctk.CTkLabel(f, text=initial_val, font=("Segoe UI", SIZES['kpi_value_font_size'], "bold"), text_color=color)
        lbl_val.pack(anchor="w", padx=14)
        lbl_sub = ctk.CTkLabel(f, text=subtitle, font=FONTS["micro"], text_color=theme_color("text_secondary"))
        lbl_sub.pack(anchor="w", padx=14, pady=(0, 10))
        return {"frame": f, "title": lbl_title, "val": lbl_val, "sub": lbl_sub}

    def _on_period_change(self, value):
        mapping = {
            "This Week": "week",
            "This Month": "month",
            "Past 30 Days": "30d",
            "Year to Date": "year"
        }
        self.seg_period.set(value)
        self.period_mode = mapping.get(value, "week")
        self.refresh()

    def _get_date_range(self):
        today = self.current_date
        if self.period_mode == "week":
            first = 6 if self.db.get_setting("week_start", "monday") == "sunday" else 0
            start_d = today - timedelta(days=(today.weekday() - first) % 7)
            end_d = start_d + timedelta(days=6)
        elif self.period_mode == "month":
            start_d = date(today.year, today.month, 1)
            next_month = date(today.year + (today.month // 12), ((today.month % 12) + 1), 1)
            end_d = next_month - timedelta(days=1)
        elif self.period_mode == "30d":
            start_d = today - timedelta(days=29)
            end_d = today
        else:  # year
            start_d = date(today.year, 1, 1)
            end_d = today
        return start_d, end_d

    def reapply_theme(self):
        """Re-skin analytics dashboard in-place when theme toggles."""
        try:
            if hasattr(self, "top_title"):
                self.top_title.configure(text_color=theme_color("text_primary"))
            if hasattr(self, "switch_routines"):
                self.switch_routines.configure(progress_color=theme_color("accent"))

            if hasattr(self, "kpi_cards"):
                for card in self.kpi_cards:
                    card["frame"].configure(fg_color=theme_color("bg_secondary"))
                    card["title"].configure(text_color=theme_color("text_muted"))
                    card["sub"].configure(text_color=theme_color("text_secondary"))

            if hasattr(self, "pie_frame"):
                self.pie_frame.configure(fg_color=theme_color("bg_secondary"))
            if hasattr(self, "lbl_pie_title"):
                self.lbl_pie_title.configure(text_color=theme_color("text_muted"))
            if hasattr(self, "canvas_pie"):
                self.canvas_pie.configure(bg=COLORS["bg_secondary"])

            if hasattr(self, "bar_frame"):
                self.bar_frame.configure(fg_color=theme_color("bg_secondary"))
            if hasattr(self, "lbl_bar_title"):
                self.lbl_bar_title.configure(text_color=theme_color("text_muted"))
            if hasattr(self, "canvas_bar"):
                self.canvas_bar.configure(bg=COLORS["bg_secondary"])

            if hasattr(self, "heatmap_container"):
                self.heatmap_container.configure(fg_color=theme_color("bg_secondary"))
            if hasattr(self, "lbl_heatmap_title"):
                self.lbl_heatmap_title.configure(text_color=theme_color("text_muted"))
            if hasattr(self, "heatmap") and hasattr(self.heatmap, "reapply_theme"):
                self.heatmap.reapply_theme()

            if hasattr(self, "insights_frame"):
                self.insights_frame.configure(fg_color=theme_color("bg_secondary"))
            if hasattr(self, "lbl_insights_title"):
                self.lbl_insights_title.configure(text_color=theme_color("text_muted"))
        except Exception:
            pass
        self.refresh()

    def refresh(self):
        self.current_date = datetime.now().date()
        key = (self.current_date, self.seg_period.get(), self.include_routines_var.get(),
               self.db.get_revision(), tuple(COLORS.values()))
        if key == self._refresh_key:
            return
        self._refresh_key = key
        self._category_colors = {c["name"]: c["color"] for c in self.db.get_all_categories()}
        start_d, end_d = self._get_date_range()
        start_str = start_d.strftime("%Y-%m-%d")
        end_str = end_d.strftime("%Y-%m-%d")

        inc_routines = self.include_routines_var.get()
        period_label = self.seg_period.get()

        # 1. Real Category Hours Query
        cat_hours = self.db.get_category_hours_summary(start_str, end_str, include_routines=inc_routines)
        total_hours = sum(cat_hours.values())

        # Update Card 1: Total Hours
        self.card_hours["val"].configure(text=f"{total_hours:.1f} hrs")
        sub_desc = f"Planned events ({period_label})" if not inc_routines else f"Events + routines ({period_label})"
        self.card_hours["sub"].configure(text=sub_desc)

        # Completed focus time is recorded independently of planned hours.
        pomo_mins = self.db.get_pomodoro_minutes_range(start_str, end_str)
        pomo_hrs = pomo_mins / 60.0

        total_focus_hours = pomo_hrs
        total_focus_mins = int(total_focus_hours * 60)

        if total_focus_hours >= 1.0:
            focus_val_str = f"{total_focus_hours:.1f} hrs"
        else:
            focus_val_str = f"{total_focus_mins} min"

        self.card_focus["val"].configure(text=focus_val_str)
        self.card_focus["sub"].configure(text=f"Recorded active work ({period_label})")

        focus = calculate_focus_score(self.db, self.current_date.isoformat())
        focus_score, score_rating = focus["score"], focus["rating"]
        self.card_pomo["val"].configure(text=f"{focus_score}%")
        self.card_pomo["sub"].configure(text=f"{score_rating} · {focus['pomodoro_mins']}/{focus['goal_minutes']} min")

        # Update Card 4: Study Streak
        streak_data = self.db.get_study_streak()
        cur_streak = streak_data.get("current", 0)
        best_streak = streak_data.get("best", 0)
        today_mins = streak_data.get("today_minutes", 0)
        goal_mins = streak_data.get("goal_minutes", 30)
        self.card_streak["val"].configure(text=f"🔥 {cur_streak} Day{'s' if cur_streak != 1 else ''}")
        self.card_streak["sub"].configure(text=f"{today_mins}/{goal_mins} min today · Record: {best_streak} days")

        # 2. Draw Category Donut Chart
        self.lbl_pie_title.configure(text=f"CATEGORY DISTRIBUTION ({period_label.upper()})")
        self._draw_pie_chart(cat_hours, total_hours)

        # 3. Draw Daily Workload Bar Chart
        daily_hours = self.db.get_daily_hours_summary(start_str, end_str, include_routines=inc_routines)
        self.lbl_bar_title.configure(text=f"DAILY WORKLOAD ({period_label.upper()})")
        self._draw_bar_chart(daily_hours, start_d, end_d)

        # 4. Refresh Heatmap with full annual data
        heatmap_start = self.current_date - timedelta(weeks=28)
        heatmap_data = self.db.get_daily_hours_summary(heatmap_start.isoformat(), self.current_date.isoformat(), include_routines=inc_routines)
        self.heatmap.set_data(heatmap_data)
        self._chart_data = (cat_hours, total_hours, daily_hours, start_d, end_d)

        # 5. Populate Productivity Insights Card
        if hasattr(self, "insights_body"):
            for w in self.insights_body.winfo_children():
                try:
                    w.destroy()
                except Exception:
                    pass

            today_str = self.current_date.strftime("%Y-%m-%d")
            insights = get_weekly_insights(self.db, self.current_date)
            chk_stats = self.db.get_checklist_stats(today_str)
            chk_pct = chk_stats.get("percent", 0)
            insights.append(f"Checklist progress: {chk_stats.get('completed', 0)}/{chk_stats.get('total', 0)} tasks ({chk_pct}%) today.")
            if total_focus_hours > 0:
                insights.append(f"Recorded focus: {focus_val_str} of active timer work in {period_label.lower()}.")
            elif total_hours > 0:
                insights.append("Start a focus timer to record work against your plan.")

            for item in insights:
                row = ctk.CTkFrame(self.insights_body, fg_color="transparent")
                row.pack(fill="x", pady=3)
                ctk.CTkLabel(row, text="•", font=FONTS["body_bold"], text_color=theme_color("accent")).pack(side="left", padx=(0, 6), anchor="n")
                label = ctk.CTkLabel(row, text=item, font=FONTS["small"], text_color=theme_color("text_primary"), wraplength=380, justify="left", anchor="w")
                label.pack(side="left", fill="x", expand=True)
                def wrap_insight(event=None, lbl=label, container=row):
                    if (not container.winfo_exists() or not self.winfo_viewable()
                            or not container.winfo_viewable() or not lbl.winfo_viewable()):
                        return
                    physical_width = event.width if event is not None else container.winfo_width()
                    width = max(80, round(physical_width / lbl._get_widget_scaling() - 30))
                    if lbl.cget("wraplength") != width:
                        lbl.configure(wraplength=width)
                row.bind("<Configure>", wrap_insight)
                row.bind("<Map>", lambda event, callback=wrap_insight: self.after_idle(callback))

    def _redraw_charts(self, event=None):
        if self._chart_data:
            categories, total, daily, start, end = self._chart_data
            self._draw_pie_chart(categories, total)
            self._draw_bar_chart(daily, start, end)

    def _draw_pie_chart(self, cat_hours: dict, total_hours: float):
        self.canvas_pie.delete("all")
        cx, cy, r = 95, 110, 75

        if total_hours <= 0:
            self.canvas_pie.create_oval(cx - r, cy - r, cx + r, cy + r, fill=COLORS["bg_tertiary"], outline=COLORS["border"])
            self.canvas_pie.create_text(cx, cy, text="No events\nin period", font=FONTS["small"], fill=COLORS["text_muted"], justify="center")
            return

        start_angle = 0
        legend_y = 24
        sorted_cats = sorted(cat_hours.items(), key=lambda x: x[1], reverse=True)

        for cat, hrs in sorted_cats:
            if hrs <= 0:
                continue
            extent = (hrs / total_hours) * 360.0
            color = self._category_colors.get(cat, CATEGORY_COLORS.get(cat, COLORS["accent"]))

            # Arc
            self.canvas_pie.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=start_angle,
                extent=extent,
                fill=color,
                outline=COLORS["bg_secondary"],
                width=2
            )
            start_angle += extent

            # Legend text
            lx = 205
            if legend_y < 200:
                self.canvas_pie.create_rectangle(lx, legend_y + 2, lx + 10, legend_y + 12, fill=color, outline="")
                pct = int((hrs / total_hours) * 100)
                self.canvas_pie.create_text(
                    lx + 16, legend_y + 7,
                    text=f"{cat}: {hrs:.1f}h ({pct}%)",
                    font=FONTS["small"], fill=COLORS["text_primary"], anchor="w"
                )
                legend_y += 22

        # Donut hole
        hole_r = 42
        self.canvas_pie.create_oval(cx - hole_r, cy - hole_r, cx + hole_r, cy + hole_r, fill=COLORS["bg_secondary"], outline="")
        self.canvas_pie.create_text(cx, cy - 6, text=f"{total_hours:.1f}h", font=FONTS["body_bold"], fill=COLORS["text_primary"])
        self.canvas_pie.create_text(cx, cy + 10, text="Total", font=FONTS["micro"], fill=COLORS["text_secondary"])

    def _draw_bar_chart(self, daily_hours: dict, start_d: date, end_d: date):
        self.canvas_bar.delete("all")
        w = max(160, self.canvas_bar.winfo_width())
        h = max(120, self.canvas_bar.winfo_height())
        pad_x = 35
        pad_y = 30
        chart_w = w - pad_x * 2
        chart_h = h - pad_y * 2

        num_days = max(1, (end_d - start_d).days + 1)
        max_hrs = max([val for val in daily_hours.values()] + [4.0])

        col_w = chart_w / num_days
        show_labels_every = max(1, round(num_days / max(1, chart_w // 35)))

        curr = start_d
        idx = 0
        today_date = datetime.now().date()

        while curr <= end_d:
            d_str = curr.strftime("%Y-%m-%d")
            hrs = daily_hours.get(d_str, 0.0)

            bx1 = pad_x + idx * col_w + 1
            bx2 = bx1 + max(2, col_w - 2)
            bar_height = (hrs / max_hrs) * chart_h
            by2 = h - pad_y
            by1 = by2 - bar_height

            is_today = (curr == today_date)
            bar_color = COLORS["today_accent"] if is_today else (COLORS["accent"] if hrs > 0 else COLORS["bg_tertiary"])

            # Bar
            if bar_height > 2:
                self.canvas_bar.create_rectangle(bx1, by1, bx2, by2, fill=bar_color, outline="", tags="bar")

            # Day label below
            if idx % show_labels_every == 0 or is_today:
                day_txt = curr.strftime("%a") if num_days <= 7 else str(curr.day)
                tc = COLORS["today_accent"] if is_today else COLORS["text_secondary"]
                self.canvas_bar.create_text(
                    (bx1 + bx2) / 2, by2 + 12,
                    text=day_txt, font=FONTS["small_bold" if is_today else "micro"], fill=tc
                )

            curr += timedelta(days=1)
            idx += 1


class AnalyticsDashboard(AppToplevel):
    """Backwards-compatible standalone window wrapper."""
    def __init__(self, master, db: TimographyDB):
        super().__init__(master)
        self.db = db
        self.title("Timography — Time Analytics & Insights")
        self.geometry("960x680")
        self.minsize(860, 580)
        self.configure(fg_color=theme_color("bg_primary"))

        self.view = AnalyticsView(self, db)
        self.view.pack(fill="both", expand=True)

    def reapply_theme(self):
        self.configure(fg_color=theme_color("bg_primary"))
        self.view.reapply_theme()
