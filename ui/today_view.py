"""An actionable overview of the current day, backed by the existing planner."""
from datetime import datetime

import customtkinter as ctk
from ui.controls import AppButton

from ui.scrolling import ScrollableFrame
from ui.theme import FONTS, theme_color


class TodayView(ctk.CTkFrame):
    def __init__(self, master, db, undo_mgr, on_event, on_add_event,
                 on_calendar, on_tasks, on_focus, on_change, **kwargs):
        super().__init__(master, fg_color=theme_color("bg_primary"), **kwargs)
        self.db = db
        self.undo_mgr = undo_mgr
        self.on_event = on_event
        self.on_focus = on_focus
        self.on_change = on_change
        self._snapshot = None
        self._task_controls = {}
        self._task_focus_buttons = {}
        self._next_event = None
        self._closing = False
        self._clock_id = None
        self._wrap_after_ids = {}

        self.content = ScrollableFrame(self, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=18, pady=16)
        self.content.grid_columnconfigure(0, weight=3, uniform="today")
        self.content.grid_columnconfigure(1, weight=2, uniform="today")
        self.title_label = ctk.CTkLabel(self.content, text="Today", font=("Segoe UI", 28, "bold"),
                                      text_color=theme_color("text_primary"), anchor="w")
        self.title_label.grid(row=0, column=0, sticky="ew", padx=4)
        self.date_label = ctk.CTkLabel(self.content, text="", font=FONTS["body"],
                                     text_color=theme_color("text_secondary"), anchor="w")
        self.date_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=(0, 14))
        self.add_button = self._button(self.content, "Plan an event", on_add_event, primary=True)
        self.add_button.grid(row=0, column=1, sticky="e")

        hero = self._card(self.content)
        hero.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        self.next_caption = self._label(hero, "UP NEXT", FONTS["small_bold"], "text_secondary")
        self.next_caption.pack(anchor="w", padx=18, pady=(16, 2))
        self.next_title = self._label(hero, "", FONTS["heading"])
        self.next_title.configure(wraplength=640)
        self.next_title.pack(fill="x", padx=18, pady=2)
        self.next_detail = self._label(hero, "", FONTS["body"], "text_secondary")
        self.next_detail.configure(wraplength=640)
        self.next_detail.pack(fill="x", padx=18, pady=(0, 12))
        hero_actions = ctk.CTkFrame(hero, fg_color="transparent")
        hero_actions.pack(fill="x", padx=18, pady=(0, 16))
        self.focus_button = self._button(hero_actions, "Start focus", lambda: on_focus(self._next_event), primary=True)
        self.focus_button.pack(side="left", padx=(0, 8))
        self.calendar_button = self._button(hero_actions, "Open calendar", on_calendar)
        self.calendar_button.pack(side="left")
        self.focus_label = self._label(hero_actions, "", FONTS["small"], "text_secondary")
        self.focus_label.pack(side="right")
        self._bind_wrap(hero, (self.next_title, self.next_detail), 44)

        self.agenda_card = self._card(self.content)
        self.agenda_card.grid(row=3, column=0, sticky="nsew", padx=(0, 8))
        self._label(self.agenda_card, "Your agenda", FONTS["subheading"]).pack(anchor="w", padx=16, pady=(16, 8))
        self.agenda_body = ctk.CTkFrame(self.agenda_card, fg_color="transparent")
        self.agenda_body.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.tasks_card = self._card(self.content)
        self.tasks_card.grid(row=3, column=1, sticky="nsew", padx=(8, 0))
        self.task_summary = self._label(self.tasks_card, "Today's tasks", FONTS["subheading"])
        self.task_summary.pack(anchor="w", padx=16, pady=(16, 6))
        self.progress = ctk.CTkProgressBar(self.tasks_card, height=6, progress_color=theme_color("accent"),
                                         fg_color=theme_color("bg_tertiary"))
        self.progress.pack(fill="x", padx=16, pady=(0, 10))
        capture = ctk.CTkFrame(self.tasks_card, fg_color="transparent")
        capture.pack(fill="x", padx=12, pady=(0, 8))
        capture.grid_columnconfigure(0, weight=1)
        self.task_entry = ctk.CTkEntry(capture, placeholder_text="Add a task for today", height=36,
                                     font=FONTS["small"], fg_color=theme_color("bg_primary"),
                                     border_color=theme_color("border"), text_color=theme_color("text_primary"))
        self.task_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.task_entry.bind("<Return>", lambda event: self._add_task())
        self.task_add_button = self._button(capture, "Add", self._add_task, width=52)
        self.task_add_button.grid(row=0, column=1)
        self.error_label = self._label(self.tasks_card, "", FONTS["small"], "accent_red")
        self.tasks_body = ctk.CTkFrame(self.tasks_card, fg_color="transparent")
        self.tasks_body.pack(fill="both", expand=True, padx=12)
        self._button(self.tasks_card, "View all tasks", on_tasks).pack(anchor="w", padx=12, pady=12)
        self._clock_id = self.after(15000, self._tick)

    @staticmethod
    def _card(master):
        return ctk.CTkFrame(master, fg_color=theme_color("bg_secondary"), corner_radius=12,
                            border_width=1, border_color=theme_color("border"))

    @staticmethod
    def _label(master, text, font, color="text_primary"):
        return ctk.CTkLabel(master, text=text, font=font, text_color=theme_color(color), anchor="w", justify="left")

    @staticmethod
    def _button(master, text, command, primary=False, width=124):
        return AppButton(master, text=text, command=command, width=width, height=36,
                            font=FONTS["small_bold"], corner_radius=8,
                            fg_color=theme_color("accent" if primary else "bg_tertiary"),
                            hover_color=theme_color("accent_hover" if primary else "border"),
                            text_color=theme_color("on_accent" if primary else "text_primary"))

    def refresh(self):
        now = datetime.now()
        today = now.date().isoformat()
        events = self.db.get_events_for_date(today)
        tasks = self.db.generate_checklist_for_date(today)
        focused = self.db.get_today_pomodoro_minutes(today)
        key = (today, now.strftime("%H:%M"), events, tasks, focused)
        if self._snapshot == key:
            return
        old = self._snapshot
        self._snapshot = key
        self.date_label.configure(text=now.strftime("%A, %B %d, %Y"))
        clock = now.strftime("%H:%M")
        remaining = [event for event in events if event["end_time"] > clock]
        upcoming = min(remaining, key=lambda event: event["start_time"]) if remaining else None
        self._next_event = upcoming
        if upcoming:
            self.next_caption.configure(text="HAPPENING NOW" if upcoming["start_time"] <= clock else "UP NEXT")
            self.next_title.configure(text=upcoming["title"])
            self.next_detail.configure(text=f"{upcoming['start_time']}–{upcoming['end_time']}  ·  {upcoming['category']}")
        else:
            self.next_caption.configure(text="ROOM TO FOCUS")
            self.next_title.configure(text="Your schedule is clear." if not events else "No more events today.")
            self.next_detail.configure(text="Start a focus session, finish a task, or plan what comes next.")
        self.focus_label.configure(text=f"{focused} min focused today")
        completed = sum(bool(task["is_completed"]) for task in tasks)
        self.task_summary.configure(text=f"Today's tasks · {completed}/{len(tasks)}")
        self.progress.set(completed / len(tasks) if tasks else 0)
        if not old or old[2] != events or old[1] != key[1] or old[0] != today:
            self._render_agenda(events, clock)
        if not old or old[3] != tasks or old[0] != today:
            self._render_tasks(tasks)

    def _render_agenda(self, events, clock):
        for child in self.agenda_body.winfo_children():
            child.destroy()
        if not events:
            self._label(self.agenda_body, "No events planned.\nAdd an event to give your day a shape.", FONTS["body"], "text_secondary").pack(fill="x", padx=4, pady=16)
        for event in events:
            row = ctk.CTkFrame(self.agenda_body, fg_color="transparent")
            row.pack(fill="x", pady=4)
            row.grid_columnconfigure(1, weight=1)
            self._label(row, event["start_time"], FONTS["time"], "text_secondary").grid(row=0, column=0, rowspan=2, sticky="n", padx=(4, 12), pady=6)
            title = self._label(row, event["title"], FONTS["body_bold"], "text_muted" if event["end_time"] <= clock else "text_primary")
            title.configure(wraplength=220)
            title.grid(row=0, column=1, sticky="ew")
            status = "Now · " if event["start_time"] <= clock < event["end_time"] else ""
            detail = self._label(row, f"{status}{event['category']} · until {event['end_time']}", FONTS["small"], "text_secondary")
            detail.configure(wraplength=220)
            detail.grid(row=1, column=1, sticky="ew")
            self._button(row, "Open", lambda item=event: self.on_event(item), width=48).grid(row=0, column=2, rowspan=2, padx=(6, 0))
            self._bind_wrap(row, (title, detail), 134)

    def _render_tasks(self, tasks):
        for child in self.tasks_body.winfo_children():
            child.destroy()
        self._task_controls.clear()
        self._task_focus_buttons.clear()
        if not tasks:
            self._label(self.tasks_body, "Nothing to do yet. Capture a task above.", FONTS["small"], "text_secondary").pack(anchor="w", pady=8)
        ordered = sorted(tasks, key=lambda item: bool(item["is_completed"]))
        for task in ordered[:8]:
            row = ctk.CTkFrame(self.tasks_body, fg_color="transparent")
            row.pack(fill="x", pady=4)
            row.grid_columnconfigure(1, weight=1)
            var = ctk.BooleanVar(value=bool(task["is_completed"]))
            checkbox = ctk.CTkCheckBox(row, text="", width=24, height=24, checkbox_width=20, checkbox_height=20,
                                      variable=var, fg_color=theme_color("accent"), border_color=theme_color("border"),
                                      command=lambda item_id=task["id"]: self._toggle_task(item_id))
            checkbox.grid(row=0, column=0, sticky="n", padx=(4, 8), pady=3)
            label = self._label(row, task["title"], FONTS["small"], "text_muted" if task["is_completed"] else "text_primary")
            label.configure(wraplength=180)
            label.grid(row=0, column=1, sticky="ew")
            if not task["is_completed"]:
                button = self._button(row, "Focus", lambda item_id=task["id"]: self._focus_task(item_id), width=50)
                button.grid(row=0, column=2, padx=(6, 0))
                self._task_focus_buttons[task["id"]] = button
            self._bind_wrap(row, (label,), 100 if not task["is_completed"] else 44)
            self._task_controls[task["id"]] = var
        if len(tasks) > 8:
            self._label(self.tasks_body, f"{len(tasks) - 8} more in Tasks", FONTS["small"], "text_secondary").pack(anchor="w", padx=4, pady=4)

    def _add_task(self):
        title = self.task_entry.get().strip()
        if not title:
            self.task_entry.focus_set()
            return
        item_id = self.db.add_checklist_item(title, datetime.now().date().isoformat())
        if item_id == -1:
            self._show_error("Could not save this task. Please try again.")
            return
        self.undo_mgr.record("add", "checklist", item_id, None, self.db.get_checklist_item(item_id))
        self.task_entry.delete(0, "end")
        self.error_label.pack_forget()
        self.refresh()
        self.on_change()

    def _toggle_task(self, item_id):
        old = self.db.get_checklist_item(item_id)
        if not self.db.toggle_checklist_item(item_id):
            self._task_controls[item_id].set(bool(old and old["is_completed"]))
            self._show_error("Could not update this task. Please try again.")
            return
        self.undo_mgr.record("toggle", "checklist", item_id, old, self.db.get_checklist_item(item_id))
        self.error_label.pack_forget()
        self.refresh()
        self.on_change()

    def _focus_task(self, item_id):
        """Keep checklist identities separate from the optional calendar source."""
        task = self.db.get_checklist_item(item_id)
        if not task:
            self._show_error("This task is no longer available.")
            return
        if task["is_completed"]:
            return
        source, event_id = None, None
        if task.get("event_id") is not None:
            source = self.db.get_event(task["event_id"])
            if source:
                event_id = source["id"]
        elif task.get("routine_id") is not None:
            source = self.db.get_routine(task["routine_id"])
        self.on_focus({
            "title": task["title"],
            "category": (source or {}).get("category") or "Study",
            "id": event_id,
        })

    def _show_error(self, message):
        self.error_label.configure(text=message)
        self.error_label.pack(fill="x", padx=16, pady=4, before=self.tasks_body)

    @staticmethod
    def _wrap_to_width(label, physical_width, inset):
        if not label.winfo_viewable():
            return
        # Tk Configure reports physical pixels; CTk wraplength takes logical pixels.
        width = max(80, round(physical_width / label._get_widget_scaling() - inset))
        if label.cget("wraplength") != width:
            label.configure(wraplength=width)

    def _wrap_labels(self, labels, physical_width, inset):
        for label in labels:
            self._wrap_to_width(label, physical_width, inset)

    def _bind_wrap(self, row, labels, inset):
        def apply():
            if row.winfo_exists() and row.winfo_viewable():
                self._wrap_labels(labels, row.winfo_width(), inset)
        def flush():
            self._wrap_after_ids.pop(row, None)
            apply()
        def schedule(event):
            if row not in self._wrap_after_ids:
                self._wrap_after_ids[row] = self.after(0, flush)
        row.bind("<Configure>", lambda event: apply())
        # Hidden views use their contents' requested sizes, so wrapping there
        # creates a feedback loop. Wait until the real viewport constrains them.
        row.bind("<Map>", schedule, add="+")

    def _tick(self):
        self._clock_id = None
        if not self._closing:
            if self.winfo_ismapped():
                self.refresh()
            self._clock_id = self.after(15000, self._tick)

    def reapply_theme(self):
        # Semantic CTk colors automatically respond to appearance changes.
        self.refresh()

    def destroy(self):
        self._closing = True
        if self._clock_id:
            self.after_cancel(self._clock_id)
        for callback in self._wrap_after_ids.values():
            self.after_cancel(callback)
        self._wrap_after_ids.clear()
        super().destroy()
