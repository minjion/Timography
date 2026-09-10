"""Floating tooltip widget for canvas items and CTk widgets."""
import tkinter as tk
from ui.theme import COLORS, FONTS


class CanvasTooltip:
    """Shows a dark floating tooltip near the cursor when hovering over tagged canvas items.

    Usage:
        tooltip = CanvasTooltip(canvas)
        tooltip.bind_item(item_id, "Title\\n09:00 - 10:00\\nTeam standup")
    """

    OFFSET_X = 12
    OFFSET_Y = 16
    PADDING_X = 10
    PADDING_Y = 6
    SHOW_DELAY_MS = 400
    FADE_IN_MS = 120

    def __init__(self, canvas: tk.Canvas):
        self.canvas = canvas
        self._tip_window = None
        self._after_id = None
        self._current_text = ""

    def bind_item(self, item_id, text: str):
        """Bind tooltip to a canvas item by its id."""
        self.canvas.tag_bind(item_id, "<Enter>", lambda e, t=text: self._schedule_show(e, t))
        self.canvas.tag_bind(item_id, "<Leave>", lambda e: self._hide())
        self.canvas.tag_bind(item_id, "<Motion>", lambda e, t=text: self._on_motion(e, t))

    def _schedule_show(self, event, text):
        self._cancel()
        self._current_text = text
        self._after_id = self.canvas.after(
            self.SHOW_DELAY_MS,
            lambda: self._show(event, text)
        )

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.canvas.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _on_motion(self, event, text):
        if self._tip_window and self._current_text == text:
            # Move existing tooltip
            x = event.x_root + self.OFFSET_X
            y = event.y_root + self.OFFSET_Y
            self._tip_window.geometry(f"+{x}+{y}")

    def _show(self, event, text):
        self._hide()
        x = event.x_root + self.OFFSET_X
        y = event.y_root + self.OFFSET_Y

        self._tip_window = tw = tk.Toplevel(self.canvas)
        tw.wm_overrideredirect(True)
        tw.wm_attributes("-topmost", True)
        tw.configure(bg=COLORS["bg_tertiary"])

        # Attempt fade-in
        try:
            tw.attributes("-alpha", 0.0)
        except Exception:
            pass

        frame = tk.Frame(tw, bg=COLORS["bg_tertiary"], padx=self.PADDING_X, pady=self.PADDING_Y)
        frame.pack()

        label = tk.Label(
            frame,
            text=text,
            font=FONTS["small"],
            fg=COLORS["text_primary"],
            bg=COLORS["bg_tertiary"],
            justify="left",
            wraplength=260
        )
        label.pack()

        tw.geometry(f"+{x}+{y}")

        # Fade in
        self._fade_in(tw, 0.0, 1.0, 0)

    def _fade_in(self, window, current_alpha, target_alpha, step):
        if window is None or not window.winfo_exists():
            return
        steps = max(1, self.FADE_IN_MS // 16)
        if step >= steps:
            try:
                window.attributes("-alpha", target_alpha)
            except Exception:
                pass
            return
        progress = step / steps
        alpha = current_alpha + (target_alpha - current_alpha) * progress
        try:
            window.attributes("-alpha", alpha)
        except Exception:
            return
        window.after(16, lambda: self._fade_in(window, current_alpha, target_alpha, step + 1))

    def _hide(self):
        self._cancel()
        self._current_text = ""
        if self._tip_window:
            try:
                self._tip_window.destroy()
            except Exception:
                pass
            self._tip_window = None
