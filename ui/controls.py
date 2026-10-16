"""App controls that release Tk callbacks together with their widgets."""
import tkinter as tk

import customtkinter as ctk


def cancel_pending_callbacks(widget):
    """Cancel queued Tcl commands owned by this widget or its descendants.

    CTk buttons queue a click animation before running their command. That command
    may delete its row or close a dialog, leaving Tk to invoke a deleted command.
    Include internal CTk descendants such as textbox scrollbar polling callbacks.
    Let normal widget destruction delete the registered commands themselves.
    """
    commands = set()
    pending = [widget]
    try:
        while pending:
            current = pending.pop()
            commands.update(getattr(current, "_tclCommands", None) or ())
            pending.extend(current.winfo_children())
        for timer in widget.tk.splitlist(widget.tk.call("after", "info")):
            script, _ = widget.tk.call("after", "info", timer)
            command = widget.tk.splitlist(script)
            if command and command[0] in commands:
                widget.tk.call("after", "cancel", timer)
    except tk.TclError:
        # Teardown may already have removed the window or its interpreter.
        return


class AppButton(ctk.CTkButton):
    def destroy(self):
        cancel_pending_callbacks(self)
        super().destroy()


class AppToplevel(ctk.CTkToplevel):
    def __init__(self, *args, **kwargs):
        self._owned_global_bindings = []
        super().__init__(*args, **kwargs)

    def bind_all(self, sequence=None, func=None, add=None):
        binding = super().bind_all(sequence, func, add)
        if func is not None and binding:
            self._owned_global_bindings.append((sequence, binding))
        return binding

    def destroy(self):
        cancel_pending_callbacks(self)
        root = self._root()
        for sequence, binding in self._owned_global_bindings:
            root._unbind(("bind", "all", sequence), binding)
        self._owned_global_bindings.clear()
        super().destroy()
