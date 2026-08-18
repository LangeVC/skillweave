from .profile import (
    RoleDefinition,
    RoutingProfile,
    ToolSpec,
    from_dict,
    load_profile,
    load_profiles,
    load_matrix,
    builtin_roles,
    resolve_role,
    TIER_FAST,
    TIER_BALANCED,
    TIER_DEEP,
    CAP_MUTATE_RUN_STATE,
    CAP_APPROVE_GATE,
    INCOMPATIBLE_PAIRS,
    RoutingProfileError,
    TIER_TO_ROUTER,
    tier_to_router,
    tier_to_mode,
    ResolutionRecord,
)

# The harness record and profile-location loading (SW-RT-003, dispatch 1) live
# beside the profile, and are exported here in the same surface.
from .harness import (  # noqa: F401
    HarnessSource,
    HarnessError,
    HarnessDetermination,
    HarnessProfileMap,
    determine_harness,
    load_profiles_from_location,
    attach_harness,
)

# The Faigate adapter is the shared model-routing surface. It lives here (not
# under council/) so both the council and the RunnerAdapter import the same
# module. The ``council.faigate_adapter`` path remains as a back-compat shim.
from .faigate_adapter import (  # noqa: F401
    CouncilProvider,
    FaigateProvider,
    ModelInfo,
    ROUTER_PROFILES,
    detect_providers,
    get_best_provider,
    get_profile,
    list_detected_providers,
    list_profiles,
    known_model_ids,
    resolve_tier,
)

# The tool-agnostic dispatch seam (SW-RT-001): a role's tool is launched, the
# work handed over, and the result bound as evidence. It sits beside the profile
# and shares the same export surface, so consumers import it from the package.
from .dispatch import (  # noqa: F401
    DispatchFailure,
    DispatchResult,
    InPlaceRecord,
    RoleOutcome,
    launch_from_role,
    run_in_place,
    tokenize_launch,
)
# Re-exported under a distinct name. `dispatch` is also the module, and a
# re-export of the function under that name shadows it: `from skillweave.routing
# import dispatch` would hand back the function while the module of the same
# name stays out of reach. The module keeps its name; the function gets a
# qualified one.
from .dispatch import dispatch as dispatch_role  # noqa: F401

__all__ = [
    "RoleDefinition",
    "RoutingProfile",
    "ToolSpec",
    "from_dict",
    "load_profile",
    "load_profiles",
    "load_matrix",
    "builtin_roles",
    "resolve_role",
    "TIER_FAST",
    "TIER_BALANCED",
    "TIER_DEEP",
    "CAP_MUTATE_RUN_STATE",
    "CAP_APPROVE_GATE",
    "INCOMPATIBLE_PAIRS",
    "RoutingProfileError",
    "TIER_TO_ROUTER",
    "tier_to_router",
    "tier_to_mode",
    "ResolutionRecord",
    "HarnessSource",
    "HarnessError",
    "HarnessDetermination",
    "HarnessProfileMap",
    "determine_harness",
    "load_profiles_from_location",
    "attach_harness",
    "CouncilProvider",
    "FaigateProvider",
    "ModelInfo",
    "ROUTER_PROFILES",
    "detect_providers",
    "get_best_provider",
    "get_profile",
    "list_detected_providers",
    "list_profiles",
    "known_model_ids",
    "resolve_tier",
    "DispatchFailure",
    "DispatchResult",
    "InPlaceRecord",
    "RoleOutcome",
    "dispatch_role",
    "launch_from_role",
    "run_in_place",
    "tokenize_launch",
]
