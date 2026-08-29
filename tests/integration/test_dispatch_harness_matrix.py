"""Harness adapter matrix integration test (SW1311-HARNESS-001).

Proves the provider-neutral adapter contract end to end against the hermetic
fixture data and the operator-dispatch application seam:

* Criterion 2 — hermetic fixture data covers the four adapters (Claude desktop
  harness, Codex, Antigravity, OpenCode) and keeps the four run-statuses
  (documented, installed, dispatch-proven, production) separate and honest.
* Criterion 6 — Controller, Ops, reviewer, observer and Integrator authorities
  are distinct; the negative-authority fixtures prove every adapter fails to
  hold each role it must not claim.
* The strict-controller pre-launch seam on ``OperatorDispatchApplication`` fails
  closed *before* any worker launch (no workspace provision) on a missing or
  stale digest and on a native-delegation bypass.
"""

import io
import sys
from pathlib import Path

import pytest
import yaml

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

_HARNESS_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "harnesses"
_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_SEQUENCE = _FIXTURES / "dispatch-sequence.yaml"
_PROFILE = _FIXTURES / "dispatch-profile.yaml"

from skillweave.dispatch.application import (  # noqa: E402
    OperatorDispatchApplication,
    ProvisionedWorkspace,
    WorkspaceSeam,
)
from skillweave.dispatch.contracts import Lane  # noqa: E402
from skillweave.dispatch.harness_contract import (  # noqa: E402
    AUTHORITY_ROLES,
    BypassNotRecordedError,
    DigestMismatchError,
    STATUS_DISPATCH_PROVEN,
    STATUS_DOCUMENTED,
    STATUS_INSTALLED,
    STATUS_PRODUCTION,
    HarnessAdapterProfile,
    StrictController,
    StrictControllerError,
    load_adapter_profiles,
)

ADAPTERS = ("claude-code", "codex", "antigravity", "opencode")


def _load(filename: str) -> dict:
    return yaml.safe_load((_HARNESS_FIXTURES / filename).read_text(encoding="utf-8")) or {}


def _profiles() -> dict[str, HarnessAdapterProfile]:
    return load_adapter_profiles(
        _load("profiles.yaml"),
        statuses=_load("statuses.yaml"),
        skill_digests=_load("digests.yaml"),
    )


class _FakeWorkspace(WorkspaceSeam):
    def __init__(self):
        self.provisions: list[str] = []
        self.releases: list[str] = []

    def provision(self, lane: Lane, run_id: str) -> ProvisionedWorkspace:
        self.provisions.append(lane.id)
        return ProvisionedWorkspace(base_sha=lane.base or "", path="/tmp/x")

    def release(self, lane: Lane, run_id: str) -> None:
        self.releases.append(lane.id)


class _RecordingInline:
    """In-line seam that records the call without launching a real process.

    A serialized/INLINE lane travels this seam; it must NOT be reached when a
    strict dispatch fails before launch. Kept hermetic so the test proves the
    gate without touching the real runner.
    """
    def __init__(self):
        self.calls = 0

    def __call__(self, command, **kwargs):
        self.calls += 1
        return _fake_result(command, kwargs)


def _fake_result(command, kwargs):
    from skillweave.fanout.dispatch import FanOutChild, FanOutResult

    class _Res:
        exit_code = 0
        termination = "exited"
        succeeded = True
        stdout = b"ok"
        stderr = b""
        stdout_receipt = None
        stderr_receipt = None
        message = ""

    child = FanOutChild(
        child_run_id=f"{kwargs.get('run_id', 'r')}-0",
        command=list(command),
        result=_Res(),
        model="m",
        subject_repo=kwargs.get("subject_repo", ""),
        subject_commit=kwargs.get("subject_commit", ""),
        tool=kwargs.get("tool", ""),
        cwd=kwargs.get("cwd"),
        raw_bytes=b"ok",
        stderr_bytes=b"",
        outcome="exit_code",
        stdout_ref=None,
        stderr_ref=None,
    )
    return FanOutResult(children=[child], overlapped=False)


class _RecordingFanout:
    """Records the parallel batch without launching real processes."""
    def __init__(self):
        self.calls = 0

    def __call__(self, commands, **kwargs):
        self.calls += 1
        result = _fake_result(commands[0] if commands else [], kwargs)
        return result


# ── Criterion 2: hermetic coverage with honest, separated statuses ────────

def test_fixture_covers_four_adapters():
    profiles = _profiles()
    assert set(profiles) == set(ADAPTERS)


