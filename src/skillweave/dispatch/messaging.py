"""Worker-to-controller messaging channel (SW-158-RETRO-003).

Worker agents can send structured DirectMessage records to the controller
through a file-based JSONL channel. The controller creates the channel before
launching a worker, passes its path via the ``SW_MSG_CHANNEL`` environment
variable, and reads all messages from the channel after the worker completes.

Messages are never parsed from stdout/stderr logs: the channel is the sole
communication path, and stdout/stderr stay reserved for the existing evidence
capture. The channel file is cleaned up after the controller reads it.

Usage (controller side)::

    channel = MessageChannel()
    run = app.dispatch(seq, prof, sink=sink, message_channel=channel)
    for msg in channel.read_messages():
        print(msg.body)

Usage (worker side, in any language)::

    import os, json
    path = os.environ["SW_MSG_CHANNEL"]
    with open(path, "a") as f:
        f.write(json.dumps({"sender": "worker", "kind": "status", "body": ...}) + "\\n")
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


#: The environment variable the controller sets for the worker to discover the
#: message channel path.
ENV_MESSAGE_CHANNEL = "SW_MSG_CHANNEL"


class MessageChannelError(Exception):
    """A message channel operation failed."""


@dataclass
class DirectMessage:
    """One structured message from a worker to the controller.

    ``sender`` identifies the worker or role that sent the message. ``kind``
    classifies the message (e.g. ``"status"``, ``"result"``, ``"progress"``,
    ``"error"``). ``body`` is the free-form payload. ``timestamp`` is set by
    the channel when the message is written.

    The message contract is intentionally minimal: no routing table, no
    priority, no ACK — it is a direct, unordered, at-most-once delivery from
    a worker to the controller.
    """

    sender: str
    kind: str
    body: Any
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sender": self.sender,
            "kind": self.kind,
            "body": self.body,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DirectMessage":
        return cls(
            sender=str(data.get("sender", "")),
            kind=str(data.get("kind", "")),
            body=data.get("body"),
            timestamp=str(data.get("timestamp", "")),
        )


class MessageChannel:
    """A file-based, write-once-then-read message channel.

    The controller creates the channel, passes ``SW_MSG_CHANNEL=<path>`` in
    the subprocess environment, then calls ``read_messages()`` after the
    worker completes to collect every ``DirectMessage`` the worker wrote.

    The channel file is removed when ``close()`` is called or when the
    channel is used as a context manager.

    Thread-safety: the file is opened once for appending; concurrent writes
    from the same worker process are serialised by the kernel on the
    underlying file descriptor (append-mode writes are atomic on most
    platforms up to PIPE_BUF). Multiple workers writing to the same channel
    file is supported but discouraged — each worker should have its own
    channel for message provenance.
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = path or tempfile.mktemp(prefix="sw-msg-")
        self._fh: Optional[Any] = None
        self._open()

    def _open(self) -> None:
        """Open the channel file for appending (creates if absent)."""
        if self._fh is not None:
            return
        try:
            self._fh = open(self._path, "a", encoding="utf-8")
        except OSError as exc:
            raise MessageChannelError(
                f"cannot open message channel '{self._path}': {exc}"
            ) from exc

    @property
    def path(self) -> str:
        """The filesystem path of the message channel."""
        return self._path

    @property
    def env(self) -> dict[str, str]:
        """The environment variable dict to pass to the worker subprocess.

        Usage::

            proc = subprocess.Popen(..., env=channel.env)
        """
        return {ENV_MESSAGE_CHANNEL: self._path}

    # -- worker-side write --------------------------------------------------

    def write(self, message: DirectMessage) -> None:
        """Append one ``DirectMessage`` as a JSONL line to the channel.

        Raises :class:`MessageChannelError` when the channel is closed or
        the write fails.
        """
        if self._fh is None:
            raise MessageChannelError("message channel is closed")
        try:
            self._fh.write(json.dumps(message.to_dict(), sort_keys=True) + "\n")
            self._fh.flush()
        except OSError as exc:
            raise MessageChannelError(
                f"cannot write to message channel '{self._path}': {exc}"
            ) from exc

    # -- controller-side read -----------------------------------------------

    def read_messages(self) -> list[DirectMessage]:
        """Read all messages written to the channel.

        After this call the channel file is closed for writing and re-opened
        for reading. Returns an empty list when the channel has no messages
        or the file does not exist.
        """
        self.close()
        if not os.path.exists(self._path):
            return []
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError as exc:
            raise MessageChannelError(
                f"cannot read message channel '{self._path}': {exc}"
            ) from exc
        messages: list[DirectMessage] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                messages.append(DirectMessage.from_dict(data))
            except (json.JSONDecodeError, TypeError):
                continue  # skip malformed lines silently
        return messages

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        """Close the write handle (idempotent)."""
        fh = self._fh
        if fh is not None:
            self._fh = None
            try:
                fh.close()
            except OSError:
                pass

    def cleanup(self) -> None:
        """Close and remove the channel file (idempotent)."""
        self.close()
        if self._path and os.path.exists(self._path):
            try:
                os.remove(self._path)
            except OSError:
                pass

    def __enter__(self) -> "MessageChannel":
        self._open()
        return self

    def __exit__(self, *args: Any) -> None:
        self.cleanup()


__all__ = [
    "ENV_MESSAGE_CHANNEL",
    "MessageChannelError",
    "DirectMessage",
    "MessageChannel",
]
