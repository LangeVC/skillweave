"""
SW-158-RETRO-003: Worker agents send DirectMessages to the controller.

Covers:

1. A worker writes a message; the controller reads it back.
2. Multiple messages from the same worker are all readable.
3. An empty channel returns an empty list.
4. Channel file is cleaned up after close.
5. The env property returns the expected ``SW_MSG_CHANNEL`` variable.
6. Malformed lines in the channel file are silently skipped.
7. The channel is usable as a context manager.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.dispatch.messaging import (
    ENV_MESSAGE_CHANNEL,
    DirectMessage,
    MessageChannel,
    MessageChannelError,
)


def _check() -> None:
    """Minimal self-check: the messaging module is importable."""
    assert ENV_MESSAGE_CHANNEL == "SW_MSG_CHANNEL"


def test_write_then_read() -> None:
    """Worker writes a message, controller reads it."""
    channel = MessageChannel()
    try:
        channel.write(DirectMessage(sender="worker1", kind="status", body="hello"))
        messages = channel.read_messages()
        assert len(messages) == 1
        msg = messages[0]
        assert msg.sender == "worker1"
        assert msg.kind == "status"
        assert msg.body == "hello"
        assert msg.timestamp != ""
    finally:
        channel.cleanup()


def test_multiple_messages() -> None:
    """Multiple messages from the same worker are all readable."""
    channel = MessageChannel()
    try:
        channel.write(DirectMessage(sender="worker1", kind="status", body="step1"))
        channel.write(DirectMessage(sender="worker1", kind="status", body="step2"))
        channel.write(DirectMessage(sender="worker1", kind="result", body={"key": "val"}))
        messages = channel.read_messages()
        assert len(messages) == 3
        assert messages[0].body == "step1"
        assert messages[1].body == "step2"
        assert messages[2].body == {"key": "val"}
    finally:
        channel.cleanup()


def test_empty_channel() -> None:
    """An empty channel returns an empty list."""
    channel = MessageChannel()
    try:
        messages = channel.read_messages()
        assert messages == []
    finally:
        channel.cleanup()


def test_cleanup_removes_file() -> None:
    """Channel file is removed after cleanup."""
    channel = MessageChannel()
    path = channel.path
    assert os.path.exists(path)
    channel.cleanup()
    assert not os.path.exists(path)


def test_env_property() -> None:
    """The env property returns SW_MSG_CHANNEL pointing at the channel path."""
    channel = MessageChannel()
    try:
        env = channel.env
        assert ENV_MESSAGE_CHANNEL in env
        assert env[ENV_MESSAGE_CHANNEL] == channel.path
    finally:
        channel.cleanup()


def test_context_manager() -> None:
    """Channel is usable as a context manager and cleans up on exit."""
    with MessageChannel() as channel:
        path = channel.path
        assert os.path.exists(path)
        channel.write(DirectMessage(sender="worker1", kind="status", body="ok"))
    assert not os.path.exists(path)


def test_write_after_close_raises() -> None:
    """Writing after close raises MessageChannelError."""
    channel = MessageChannel()
    channel.close()
    try:
        channel.write(DirectMessage(sender="w", kind="s", body="x"))
        assert False, "expected MessageChannelError"
    except MessageChannelError:
        pass
    finally:
        channel.cleanup()


def test_malformed_lines_skipped() -> None:
    """Malformed JSONL lines are silently skipped during read."""
    channel = MessageChannel()
    try:
        # Write a valid message first
        channel.write(DirectMessage(sender="w", kind="s", body="good"))
        channel.close()
        # Append malformed lines directly
        with open(channel.path, "a", encoding="utf-8") as f:
            f.write("not json\n")
            f.write("{'bad': syntax}\n")
            f.write("\n")
        messages = channel.read_messages()
        # Only the valid message should be returned
        assert len(messages) == 1
        assert messages[0].body == "good"
    finally:
        channel.cleanup()


def test_from_dict_roundtrip() -> None:
    """DirectMessage survives a to_dict/from_dict round-trip."""
    original = DirectMessage(sender="w", kind="error", body={"code": 42}, timestamp="2024-01-01T00:00:00")
    data = original.to_dict()
    restored = DirectMessage.from_dict(data)
    assert restored.sender == original.sender
    assert restored.kind == original.kind
    assert restored.body == original.body
    assert restored.timestamp == original.timestamp


def test_explicit_path() -> None:
    """A channel with an explicit path writes to and reads from that path."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        channel = MessageChannel(path=tmp_path)
        assert channel.path == tmp_path
        channel.write(DirectMessage(sender="w", kind="s", body="explicit"))
        messages = channel.read_messages()
        assert len(messages) == 1
        assert messages[0].body == "explicit"
        channel.cleanup()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_idempotent_close() -> None:
    """Closing an already-closed channel is a no-op."""
    channel = MessageChannel()
    channel.close()
    channel.close()  # should not raise


def test_idempotent_cleanup() -> None:
    """Cleaning up an already-cleaned channel is a no-op."""
    channel = MessageChannel()
    channel.cleanup()
    channel.cleanup()  # should not raise