def test_statuses_are_four_separate_axes_per_adapter():
    # A documented name never reads as a proven run; production is never claimed
    # without a proven run; installed is a target, not a record.
    profiles = _profiles()
    for adapter in ADAPTERS:
        p = profiles[adapter]
        # Only opencode has a proven real run; the other three must stay honest.
        if adapter == "opencode":
            assert p.status(STATUS_DISPATCH_PROVEN) is True
        else:
            assert p.status(STATUS_DISPATCH_PROVEN) is False
        # No adapter ships a production profile.
        assert p.status(STATUS_PRODUCTION) is False


def test_documented_never_asserts_proven():
    profiles = _profiles()
    for adapter in ("claude-code", "codex", "antigravity"):
        p = profiles[adapter]
        assert p.status(STATUS_DOCUMENTED) is True
        assert p.status(STATUS_DISPATCH_PROVEN) is False


def test_honest_statuses_are_enforced_by_the_loader():
    # A profile that claims production without a proven run is refused by
    # assert_statuses_honest — the axis separation is contractual, not cosmetic.
    with pytest.raises(Exception):
        load_adapter_profiles(
            {"opencode": {"statuses": {"production": True, "dispatch-proven": False}}},
        )


# ── Criterion 6: distinct authorities + negative-authority matrix ─────────

def test_each_adapter_holds_exactly_one_distinct_authority():
    profiles = _profiles()
    for adapter in ADAPTERS:
        role = profiles[adapter].authority_role()
        assert role in AUTHORITY_ROLES, f"adapter '{adapter}' authority {role!r}"
    # The five authorities map one-to-one across the four adapters plus the
    # observer/integrator surfaces; the negative matrix below proves no role
    # holds a foreign one.
    roles = frozenset(profiles[a].authority_role() for a in ADAPTERS)
    assert roles == frozenset({"controller", "ops", "reviewer", "integrator"})


def test_negative_authority_fixtures_pass_for_every_adapter():
    # The negative-authority fixture files pin, for every adapter, the set of
    # roles it must NOT hold. Each adapter's real authority must be disjoint
    # from its forbidden set (criterion 6: distinct, never conflation).
    negative = _load("negative-authority.yaml")
    forbidden_by_adapter = negative.get("forbidden-authority", {})
    profiles = _profiles()
    for adapter, forbidden in forbidden_by_adapter.items():
        real = profiles[adapter].authority_role()
        assert real not in forbidden, (
            f"adapter '{adapter}' must not hold '{real}' (negative authority violated)"
        )
        for role in forbidden:
            assert profiles[adapter].has_authority(role) is False


def test_negative_authority_profile_is_refused():
    # A malformed profile claiming a second foreign role is refused by the
    # strict reconcile seam.
    negative = _load("negative-authority.yaml")
    bad = negative["negative-authority-profiles"]["claude-code"]
    controller = StrictController(require_skillweave_dispatch=True)
    profile = HarnessAdapterProfile.from_dict(bad, adapter_name="claude-code")
    with pytest.raises(Exception):
        controller.reconcile_authority(profile)


# ── Strict pre-launch seam on the application ─────────────────────────────

def _app() -> tuple[OperatorDispatchApplication, _FakeWorkspace]:
    ws = _FakeWorkspace()
    app = OperatorDispatchApplication(
        workspace_seam=ws,
        fanout_seam=_RecordingFanout(),
        inline_seam=_RecordingInline(),
    )
    return app, ws


def test_strict_pre_launch_seam_refuses_before_worker_launch_on_missing_binding():
    # With a strict controller configured but NO adapter binding supplied, the
    # pre-launch seam refuses (missing installed skill digests) before any
    # workspace is provisioned or any child launches.
    app, ws = _app()
    app._strict_controller = StrictController(require_skillweave_dispatch=True)
    with pytest.raises(Exception) as exc:
        app.dispatch(
            str(_SEQUENCE), str(_PROFILE), wave="0", sink=io.StringIO(),
            work=b"the exact task brief",
        )
    assert "installed skill digests" in str(exc.value)
    assert ws.provisions == []  # fail closed before any worker launch


def test_strict_pre_launch_seam_refuses_before_launch_on_stale_digest():
    # A strict dispatch against an adapter whose observed digests are stale is
    # refused before launch, naming the mismatched asset.
    profiles = _profiles()
    adapter = profiles["opencode"]
    app, ws = _app()
    app._strict_controller = StrictController(require_skillweave_dispatch=True)
    observed = dict(adapter.skill_digests)
    first = next(iter(observed))
    observed[first] = "STALE"
    with pytest.raises(DigestMismatchError) as exc:
        app.dispatch(
            str(_SEQUENCE), str(_PROFILE), wave="0", sink=io.StringIO(),
            work=b"the exact task brief",
            strict_adapter=adapter,
            strict_skill_digests=observed,
        )
    assert exc.value.asset == first
    assert ws.provisions == []


