"""Natural Language event parser for Timography.

Parses freeform text like:
- "meeting with Ali tomorrow 3pm"
- "study math friday 2-4pm"
- "gym at 6pm for 45 min"
- "lunch with Sarah next wednesday noon"
into structured event dictionaries.
"""
import re
from datetime import datetime, date, timedelta
from ui.theme import CATEGORY_COLORS

WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

CATEGORY_KEYWORDS = {
    "Study": ["study", "exam", "homework", "class", "lecture", "assignment", "revision", "read", "math", "physics", "chemistry", "biology", "history", "quiz", "course", "lab"],
    "Health": ["gym", "workout", "run", "running", "training", "exercise", "walk", "doctor", "dentist", "med", "pill", "fitness", "yoga", "swim", "stretch"],
    "Work": ["meeting", "sync", "standup", "client", "work", "project", "presentation", "code", "dev", "review", "call with team", "interview", "office"],
    "Social": ["lunch", "dinner", "party", "coffee", "hangout", "movie", "cinema", "beer", "drinks", "friend", "date", "game", "gaming"],
    "Personal": ["groceries", "clean", "laundry", "errand", "buy", "pay", "bank", "shopping", "cook", "relax", "nap", "haircut"],
}


def parse_natural_event(text: str, reference_date: date = None) -> dict:
    """Parse a freeform natural language string into event attributes.

    Returns dict with keys:
    - title: str
    - date: str (YYYY-MM-DD)
    - start_time: str (HH:MM)
    - end_time: str (HH:MM)
    - category: str
    - color: str
    """
    if reference_date is None:
        reference_date = datetime.now().date()

    original_text = text.strip()
    working_text = " " + original_text.lower() + " "

    target_date = reference_date
    start_hour, start_min = 9, 0
    duration_minutes = 60
    explicit_end = None

    # 1. Parse Duration (e.g., "for 2 hours", "for 45 min", "for 1.5h")
    dur_match = re.search(r'\bfor\s+(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m)\b', working_text)
    if dur_match:
        val = float(dur_match.group(1))
        unit = dur_match.group(2)
        if unit.startswith('h'):
            duration_minutes = int(val * 60)
        else:
            duration_minutes = int(val)
        working_text = working_text[:dur_match.start()] + " " + working_text[dur_match.end():]

    # 2. Parse Date
    # Relative days
    if " tomorrow " in working_text:
        target_date = reference_date + timedelta(days=1)
        working_text = working_text.replace(" tomorrow ", " ")
    elif " today " in working_text or " tonight " in working_text:
        target_date = reference_date
        working_text = working_text.replace(" today ", " ").replace(" tonight ", " ")
    elif " yesterday " in working_text:
        target_date = reference_date - timedelta(days=1)
        working_text = working_text.replace(" yesterday ", " ")
    else:
        # Weekday match: e.g. "next friday", "this monday", "on wednesday", "friday"
        wd_match = re.search(r'\b(?:on\s+|this\s+|next\s+)?(monday|mon|tuesday|tue|tues|wednesday|wed|thursday|thu|thur|thurs|friday|fri|saturday|sat|sunday|sun)\b', working_text)
        if wd_match:
            wd_name = wd_match.group(1)
            target_dow = WEEKDAYS[wd_name]
            current_dow = reference_date.weekday()
            diff = (target_dow - current_dow) % 7
            if "next " in wd_match.group(0) and diff == 0:
                diff = 7
            elif diff == 0:
                diff = 7  # default to next occurrence
            target_date = reference_date + timedelta(days=diff)
            working_text = working_text[:wd_match.start()] + " " + working_text[wd_match.end():]
        else:
            # Month + Day match: e.g. "jan 15", "october 24th", "15 sep"
            month_match = re.search(r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?\b', working_text)
            if month_match:
                m_str = month_match.group(1)
                d_num = int(month_match.group(2))
                m_num = MONTHS.get(m_str[:3], reference_date.month)
                year = reference_date.year
                try:
                    target_date = date(year, m_num, d_num)
                    if target_date < reference_date:
                        target_date = date(year + 1, m_num, d_num)
                except ValueError:
                    pass
                working_text = working_text[:month_match.start()] + " " + working_text[month_match.end():]

    # 3. Parse Time Range or Single Time
    # Time range: e.g., "from 2 to 4pm", "2pm - 4pm", "14:00 - 15:30", "2:00-3:30pm", "2-4pm"
    range_match = re.search(r'\b(?:from\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:to|-)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b', working_text)
    if range_match:
        h1, m1, ap1, h2, m2, ap2 = range_match.groups()
        h1 = int(h1)
        m1 = int(m1 or 0)
        h2 = int(h2)
        m2 = int(m2 or 0)

        # Infer am/pm for first if missing
        if ap2 and not ap1:
            ap1 = ap2
            if ap2 == "pm" and h1 > h2:
                ap1 = "am"

        if ap1 == "pm" and h1 < 12:
            h1 += 12
        elif ap1 == "am" and h1 == 12:
            h1 = 0

        if ap2 == "pm" and h2 < 12:
            h2 += 12
        elif ap2 == "am" and h2 == 12:
            h2 = 0

        start_hour, start_min = h1, m1
        explicit_end = (h2, m2)
        working_text = working_text[:range_match.start()] + " " + working_text[range_match.end():]
    else:
        # Single time: e.g., "at 3pm", "at 15:30", "3:30pm", "noon", "midnight", "morning"
        if " noon " in working_text:
            start_hour, start_min = 12, 0
            working_text = working_text.replace(" noon ", " ")
        elif " midnight " in working_text:
            start_hour, start_min = 0, 0
            working_text = working_text.replace(" midnight ", " ")
        elif " morning " in working_text:
            start_hour, start_min = 9, 0
            working_text = working_text.replace(" morning ", " ")
        elif " afternoon " in working_text:
            start_hour, start_min = 14, 0
            working_text = working_text.replace(" afternoon ", " ")
        elif " evening " in working_text or " tonight " in original_text.lower():
            start_hour, start_min = 18, 0
            working_text = working_text.replace(" evening ", " ")
        else:
            time_match = re.search(r'\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b', working_text)
            if time_match:
                h_str, m_str, ap = time_match.groups()
                h = int(h_str)
                m = int(m_str or 0)
                if ap:
                    if ap == "pm" and h < 12:
                        h += 12
                    elif ap == "am" and h == 12:
                        h = 0
                    start_hour, start_min = h, m
                    working_text = working_text[:time_match.start()] + " " + working_text[time_match.end():]
                elif "at " in time_match.group(0) or m_str is not None:
                    if 1 <= h <= 6:
                        h += 12  # assume afternoon for small numbers like "at 3"
                    start_hour, start_min = h, m
                    working_text = working_text[:time_match.start()] + " " + working_text[time_match.end():]

    # Calculate end time
    if explicit_end:
        end_hour, end_min = explicit_end
    else:
        start_total = start_hour * 60 + start_min
        end_total = min(23 * 60 + 59, start_total + duration_minutes)
        end_hour = end_total // 60
        end_min = end_total % 60

    # 4. Clean up title
    cleaned_title = re.sub(r'\s+', ' ', working_text).strip()
    # Remove dangling prepositions like "at", "on", "for", "with"
    cleaned_title = re.sub(r'^(?:at|on|for|in)\s+', '', cleaned_title, flags=re.I)
    cleaned_title = re.sub(r'\s+(?:at|on|for|in)$', '', cleaned_title, flags=re.I)

    if not cleaned_title:
        cleaned_title = original_text.capitalize()
    else:
        cleaned_title = cleaned_title.capitalize()

    # 5. Detect Category & Color
    detected_category = "Work"
    lower_orig = original_text.lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in lower_orig for kw in keywords):
            detected_category = cat
            break

    color = CATEGORY_COLORS.get(detected_category, "#58a6ff")

    return {
        "title": cleaned_title,
        "date": target_date.strftime("%Y-%m-%d"),
        "start_time": f"{start_hour:02d}:{start_min:02d}",
        "end_time": f"{end_hour:02d}:{end_min:02d}",
        "category": detected_category,
        "color": color,
    }
