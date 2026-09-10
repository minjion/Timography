"""Google Calendar-style Time Grid with drag-and-drop, animations, and modern visuals."""
from datetime import datetime, date, timedelta
import tkinter as tk
import customtkinter as ctk
from ui.theme import (
    COLORS, FONTS, SHADOW_COLOR, SHADOW_OFFSET,
    HOUR_BAND_EVEN, HOUR_BAND_ODD, TODAY_COLUMN_TINT,
    ANIM_SCROLL_MS, ANIM_SNAP_MS, DRAG_THRESHOLD_PX, SNAP_MINUTES,
    CURRENT_TIME_TICK_MS,
)
from ui.animations import (
    Animation, ease_out_cubic, ease_out_quad, lerp,
    brighten_color, darken_color, animate_scroll,
)
from ui.tooltip import CanvasTooltip


class TimeGrid(ctk.CTkFrame):
    def __init__(self, master, on_event_clicked=None, on_slot_clicked=None,
                 on_event_moved=None, **kwargs):
        super().__init__(master, fg_color=COLORS["bg_primary"], **kwargs)
        self.on_event_clicked = on_event_clicked
        self.on_slot_clicked = on_slot_clicked
        self.on_event_moved = on_event_moved

        self.mode = "week"
        self.current_date = datetime.now().date()
        self.events_by_date = {}

        self.hour_height = 54
        self.gutter_width = 56
        self.start_hour = 0
        self.end_hour = 24
        self.total_hours = self.end_hour - self.start_hour
        self.canvas_height = self.total_hours * self.hour_height

        # Event tracking
        self._event_items = {}      # canvas item_id -> event dict
        self._event_rects = {}      # canvas rect_id -> (x1, y1, x2, y2, ev)
        self._item_to_rect = {}     # canvas item_id -> rect_id
        self._hover_rect = None     # currently hovered rect id

        # Drag state
        self._drag_active = False
        self._drag_event = None
        self._drag_start_cx = 0
        self._drag_start_cy = 0
        self._drag_ghost_ids = []
        self._drag_offset_y = 0
        self._press_item = None
        self._last_ghost_dx = 0
        self._last_ghost_dy = 0

        # Current time line
        self._time_line_ids = []
        self._time_tick_id = None

        self._build_ui()

    def _build_ui(self):
        self.header_frame = ctk.CTkFrame(self, height=52, fg_color=COLORS["bg_secondary"], corner_radius=0)
        self.header_frame.pack(fill="x", side="top")
        self.header_frame.pack_propagate(False)

        self.body_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_primary"], corner_radius=0)
        self.body_frame.pack(fill="both", expand=True, side="top")

        self.canvas = tk.Canvas(
            self.body_frame, bg=COLORS["bg_primary"],
            bd=0, highlightthickness=0, yscrollincrement=10
        )
        self.scrollbar = ctk.CTkScrollbar(self.body_frame, orientation="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.tooltip = CanvasTooltip(self.canvas)

        # Bindings
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

    # ─── Scroll ───

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_canvas_configure(self, event):
        self.canvas.configure(scrollregion=(0, 0, event.width, self.canvas_height))
        self.render()

    def scroll_to_hour(self, hour: int = 8):
        fraction = max(0.0, min(1.0, (hour * self.hour_height) / float(self.canvas_height)))
        animate_scroll(self.canvas, fraction, ANIM_SCROLL_MS)

    # ─── Data ───

    def set_data(self, mode, target_date, events_by_date):
        self.mode = mode
        self.current_date = target_date.date() if isinstance(target_date, datetime) else target_date
        self.events_by_date = events_by_date or {}
        self.render()

    def _get_dates(self):
        if self.mode == "day":
            return [self.current_date]
        start = self.current_date - timedelta(days=self.current_date.weekday())
        return [start + timedelta(days=i) for i in range(7)]

    # ─── Render ───

    def render(self):
        dates = self._get_dates()
        num_cols = len(dates)
        width = self.canvas.winfo_width()
        if width <= 10:
            width = 800
        grid_width = max(100, width - self.gutter_width)
        col_width = grid_width / num_cols
        today = datetime.now().date()

        # Cancel pending time tick
        if self._time_tick_id:
            try:
                self.after_cancel(self._time_tick_id)
            except Exception:
                pass

        # ── Header ──
        for w in self.header_frame.winfo_children():
            w.destroy()

        corner = ctk.CTkLabel(self.header_frame, text="", font=FONTS["micro"],
                              text_color=COLORS["text_muted"], width=self.gutter_width, fg_color="transparent")
        corner.pack(side="left")

        hcols = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        hcols.pack(side="left", fill="both", expand=True)
        for i in range(num_cols):
            hcols.columnconfigure(i, weight=1)

        day_short = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
        for idx, d in enumerate(dates):
            box = ctk.CTkFrame(hcols, fg_color="transparent")
            box.grid(row=0, column=idx, sticky="nsew", padx=2, pady=4)
            is_today = (d == today)
            dow = day_short[d.weekday()] if self.mode == "week" else d.strftime("%A").upper()
            dc = COLORS["today_accent"] if is_today else COLORS["text_secondary"]
            ctk.CTkLabel(box, text=dow, font=FONTS["micro"], text_color=dc).pack(anchor="center")
            bg = COLORS["today_accent"] if is_today else "transparent"
            tc = COLORS["bg_primary"] if is_today else COLORS["text_primary"]
            ctk.CTkLabel(box, text=str(d.day), font=FONTS["body_bold"], text_color=tc,
                         fg_color=bg, corner_radius=12 if is_today else 0,
                         width=26, height=26).pack(anchor="center")

        # ── Canvas ──
        self.canvas.delete("all")
        self._event_items.clear()
        self._event_rects.clear()
        self._item_to_rect.clear()
        self._time_line_ids.clear()

        # Today column tint
        for idx, d in enumerate(dates):
            if d == today:
                x1 = self.gutter_width + idx * col_width
                x2 = x1 + col_width
                self.canvas.create_rectangle(x1, 0, x2, self.canvas_height,
                                             fill=TODAY_COLUMN_TINT, outline="", tags="bg")

        # Alternating hour bands
        for h in range(self.start_hour, self.end_hour):
            y1 = h * self.hour_height
            y2 = y1 + self.hour_height
            fill = HOUR_BAND_ODD if h % 2 else HOUR_BAND_EVEN
            self.canvas.create_rectangle(self.gutter_width, y1, width, y2,
                                         fill=fill, outline="", tags="bg")

        # Re-draw today tint on top of bands
        for idx, d in enumerate(dates):
            if d == today:
                x1 = self.gutter_width + idx * col_width
                x2 = x1 + col_width
                self.canvas.create_rectangle(x1, 0, x2, self.canvas_height,
                                             fill=TODAY_COLUMN_TINT, outline="", stipple="gray25", tags="bg")

        # Grid lines and hour labels
        for h in range(self.start_hour, self.end_hour + 1):
            y = h * self.hour_height
            if h < self.end_hour:
                self.canvas.create_text(self.gutter_width - 8, y + 2, text=f"{h:02d}:00",
                                        font=FONTS["grid_hour"], fill=COLORS["grid_hour_text"], anchor="ne")
            self.canvas.create_line(self.gutter_width, y, width, y,
                                    fill=COLORS["grid_line"], width=1)
            if h < self.end_hour:
                half_y = y + self.hour_height // 2
                self.canvas.create_line(self.gutter_width + 4, half_y, width, half_y,
                                        fill=COLORS["grid_line_subtle"], dash=(2, 4), width=1)

        # Column separators
        for idx in range(num_cols + 1):
            x = self.gutter_width + idx * col_width
            self.canvas.create_line(x, 0, x, self.canvas_height, fill=COLORS["grid_line"], width=1)

        # ── Events ──
        for col_idx, d in enumerate(dates):
            d_str = d.strftime("%Y-%m-%d")
            ev_list = self.events_by_date.get(d_str, [])
            if not ev_list:
                continue

            parsed = []
            for ev in ev_list:
                try:
                    sh, sm = map(int, ev["start_time"].split(":"))
                    eh, em = map(int, ev["end_time"].split(":"))
                    s_min = sh * 60 + sm
                    e_min = eh * 60 + em
                    if e_min <= s_min:
                        e_min = s_min + 30
                    parsed.append((s_min, e_min, ev))
                except (ValueError, KeyError):
                    continue
            parsed.sort(key=lambda x: x[0])

            columns = []
            for item in parsed:
                placed = False
                for col in columns:
                    if col[-1][1] <= item[0]:
                        col.append(item)
                        placed = True
                        break
                if not placed:
                    columns.append([item])

            n_overlap = len(columns)
            col_x = self.gutter_width + col_idx * col_width

            for sub_i, col in enumerate(columns):
                sw = (col_width - 8) / max(1, n_overlap)
                x1 = col_x + 4 + sub_i * sw
                x2 = x1 + sw - 2

                for s_min, e_min, ev in col:
                    y1 = (s_min / 60.0) * self.hour_height
                    y2 = (e_min / 60.0) * self.hour_height
                    y2 = max(y2, y1 + 24)
                    self._draw_event_block(x1, y1, x2, y2, ev)

        # ── Current time line ──
        self._draw_current_time(dates, col_width, today)
        self._schedule_time_tick()

    # ─── Event Block Drawing ───

    def _rounded_rect(self, x1, y1, x2, y2, r=5, **kw):
        """Draw a rounded rectangle on the canvas."""
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.canvas.create_polygon(pts, smooth=True, **kw)

    def _draw_event_block(self, x1, y1, x2, y2, ev):
        color = ev.get("color") or COLORS["accent"]
        is_routine = ev.get("is_routine", False)
        title = ev.get("title", "Event")
        time_text = f"{ev.get('start_time', '')} - {ev.get('end_time', '')}"
        desc = ev.get("description", "")
        tag = f"ev_{id(ev)}"

        # Shadow
        sx, sy = SHADOW_OFFSET
        self._rounded_rect(x1 + sx, y1 + sy, x2 + sx, y2 + sy, r=5,
                           fill=SHADOW_COLOR, outline="", tags=(tag, "shadow"))

        # Main block
        outline_c = COLORS["routine_tag"] if is_routine else ""
        dash = (4, 3) if is_routine else ()
        rect_id = self._rounded_rect(x1, y1, x2, y2, r=5,
                                      fill=color, outline=outline_c,
                                      width=1.5 if is_routine else 0,
                                      dash=dash, tags=(tag, "event_item"))
        self._event_items[rect_id] = ev
        self._event_rects[rect_id] = (x1, y1, x2, y2, ev)
        self._item_to_rect[rect_id] = rect_id

        # Left accent bar
        accent_c = COLORS["routine_tag"] if is_routine else brighten_color(color, 0.3)
        bar_id = self._rounded_rect(x1, y1 + 2, x1 + 4, y2 - 2, r=2,
                                     fill=accent_c, outline="", tags=(tag, "event_item"))
        self._event_items[bar_id] = ev
        self._item_to_rect[bar_id] = rect_id

        # Title
        disp = f"[R] {title}" if is_routine else title
        avail_w = max(10, x2 - x1 - 14)
        t_id = self.canvas.create_text(x1 + 9, y1 + 5, text=disp,
                                        font=FONTS["grid_event_title"],
                                        fill="#ffffff", anchor="nw",
                                        width=avail_w, tags=(tag, "event_item"))
        self._event_items[t_id] = ev
        self._item_to_rect[t_id] = rect_id

        # Time label
        if y2 - y1 >= 38:
            tm_id = self.canvas.create_text(x1 + 9, y1 + 19, text=time_text,
                                             font=FONTS["grid_event_time"],
                                             fill=darken_color("#ffffff", 0.25), anchor="nw",
                                             width=avail_w, tags=(tag, "event_item"))
            self._event_items[tm_id] = ev
            self._item_to_rect[tm_id] = rect_id

        # Description snippet
        if y2 - y1 >= 56 and desc:
            snippet = desc[:40] + ("..." if len(desc) > 40 else "")
            d_id = self.canvas.create_text(x1 + 9, y1 + 33, text=snippet,
                                            font=FONTS["micro"],
                                            fill=darken_color("#ffffff", 0.4), anchor="nw",
                                            width=avail_w, tags=(tag, "event_item"))
            self._event_items[d_id] = ev
            self._item_to_rect[d_id] = rect_id

        # Hover bindings
        self.canvas.tag_bind(tag, "<Enter>", lambda e, r=rect_id, c=color: self._on_hover_enter(r, c))
        self.canvas.tag_bind(tag, "<Leave>", lambda e, r=rect_id, c=color: self._on_hover_leave(r, c))

        # Tooltip
        tip_lines = [title, time_text]
        if desc:
            tip_lines.append(desc[:80])
        cat = ev.get("category", "")
        if cat:
            tip_lines.append(f"Category: {cat}")
        if is_routine:
            tip_lines.append("(Routine - click to manage)")
        self.tooltip.bind_item(tag, "\n".join(tip_lines))

        # Drag cursor for regular events, arrow for routines
        if is_routine:
            self.canvas.tag_bind(tag, "<Enter>", lambda e, r=rect_id, c=color: self._on_hover_enter(r, c), add="+")
        else:
            pass  # default cursor, draggable

    def _on_hover_enter(self, rect_id, base_color):
        self._hover_rect = rect_id
        bright = brighten_color(base_color, 0.18)
        try:
            self.canvas.itemconfigure(rect_id, fill=bright)
        except Exception:
            pass

    def _on_hover_leave(self, rect_id, base_color):
        self._hover_rect = None
        try:
            self.canvas.itemconfigure(rect_id, fill=base_color)
        except Exception:
            pass

    # ─── Current Time ───

    def _draw_current_time(self, dates, col_width, today):
        for item_id in self._time_line_ids:
            try:
                self.canvas.delete(item_id)
            except Exception:
                pass
        self._time_line_ids.clear()

        now = datetime.now()
        for col_idx, d in enumerate(dates):
            if d == today:
                now_y = (now.hour + now.minute / 60.0) * self.hour_height
                x1 = self.gutter_width + col_idx * col_width
                x2 = x1 + col_width

                # Time badge on gutter
                time_str = now.strftime("%H:%M")
                badge_id = self.canvas.create_text(
                    self.gutter_width - 4, now_y,
                    text=time_str, font=FONTS["micro"],
                    fill=COLORS["current_time_line"], anchor="e"
                )
                self._time_line_ids.append(badge_id)

                # Red line
                line_id = self.canvas.create_line(
                    x1, now_y, x2, now_y,
                    fill=COLORS["current_time_line"], width=2
                )
                self._time_line_ids.append(line_id)

                # Red dot
                dot_id = self.canvas.create_oval(
                    x1 - 4, now_y - 4, x1 + 4, now_y + 4,
                    fill=COLORS["current_time_line"], outline=""
                )
                self._time_line_ids.append(dot_id)

    def _schedule_time_tick(self):
        self._time_tick_id = self.after(CURRENT_TIME_TICK_MS, self._time_tick)

    def _time_tick(self):
        dates = self._get_dates()
        width = self.canvas.winfo_width()
        if width <= 10:
            width = 800
        grid_width = max(100, width - self.gutter_width)
        col_width = grid_width / len(dates)
        today = datetime.now().date()
        self._draw_current_time(dates, col_width, today)
        self._schedule_time_tick()

    # ─── Drag & Drop ───

    def _on_press(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        self._drag_start_cx = cx
        self._drag_start_cy = cy
        self._drag_active = False
        self._drag_event = None
        self._press_item = None

        items = self.canvas.find_overlapping(cx - 1, cy - 1, cx + 1, cy + 1)
        for item_id in reversed(items):
            if item_id in self._event_items:
                ev = self._event_items[item_id]
                rect_id = self._item_to_rect.get(item_id, item_id)
                self._press_item = rect_id
                if not ev.get("is_routine", False):
                    self._drag_event = ev
                    if rect_id in self._event_rects:
                        _, ey1, _, _, _ = self._event_rects[rect_id]
                        self._drag_offset_y = cy - ey1
                    else:
                        self._drag_offset_y = 0
                else:
                    self._drag_event = None
                return

    def _on_drag(self, event):
        if self._drag_event is None:
            return
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        dx = abs(cx - self._drag_start_cx)
        dy = abs(cy - self._drag_start_cy)

        if not self._drag_active:
            if dx + dy < DRAG_THRESHOLD_PX:
                return
            self._drag_active = True
            self._create_ghost()

        self._move_ghost(cx, cy)

    def _on_release(self, event):
        if self._drag_active and self._drag_event is not None:
            cx = self.canvas.canvasx(event.x)
            cy = self.canvas.canvasy(event.y)
            self._drop_event(cx, cy)
        elif self._press_item is not None and not self._drag_active:
            # It was a click, not a drag
            ev = self._event_items.get(self._press_item)
            if ev and self.on_event_clicked:
                self.on_event_clicked(ev)
        elif not self._drag_active and self._drag_event is None:
            # Clicked on empty space
            cx = self.canvas.canvasx(event.x)
            cy = self.canvas.canvasy(event.y)
            self._handle_empty_click(cx, cy)

        self._cleanup_drag()

    def _create_ghost(self):
        if self._press_item not in self._event_rects:
            return
        x1, y1, x2, y2, ev = self._event_rects[self._press_item]
        color = ev.get("color", COLORS["accent"])
        ghost_color = brighten_color(color, 0.15)
        title = ev.get("title", "")

        # Ghost shadow
        sx, sy = SHADOW_OFFSET
        gs = self._rounded_rect(x1 + sx + 1, y1 + sy + 1, x2 + sx + 1, y2 + sy + 1, r=5,
                                fill=SHADOW_COLOR, outline="", tags="ghost")
        self._drag_ghost_ids.append(gs)

        # Ghost block
        gr = self._rounded_rect(x1, y1, x2, y2, r=5,
                                fill=ghost_color, outline=COLORS["accent_hover"],
                                width=2, tags="ghost")
        self._drag_ghost_ids.append(gr)

        # Ghost title
        avail_w = max(10, x2 - x1 - 14)
        gt = self.canvas.create_text(x1 + 9, y1 + 5, text=title,
                                      font=FONTS["grid_event_title"],
                                      fill="#ffffff", anchor="nw", width=avail_w, tags="ghost")
        self._drag_ghost_ids.append(gt)

        # Store ghost dimensions
        self._ghost_w = x2 - x1
        self._ghost_h = y2 - y1
        self._ghost_base_x1 = x1
        self._ghost_base_y1 = y1

        # Dim original
        try:
            self.canvas.itemconfigure(self._press_item, stipple="gray50")
        except Exception:
            pass

    def _move_ghost(self, cx, cy):
        if not self._drag_ghost_ids:
            return
        new_y1 = cy - self._drag_offset_y
        # Snap to 15-min grid
        snap_px = (SNAP_MINUTES / 60.0) * self.hour_height
        new_y1 = round(new_y1 / snap_px) * snap_px

        dates = self._get_dates()
        num_cols = len(dates)
        width = self.canvas.winfo_width()
        grid_width = max(100, width - self.gutter_width)
        col_width = grid_width / num_cols
        col_idx = int((cx - self.gutter_width) // col_width)
        col_idx = max(0, min(num_cols - 1, col_idx))
        new_x1 = self.gutter_width + col_idx * col_width + 4

        dx = new_x1 - self._ghost_base_x1
        dy = new_y1 - self._ghost_base_y1

        # Move all ghost items
        for gid in self._drag_ghost_ids:
            coords = self.canvas.coords(gid)
            if not coords:
                continue
            orig_coords = self.canvas.coords(gid)
            # Reset to base position then apply delta
            # Simpler: just use canvas.move with delta from last position
        # Use moveto approach: delete and recreate is simpler for polygons
        # Instead, track cumulative delta
        if not hasattr(self, '_last_ghost_dx'):
            self._last_ghost_dx = 0
            self._last_ghost_dy = 0

        ddx = dx - self._last_ghost_dx
        ddy = dy - self._last_ghost_dy

        for gid in self._drag_ghost_ids:
            self.canvas.move(gid, ddx, ddy)

        self._last_ghost_dx = dx
        self._last_ghost_dy = dy
        self._ghost_base_x1_current = new_x1
        self._ghost_base_y1_current = new_y1

    def _drop_event(self, cx, cy):
        ev = self._drag_event
        if not ev or not self.on_event_moved:
            return

        # Calculate new time from y position
        new_y1 = cy - self._drag_offset_y
        snap_px = (SNAP_MINUTES / 60.0) * self.hour_height
        new_y1 = round(new_y1 / snap_px) * snap_px

        new_start_minutes = (new_y1 / self.hour_height) * 60
        new_start_minutes = max(0, min(23 * 60 + 45, new_start_minutes))
        new_start_minutes = round(new_start_minutes / SNAP_MINUTES) * SNAP_MINUTES

        # Calculate duration
        try:
            sh, sm = map(int, ev["start_time"].split(":"))
            eh, em = map(int, ev["end_time"].split(":"))
            duration = (eh * 60 + em) - (sh * 60 + sm)
        except (ValueError, KeyError):
            duration = 60

        new_end_minutes = min(23 * 60 + 59, new_start_minutes + duration)
        new_start_h = int(new_start_minutes // 60)
        new_start_m = int(new_start_minutes % 60)
        new_end_h = int(new_end_minutes // 60)
        new_end_m = int(new_end_minutes % 60)

        new_start = f"{new_start_h:02d}:{new_start_m:02d}"
        new_end = f"{new_end_h:02d}:{new_end_m:02d}"

        # Calculate new date from x position
        dates = self._get_dates()
        num_cols = len(dates)
        width = self.canvas.winfo_width()
        grid_width = max(100, width - self.gutter_width)
        col_width = grid_width / num_cols
        col_idx = int((cx - self.gutter_width) // col_width)
        col_idx = max(0, min(num_cols - 1, col_idx))
        new_date = dates[col_idx].strftime("%Y-%m-%d")

        self.on_event_moved(ev, new_date, new_start, new_end)

    def _cleanup_drag(self):
        for gid in self._drag_ghost_ids:
            try:
                self.canvas.delete(gid)
            except Exception:
                pass
        self._drag_ghost_ids.clear()
        if self._press_item:
            try:
                self.canvas.itemconfigure(self._press_item, stipple="")
            except Exception:
                pass
        self._drag_active = False
        self._drag_event = None
        self._press_item = None
        self._last_ghost_dx = 0
        self._last_ghost_dy = 0

    def _handle_empty_click(self, cx, cy):
        if cx < self.gutter_width:
            return
        # Check if we actually hit an event (routine click, etc.)
        items = self.canvas.find_overlapping(cx - 1, cy - 1, cx + 1, cy + 1)
        for item_id in items:
            if item_id in self._event_items:
                ev = self._event_items[item_id]
                if self.on_event_clicked:
                    self.on_event_clicked(ev)
                return

        dates = self._get_dates()
        num_cols = len(dates)
        width = self.canvas.winfo_width()
        grid_width = max(100, width - self.gutter_width)
        col_width = grid_width / num_cols
        col_idx = int((cx - self.gutter_width) // col_width)
        if 0 <= col_idx < num_cols:
            clicked_date = dates[col_idx]
            clicked_hour = int(cy // self.hour_height)
            clicked_hour = max(0, min(23, clicked_hour))
            start_time_str = f"{clicked_hour:02d}:00"
            date_str = clicked_date.strftime("%Y-%m-%d")
            if self.on_slot_clicked:
                self.on_slot_clicked(date_str, start_time_str)
