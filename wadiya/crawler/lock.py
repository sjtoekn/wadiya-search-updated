"""Single-crawler lock: an OS-level advisory lock on a file next to the database.
The OS releases it automatically when the process exits or is killed, so a crash can never leave a stale lock."""
from __future__ import annotations

import os

try:
    import fcntl

    def _lock(fh):
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fh):
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
except ImportError:                      # Windows
    import msvcrt

    def _lock(fh):
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(fh):
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


class CrawlAlreadyRunning(RuntimeError):
    pass


class CrawlLock:
    def __init__(self, path: str):
        self.path, self._fh = str(path), None

    def __enter__(self):
        fh = open(self.path, "a+")
        try:
            _lock(fh)
        except OSError:
            fh.seek(0)
            holder = fh.read().strip() or "unknown"
            fh.close()
            raise CrawlAlreadyRunning(f"another crawler is already running (pid {holder}); lock file: {self.path}")
        fh.seek(0); fh.truncate(); fh.write(str(os.getpid())); fh.flush()
        self._fh = fh
        return self

    def __exit__(self, *exc):
        if self._fh:
            try:
                _unlock(self._fh)
            finally:
                self._fh.close(); self._fh = None
        return False
