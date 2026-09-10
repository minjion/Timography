"""Undo and Redo action stack manager for Timography."""
import json
import logging
from datetime import datetime
from core.database import TimographyDB

logger = logging.getLogger(__name__)


class UndoManager:
    def __init__(self, db: TimographyDB):
        self.db = db

    def record(self, action_type: str, target_type: str, target_id: int, old_data: dict | None = None, new_data: dict | None = None):
        """Record an action for undo capability."""
        old_json = json.dumps(old_data) if old_data else None
        new_json = json.dumps(new_data) if new_data else None
        self.db.log_action(action_type, target_type, target_id, old_json, new_json)

    def undo(self) -> str | None:
        """Undo the most recent operation. Returns a user-friendly description or None."""
        action = self.db.pop_last_undoable_action()
        if not action:
            return None

        act_type = action["action_type"]
        target_type = action["target_type"]
        target_id = action["target_id"]
        old_data = json.loads(action["old_data"]) if action["old_data"] else None
        new_data = json.loads(action["new_data"]) if action["new_data"] else None

        try:
            if target_type == "event":
                if act_type == "add":
                    # Undo add -> delete the event
                    self.db.delete_event(target_id)
                    title = new_data.get("title", "Event") if new_data else "Event"
                    return f"Undid add: '{title}' removed"

                elif act_type == "delete":
                    # Undo delete -> re-insert the event
                    if old_data:
                        new_id = self.db.add_event(
                            title=old_data["title"],
                            description=old_data.get("description", ""),
                            start_time=old_data["start_time"],
                            end_time=old_data["end_time"],
                            date=old_data["date"],
                            color=old_data.get("color", "#58a6ff"),
                            category=old_data.get("category", "Work"),
                            recurring=old_data.get("recurring", "none"),
                            reminder_minutes=old_data.get("reminder_minutes", 10)
                        )
                        return f"Undid delete: '{old_data['title']}' restored"

                elif act_type in ("update", "move"):
                    # Undo update/move -> restore old fields
                    if old_data:
                        self.db.update_event(
                            target_id,
                            title=old_data.get("title"),
                            start_time=old_data.get("start_time"),
                            end_time=old_data.get("end_time"),
                            date=old_data.get("date"),
                            category=old_data.get("category"),
                            color=old_data.get("color")
                        )
                        return f"Undid {act_type}: '{old_data.get('title', 'Event')}' restored to {old_data.get('start_time', '')}"

            elif target_type == "checklist":
                if act_type == "toggle":
                    self.db.toggle_checklist_item(target_id)
                    return "Undid checklist toggle"
                elif act_type == "add":
                    self.db.delete_checklist_item(target_id)
                    return "Undid checklist task creation"
                elif act_type == "delete" and old_data:
                    self.db.add_checklist_item(
                        title=old_data["title"],
                        date_str=old_data["date"],
                        event_id=old_data.get("event_id"),
                        routine_id=old_data.get("routine_id")
                    )
                    return f"Undid task deletion: '{old_data.get('title', 'Task')}' restored"

        except Exception as e:
            logger.error(f"Failed to execute undo: {e}")
            return None

        return "Action undone"

    def redo(self) -> str | None:
        """Redo the most recently undone operation. Returns a user-friendly description or None."""
        action = self.db.pop_last_redoable_action()
        if not action:
            return None

        act_type = action["action_type"]
        target_type = action["target_type"]
        target_id = action["target_id"]
        old_data = json.loads(action["old_data"]) if action["old_data"] else None
        new_data = json.loads(action["new_data"]) if action["new_data"] else None

        try:
            if target_type == "event":
                if act_type == "add" and new_data:
                    self.db.add_event(
                        title=new_data.get("title", "Event"),
                        description=new_data.get("description", ""),
                        start_time=new_data.get("start_time", "09:00"),
                        end_time=new_data.get("end_time", "10:00"),
                        date=new_data.get("date", datetime.now().strftime("%Y-%m-%d")),
                        color=new_data.get("color", "#58a6ff"),
                        category=new_data.get("category", "Work"),
                        recurring=new_data.get("recurring", "none"),
                        reminder_minutes=new_data.get("reminder_minutes", 10)
                    )
                    return f"Redid add: '{new_data.get('title', 'Event')}'"

                elif act_type == "delete":
                    self.db.delete_event(target_id)
                    return "Redid delete"

                elif act_type in ("update", "move") and new_data:
                    self.db.update_event(
                        target_id,
                        title=new_data.get("title"),
                        start_time=new_data.get("start_time"),
                        end_time=new_data.get("end_time"),
                        date=new_data.get("date"),
                        category=new_data.get("category"),
                        color=new_data.get("color")
                    )
                    return f"Redid {act_type}: '{new_data.get('title', 'Event')}' moved to {new_data.get('start_time', '')}"

            elif target_type == "checklist":
                if act_type == "toggle":
                    self.db.toggle_checklist_item(target_id)
                    return "Redid checklist toggle"

        except Exception as e:
            logger.error(f"Failed to execute redo: {e}")
            return None

        return "Action redone"
