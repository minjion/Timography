"""Lightweight animation engine for Timography using tkinter .after() loops."""
from time import monotonic


def ease_out_cubic(t: float) -> float:
    """Smooth deceleration — fast start, gentle stop."""
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_quad(t: float) -> float:
    """Smooth start and end."""
    if t < 0.5:
        return 2.0 * t * t
    return 1.0 - (-2.0 * t + 2.0) ** 2 / 2.0


def ease_out_quad(t: float) -> float:
    return 1.0 - (1.0 - t) ** 2


def ease_out_back(t: float) -> float:
    """Slight overshoot bounce."""
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between a and b by factor t (0-1)."""
    return a + (b - a) * t


def lerp_color(hex_a: str, hex_b: str, t: float) -> str:
    """Interpolate between two hex colors by factor t (0..1)."""
    t = max(0.0, min(1.0, t))
    ra, ga, ba = int(hex_a[1:3], 16), int(hex_a[3:5], 16), int(hex_a[5:7], 16)
    rb, gb, bb = int(hex_b[1:3], 16), int(hex_b[3:5], 16), int(hex_b[5:7], 16)
    r = int(ra + (rb - ra) * t)
    g = int(ga + (gb - ga) * t)
    b = int(ba + (bb - ba) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def brighten_color(hex_color: str, factor: float = 0.25) -> str:
    """Brighten a hex color by mixing it toward white."""
    return lerp_color(hex_color, "#ffffff", factor)


def darken_color(hex_color: str, factor: float = 0.3) -> str:
    """Darken a hex color by mixing it toward black."""
    return lerp_color(hex_color, "#000000", factor)


class Animation:
    """Runs a tween animation over duration_ms, calling on_frame(progress) each tick.

    Usage:
        anim = Animation(widget, 300, on_frame=lambda p: ..., on_complete=lambda: ...)
        anim.start()
    """

    FPS = 60
    INTERVAL = max(8, 1000 // FPS)  # ~16ms per frame

    def __init__(self, widget, duration_ms: int, on_frame=None, on_complete=None,
                 easing=ease_out_cubic):
        self.widget = widget
        self.duration_ms = max(1, duration_ms)
        self.on_frame = on_frame
        self.on_complete = on_complete
        self.easing = easing
        self._elapsed = 0
        self._running = False
        self._after_id = None

    def start(self):
        self.stop()
        self._elapsed = 0
        self._started_at = monotonic()
        self._running = True
        self._tick()

    def stop(self):
        self._running = False
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _tick(self):
        if not self._running:
            return
        self._elapsed = (monotonic() - self._started_at) * 1000
        raw_t = min(1.0, self._elapsed / self.duration_ms)
        eased_t = self.easing(raw_t)

        if self.on_frame:
            try:
                self.on_frame(eased_t)
            except Exception:
                self._running = False
                return

        if raw_t >= 1.0:
            self._running = False
            if self.on_complete:
                try:
                    self.on_complete()
                except Exception:
                    pass
            return

        self._after_id = self.widget.after(self.INTERVAL, self._tick)


def animate_scroll(canvas, target_y: float, duration_ms: int = 350):
    """Smoothly scroll a canvas to a target y fraction (0.0 - 1.0)."""
    start_y = canvas.yview()[0]
    target_frac = max(0.0, min(1.0, target_y))

    def on_frame(t):
        current = lerp(start_y, target_frac, t)
        canvas.yview_moveto(current)

    anim = Animation(canvas, duration_ms, on_frame=on_frame, easing=ease_out_cubic)
    anim.start()
    return anim


def fade_window(window, target_alpha: float = 1.0, duration_ms: int = 200):
    """Fade a toplevel window from current alpha to target alpha."""
    try:
        start_alpha = float(window.attributes('-alpha'))
    except Exception:
        start_alpha = 0.0

    def on_frame(t):
        try:
            current = lerp(start_alpha, target_alpha, t)
            window.attributes('-alpha', current)
        except Exception:
            pass

    anim = Animation(window, duration_ms, on_frame=on_frame, easing=ease_out_quad)
    anim.start()
    return anim
