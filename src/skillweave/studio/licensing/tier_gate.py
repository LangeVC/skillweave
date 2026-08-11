"""Tier enforcement gate for SkillWeave Studio features.

The ``require_studio()`` decorator / context-manager blocks execution
of Studio-tier hooks unless a valid license is present.  The sole
exception is the ``pre_discovery`` injection point (mentoring hooks),
which is available on the Free tier.
"""

from __future__ import annotations

import functools
import logging
from enum import Enum
from typing import Any, Callable, Optional

from .jwt_validator import LicenseValidator, LicensePayload, LicenseError

logger = logging.getLogger(__name__)

FREE_TIER_POSITIONS = frozenset({"pre_discovery"})


class Tier(str, Enum):
    FREE = "free"
    STUDIO = "studio"


class TierGate:
    """Evaluates whether the current license tier allows a hook to run."""

    def __init__(self, validator: Optional[LicenseValidator] = None):
        self._validator = validator or LicenseValidator()
        self._cached_payload: Optional[LicensePayload] = None

    def check(self, phase: str, position: str) -> Tier:
        """Return the effective tier.  Raises LicenseError if Studio is
        required but no valid license exists.

        Free-tier bypass: ``pre_discovery`` hooks always run.
        """
        injection_point = f"{position}_{phase}"

        if injection_point in FREE_TIER_POSITIONS:
            return Tier.FREE

        payload = self._get_license()
        if payload is None or payload.tier != "studio":
            raise LicenseError(
                f"Studio license required for {injection_point}. "
                "Get a license at https://skillweave.xyz/studio"
            )

        return Tier.STUDIO

    def get_tier(self) -> Tier:
        """Return current tier without raising."""
        payload = self._get_license()
        if payload and payload.tier == "studio":
            return Tier.STUDIO
        return Tier.FREE

    def is_studio(self) -> bool:
        return self.get_tier() == Tier.STUDIO

    def _get_license(self) -> Optional[LicensePayload]:
        if self._cached_payload is not None and self._cached_payload.is_valid:
            return self._cached_payload
        try:
            self._cached_payload = self._validator.load_from_disk()
        except Exception as e:
            logger.debug("License load failed: %s", e)
            self._cached_payload = None
        return self._cached_payload


def require_studio(func: Optional[Callable] = None, *, gate: Optional[TierGate] = None) -> Any:
    """Decorator that gates a function behind a Studio license.

    Usage::

        @require_studio
        async def my_studio_hook(ctx):
            ...

        # or with explicit gate
        @require_studio(gate=my_gate)
        async def my_hook(ctx):
            ...
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            _gate = gate or TierGate()
            if not _gate.is_studio():
                raise LicenseError(
                    f"Studio license required to run {fn.__name__}. "
                    "Get a license at https://skillweave.xyz/studio"
                )
            return await fn(*args, **kwargs)

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator
