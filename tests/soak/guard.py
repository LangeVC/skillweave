"""Double-start prevention guard and single-instance locks (SW-SOAK-001).

Guarantees that a soak test, coordinator instance, or worker lane cannot be started
concurrently if an instance is already active. Overlapping starts are blocked
fail-closed before execution begins.
"""

from __future__ import annotations

import fcntl
import json
import os
import signal
import socket
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


class DoubleStartPreventedError(RuntimeError):
    """Raised when an attempt is made to start an already running soak test or process."""

    def __init__(self, lock_path: str, holder_info: Dict[str, Any]):
        self.lock_path = lock_path
        self.holder_info = holder_info
        holder_pid = holder_info.get("pid", "unknown")
        holder_time = holder_info.get("acquired_at", "unknown")
        holder_host = holder_info.get("host", "unknown")
        super().__init__(
            f"Double-start prevented: Active instance already running on {holder_host} "
            f"(PID {holder_pid}, acquired at {holder_time}). Lock file: '{lock_path}'"
        )


@dataclass
class LockInfo:
    """Metadata recorded in the lock file."""

    pid: int
    host: str
    acquired_at: str
    tag: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pid": self.pid,
            "host": self.host,
            "acquired_at": self.acquired_at,
            "tag": self.tag,
        }


class DoubleStartGuard:
    """File-based single instance lock enforcing single execution.

    Uses OS advisory file locking (fcntl.flock) and PID inspection to block
    duplicate starts while automatically cleaning up stale locks from aborted runs.
    """

    def __init__(self, lock_path: Optional[str] = None, tag: str = "soak-runner") -> None:
        if lock_path:
            self.lock_path = Path(lock_path).resolve()
        else:
            self.lock_path = Path(tempfile.gettempdir()) / f"skillweave_soak_{tag}.lock"

        self.tag = tag
        self._fd: Optional[int] = None
        self._is_locked: bool = False

    @property
    def is_locked(self) -> bool:
        return self._is_locked

    def acquire(self, timeout_seconds: float = 0.0) -> bool:
        """Attempt to acquire the lock.

        If already locked by another active process:
        - Raises :class:`DoubleStartPreventedError` if timeout_seconds == 0
        - Retries up to timeout_seconds before raising

        Returns True on successful acquisition.
        """
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        start_time = time.time()

        while True:
            try:
                # Open or create the lock file
                fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT, 0o644)
                # Try non-blocking exclusive lock
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

                # Successfully locked
                self._fd = fd
                self._is_locked = True

                # Write owner metadata
                info = LockInfo(
                    pid=os.getpid(),
                    host=socket.gethostname(),
                    acquired_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    tag=self.tag,
                )
                os.ftruncate(fd, 0)
                os.lseek(fd, 0, os.SEEK_SET)
                payload = json.dumps(info.to_dict()).encode("utf-8")
                os.write(fd, payload)
                os.fsync(fd)
                return True

            except (IOError, OSError):
                # Lock is held by another process
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass

                # Read holder info if possible
                holder_info = self._read_holder_info()

                # Check if holder process is actually dead (stale lock cleanup)
                if self._is_stale_lock(holder_info):
                    # Attempt to remove stale lock file and retry immediately
                    try:
                        os.remove(str(self.lock_path))
                        continue
                    except OSError:
                        pass

                elapsed = time.time() - start_time
                if elapsed >= timeout_seconds:
                    raise DoubleStartPreventedError(str(self.lock_path), holder_info)

                time.sleep(min(0.05, timeout_seconds - elapsed))

    def _read_holder_info(self) -> Dict[str, Any]:
        """Read metadata of the current lock holder."""
        try:
            if self.lock_path.exists():
                content = self.lock_path.read_text(encoding="utf-8").strip()
                if content:
                    return json.loads(content)
        except Exception:
            pass
        return {"pid": "unknown", "acquired_at": "unknown", "host": "unknown", "tag": self.tag}

    def _is_stale_lock(self, holder_info: Dict[str, Any]) -> bool:
        """Check whether the lock holder PID is no longer alive on this host."""
        holder_pid = holder_info.get("pid")
        holder_host = holder_info.get("host")
        if not isinstance(holder_pid, int):
            return False

        # Only check PID if on the same host
        if holder_host and holder_host != socket.gethostname():
            return False

        try:
            # Signal 0 checks if process exists without killing it
            os.kill(holder_pid, 0)
            return False  # Still alive
        except OSError:
            # Process does not exist -> stale lock
            return True

    def release(self) -> None:
        """Release the held lock."""
        if self._is_locked and self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except OSError:
                pass
            finally:
                self._fd = None
                self._is_locked = False

            try:
                if self.lock_path.exists():
                    os.remove(str(self.lock_path))
            except OSError:
                pass

    def __enter__(self) -> DoubleStartGuard:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
