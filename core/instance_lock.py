"""Process-scoped lock for a local database; OS releases it after a crash."""
from pathlib import Path
import os


class InstanceLock:
    def __init__(self, db_path):
        self.path = Path(db_path).resolve().with_suffix(".lock")
        self._file = None

    def acquire(self):
        if self._file is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        handle.truncate(1)
        handle.write(str(os.getpid()).encode("ascii"))
        handle.flush()
        self._file = handle
        return True

    def release(self):
        handle, self._file = self._file, None
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
        # Keep the lock file: unlinking it can race a newly acquired instance.
