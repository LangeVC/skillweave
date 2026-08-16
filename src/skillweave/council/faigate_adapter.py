"""Back-compat shim.

The Faigate adapter no longer lives under ``council/``. Its single shared
surface is :mod:`skillweave.routing.faigate_adapter`, which both the council
and the RunnerAdapter import. This module forwards to that surface so existing
``skillweave.council.faigate_adapter`` import paths keep resolving — it is NOT
a second copy of the adapter.
"""

from skillweave.routing.faigate_adapter import *  # noqa: F401,F403
from skillweave.routing.faigate_adapter import (  # noqa: F401
    CouncilProvider,
    FaigateProvider,
    GenericRouterProvider,
    ModelInfo,
    OpenRouterProvider,
    ROUTER_PROFILES,
    SingleModelProvider,
    detect_providers,
    get_best_provider,
    get_profile,
    list_detected_providers,
    list_profiles,
)
