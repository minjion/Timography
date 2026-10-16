"""Persistent undo/redo using atomic database snapshots."""
import json
import logging
from core.database import TimographyDB

logger = logging.getLogger(__name__)


class UndoManager:
    def __init__(self, db: TimographyDB):
        self.db = db

    def record(self, action_type, target_type, target_id, old_data=None, new_data=None):
        if action_type in ('add', 'update', 'move'):
            getter = self.db.get_event if target_type == 'event' else self.db.get_checklist_item
            new_data = getter(target_id) or new_data
        self.db.log_action(action_type, target_type, target_id,
            json.dumps(old_data) if old_data else None,
            json.dumps(new_data) if new_data else None)

    def _apply(self, redo):
        try:
            action = self.db.apply_history_action(redo=redo)
        except Exception:
            logger.exception('Could not apply %s', 'redo' if redo else 'undo')
            return None
        if not action:
            return None
        return f"{'Redid' if redo else 'Undid'} {action['target_type']} {action['action_type']}"

    def undo(self):
        return self._apply(False)

    def redo(self):
        return self._apply(True)
