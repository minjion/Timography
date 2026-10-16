"""Timography theme constants — GitHub Dark inspired with centralized UI scaling."""

# ---------------------------------------------------------------------------
# Global UI density scale
#   1.0  = original compact sizing
# Display DPI is applied by CustomTkinter; density stays at 1.0.
# ---------------------------------------------------------------------------
UI_SCALE = 1.0  # CustomTkinter already applies the display's DPI scaling.


def _s(px: int) -> int:
    """Scale a pixel value by the global UI density factor."""
    return round(px * UI_SCALE)


# ---------------------------------------------------------------------------
# Color Palettes — Dark (GitHub Dark) and Light (GitHub Light)
# ---------------------------------------------------------------------------
DARK_COLORS = {
    "bg_primary": "#0d1117",
    "bg_secondary": "#161b22",
    "bg_tertiary": "#21262d",
    "accent": "#58a6ff",
    "accent_hover": "#79c0ff",
    "accent_red": "#f85149",
    "accent_green": "#3fb950",
    "accent_yellow": "#d29922",
    "accent_purple": "#bc8cff",
    "accent_orange": "#f0883e",
    "text_primary": "#f0f6fc",
    "text_secondary": "#8b949e",
    "text_muted": "#8b949e",
    "on_accent": "#0d1117",
    "border": "#30363d",
    "transparent": "#000001",
    "grid_line": "#21262d",
    "grid_line_subtle": "#181d24",
    "grid_hour_text": "#8b949e",
    "current_time_line": "#ea4335",
    "today_bg": "#1f2a3d",
    "today_accent": "#58a6ff",
    "routine_tag": "#bc8cff",
    "shadow": "#080b10",
    "hour_band_even": "#0d1117",
    "hour_band_odd": "#0f1319",
    "today_column_tint": "#111d2e",
}

LIGHT_COLORS = {
    "bg_primary": "#f8f9fa",
    "bg_secondary": "#ffffff",
    "bg_tertiary": "#edf2f7",
    "accent": "#2563eb",
    "accent_hover": "#1d4ed8",
    "accent_red": "#dc2626",
    "accent_green": "#16a34a",
    "accent_yellow": "#d97706",
    "accent_purple": "#7c3aed",
    "accent_orange": "#ea580c",
    "text_primary": "#0f172a",
    "text_secondary": "#475569",
    "text_muted": "#64748b",
    "on_accent": "#ffffff",
    "border": "#e2e8f0",
    "transparent": "#000001",
    "grid_line": "#e2e8f0",
    "grid_line_subtle": "#f1f5f9",
    "grid_hour_text": "#64748b",
    "current_time_line": "#dc2626",
    "today_bg": "#dbeafe",
    "today_accent": "#2563eb",
    "routine_tag": "#7c3aed",
    "shadow": "#cbd5e1",
    "hour_band_even": "#ffffff",
    "hour_band_odd": "#f8f9fa",
    "today_column_tint": "#eff6ff",
}

# Active palette — mutable dict, contents swapped by apply_theme()
COLORS = dict(DARK_COLORS)

# Current theme mode tracker
_current_theme = "dark"


def get_current_theme() -> str:
    """Return the current theme mode ('dark' or 'light')."""
    return _current_theme


def theme_color(key: str) -> tuple[str, str]:
    """CTk light/dark pairs; native Tk canvases use COLORS and redraw instead."""
    return LIGHT_COLORS[key], DARK_COLORS[key]


def canvas_font(font, scale=1.0):
    """Tk canvas fonts use explicit pixels instead of point-based DPI scaling."""
    return (font[0], -round(font[1] * scale), *font[2:])


def text_on_color(color):
    """Readable text on fixed category colors in either appearance mode."""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return "#0d1117" if (r * 299 + g * 587 + b * 114) / 1000 > 145 else "#ffffff"


def apply_theme(mode: str):
    """Switch the active color palette. mode = 'dark' or 'light'.

    Because COLORS is mutated in-place (same dict object), every module
    that imported ``from ui.theme import COLORS`` sees the new values
    immediately on next read.
    """
    global _current_theme, SHADOW_COLOR, HOUR_BAND_EVEN, HOUR_BAND_ODD, TODAY_COLUMN_TINT
    mode = mode.lower() if isinstance(mode, str) else "dark"
    if mode not in ("light", "dark"):
        mode = "dark"
    _current_theme = mode
    source = LIGHT_COLORS if mode == "light" else DARK_COLORS
    COLORS.clear()
    COLORS.update(source)
    # Keep legacy module-level aliases in sync
    SHADOW_COLOR = COLORS["shadow"]
    HOUR_BAND_EVEN = COLORS["hour_band_even"]
    HOUR_BAND_ODD = COLORS["hour_band_odd"]
    TODAY_COLUMN_TINT = COLORS["today_column_tint"]
    # Tell CustomTkinter
    try:
        import customtkinter as ctk
        defaults = ctk.ThemeManager.theme
        defaults["CTkOptionMenu"].update(
            fg_color=theme_color("bg_tertiary"), text_color=theme_color("text_primary"),
            button_color=theme_color("bg_tertiary"), button_hover_color=theme_color("border"),
        )
        defaults["CTkSegmentedButton"].update(
            fg_color=theme_color("bg_tertiary"), text_color=theme_color("text_primary"),
            selected_color=theme_color("today_bg"), selected_hover_color=theme_color("today_bg"),
            unselected_color=theme_color("bg_tertiary"), unselected_hover_color=theme_color("border"),
        )
        defaults["CTkCheckBox"].update(text_color=theme_color("text_primary"),
            border_color=theme_color("border"), checkmark_color=theme_color("on_accent"))
        ctk.set_appearance_mode(mode)
    except ImportError:
        pass


