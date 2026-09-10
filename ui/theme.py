"""Timography theme constants — GitHub Dark inspired."""

COLORS = {
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
    "text_muted": "#484f58",
    "border": "#30363d",
    "transparent": "#000001",
    "grid_line": "#21262d",
    "grid_line_subtle": "#181d24",
    "grid_hour_text": "#8b949e",
    "current_time_line": "#ea4335",
    "today_bg": "#1f2a3d",
    "today_accent": "#58a6ff",
    "routine_tag": "#bc8cff",
}

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
    "heading": ("Segoe UI", 18, "bold"),
    "subheading": ("Segoe UI", 14, "bold"),
    "title_medium": ("Segoe UI", 13, "bold"),
    "body": ("Segoe UI", 12),
    "body_bold": ("Segoe UI", 12, "bold"),
    "small": ("Segoe UI", 10),
    "small_bold": ("Segoe UI", 10, "bold"),
    "micro": ("Segoe UI", 9),
    "time": ("Consolas", 11),
    "time_large": ("Consolas", 14, "bold"),
    "widget_title": ("Segoe UI", 15, "bold"),
    "widget_event": ("Segoe UI", 11),
    "widget_time": ("Consolas", 10),
    "grid_hour": ("Segoe UI", 9),
    "grid_event_title": ("Segoe UI", 10, "bold"),
    "grid_event_time": ("Segoe UI", 9),
}

WIDGET_CORNER_RADIUS = 15
CARD_CORNER_RADIUS = 10
BUTTON_CORNER_RADIUS = 8
EVENT_CORNER_RADIUS = 6

# Shadow and depth
SHADOW_COLOR = "#080b10"
SHADOW_OFFSET = (2, 2)

# Grid visual
HOUR_BAND_EVEN = "#0d1117"       # default bg for even hours
HOUR_BAND_ODD = "#0f1319"        # slightly lighter for odd hours
TODAY_COLUMN_TINT = "#111d2e"     # blue tint for today column

# Animation timing (milliseconds)
ANIM_SCROLL_MS = 350
ANIM_FADE_MS = 200
ANIM_SNAP_MS = 150
ANIM_HOVER_MS = 120
DRAG_THRESHOLD_PX = 5
SNAP_MINUTES = 15
CURRENT_TIME_TICK_MS = 15000     # update red line every 15 seconds
