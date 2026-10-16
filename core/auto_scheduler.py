"""Smart Auto-Scheduler and Gap Suggestion Engine for Timography."""
from core.database import TimographyDB
from datetime import datetime


class AutoScheduler:
    def __init__(self, db: TimographyDB):
        self.db = db

    def suggest_best_slot(self, date_str: str, duration_minutes: int = 60, category: str = "Study") -> dict | None:
        """Find the optimal free time window for a task based on category preferences."""
        free_slots = self.db.find_free_slots(date_str, duration_minutes, min_hour=8, max_hour=22)
        now = datetime.now()
        if date_str < now.date().isoformat():
            return None
        if date_str == now.date().isoformat():
            next_quarter = ((now.hour * 60 + now.minute) // 15 + 1) * 15
            remaining_slots = []
            for slot in free_slots:
                sh, sm = map(int, slot["start"].split(":"))
                eh, em = map(int, slot["max_end"].split(":"))
                start, end = max(sh * 60 + sm, next_quarter), eh * 60 + em
                if end - start >= duration_minutes:
                    remaining_slots.append({**slot, "start": f"{start // 60:02d}:{start % 60:02d}",
                        "end": f"{(start + duration_minutes) // 60:02d}:{(start + duration_minutes) % 60:02d}",
                        "available_minutes": end - start})
            free_slots = remaining_slots
        if not free_slots:
            return None

        # Preferred peak hours (in minutes from midnight)
        category_preferences = {
            "Study": [(14 * 60, 18 * 60), (9 * 60, 12 * 60)],      # Afternoon or late morning
            "Work": [(9 * 60, 12 * 60), (13 * 60, 17 * 60)],       # Standard work hours
            "Health": [(17 * 60, 20 * 60), (7 * 60, 9 * 60)],      # Evening or early morning
            "Social": [(12 * 60, 14 * 60), (18 * 60, 21 * 60)],    # Lunch or dinner hours
            "Personal": [(12 * 60, 13 * 60), (19 * 60, 21 * 60)],  # Midday or evening
        }

        prefs = category_preferences.get(category, [(10 * 60, 16 * 60)])

        def score_slot(slot):
            sh, sm = map(int, slot["start"].split(":"))
            slot_start_min = sh * 60 + sm
            # Distance to closest preferred window
            min_dist = 9999
            for p_start, p_end in prefs:
                if p_start <= slot_start_min <= p_end:
                    min_dist = 0
                    break
                dist = min(abs(slot_start_min - p_start), abs(slot_start_min - p_end))
                min_dist = min(min_dist, dist)

            # Bonus if slot doesn't waste excessive spare time (tight fit)
            waste_penalty = abs(slot["available_minutes"] - duration_minutes) * 0.2
            return min_dist + waste_penalty

        # A free interval may start before a preferred window. Consider starts
        # inside it, rather than ranking only the beginning of each gap.
        candidates = list(free_slots)
        for slot in free_slots:
            start = int(slot["start"][:2]) * 60 + int(slot["start"][3:])
            end = int(slot["max_end"][:2]) * 60 + int(slot["max_end"][3:])
            for preferred_start, preferred_end in prefs:
                candidate = max(start, preferred_start)
                if candidate + duration_minutes <= min(end, preferred_end):
                    candidates.append({**slot, "start": f"{candidate // 60:02d}:{candidate % 60:02d}",
                        "end": f"{(candidate + duration_minutes) // 60:02d}:{(candidate + duration_minutes) % 60:02d}",
                        "available_minutes": end - candidate})
        candidates.sort(key=score_slot)
        return candidates[0]

    def get_smart_suggestions(self, date_str: str) -> list[dict]:
        """Analyze the day's schedule and return actionable productivity insights & suggestions."""
        events = self.db.get_events_for_date(date_str, include_routines=True)
        suggestions = []

        if not events:
            return [{
                "type": "empty_day",
                "icon": "☀️",
                "message": "Completely free day today! Schedule a focused deep work session or enjoy recharging.",
                "action": "schedule_study",
                "suggested_duration": 90
            }]

        parsed_events = []
        for ev in events:
            try:
                sh, sm = map(int, ev["start_time"].split(":"))
                eh, em = map(int, ev["end_time"].split(":"))
                parsed_events.append({
                    "start": sh * 60 + sm,
                    "end": eh * 60 + em,
                    "title": ev.get("title", ""),
                    "category": ev.get("category", "")
                })
            except Exception:
                continue

        parsed_events.sort(key=lambda x: x["start"])

        # Merge nested/overlapping events before measuring continuous busy spans.
        blocks = []
        for event in parsed_events:
            if event["end"] <= event["start"]:
                continue
            if blocks and event["start"] - blocks[-1][1] < 15:
                blocks[-1][1] = max(blocks[-1][1], event["end"])
            else:
                blocks.append([event["start"], event["end"]])
        for start, end in blocks:
            duration = end - start
            if duration >= 180:
                suggestions.append({"type": "fatigue_warning", "icon": "☕",
                    "message": f"{duration // 60}h+ of continuous activity "
                               f"({start // 60:02d}:{start % 60:02d} - {end // 60:02d}:{end % 60:02d}). "
                               "Remember to take a breather!", "action": None})

        # Check for high-value open gaps (45 to 120 mins) during midday/afternoon
        free_slots = self.db.find_free_slots(date_str, duration_minutes=45, min_hour=9, max_hour=19)
        for slot in free_slots:
            if 45 <= slot["available_minutes"] <= 120:
                suggestions.append({
                    "type": "gap_opportunity",
                    "icon": "⚡",
                    "message": f"{slot['available_minutes']} min free gap at {slot['start']}. Perfect time for a quick study review or workout!",
                    "action": "fill_gap",
                    "slot": slot
                })
                break  # Show at most one gap highlight

        # Check if study category is missing
        study_hours = sum((e["end"] - e["start"]) for e in parsed_events if e["category"].lower() == "study")
        if study_hours == 0 and free_slots:
            suggestions.append({
                "type": "missing_study",
                "icon": "📚",
                "message": "No study blocks scheduled today. Want to auto-schedule 45 minutes?",
                "action": "auto_study",
                "suggested_duration": 45
            })

        return suggestions
