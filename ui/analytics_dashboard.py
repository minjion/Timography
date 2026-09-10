"""Full Analytics View & Dashboard with Interactive Period Filters, Real Calculations, and Donut/Bar Charts."""
from datetime import datetime, date, timedelta
import tkinter as tk
import customtkinter as ctk
from ui.theme import COLORS, FONTS, CATEGORY_COLORS, CARD_CORNER_RADIUS, BUTTON_CORNER_RADIUS
from core.database import TimographyDB
from core.analytics import calculate_focus_score, get_weekly_insights
from ui.heatmap import ActivityHeatmap


class AnalyticsView(ctk.CTkFrame):
    def __init__(self, master, db: TimographyDB, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.db = db
        self.current_date = datetime.now().date()
        self.period_mode = "week"  # "week", "month", "30d", "year"

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # Top Header & Period Selector
        top_bar = ctk.CTkFrame(self, fg_color="transparent", height=44)
        top_bar.pack(fill="x", padx=20, pady=(14, 8))

        ctk.CTkLabel(
            top_bar,
            text="Productivity & Time Analytics",
            font=FONTS["heading"],
            text_color=COLORS["text_primary"]
        ).pack(side="left")

        self.seg_period = ctk.CTkSegmentedButton(
            top_bar,
            values=["This Week", "This Month", "Past 30 Days", "Year to Date"],
            font=FONTS["small_bold"],
            command=self._on_period_change
        )
        self.seg_period.set("This Week")
        self.seg_period.pack(side="right")

        # Scrollable dashboard body
        self.scroll_body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_body.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        # 1. 4 Metric Cards in a Grid
        cards_grid = ctk.CTkFrame(self.scroll_body, fg_color="transparent")
        cards_grid.pack(fill="x", pady=(0, 12))
        for i in range(4):
            cards_grid.columnconfigure(i, weight=1)

        # Card 1: Total Hours
        self.card_hours = self._create_kpi_card(cards_grid, 0, "TOTAL SCHEDULED", "-- hrs", "Across events & routines", COLORS["accent"])

        # Card 2: Focus Score
        self.card_focus = self._create_kpi_card(cards_grid, 1, "FOCUS SCORE", "-- / 100", "Daily concentration metric", COLORS["accent_green"])

        # Card 3: Pomodoro Time
        self.card_pomo = self._create_kpi_card(cards_grid, 2, "POMODORO TIME", "-- min", "Logged focus sessions", COLORS["accent_purple"])

        # Card 4: Study Streak
        self.card_streak = self._create_kpi_card(cards_grid, 3, "STUDY STREAK", "🔥 0 Days", "Consecutive study days", COLORS["accent_orange"])

        # 2. Charts Row: Donut Chart on Left, Daily Bar Chart on Right
        charts_row = ctk.CTkFrame(self.scroll_body, fg_color="transparent")
        charts_row.pack(fill="x", pady=(0, 12))
        charts_row.columnconfigure(0, weight=1)
        charts_row.columnconfigure(1, weight=1)

        # Left: Donut Chart Card
        self.pie_frame = ctk.CTkFrame(charts_row, fg_color=COLORS["bg_secondary"], corner_radius=CARD_CORNER_RADIUS)
        self.pie_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.lbl_pie_title = ctk.CTkLabel(
            self.pie_frame,
            text="CATEGORY DISTRIBUTION (THIS WEEK)",
            font=FONTS["micro"],
            text_color=COLORS["text_muted"]
        )
        self.lbl_pie_title.pack(anchor="w", padx=16, pady=(12, 4))

        self.canvas_pie = tk.Canvas(self.pie_frame, bg=COLORS["bg_secondary"], bd=0, highlightthickness=0, height=220)
        self.canvas_pie.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        # Right: Bar Chart Card
        self.bar_frame = ctk.CTkFrame(charts_row, fg_color=COLORS["bg_secondary"], corner_radius=CARD_CORNER_RADIUS)
        self.bar_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        self.lbl_bar_title = ctk.CTkLabel(
            self.bar_frame,
            text="DAILY WORKLOAD (HOURS PER DAY)",
            font=FONTS["micro"],
            text_color=COLORS["text_muted"]
        )
        self.lbl_bar_title.pack(anchor="w", padx=16, pady=(12, 4))

        self.canvas_bar = tk.Canvas(self.bar_frame, bg=COLORS["bg_secondary"], bd=0, highlightthickness=0, height=220)
        self.canvas_bar.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        # 3. Heatmap Row
        heatmap_container = ctk.CTkFrame(self.scroll_body, fg_color=COLORS["bg_secondary"], corner_radius=CARD_CORNER_RADIUS)
        heatmap_container.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            heatmap_container,
            text="ANNUAL ACTIVITY HEATMAP (PAST 28 WEEKS)",
            font=FONTS["micro"],
            text_color=COLORS["text_muted"]
        ).pack(anchor="w", padx=16, pady=(12, 4))

        self.heatmap = ActivityHeatmap(heatmap_container, weeks=28)
        self.heatmap.pack(fill="x", padx=12, pady=(0, 12))

    def _create_kpi_card(self, parent, col, title, initial_val, subtitle, color):
        f = ctk.CTkFrame(parent, fg_color=COLORS["bg_secondary"], corner_radius=CARD_CORNER_RADIUS)
        f.grid(row=0, column=col, sticky="nsew", padx=4)

        ctk.CTkLabel(f, text=title, font=FONTS["micro"], text_color=COLORS["text_muted"]).pack(anchor="w", padx=14, pady=(10, 2))
        lbl_val = ctk.CTkLabel(f, text=initial_val, font=("Segoe UI", 24, "bold"), text_color=color)
        lbl_val.pack(anchor="w", padx=14)
        lbl_sub = ctk.CTkLabel(f, text=subtitle, font=FONTS["micro"], text_color=COLORS["text_secondary"])
        lbl_sub.pack(anchor="w", padx=14, pady=(0, 10))
        return {"val": lbl_val, "sub": lbl_sub}

    def _on_period_change(self, value):
        mapping = {
            "This Week": "week",
            "This Month": "month",
            "Past 30 Days": "30d",
            "Year to Date": "year"
        }
        self.period_mode = mapping.get(value, "week")
        self.refresh()

    def _get_date_range(self):
        today = self.current_date
        if self.period_mode == "week":
            start_d = today - timedelta(days=today.weekday())
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

    def refresh(self):
        start_d, end_d = self._get_date_range()
        start_str = start_d.strftime("%Y-%m-%d")
        end_str = end_d.strftime("%Y-%m-%d")

        # 1. Real Category Hours Query
        cat_hours = self.db.get_category_hours_summary(start_str, end_str)
        total_hours = sum(cat_hours.values())

        # Update Card 1: Total Hours
        self.card_hours["val"].configure(text=f"{total_hours:.1f} hrs")
        period_label = self.seg_period.get()
        self.card_hours["sub"].configure(text=f"Total scheduled ({period_label})")

        # Update Card 2: Focus Score
        today_str = self.current_date.strftime("%Y-%m-%d")
        score_data = calculate_focus_score(self.db, today_str)
        self.card_focus["val"].configure(text=f"{score_data['score']} / 100")
        self.card_focus["sub"].configure(text=f"{score_data['rating']} ({score_data['avg_block_mins']}m avg block)")

        # Update Card 3: Pomodoro Time
        pomo_mins = self.db.get_today_pomodoro_minutes(today_str)
        p_hrs = pomo_mins / 60.0
        self.card_pomo["val"].configure(text=f"{p_hrs:.1f} hrs" if p_hrs >= 1 else f"{pomo_mins} min")
        self.card_pomo["sub"].configure(text="Today's deep work sessions")

        # Update Card 4: Study Streak
        streak_data = self.db.get_study_streak()
        cur_streak = streak_data.get("current", 0)
        best_streak = streak_data.get("best", 0)
        self.card_streak["val"].configure(text=f"🔥 {cur_streak} Day{'s' if cur_streak != 1 else ''}")
        self.card_streak["sub"].configure(text=f"All-time record: {best_streak} days")

        # 2. Draw Category Donut Chart
        self.lbl_pie_title.configure(text=f"CATEGORY DISTRIBUTION ({period_label.upper()})")
        self._draw_pie_chart(cat_hours, total_hours)

        # 3. Draw Daily Workload Bar Chart
        daily_hours = self.db.get_daily_hours_summary(start_str, end_str)
        self.lbl_bar_title.configure(text=f"DAILY WORKLOAD ({period_label.upper()})")
        self._draw_bar_chart(daily_hours, start_d, end_d)

        # 4. Refresh Heatmap with full annual data
        heatmap_data = self.db.get_heatmap_data(self.current_date.year)
        self.heatmap.set_data(heatmap_data)

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
            color = CATEGORY_COLORS.get(cat, COLORS["accent"])

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
        self.canvas_pie.create_text(cx, cy + 10, text="Total", font=FONTS["micro"], fill=COLORS["text_muted"])

    def _draw_bar_chart(self, daily_hours: dict, start_d: date, end_d: date):
        self.canvas_bar.delete("all")
        w = 420
        h = 220
        pad_x = 35
        pad_y = 30
        chart_w = w - pad_x * 2
        chart_h = h - pad_y * 2

        num_days = max(1, (end_d - start_d).days + 1)
        max_hrs = max([val for val in daily_hours.values()] + [4.0])

        col_w = chart_w / num_days
        show_labels_every = max(1, num_days // 10)

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
                tc = COLORS["today_accent"] if is_today else COLORS["text_muted"]
                self.canvas_bar.create_text(
                    (bx1 + bx2) / 2, by2 + 12,
                    text=day_txt, font=FONTS["small_bold" if is_today else "micro"], fill=tc
                )

            curr += timedelta(days=1)
            idx += 1


class AnalyticsDashboard(ctk.CTkToplevel):
    """Backwards-compatible standalone window wrapper."""
    def __init__(self, master, db: TimographyDB):
        super().__init__(master)
        self.db = db
        self.title("Timography — Time Analytics & Insights")
        self.geometry("960x680")
        self.minsize(860, 580)
        self.configure(fg_color=COLORS["bg_primary"])

        view = AnalyticsView(self, db)
        view.pack(fill="both", expand=True)
