"""High-performance, zero-flicker Daily Checklist component for Timography."""
from datetime import datetime
import tkinter as tk
import customtkinter as ctk
from ui.theme import COLORS, FONTS, CARD_CORNER_RADIUS, BUTTON_CORNER_RADIUS
from core.database import TimographyDB


class ChecklistPanel(ctk.CTkFrame):
    def __init__(self, master, db: TimographyDB, on_stats_change=None,
                 on_event_focus=None, undo_mgr=None, is_full_tab: bool = False, **kwargs):
        super().__init__(master, fg_color=COLORS["bg_secondary"], corner_radius=0, **kwargs)
        self.db = db
        self.on_stats_change = on_stats_change
        self.on_event_focus = on_event_focus
        self.undo_mgr = undo_mgr
        self.is_full_tab = is_full_tab
        self.current_date_str = datetime.now().strftime("%Y-%m-%d")

        self._rows = {}  # item_id -> {"row": frame, "cb": checkbox, "var": boolean_var, "item": dict}
        self._stats = {"completed": 0, "total": 0}
        self.filter_mode = "all"  # "all", "pending", "completed"

        self._build_ui()
        self.load_date(self.current_date_str)

    def _build_ui(self):
        pad_x = 24 if self.is_full_tab else 12

        # Header
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent", height=48)
        self.header_frame.pack(fill="x", padx=pad_x, pady=(12, 4))
        self.header_frame.pack_propagate(False)

        self.title_lbl = ctk.CTkLabel(
            self.header_frame,
            text="Today's Checklist",
            font=FONTS["heading"] if self.is_full_tab else FONTS["title_medium"],
            text_color=COLORS["text_primary"]
        )
        self.title_lbl.pack(side="left")

        actions_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        actions_box.pack(side="right")

        if self.is_full_tab:
            # Filter segmented buttons
            self.seg_filter = ctk.CTkSegmentedButton(
                actions_box,
                values=["All", "Pending", "Completed"],
                font=FONTS["small"],
                command=self._on_filter_changed
            )
            self.seg_filter.set("All")
            self.seg_filter.pack(side="left", padx=(0, 10))

        self.sync_btn = ctk.CTkButton(
            actions_box,
            text="↻ Sync Schedule",
            font=FONTS["small_bold" if self.is_full_tab else "micro"],
            width=110 if self.is_full_tab else 60,
            height=28,
            fg_color=COLORS["bg_tertiary"],
            hover_color=COLORS["border"],
            text_color=COLORS["accent"],
            command=self._sync_from_schedule
        )
        self.sync_btn.pack(side="left")

        # Progress bar container
        self.progress_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_tertiary"], corner_radius=6, height=36)
        self.progress_frame.pack(fill="x", padx=pad_x, pady=(4, 8))
        self.progress_frame.pack_propagate(False)

        self.lbl_progress = ctk.CTkLabel(
            self.progress_frame,
            text="0 / 0 completed (0%)",
            font=FONTS["small_bold"],
            text_color=COLORS["text_secondary"]
        )
        self.lbl_progress.pack(side="left", padx=12)

        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame,
            height=8,
            corner_radius=4,
            progress_color=COLORS["accent_green"],
            fg_color=COLORS["bg_primary"]
        )
        self.progress_bar.pack(side="right", fill="x", expand=True, padx=(0, 12))
        self.progress_bar.set(0.0)

        # Scrollable items area
        self.items_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.items_scroll.pack(fill="both", expand=True, padx=pad_x - 4, pady=(0, 6))

        # Bottom Add Task Entry
        self.bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.bottom_frame.pack(fill="x", padx=pad_x, pady=(4, 12))

        self.entry_add = ctk.CTkEntry(
            self.bottom_frame,
            placeholder_text="+ Type task name and press Enter...",
            font=FONTS["body" if self.is_full_tab else "small"],
            fg_color=COLORS["bg_tertiary"],
            border_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            height=36 if self.is_full_tab else 32
        )
        self.entry_add.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_add.bind("<Return>", lambda e: self._add_manual_item())

        self.btn_add = ctk.CTkButton(
            self.bottom_frame,
            text="Add Task",
            font=FONTS["body_bold" if self.is_full_tab else "small_bold"],
            width=80 if self.is_full_tab else 50,
            height=36 if self.is_full_tab else 32,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color=COLORS["bg_primary"],
            command=self._add_manual_item
        )
        self.btn_add.pack(side="right")

    def load_date(self, date_str: str):
        self.current_date_str = date_str
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        now_d = datetime.now().date()
        if dt.date() == now_d:
            self.title_lbl.configure(text="Today's Checklist")
        else:
            self.title_lbl.configure(text=f"Checklist ({dt.strftime('%A, %b %d')})")

        # Ensure checklist generated
        self.db.generate_checklist_for_date(date_str)
        self.refresh()

    def _on_filter_changed(self, value):
        self.filter_mode = value.lower()
        self._apply_filter_visibility()

    def _apply_filter_visibility(self):
        for item_id, info in self._rows.items():
            is_completed = bool(info["item"].get("is_completed", False))
            if self.filter_mode == "pending" and is_completed:
                info["row"].pack_forget()
            elif self.filter_mode == "completed" and not is_completed:
                info["row"].pack_forget()
            else:
                info["row"].pack(fill="x", pady=2)

    def _sync_from_schedule(self):
        """Re-synchronize items from today's schedule into checklist."""
        events = self.db.get_events_for_date(self.current_date_str, include_routines=True)
        existing = self.db.get_checklist(self.current_date_str)
        existing_event_ids = {it["event_id"] for it in existing if it["event_id"]}
        existing_routine_ids = {it["routine_id"] for it in existing if it["routine_id"]}

        for ev in events:
            if ev.get("is_routine"):
                r_id = ev.get("routine_id")
                if r_id and r_id not in existing_routine_ids:
                    title = f"{ev.get('title', '')} ({ev.get('start_time', '')} - {ev.get('end_time', '')})"
                    self.db.add_checklist_item(title, self.current_date_str, routine_id=r_id)
            else:
                e_id = ev.get("id")
                if e_id and e_id not in existing_event_ids:
                    title = f"{ev.get('title', '')} ({ev.get('start_time', '')} - {ev.get('end_time', '')})"
                    self.db.add_checklist_item(title, self.current_date_str, event_id=e_id)

        self.refresh()

    def _add_manual_item(self):
        text = self.entry_add.get().strip()
        if not text:
            return
        item_id = self.db.add_checklist_item(text, self.current_date_str)
        if self.undo_mgr and item_id != -1:
            self.undo_mgr.record("add", "checklist", item_id, None, {"title": text, "date": self.current_date_str})
        self.entry_add.delete(0, "end")

        item = {
            "id": item_id,
            "title": text,
            "date": self.current_date_str,
            "is_completed": 0
        }
        self._create_and_append_row(item)
        self._stats["total"] += 1
        self._update_progress_ui()

    def refresh(self):
        """Initial or date-switch load: clear and populate all rows."""
        for w in self.items_scroll.winfo_children():
            w.destroy()
        self._rows.clear()

        items = self.db.get_checklist(self.current_date_str)
        stats = self.db.get_checklist_stats(self.current_date_str)
        self._stats["completed"] = stats["completed"]
        self._stats["total"] = stats["total"]

        self._update_progress_ui()

        if not items:
            self.lbl_empty = ctk.CTkLabel(
                self.items_scroll,
                text="No items scheduled.\nTap '+ Type task name' below or '↻ Sync Schedule'.",
                font=FONTS["body" if self.is_full_tab else "small"],
                text_color=COLORS["text_muted"]
            )
            self.lbl_empty.pack(pady=30)
            return

        for it in items:
            self._create_and_append_row(it)

    def _create_and_append_row(self, item: dict):
        if hasattr(self, 'lbl_empty') and self.lbl_empty.winfo_exists():
            self.lbl_empty.destroy()

        item_id = item["id"]
        is_done = bool(item.get("is_completed", False))

        row = ctk.CTkFrame(self.items_scroll, fg_color="transparent")
        row.pack(fill="x", pady=2)

        var = tk.BooleanVar(value=is_done)

        text_color = COLORS["text_muted"] if is_done else COLORS["text_primary"]
        display_text = item.get("title", "")

        cb = ctk.CTkCheckBox(
            row,
            text=display_text,
            variable=var,
            command=lambda i_id=item_id: self._on_toggle_in_place(i_id),
            font=FONTS["body" if self.is_full_tab else "small"],
            text_color=text_color,
            fg_color=COLORS["accent_green"],
            hover_color=COLORS["accent_green"],
            border_color=COLORS["border"],
            corner_radius=4,
            checkbox_width=20 if self.is_full_tab else 18,
            checkbox_height=20 if self.is_full_tab else 18
        )
        cb.pack(side="left", fill="x", expand=True, padx=(4, 4))

        del_btn = ctk.CTkButton(
            row,
            text="✕",
            font=FONTS["small" if self.is_full_tab else "micro"],
            width=26 if self.is_full_tab else 20,
            height=26 if self.is_full_tab else 20,
            fg_color="transparent",
            hover_color=COLORS["bg_tertiary"],
            text_color=COLORS["text_muted"],
            command=lambda i_id=item_id, t=display_text: self._delete_item_in_place(i_id, t)
        )
        del_btn.pack(side="right", padx=(2, 4))

        self._rows[item_id] = {
            "row": row,
            "cb": cb,
            "var": var,
            "item": item
        }

    def _on_toggle_in_place(self, item_id: int):
        """0ms latency, zero flicker in-place mutation."""
        row_info = self._rows.get(item_id)
        if not row_info:
            return

        is_now_done = row_info["var"].get()
        row_info["item"]["is_completed"] = 1 if is_now_done else 0

        # Update text color immediately
        new_color = COLORS["text_muted"] if is_now_done else COLORS["text_primary"]
        row_info["cb"].configure(text_color=new_color)

        # Update stats in-place
        if is_now_done:
            self._stats["completed"] += 1
        else:
            self._stats["completed"] = max(0, self._stats["completed"] - 1)

        self._update_progress_ui()

        # Database update asynchronously / in background
        self.after(5, lambda: self._commit_toggle_to_db(item_id))

    def _commit_toggle_to_db(self, item_id: int):
        self.db.toggle_checklist_item(item_id)
        if self.undo_mgr:
            self.undo_mgr.record("toggle", "checklist", item_id)
        if self.on_stats_change:
            self.on_stats_change(self._stats["completed"], self._stats["total"])

    def _delete_item_in_place(self, item_id: int, title: str):
        row_info = self._rows.get(item_id)
        if not row_info:
            return

        was_done = bool(row_info["item"].get("is_completed", False))
        row_info["row"].destroy()
        del self._rows[item_id]

        self._stats["total"] = max(0, self._stats["total"] - 1)
        if was_done:
            self._stats["completed"] = max(0, self._stats["completed"] - 1)

        self._update_progress_ui()

        self.db.delete_checklist_item(item_id)
        if self.undo_mgr:
            self.undo_mgr.record("delete", "checklist", item_id, {"title": title, "date": self.current_date_str}, None)

        if self.on_stats_change:
            self.on_stats_change(self._stats["completed"], self._stats["total"])

    def _update_progress_ui(self):
        done = self._stats["completed"]
        tot = self._stats["total"]
        pct = int((done / tot * 100)) if tot > 0 else 0
        self.lbl_progress.configure(text=f"{done} / {tot} completed ({pct}%)")
        self.progress_bar.set(done / max(1, tot))
