"""GitHub-style activity and productivity heatmap component for Timography."""
from datetime import datetime, timedelta
import tkinter as tk
import customtkinter as ctk
from ui.theme import theme_color
from ui.theme import COLORS, FONTS
from ui.tooltip import CanvasTooltip

# Heatmap color scale (GitHub inspired)
HEAT_LEVELS = [
    (0.0, "#161b22"),     # 0h
    (1.5, "#0e4429"),     # up to 1.5h
    (3.5, "#006d32"),     # up to 3.5h
    (6.0, "#26a641"),     # up to 6.0h
    (999, "#39d353"),     # > 6h
]


class ActivityHeatmap(ctk.CTkFrame):
    def __init__(self, master, data_by_date: dict = None, weeks: int = 24, **kwargs):
        super().__init__(master, fg_color=theme_color("bg_secondary"), corner_radius=8, **kwargs)
        self.data_by_date = data_by_date or {}
        self.weeks = weeks
        self.cell_size = 11
        self.cell_pad = 3
        self._build_ui()

    def _build_ui(self):
        self.canvas_w = self.weeks * (self.cell_size + self.cell_pad) + 40
        self.canvas_h = 7 * (self.cell_size + self.cell_pad) + 30

        self.canvas = tk.Canvas(
            self,
            bg=COLORS["bg_secondary"],
            bd=0,
            highlightthickness=0,
            width=self.canvas_w,
            height=self.canvas_h
        )
        self.canvas.pack(fill="both", expand=True, padx=8, pady=8)
        self.tooltip = CanvasTooltip(self.canvas)
        self.canvas.bind("<Configure>", lambda e: self.render())
        self.render()

    def set_data(self, data_by_date: dict):
        self.data_by_date = data_by_date or {}
        self.render()

    def reapply_theme(self):
        """Re-skin heatmap in-place when theme toggles."""
        try:
            self.configure(fg_color=theme_color("bg_secondary"))
            self.canvas.configure(bg=COLORS["bg_secondary"])
        except Exception:
            pass
        self.render()

    def render(self):
        self.tooltip.clear()
        self.canvas.delete("all")
        width = self.canvas.winfo_width()
        if width > 40:
            self.cell_size = max(5, min(11, int((width - 40) / self.weeks) - self.cell_pad))
        today = datetime.now().date()
        # Find ending Sunday
        end_date = today + timedelta(days=(6 - today.weekday()))
        start_date = end_date - timedelta(weeks=self.weeks) + timedelta(days=1)

        # Day labels: Mon, Wed, Fri
        day_names = ["M", "", "W", "", "F", "", ""]
        for row, name in enumerate(day_names):
            if name:
                y = 18 + row * (self.cell_size + self.cell_pad) + 5
                self.canvas.create_text(12, y, text=name, font=FONTS["micro"], fill=COLORS["text_muted"])

        curr = start_date
        col = 0
        while curr <= end_date:
            row = curr.weekday()
            x1 = 26 + col * (self.cell_size + self.cell_pad)
            y1 = 18 + row * (self.cell_size + self.cell_pad)
            x2 = x1 + self.cell_size
            y2 = y1 + self.cell_size

            d_str = curr.strftime("%Y-%m-%d")
            hours = self.data_by_date.get(d_str, 0.0)

            # Determine color
            if hours <= 0:
                fill_color = COLORS["bg_tertiary"]
            else:
                fill_color = HEAT_LEVELS[-1][1]
                for threshold, col_val in HEAT_LEVELS[1:]:
                    if hours <= threshold:
                        fill_color = col_val
                        break

            cell_tag = f"cell_{d_str}"
            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                fill=fill_color,
                outline=COLORS["border"] if hours == 0 else "",
                tags=cell_tag
            )

            # Tooltip
            tip_text = f"{curr.strftime('%a, %b %d')}\n{hours:.1f} hours scheduled"
            self.tooltip.bind_item(cell_tag, tip_text)

            if row == 6:
                col += 1
            curr += timedelta(days=1)
