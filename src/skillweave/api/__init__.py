"""SkillWeave Stable Python API.

``SW-API-001``. Exposes the Run Application Service without allowing direct Store/Dispatcher bypass.
"""

from .run import execute_run
from skillweave.runsvc import RunExecution, RunIntegrationError, RunExecutionError

__all__ = [
    "execute_run",
    "RunExecution",
    "RunExecutionError",
    "RunIntegrationError",
]
