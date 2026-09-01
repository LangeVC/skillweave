"""Rework brief generation for SkillWeave lanes.

This package automates the creation of structured rework briefs from gate
logs after a Lane fails its review gate. It replaces the manual step in which
a controller would inspect the gate output and hand-author a correction brief.

Public API
----------
``ReworkBriefWriter``
    Finds the latest gate log for a lane, extracts failing criteria, and
    writes a Markdown rework brief to ``.skillweave/rework/``.

``GateLogReader``
    Loads a gate log (JSON or YAML) from the standard tracking-log location
    and normalises it into a ``GateLogEntry`` list.
"""

from skillweave.rework.brief import (
    GateLogEntry,
    GateLogReader,
    ReworkBrief,
    ReworkBriefWriter,
    ReworkError,
)

__all__ = [
    "GateLogEntry",
    "GateLogReader",
    "ReworkBrief",
    "ReworkBriefWriter",
    "ReworkError",
]
