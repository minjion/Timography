"""Queue background callbacks without calling Tk from worker threads."""
from queue import SimpleQueue, Empty
import logging

logger = logging.getLogger(__name__)


class UIDispatcher:
    def __init__(self, root):
        self.root = root
        self.queue = SimpleQueue()
        self.closed = False
        self.after_id = root.after(50, self._drain)

    def post(self, callback):
        if not self.closed:
            self.queue.put(callback)

    def _drain(self):
        for _ in range(100):
            if self.closed:
                return
            try:
                callback = self.queue.get_nowait()
            except Empty:
                break
            try:
                callback()
            except Exception:
                logger.exception("Background UI callback failed")
        self.after_id = self.root.after(50, self._drain)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.root.after_cancel(self.after_id)