def test_dispatch_level_native_delegation_bypass_records_and_refuses_before_launch():
    # F-HARNESS-001: the adapter's declared native-delegation bypass must be
    # consumed by the real pre-launch seam. app.dispatch records and refuses it
    # before any workspace is provisioned or any worker launches.
    profiles = _profiles()
    adapter = profiles["antigravity"]
    assert "native-delegation" in adapter.bypass_flags()
    ws = _FakeWorkspace()
    inline = _RecordingInline()
    fanout = _RecordingFanout()
    app = OperatorDispatchApplication(
        workspace_seam=ws,
        fanout_seam=fanout,
        inline_seam=inline,
    )
    app._strict_controller = StrictController(require_skillweave_dispatch=True)
    with pytest.raises(BypassNotRecordedError) as exc:
        app.dispatch(
            str(_SEQUENCE), str(_PROFILE), wave="0", sink=io.StringIO(),
            work=b"the exact task brief",
            strict_adapter=adapter,
            strict_skill_digests=dict(adapter.skill_digests),
        )
    assert exc.value.asset == "antigravity"
    assert "native-delegation" in str(exc.value)
    assert ws.provisions == []
    assert inline.calls == 0
    assert fanout.calls == 0


def test_dispatch_level_direct_shell_bypass_refuses_before_launch():
    # F-HARNESS-001: an adapter declaring a direct-shell bypass is recorded and
    # refused by the real pre-launch seam before any provisioning or launch.
    adapter = HarnessAdapterProfile(
        name="direct-shell-harness",
        authority={"role": "controller"},
        delegation={"skillweave-dispatch": True, "direct-shell": True},
        skill_digests={"skillweave-promptchain": "deadbeef"},
    )
    ws = _FakeWorkspace()
    inline = _RecordingInline()
    fanout = _RecordingFanout()
    app = OperatorDispatchApplication(
        workspace_seam=ws,
        fanout_seam=fanout,
        inline_seam=inline,
    )
    app._strict_controller = StrictController(require_skillweave_dispatch=True)
    with pytest.raises(BypassNotRecordedError) as exc:
        app.dispatch(
            str(_SEQUENCE), str(_PROFILE), wave="0", sink=io.StringIO(),
            work=b"the exact task brief",
            strict_adapter=adapter,
            strict_skill_digests=dict(adapter.skill_digests),
        )
    assert "direct-shell" in str(exc.value)
    assert ws.provisions == []
    assert inline.calls == 0
    assert fanout.calls == 0


def test_strict_dispatch_refuses_empty_task_brief_before_launch():
    # F-HARNESS-002: the real dispatch default is work=b"" — an empty brief is
    # a missing exact task brief, refused before any provisioning.
    profiles = _profiles()
    adapter = profiles["opencode"]
    ws = _FakeWorkspace()
    inline = _RecordingInline()
    fanout = _RecordingFanout()
    app = OperatorDispatchApplication(
        workspace_seam=ws,
        fanout_seam=fanout,
        inline_seam=inline,
    )
    app._strict_controller = StrictController(require_skillweave_dispatch=True)
    with pytest.raises(StrictControllerError) as exc:
        app.dispatch(
            str(_SEQUENCE), str(_PROFILE), wave="0", sink=io.StringIO(),
            strict_adapter=adapter,
            strict_skill_digests=dict(adapter.skill_digests),
        )
    assert "exact task brief" in str(exc.value)
    assert ws.provisions == []
    assert inline.calls == 0
    assert fanout.calls == 0


def test_adapter_native_delegation_bypass_fails_closed_and_recorded():
    # Antigravity declares a native-delegation bypass. Under strict SkillWeave
    # dispatch that bypass is recorded and refused by the controller — a worker
    # never launches through a foreign hand-off.
    profiles = _profiles()
    adapter = profiles["antigravity"]
    assert "native-delegation" in adapter.bypass_flags()
    controller = StrictController(require_skillweave_dispatch=True)
    with pytest.raises(BypassNotRecordedError) as exc:
        controller.record_attempt(
            kind="native-delegation", detail="hand-off", adapter=adapter
        )
    assert exc.value.asset == "antigravity"
    assert len(controller.attempts) == 1
    assert controller.attempts[0]["kind"] == "native-delegation"


def test_non_strict_dispatch_unchanged_without_a_controller():
    # Without a strict controller the seam is a no-op: existing dispatch,
    # receipt and topology behaviour is preserved.
    app, ws = _app()
    run = app.dispatch(
        str(_SEQUENCE), str(_PROFILE), wave="0", sink=io.StringIO(),
        work=b"task brief",
    )
    assert run.run_id
    # Provision happened (the covered lanes ran) — the seam did not interfere.
    assert len(ws.provisions) >= 1


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
