"""Configuration test for SW-135-008: busy_timeout is set explicitly.

A concurrency-critical property of ``SQLiteRunStore`` — how long a second
writer waits for the SQLite write lock before failing with "database is
locked" — currently hangs off a library default (``sqlite3.connect`` sets a
5000 ms busy timeout) that nobody chose and that a caller can override by
supplying their own connection. So the WAL promise is only held by accident.

The fix makes the value explicit: the store sets ``PRAGMA busy_timeout``
itself, with a justified value and a comment explaining why, so the behaviour
no longer depends on the connect default.

This test therefore checks the CONFIGURATION, not a change in behaviour: it
asserts the store reports a nonzero, expected busy_timeout. There is no
red-vs-old-code proof here; that would be a sham, because the old code (via
the connect default) already behaved correctly.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from skillweave.runtime.store import SQLiteRunStore


def test_store_sets_busy_timeout_explicitly():
    store = SQLiteRunStore(":memory:")
    try:
        value = store._conn.execute("PRAGMA busy_timeout").fetchone()[0]
    finally:
        store.close()

    assert value > 0, (
        "busy_timeout must be set explicitly to a positive value so the WAL "
        "promise does not depend on the sqlite3.connect default; got %r" % value
    )


if __name__ == "__main__":
    test_store_sets_busy_timeout_explicitly()
    print("OK: busy_timeout configured explicitly")
