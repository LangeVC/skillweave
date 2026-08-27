"""Authoritative dispatch profile resolution (SW138-PROFILE-001).

Integration proof across the dispatch contract, the routing profile, and the
tool-agnostic launch seam. Five acceptance criteria, each as a red/green proof:

1. A mutating dispatch without an explicit profile path fails before any
   process launch; there is no repository-wide implicit default.
2. Changing only the profile's launch command or model changes the actual child
   invocation and the requested/resolved-model receipt fields.
3. Ops, reviewer and observer each resolve to an explicit ToolSpec launch or an
   explicit in-place mode; an absent required role fails naming that role.
4. ``timeout``, ``max_retries``, ``min_models_required`` and
   ``on_model_failure`` resolve through one documented precedence chain and are
   not replaceable by a side table.
5. No implementation branch under ``src/skillweave/dispatch/`` matches a
   literal harness or model name.

The existing ``profiles/example-standard.yaml`` and the routing seams
(``launch_from_role``, ``load_profiles_from_location``) are reused unchanged;
this module only adds the authoritative resolution in front of them.
"""

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from skillweave.dispatch.profile_resolution import (  # noqa: E402
    ProfileResolutionError,
    ResolvedRole,
    resolve_dispatch_profile,
    resolve_limits,
)
from skillweave.routing import (  # noqa: E402
    ToolSpec,
    launch_from_role,
    load_profiles_from_location,
)
from skillweave.routing.profile import Limits  # noqa: E402

_REPO = Path(__file__).resolve().parent.parent.parent
_EXAMPLE_PROFILE = _REPO / "profiles" / "example-standard.yaml"

REQUIRED_ROLES = ("ops", "reviewer", "observer")


def _resolve_example(**kwargs):
    kwargs.setdefault("profile_path", str(_EXAMPLE_PROFILE))
    kwargs.setdefault("required_roles", REQUIRED_ROLES)
    return resolve_dispatch_profile(**kwargs)


# ── Criterion 1: explicit path required, no implicit default ───────────────

def test_mutating_dispatch_without_profile_path_fails_before_launch():
    # No repository-wide default: an absent/empty path is refused before any
    # tool is launched. The failure names the missing field.
    for bad in (None, "", "   "):
        with pytest.raises(ProfileResolutionError) as exc:
            resolve_dispatch_profile(bad, REQUIRED_ROLES)
        assert exc.value.field == "profile.path"


def test_missing_profile_location_fails_before_launch():
    # A caller-named path that does not exist surfaces from the loader, still
    # before any launch — there is no silent fallback directory.
    missing = str(_REPO / "profiles" / "does-not-exist.yaml")
    with pytest.raises(Exception) as exc:
        resolve_dispatch_profile(missing, REQUIRED_ROLES)
    # HarnessError (from load_profiles_from_location) or ProfileResolutionError
    # are both acceptable: the point is that nothing launched.
    assert "does-not-exist" in str(exc.value)


def test_example_profile_is_a_declared_location_not_a_default():
    # The example file loads only because the caller names its path; the same
    # location must be reachable but is never implied by the resolver.
    profiles = load_profiles_from_location(_EXAMPLE_PROFILE)
    assert "example-standard" in profiles


# ── Criterion 2: launch command / model drive the child + receipt ─────────

def test_launch_command_from_profile_drives_child_invocation():
    resolved = _resolve_example()
    ops = resolved.role("ops")
    assert ops.is_launch() is True
    assert ops.launch_command() is not None
    # The child invocation is the resolved launch command, against which the
    # tool-agnostic seam launches. Change the profile string → change this.
    tool = ops.tool
    assert tool.name == "opencode"
    assert "--model" in tool.launch_command


def test_changing_only_the_launch_command_changes_child_invocation():
    baseline = _resolve_example()
    baseline_cmd = baseline.role("ops").launch_command()

    # A profile that differs only in the launch command must change the child
    # invocation, and nothing else (model receipt and in-place status unchanged).
    import tempfile

    import yaml

    raw = yaml.safe_load(_EXAMPLE_PROFILE.read_text(encoding="utf-8"))
    original_cmd = raw["roles"]["ops"]["tool"]["launch_command"]
    raw["roles"]["ops"]["tool"]["launch_command"] = original_cmd + " --extra"
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tmp:
        yaml.safe_dump(raw, tmp)
        tmp_path = tmp.name

    try:
        altered = resolve_dispatch_profile(tmp_path, REQUIRED_ROLES)
    finally:
        Path(tmp_path).unlink()

    baseline_ops = baseline.role("ops")
    altered_ops = altered.role("ops")
    assert altered_ops.launch_command() == original_cmd + " --extra"
    assert altered_ops.launch_command() != baseline_cmd
    # The model receipt is unchanged: only the launch command moved.
    assert altered_ops.model.to_dict() == baseline_ops.model.to_dict()


