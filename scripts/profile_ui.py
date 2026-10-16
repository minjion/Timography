"""Measure real Tk interactions against an isolated representative schedule."""
import json
from datetime import date, timedelta
from pathlib import Path
from statistics import median
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import customtkinter as ctk
from core.database import TimographyDB
from ui.main_window import MainWindow
from ui.theme import apply_theme


def main():
    apply_theme("dark")
    root = ctk.CTk()
    root.withdraw()
    root.update()
    db = TimographyDB(":memory:")
    db.initialize()
    today = date.today()
    for offset in range(-180, 15):
        for hour in (9, 11, 14, 16):
            db.add_event(f"Study block {hour}", "Review material", f"{hour:02}:00",
                         f"{hour + 1:02}:00", (today + timedelta(days=offset)).isoformat(),
                         "#58a6ff", "Study", "none", 10)
    queries = []
    db._get_conn().set_trace_callback(queries.append)
    started = perf_counter()
    window = MainWindow(root, db)
    window.deiconify()
    root.update()
    results = {"startup_ms": round((perf_counter() - started) * 1000, 1)}
    window.switch_tab("calendar")
    root.update()

    def measure(name, action):
        elapsed, counts = [], []
        for _ in range(5):
            queries.clear()
            started = perf_counter()
            action()
            root.update()
            elapsed.append((perf_counter() - started) * 1000)
            counts.append(sum(q.lstrip().upper().startswith("SELECT") for q in queries))
        results[name] = {"median_ms": round(median(elapsed), 1), "selects": median(counts)}

    try:
        measure("calendar_refresh", window.refresh)
        measure("navigate_week", lambda: window._navigate(1))
        measure("tasks_roundtrip", lambda: (window.switch_tab("tasks"), window.switch_tab("calendar")))
        measure("analytics_roundtrip", lambda: (window.switch_tab("analytics"), window.switch_tab("calendar")))
        window.switch_tab("analytics")
        measure("analytics_refresh", window.view_analytics.refresh)
        print(json.dumps(results, indent=2), flush=True)
        if "--profile" in sys.argv:
            import cProfile
            import pstats
            window.switch_tab("calendar")
            profiler = cProfile.Profile()
            profiler.enable()
            window._navigate(1)
            root.update_idletasks()
            profiler.disable()
            pstats.Stats(profiler).sort_stats("cumulative").print_stats(20)
    finally:
        root.destroy()
        db.close()


if __name__ == "__main__":
    main()
