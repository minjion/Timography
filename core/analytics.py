"""Productivity analytics, focus score, and insight algorithms for Timography."""
from datetime import datetime, date, timedelta
from core.database import TimographyDB


def calculate_focus_score(db: TimographyDB, date_str: str) -> dict:
    """Calculate daily Focus Score (0 to 100).

    Factors:
    1. Uninterrupted block length (longer blocks = higher score)
    2. Context switching penalty (switching categories frequently = lower score)
    3. Checklist task completion rate (higher completion = higher score)
    4. Pomodoro focus time bonus
    """
    events = db.get_events_for_date(date_str, include_routines=True)
    if not events:
        return {"score": 50, "rating": "Neutral", "advice": "No events scheduled today."}

    parsed = []
    for ev in events:
        try:
            sh, sm = map(int, ev["start_time"].split(":"))
            eh, em = map(int, ev["end_time"].split(":"))
            dur = (eh * 60 + em) - (sh * 60 + sm)
            if dur > 0:
                parsed.append({"dur": dur, "cat": ev.get("category", "Other")})
        except Exception:
            continue

    if not parsed:
        return {"score": 50, "rating": "Neutral", "advice": "No valid event durations found."}

    # 1. Block length score (target: average block >= 60 min)
    avg_block = sum(p["dur"] for p in parsed) / len(parsed)
    block_score = min(40, int((avg_block / 60.0) * 40))

    # 2. Context switching penalty
    cat_switches = 0
    for i in range(1, len(parsed)):
        if parsed[i]["cat"] != parsed[i - 1]["cat"]:
            cat_switches += 1
    switch_score = max(5, 30 - (cat_switches * 5))

    # 3. Checklist completion score
    stats = db.get_checklist_stats(date_str)
    check_score = int(stats["percent"] * 0.2)  # up to 20 pts

    # 4. Pomodoro bonus (up to 10 pts)
    pomo_mins = db.get_today_pomodoro_minutes(date_str)
    pomo_score = min(10, int((pomo_mins / 50.0) * 10))

    total_score = max(10, min(100, block_score + switch_score + check_score + pomo_score))

    if total_score >= 80:
        rating = "Deep Focus"
        advice = "Outstanding concentration! Minimal fragmentation and high task completion."
    elif total_score >= 60:
        rating = "Good Momentum"
        advice = "Solid productivity with steady progress across scheduled blocks."
    else:
        rating = "Fragmented"
        advice = "Lots of task-switching. Consider grouping similar tasks into longer blocks."

    return {
        "score": total_score,
        "rating": rating,
        "advice": advice,
        "avg_block_mins": int(avg_block),
        "switches": cat_switches,
        "pomodoro_mins": pomo_mins
    }


def get_weekly_insights(db: TimographyDB, reference_date: date = None) -> list[str]:
    """Generate high-level weekly summary takeaways."""
    if reference_date is None:
        reference_date = datetime.now().date()

    start_of_week = reference_date - timedelta(days=reference_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    cat_hours = db.get_category_hours_summary(start_of_week.strftime("%Y-%m-%d"), end_of_week.strftime("%Y-%m-%d"))
    total_hours = sum(cat_hours.values())
    streak = db.get_study_streak()

    insights = []
    if total_hours > 0:
        top_cat = max(cat_hours.items(), key=lambda x: x[1])
        insights.append(f"⏱️ Total scheduled: {total_hours:.1f} hours this week.")
        insights.append(f"🏆 Top category: {top_cat[0]} ({top_cat[1]:.1f} hours, {int(top_cat[1]/total_hours*100)}% of your time).")
    else:
        insights.append("⏱️ No hours scheduled yet this week.")

    if streak["current"] > 0:
        insights.append(f"🔥 Active study streak: {streak['current']} day{'s' if streak['current'] > 1 else ''}! (Best: {streak['best']} days)")

    return insights
