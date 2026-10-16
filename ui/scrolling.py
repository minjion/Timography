"""Preserve precision-touchpad deltas in canvas and scrollable-frame views."""
import sys
import customtkinter as ctk


class WheelAccumulator:
    def __init__(self):
        self.remainder = 0.0

    def steps(self, delta):
        pixels = -delta / 6 if sys.platform.startswith("win") else -delta
        if pixels * self.remainder < 0:
            self.remainder = 0.0
        self.remainder += pixels
        steps = int(round(self.remainder, 10))
        self.remainder -= steps
        return steps


class StableScrollbar(ctk.CTkScrollbar):
    """Coalesce Tk scroll notifications without entering nested idle loops.

    CTk 6 draws its scrollbar by calling update_idletasks(), which can immediately
    invoke the same canvas's scroll callback again while wrapping changes its
    geometry. Timer callbacks (rather than idle callbacks) break that recursion.
    """
    def __init__(self, *args, **kwargs):
        self._closed = False
        self._pending_values = None
        self._set_after_id = None
        self._draw_after_id = None
        self._drawing = False
        self._pending_draw = None
        super().__init__(*args, **kwargs)

    def set(self, first, last):
        if self._closed:
            return
        values = float(first), float(last)
        if self._pending_values is None and values == self.get():
            return
        self._pending_values = values
        if self._set_after_id is None:
            self._set_after_id = self.after(0, self._flush_values)

    def _flush_values(self):
        self._set_after_id = None
        values, self._pending_values = self._pending_values, None
        if not self._closed and values is not None and values != self.get():
            super().set(*values)

    def _draw(self, no_color_updates=False):
        if self._closed:
            return
        if self._drawing:
            self._pending_draw = no_color_updates if self._pending_draw is None else self._pending_draw and no_color_updates
            if self._draw_after_id is None:
                self._draw_after_id = self.after(0, self._flush_draw)
            return
        self._drawing = True
        try:
            # Retain CTk's renderer/colors, but let Tk paint through its normal
            # event loop. CTk 6's forced update_idletasks() can also remain inside
            # an endless geometry loop even when scroll .set() is deferred.
            super(ctk.CTkScrollbar, self)._draw(no_color_updates)
            first, last = self._get_scrollbar_values_for_minimum_pixel_size()
            recolor = self._draw_engine.draw_rounded_scrollbar(
                self._apply_widget_scaling(self._current_width),
                self._apply_widget_scaling(self._current_height),
                self._apply_widget_scaling(self._corner_radius),
                self._apply_widget_scaling(self._border_spacing),
                first, last, self._orientation,
            )
            if not no_color_updates or recolor:
                button = self._button_hover_color if self._hover_state else self._button_color
                color = self._apply_appearance_mode(button)
                self._canvas.itemconfig("scrollbar_parts", fill=color, outline=color)
                background = self._bg_color if self._fg_color == "transparent" else self._fg_color
                color = self._apply_appearance_mode(background)
                self._canvas.configure(bg=color)
                self._canvas.itemconfig("border_parts", fill=color, outline=color)
        finally:
            self._drawing = False

    def _flush_draw(self):
        self._draw_after_id = None
        pending, self._pending_draw = self._pending_draw, None
        if not self._closed and pending is not None:
            self._draw(no_color_updates=pending)

    def destroy(self):
        self._closed = True
        for callback in (self._set_after_id, self._draw_after_id):
            if callback is not None:
                self.after_cancel(callback)
        self._set_after_id = self._draw_after_id = None
        super().destroy()


class ScrollableFrame(ctk.CTkScrollableFrame):
    """Use CTk's descendant routing without dropping small wheel movements."""
    def __init__(self, *args, **kwargs):
        self._wheel = WheelAccumulator()
        self._global_bindings = []
        super().__init__(*args, **kwargs)
        old = self._scrollbar
        self._scrollbar = StableScrollbar(
            self._parent_frame, orientation=self._orientation,
            command=self._parent_canvas.xview if self._orientation == "horizontal" else self._parent_canvas.yview,
            fg_color=old.cget("fg_color"), button_color=old.cget("button_color"),
            button_hover_color=old.cget("button_hover_color"),
        )
        axis = "xscrollcommand" if self._orientation == "horizontal" else "yscrollcommand"
        self._parent_canvas.configure(**{axis: self._scrollbar.set})
        old.destroy()
        self._create_grid()
        if sys.platform.startswith("win"):
            self._scrollbar._canvas.bind("<MouseWheel>", self._scrollbar_wheel)

    def _scrollbar_wheel(self, event):
        steps = self._wheel.steps(event.delta)
        if steps:
            if self._orientation == "horizontal":
                self._parent_canvas.xview_scroll(steps, "units")
            else:
                self._parent_canvas.yview_scroll(steps, "units")
        return "break"

    def bind_all(self, sequence=None, func=None, add=None):
        binding = super().bind_all(sequence, func, add)
        if func is not None and binding:
            self._global_bindings.append((sequence, binding))
        return binding

    def destroy(self):
        # Tk registers bind_all commands on the root. Remove only our callbacks,
        # preserving scrolling in other views and avoiding retained closed dialogs.
        root = self._root()
        for sequence, binding in self._global_bindings:
            root._unbind(("bind", "all", sequence), binding)
        self._global_bindings.clear()
        super().destroy()

    def _mouse_wheel_all(self, event):
        if not self._check_if_valid_scroll(event.widget):
            return
        if not sys.platform.startswith("win"):
            return super()._mouse_wheel_all(event)
        steps = self._wheel.steps(event.delta)
        horizontal = self._orientation == "horizontal" or self._shift_pressed
        if steps:
            if horizontal:
                self._parent_canvas.xview_scroll(steps, "units")
            else:
                self._parent_canvas.yview_scroll(steps, "units")
