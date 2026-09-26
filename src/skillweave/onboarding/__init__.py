"""Operator onboarding service (SW-156-ONBOARD-002).

A single :class:`OnboardingService` is shared by the ``skillweave-onboarding``
skill and the CLI entry point. It wraps the existing
:mod:`skillweave.onboarding_cli` profile/phase/goal flow and adds preview,
durable persistence to ``skillweave.config/``, generated state to
``.skillweave/``, idempotence and reprofile-diff support.
"""

from .service import (
    OnboardingService,
    OnboardingPreview,
    OnboardingState,
    OnboardingDiff,
)

__all__ = [
    "OnboardingService",
    "OnboardingPreview",
    "OnboardingState",
    "OnboardingDiff",
]
