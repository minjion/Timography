"""Shared validation for schedule input and persisted settings."""
import re
from datetime import date


def validate_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Use a date in YYYY-MM-DD format.")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Enter a valid calendar date.") from exc


def time_minutes(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError("Use a time in HH:MM format (00:00–23:59).")
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def validate_schedule(data):
    if not data.get("title", "").strip():
        raise ValueError("Enter a title.")
    if "date" in data:
        validate_date(data["date"])
    start = time_minutes(data["start_time"])
    end = time_minutes(data["end_time"])
    if end <= start:
        raise ValueError("End time must be after start time on the same day.")
    if "color" in data and not re.fullmatch(r"#[0-9a-fA-F]{6}", data["color"] or ""):
        raise ValueError("Choose a valid color.")
    if int(data.get("reminder_minutes", 0)) < 0:
        raise ValueError("Reminder minutes cannot be negative.")


SETTING_RANGES = {
    "pomo_work": (1, 180), "pomo_short_break": (1, 60),
    "pomo_long_break": (1, 120), "pomo_cycles": (1, 12),
    "streak_goal_minutes": (1, 1440), "morning_briefing_hour": (0, 23),
    "default_reminder": (0, 120),
}


def validate_settings(settings):
    if "theme" in settings and settings["theme"] not in ("light", "dark"):
        raise ValueError("Select a light or dark theme.")
    if "week_start" in settings and settings["week_start"] not in ("monday", "sunday"):
        raise ValueError("Select Monday or Sunday as the first day of the week.")
    for key, (low, high) in SETTING_RANGES.items():
        if key not in settings:
            continue
        try:
            value = int(settings[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key.replace('_', ' ').capitalize()} must be a whole number.") from exc
        if not low <= value <= high:
            raise ValueError(f"{key.replace('_', ' ').capitalize()} must be between {low} and {high}.")