CATEGORY_COLORS = {
    "Work": "#58a6ff",
    "Personal": "#3fb950",
    "Health": "#f85149",
    "Study": "#bc8cff",
    "Social": "#f0883e",
    "Routine": "#d29922",
    "Other": "#8b949e",
}

FONTS = {
    "heading":          ("Segoe UI", 20, "bold"),
    "subheading":       ("Segoe UI", 16, "bold"),
    "title_medium":     ("Segoe UI", 15, "bold"),
    "body":             ("Segoe UI", 14),
    "body_bold":        ("Segoe UI", 14, "bold"),
    "small":            ("Segoe UI", 12),
    "small_bold":       ("Segoe UI", 12, "bold"),
    "micro":            ("Segoe UI", 11),
    "time":             ("Consolas", 13),
    "time_large":       ("Consolas", 16, "bold"),
    "widget_title":     ("Segoe UI", 17, "bold"),
    "widget_event":     ("Segoe UI", 13),
    "widget_time":      ("Consolas", 12),
    "grid_hour":        ("Segoe UI", 11),
    "grid_event_title": ("Segoe UI", 12, "bold"),
    "grid_event_time":  ("Segoe UI", 11),
}

WIDGET_CORNER_RADIUS = 15
CARD_CORNER_RADIUS = 10
BUTTON_CORNER_RADIUS = 8
EVENT_CORNER_RADIUS = 6

# Shadow and depth (kept as module-level for backward compat — updated by apply_theme)
SHADOW_COLOR = COLORS["shadow"]
SHADOW_OFFSET = (2, 2)

# Grid visual (kept as module-level for backward compat — updated by apply_theme)
HOUR_BAND_EVEN = COLORS["hour_band_even"]
HOUR_BAND_ODD = COLORS["hour_band_odd"]
TODAY_COLUMN_TINT = COLORS["today_column_tint"]


# Animation timing (milliseconds)
ANIM_SCROLL_MS = 350
ANIM_FADE_MS = 200
ANIM_SNAP_MS = 150
ANIM_HOVER_MS = 120
DRAG_THRESHOLD_PX = 5
SNAP_MINUTES = 15
CURRENT_TIME_TICK_MS = 15000     # update red line every 15 seconds

# ---------------------------------------------------------------------------
# Centralized layout dimensions — every UI file pulls from here
# ---------------------------------------------------------------------------
SIZES = {
    # Main window
    "window_width": _s(1200),
    "window_height": _s(780),
    "window_min_w": _s(900),
    "window_min_h": _s(600),

    # Top navigation bar
    "top_bar_height": _s(52),
    "tab_btn_width": _s(100),
    "tab_btn_height": _s(34),
    "nav_btn_size": _s(30),
    "today_btn_width": _s(56),
    "mode_btn_width": _s(44),
    "mode_btn_height": _s(28),
    "create_btn_width": _s(90),
    "quick_btn_width": _s(72),

    # Sidebar
    "sidebar_width": _s(240),
    "mini_cal_day_size": _s(32),
    "mini_cal_nav_btn": _s(26),
    "category_checkbox": _s(18),
    "streak_height": _s(28),

    # Time grid
    "hour_height": _s(56),
    "gutter_width": _s(52),
    "header_height": _s(54),
    "event_min_height": _s(24),
    "day_badge_size": _s(28),

    # Checklist
    "checkbox_size": _s(20),
    "row_height": _s(38),
    "progress_bar_h": _s(6),
    "filter_btn_height": _s(28),
    "checklist_entry_h": _s(36),
    "checklist_add_btn_w": _s(80),

    # Event dialog
    "dialog_width": _s(440),
    "dialog_height": _s(600),
    "dialog_min_w": _s(400),
    "dialog_min_h": _s(500),
    "field_height": _s(34),
    "action_btn_height": _s(38),
    "action_bar_height": _s(54),
    "color_dot_size": _s(32),
    "time_menu_width": _s(70),

    # Desktop widget
    "widget_width": _s(300),
    "widget_height": _s(460),
    "widget_card_height": _s(68),
    "widget_btn_size": _s(28),

    # Analytics
    "kpi_value_font_size": _s(24),
    "heatmap_cell": _s(11),
    "heatmap_pad": _s(3),

    # Pomodoro
    "timer_font_size": _s(64),
    "pomo_btn_width": _s(120),
    "pomo_btn_height": _s(38),

    # Exams
    "exam_add_btn_w": _s(150),
    "exam_add_btn_h": _s(32),
    "exam_badge_w": _s(100),
    "exam_badge_h": _s(26),

    # Routines
    "routine_action_btn_w": _s(130),
    "routine_action_btn_h": _s(32),
    "routine_edit_btn_w": _s(50),
    "routine_small_btn": _s(26),

    # Quick-Add
    "quick_add_width": _s(520),
    "quick_add_height": _s(260),
    "quick_add_entry_h": _s(38),

    # Misc shared
    "small_icon_btn": _s(26),
    "color_swatch": _s(28),
}
