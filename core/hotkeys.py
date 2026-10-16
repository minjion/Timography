"""Global and in-app keyboard shortcut manager for Timography."""
import logging
from config import QUICK_ADD_HOTKEY

logger = logging.getLogger(__name__)


class GlobalHotkeyManager:
    """Manages global system-wide hotkeys (e.g., Ctrl+Space for Quick Add)."""

    def __init__(self, root, on_quick_add_callback, dispatch=None):
        self.root = root
        self.on_quick_add_callback = on_quick_add_callback
        self._listener = None
        self.dispatch = dispatch or (lambda callback: root.after(0, callback))

    def start(self):
        try:
            from pynput import keyboard

            def _trigger_quick_add():
                if self.on_quick_add_callback:
                    self.dispatch(self.on_quick_add_callback)

            hotkeys = {
                QUICK_ADD_HOTKEY: _trigger_quick_add
            }

            self._listener = keyboard.GlobalHotKeys(hotkeys)
            self._listener.daemon = True
            self._listener.start()
            logger.info(f"Global hotkey listener started for {QUICK_ADD_HOTKEY}")
        except Exception as e:
            logger.warning(f"Could not initialize global hotkeys: {e}")

    def stop(self):
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass


def bind_window_shortcuts(window, actions: dict):
    """Bind in-app keyboard shortcuts to a window or toplevel widget.

    actions dict example:
    {
        "<Key-n>": on_new_event,
        "<Key-t>": on_today,
        "<Key-d>": on_day_view,
        "<Key-w>": on_week_view,
        "<Control-z>": on_undo,
        "<Control-y>": on_redo,
        "<Control-f>": on_search_focus,
        "<Key-c>": on_toggle_checklist,
    }
    """
    for key, handler in actions.items():
        try:
            window.bind(key, lambda e, h=handler: _safe_call(h, e))
        except Exception as e:
            logger.debug(f"Could not bind {key}: {e}")


def _safe_call(handler, event):
    # Don't trigger letter shortcuts when typing inside an entry or text widget
    widget_class = event.widget.__class__.__name__.lower()
    if "entry" in widget_class or "textbox" in widget_class or "text" in widget_class:
        return  # Text widgets own typing and native undo/redo, including Ctrl keys.
    handler()