def test_changing_only_the_model_changes_receipt_fields():
    import tempfile

    import yaml

    raw = yaml.safe_load(_EXAMPLE_PROFILE.read_text(encoding="utf-8"))
    raw["roles"]["ops"]["model"] = "faigate/deepseek-v4-flash"
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tmp:
        yaml.safe_dump(raw, tmp)
        tmp_path = tmp.name

    try:
        altered = resolve_dispatch_profile(tmp_path, REQUIRED_ROLES)
    finally:
        Path(tmp_path).unlink()

    baseline = _resolve_example()
    assert baseline.role("ops").model.requested == "faigate/deepseek-v4-pro"
    assert altered.role("ops").model.requested == "faigate/deepseek-v4-flash"
    # The resolved receipt follows the requested model (concrete stays concrete).
    assert altered.role("ops").model.resolved == "faigate/deepseek-v4-flash"
    assert altered.role("ops").model.to_dict() != baseline.role("ops").model.to_dict()


def test_receipt_keeps_requested_and_resolved_apart():
    resolved = _resolve_example()
    receipt = resolved.role("ops").model
    assert receipt is not None
    assert "requested" in receipt.to_dict()
    assert "resolved" in receipt.to_dict()


# ── Criterion 3: each role -> explicit launch or explicit in-place ─────────

def test_ops_and_reviewer_resolve_to_explicit_launch():
    resolved = _resolve_example()
    for role_key in ("ops", "reviewer"):
        r = resolved.role(role_key)
        assert r.is_launch() is True, f"{role_key} must launch"
        assert r.tool is not None
        assert r.in_place is False


def test_observer_resolves_to_explicit_in_place():
    resolved = _resolve_example()
    observer = resolved.role("observer")
    assert observer.is_launch() is False
    assert observer.in_place is True
    assert observer.tool is None
    assert observer.launch_command() is None


def test_absent_required_role_fails_naming_the_role():
    with pytest.raises(ProfileResolutionError) as exc:
        resolve_dispatch_profile(str(_EXAMPLE_PROFILE), ("ops", "nonexistent-role"))
    assert exc.value.field == "roles.nonexistent-role"
    assert "nonexistent-role" in str(exc.value)


def test_resolved_roles_align_with_the_launch_seam():
    # The resolved tool spec is exactly what launch_from_role consumes: for an
    # in-place role it records in place, for a launch role it dispatches. This
    # proves the resolution output is the seam's real input, not an invented one.
    resolved = _resolve_example()

    observer = resolved.role("observer")
    outcome = launch_from_role(
        observer.role,
        None,
        b"",
        run_id="run-ir",
        subject_repo="skillweave/skillweave",
        subject_commit="0" * 40,
        model=observer.model.resolved if observer.model is not None else "in-place",
    )
    assert outcome.in_place is True

    ops = resolved.role("ops")
    assert isinstance(ops.tool, ToolSpec)


# ── Criterion 4: one documented precedence chain for the four limits ───────

def test_limits_resolve_override_then_profile_then_default():
    profile_limits = Limits(timeout=30.0, max_retries=2, min_models_required=4, on_model_failure="abort")

    # Override set on every field wins.
    override = Limits(timeout=1.0, max_retries=0, min_models_required=1, on_model_failure="skip")
    out = resolve_limits(profile_limits, override)
    assert out.timeout == 1.0
    assert out.max_retries == 0
    assert out.min_models_required == 1
    assert out.on_model_failure == "skip"

    # No override -> profile limits.
    out = resolve_limits(profile_limits, None)
    assert out.timeout == 30.0
    assert out.max_retries == 2
    assert out.min_models_required == 4
    assert out.on_model_failure == "abort"

    # No profile, no override -> documented defaults.
    out = resolve_limits(None, None)
    assert out.timeout == 60.0
    assert out.max_retries == 1
    assert out.min_models_required == 2
    assert out.on_model_failure == "skip"


def test_each_limit_resolves_independently_through_the_same_chain():
    # One field overridden, the rest inherited from profile: the chain is
    # per-field, not all-or-nothing.
    profile_limits = Limits(timeout=30.0, max_retries=2, min_models_required=4, on_model_failure="retry")
    override = Limits(timeout=5.0, max_retries=None, min_models_required=None, on_model_failure=None)
    out = resolve_limits(profile_limits, override)
    assert out.timeout == 5.0
    assert out.max_retries == 2
    assert out.min_models_required == 4
    assert out.on_model_failure == "retry"


def test_resolved_dispatch_carries_the_single_resolved_limits():
    resolved = _resolve_example()
    # The profile declares timeout 60.0 / max_retries 1 / min 2 / skip; no
    # override, so those flow through the chain into the resolved dispatch.
    assert resolved.limits is not None
    assert resolved.limits.timeout == 60.0
    assert resolved.limits.max_retries == 1
    assert resolved.limits.min_models_required == 2
    assert resolved.limits.on_model_failure == "skip"


# ── Criterion 5: no literal harness/model name in dispatch implementation ──

def test_no_literal_harness_or_model_name_in_dispatch_source():
    # The dispatch package (both modules) must carry no concrete harness or
    # model name: those are profile data, never a branch in the implementation.
    dispatch_dir = _SRC / "skillweave" / "dispatch"
    forbidden = ("opencode", "deepseek", "claude code", "codex", "gemini")
    offenders = []
    for module in dispatch_dir.glob("*.py"):
        lowered = module.read_text(encoding="utf-8").lower()
        for name in forbidden:
            if name in lowered:
                offenders.append((module.name, name))
    assert not offenders, (
        f"literal harness/model name in dispatch source: {offenders}"
    )


def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
