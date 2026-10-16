"""Exercise real Tk views using an isolated database. Requires a desktop session."""
import argparse
from datetime import date, datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import customtkinter as ctk
from core.database import TimographyDB
from ui.main_window import MainWindow
from ui.event_dialog import EventDialog
from ui.settings_dialog import SettingsDialog
from ui.routines_dialog import RoutineEditDialog
from ui.quick_add import QuickAddDialog
from ui.widget import DesktopWidget
from ui.theme import apply_theme, COLORS, get_current_theme


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args()
    apply_theme("dark")
    errors = []
    root = ctk.CTk()
    root.withdraw()
    root.update()
    root.report_callback_exception = lambda kind, value, tb: errors.append(f"{kind.__name__}: {value}")
    bgerror_recorder = root.register(lambda message, info: errors.append(f"Tcl background error: {message}\n{info}"))
    root.tk.call("proc", "bgerror", "message", f"{bgerror_recorder} $message $::errorInfo")
    db = TimographyDB(":memory:")
    db.initialize()
    today = date.today().isoformat()
    db.add_event("Read and annotate the next chapter of the course textbook", "Review notes", "09:00", "10:00", today, "#58a6ff", "Work", "none", 10)
    db.add_event("Meeting overlapping with reading", "", "09:30", "10:30", today, "#bc8cff", "Study", "none", 10)
    db.add_exam("Mathematics final exam", today)
    window = MainWindow(root, db)
    window.deiconify()
    window.attributes("-alpha", 1)

    def pump():
        root.after(300, root.quit)
        root.mainloop()

    def capture(widget, name):
        if args.capture:
            from PIL import ImageGrab
            import ctypes
            output = Path("artifacts/ui-audit")
            output.mkdir(parents=True, exist_ok=True)
            widget.lift()
            pump()
            hwnd = ctypes.windll.user32.GetParent(widget.winfo_id()) or widget.winfo_id()
            ImageGrab.grab(window=hwnd).save(output / f"{name}.png")

    def visible(widget):
        assert widget.winfo_ismapped(), f"Hidden control: {widget}"
        assert widget.winfo_width() > 8 and widget.winfo_height() > 8, f"Clipped control: {widget}"
        parent = widget.master
        assert widget.winfo_x() + widget.winfo_width() <= parent.winfo_width() + 2, f"Horizontal clipping: {widget}"

    try:
        for width, height in ((900, 600), (1200, 780)):
            window.geometry(f"{width}x{height}")
            for mode in ("dark", "light"):
                window._on_theme_change(mode)
                for tab in ("today", "calendar", "tasks", "focus", "analytics", "exams", "routines"):
                    window.switch_tab(tab)
                    pump()
                    for button in window.tab_buttons.values():
                        visible(button)
                    visible(window.btn_settings)
                    visible(window.btn_create_event)
                    if tab == "calendar":
                        assert window.time_grid.canvas.cget("bg") == COLORS["bg_primary"]
                        visible(window.btn_add_cat)
                        for item, rect in window.time_grid._item_to_rect.items():
                            if window.time_grid.canvas.type(item) == "text":
                                x1, y1, x2, y2, event = window.time_grid._event_rects[rect]
                                bbox = window.time_grid.canvas.bbox(item)
                                if bbox:
                                    assert bbox[0] >= x1 and bbox[2] <= x2 + 1 and bbox[3] <= y2 + 1, f"Event text escapes its card: {bbox}"
                    capture(window, f"{width}-{mode}-{tab}")
                    print(f"OK {width}x{height} {mode} {tab}", flush=True)
        window.switch_tab("calendar")
        for dialog_cls in (EventDialog, SettingsDialog, RoutineEditDialog, QuickAddDialog):
            dialog = dialog_cls(window, db)
            pump()
            if isinstance(dialog, QuickAddDialog):
                dialog.entry_input.insert(0, "study tomorrow at 2pm for 15m")
                dialog._on_text_change()
                dialog._auto_schedule_slot()
                start = datetime.strptime(dialog.parsed_data["start_time"], "%H:%M")
                end = datetime.strptime(dialog.parsed_data["end_time"], "%H:%M")
                assert (end - start).total_seconds() == 900, "Auto-schedule changed a short task duration"
            capture(dialog, dialog_cls.__name__)
            for name in ("btn_save", "save_btn"):
                if hasattr(dialog, name):
                    visible(getattr(dialog, name))
            dialog.destroy()
            pump()
            print(f"OK {dialog_cls.__name__}", flush=True)
        widget = DesktopWidget(root, db)
        for mode in ("dark", "light"):
            apply_theme(mode)
            widget.reapply_theme()
            pump()
            visible(widget.add_btn)
            visible(widget.focus_btn)
            capture(widget, f"widget-{mode}")
        controls = dict(widget._checklist_controls)
        task_id = next(iter(controls))
        widget._toggle_checklist(task_id)
        stats = db.get_checklist_stats(today)
        widget.update_checklist_progress(stats["completed"], stats["total"])
        assert widget._checklist_controls == controls, "Checklist toggle rebuilt widget controls"
        assert controls[task_id].get() == db.get_checklist_item(task_id)["is_completed"]
        assert widget.undo_mgr.undo(), "Widget completion was not recorded in history"
        assert not db.get_checklist_item(task_id)["is_completed"]
        widget.destroy()
        dialog = SettingsDialog(window, db, on_theme_change=window._on_theme_change,
                                on_save_callback=window._on_settings_saved)
        original_theme = get_current_theme()
        preview = "dark" if original_theme == "light" else "light"
        dialog._on_theme_preview("Dark" if preview == "dark" else "Light")
        pump()
        assert window.time_grid.canvas.cget("bg") == COLORS["bg_primary"]
        dialog.destroy()
        assert get_current_theme() == original_theme
        assert db.get_setting("theme") is None
        dialog = SettingsDialog(window, db, on_theme_change=window._on_theme_change,
                                on_save_callback=window._on_settings_saved)
        dialog.pomo_work_var.set("37")
        dialog.week_var.set("Sunday")
        dialog._save_settings()
        pump()
        assert window.view_focus.work_min == 37
        assert window.time_grid._get_dates()[0].weekday() == 6
        print("OK settings preview rollback, save, Pomodoro and week-start preferences", flush=True)
        window.switch_tab("tasks")
        panel = window.view_tasks
        panel._on_filter_changed("Pending")
        item_id = next(iter(panel._rows))
        panel._rows[item_id]["var"].set(True)
        panel._on_toggle_in_place(item_id)
        panel.refresh()
        pump()
        assert not panel._rows[item_id]["row"].winfo_ismapped()
        panel._on_filter_changed("All")
        window.switch_tab("calendar")
        window.search_entry.insert(0, "read")
        window._run_search()
        matches = [event for events in window.time_grid.events_by_date.values() for event in events]
        assert matches and any(event["title"].startswith("Read and annotate") for event in matches)
        assert all("read" in event["title"].lower() or "read" in event.get("description", "").lower() for event in matches)
        window.search_entry.delete(0, "end")
        window._run_search()
        print("OK checklist filters and event search", flush=True)
        grid = window.time_grid
        grid.scroll_to_hour(8, animate=False)
        pump()
        before = grid.canvas.yview()[0]
        for _ in range(6):
            grid.canvas.event_generate("<MouseWheel>", delta=-1)
        pump()
        assert grid.canvas.yview()[0] > before, "Small touchpad deltas were lost in calendar"
        for _ in range(6):
            grid.canvas.event_generate("<MouseWheel>", delta=1)
        pump()
        assert abs(grid.canvas.yview()[0] - before) < 0.00001, "Reverse touchpad scrolling lost deltas"
        canvas_items = grid.canvas.find_all()
        header_widgets = tuple(grid.header_frame.winfo_children())
        window.refresh()
        pump()
        assert grid.canvas.find_all() == canvas_items, "Unchanged calendar was redrawn"
        assert tuple(grid.header_frame.winfo_children()) == header_widgets
        window.switch_tab("tasks")
        pump()
        task_rows = tuple(info["row"] for info in panel._rows.values())
        window.switch_tab("calendar")
        window.switch_tab("tasks")
        pump()
        assert tuple(info["row"] for info in panel._rows.values()) == task_rows
        window.geometry("900x600")
        window.switch_tab("analytics")
        pump()
        analytics = window.view_analytics
        scroll_canvas = analytics.scroll_body._parent_canvas
        scroll_canvas.yview_moveto(0)
        before = scroll_canvas.yview()[0]
        other_before = window.categories_scroll._parent_canvas.yview()
        for _ in range(6):
            analytics.card_focus["val"]._label.event_generate("<MouseWheel>", delta=-1)
        pump()
        assert scroll_canvas.yview()[0] > before, "Small touchpad deltas were lost over nested labels"
        assert window.categories_scroll._parent_canvas.yview() == other_before, "Wheel scrolled another pane"
        before = scroll_canvas.yview()[0]
        for _ in range(6):
            analytics.scroll_body._scrollbar._canvas.event_generate("<MouseWheel>", delta=-1)
        pump()
        assert scroll_canvas.yview()[0] > before, "Small wheel deltas were lost over scrollbar"
        bindings = root.bind_all("<MouseWheel>")
        dialog = EventDialog(window, db)
        pump()
        dialog.destroy()
        pump()
        assert root.bind_all("<MouseWheel>").strip() == bindings.strip(), "Closed dialog retained wheel callbacks"
        assert analytics.card_focus["val"].cget("text") == "0 min", "Planned events counted as recorded focus"
        session = db.start_pomodoro("Recorded focus", work_minutes=30)
        db.update_pomodoro(session, cycles_completed=1)
        analytics.refresh()
        assert analytics.card_focus["val"].cget("text") == "30 min"
        print("OK precision scrolling, pane routing, binding cleanup, retained views and focus metrics", flush=True)
        assert not errors, "\n".join(errors)
        print("UI smoke checks passed; no Tk callback errors.", flush=True)
    finally:
        root.destroy()
        db.close()


if __name__ == "__main__":
    main()
