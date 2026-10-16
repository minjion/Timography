"""Check real pointer release and popup cleanup, including Tcl background errors."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import customtkinter as ctk
from core.database import TimographyDB
from ui.controls import AppButton, AppToplevel
from ui.event_dialog import EventDialog
from ui.settings_dialog import SettingsDialog
from ui.checklist_panel import ChecklistPanel


def main():
    root = ctk.CTk()
    root.withdraw()
    root.update()
    errors = []
    root.report_callback_exception = lambda kind, value, tb: errors.append(str(value))
    recorder = root.register(lambda message, info: errors.append(f"{message}\n{info}"))
    root.tk.call("proc", "bgerror", "message", f"{recorder} $message $::errorInfo")
    db = TimographyDB(":memory:")
    db.initialize()

    def pump(ms=250):
        root.after(ms, root.quit)
        root.mainloop()

    def click(button):
        button._canvas.event_generate("<Enter>", x=5, y=5)
        button._canvas.event_generate("<ButtonPress-1>", x=5, y=5)
        button._canvas.event_generate("<ButtonRelease-1>", x=5, y=5)
        pump()

    try:
        before = root.bind_all("<Button-1>") or ""
        dialog = AppToplevel(root)
        button = AppButton(dialog, text="Save and close", command=dialog.destroy)
        button.pack(padx=20, pady=20)
        pump()
        click(button)
        assert not dialog.winfo_exists()
        assert not errors, errors
        assert root.bind_all("<Button-1>").strip() == before.strip(), (repr(before), repr(root.bind_all("<Button-1>")))
        for _ in range(3):
            dialog = AppToplevel(root)
            # Closing before CTk's 200ms icon timer must also cancel that timer.
            dialog.destroy()
            pump()
        after = root.bind_all("<Button-1>") or ""
        assert after.strip() == before.strip(), "Closed popup retained a global focus callback"
        assert not errors, errors
        print("OK real pointer close, immediate popup close and global binding cleanup", flush=True)

        parent = AppToplevel(root)
        parent.geometry("700x600")
        pump()
        baseline = root.bind_all("<Button-1>") or ""
        day = date.today().isoformat()
        dialog = EventDialog(parent, db, default_date=day, default_time="09:00")
        dialog.ent_title.insert(0, "Mouse-created event")
        pump()
        click(dialog.btn_save)
        assert not dialog.winfo_exists()
        event = db.get_events_for_date(day, include_routines=False)[0]
        assert event["title"] == "Mouse-created event"
        assert root.bind_all("<Button-1>").strip() == baseline.strip()
        dialog = EventDialog(parent, db, event=db.get_event(event["id"]))
        pump()
        click(dialog.btn_delete)
        assert db.get_event(event["id"]) is None
        assert root.bind_all("<Button-1>").strip() == baseline.strip()
        settings = SettingsDialog(parent, db)
        pump()
        click(settings.save_btn)
        assert not settings.winfo_exists()
        assert root.bind_all("<Button-1>").strip() == baseline.strip()
        print("OK real mouse create/delete event and Save Settings close dialogs cleanly", flush=True)

        item_id = db.add_checklist_item("Delete through actual mouse release", day)
        panel = ChecklistPanel(parent, db)
        panel.pack(fill="both", expand=True)
        panel.load_date(day)
        pump()
        panel.items_scroll._parent_canvas.yview_moveto(1)
        pump()
        row = panel._rows[item_id]["row"]
        delete_button = next(child for child in row.winfo_children()
                             if isinstance(child, AppButton) and child.cget("text") == "✕")
        click(delete_button)
        assert db.get_checklist_item(item_id) is None
        assert item_id not in panel._rows
        assert not errors, "\n".join(errors)
        parent.destroy()
        pump()
        assert root.bind_all("<Button-1>").strip() == before.strip()
        assert not errors, "\n".join(errors)
        print("UI lifecycle checks passed with no Python or Tcl background callback errors.", flush=True)
    finally:
        root.destroy()
        db.close()


if __name__ == "__main__":
    main()
