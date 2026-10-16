"""Productivity analytics, focus score, and insight algorithms for Timography."""
from datetime import datetime, date, timedelta
from core.database import TimographyDB


def calculate_focus_score(db: TimographyDB, date_str: str) -> dict:
    """Transparent percentage of the saved daily recorded-focus goal (not a quality rating)."""
    categories = [c.strip() for c in db.get_setting(
        "streak_categories", "Work,Study,Health,Personal").split(",") if c.strip()]
    seconds = db.get_focus_seconds_by_date(date_str, date_str, categories).get(date_str, 0)
    goal = db.get_int_setting("streak_goal_minutes", 30, 1, 1440)
    score = min(100, int(seconds / (goal * 60) * 100))
    rating = "Goal reached" if score == 100 else "In progress" if seconds else "Ready to start"
    return {"score": score, "rating": rating,
            "advice": f"{int(seconds / 60)} of {goal} recorded focus minutes. Pauses and breaks do not count.",
            "pomodoro_mins": int(seconds / 60), "goal_minutes": goal}


def get_weekly_insights(db: TimographyDB, reference_date: date = None) -> list[str]:
    """Generate high-level weekly summary takeaways."""
    if reference_date is None:
        reference_date = datetime.now().date()

    first = 6 if db.get_setting("week_start", "monday") == "sunday" else 0
    start_of_week = reference_date - timedelta(days=(reference_date.weekday() - first) % 7)
    end_of_week = start_of_week + timedelta(days=6)

    cat_hours = db.get_category_hours_summary(start_of_week.strftime("%Y-%m-%d"), end_of_week.strftime("%Y-%m-%d"))
    total_hours = sum(cat_hours.values())
    streak = db.get_study_streak()

    insights = []
    if total_hours > 0:
        top_cat = max(cat_hours.items(), key=lambda x: x[1])
        insights.append(f"⏱️ Total scheduled: {total_hours:.1f} hours this week.")
        insights.append(f"🏆 Top category: {top_cat[0]} ({top_cat[1]:.1f} hours, {int(top_cat[1]/total_hours*100)}% of planned time).")
    else:
        insights.append("⏱️ No hours scheduled yet this week.")

    if streak["current"] > 0:
        insights.append(f"🔥 Recorded focus streak: {streak['current']} day{'s' if streak['current'] > 1 else ''}! (Best: {streak['best']} days)")

    return insights
