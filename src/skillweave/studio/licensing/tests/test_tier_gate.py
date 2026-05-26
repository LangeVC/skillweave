"""Tests for tier gate enforcement."""

import pytest
from unittest.mock import patch, MagicMock
from skillweave.studio.licensing.tier_gate import (
    TierGate, Tier, require_studio, FREE_TIER_POSITIONS,
)
from skillweave.studio.licensing.jwt_validator import (
    LicenseValidator, LicensePayload, LicenseError,
)
import time


def _make_studio_payload() -> LicensePayload:
    return LicensePayload(
        sub="test@studio.com",
        tier="studio",
        iat=int(time.time()),
        exp=int(time.time()) + 3600,
    )


def _make_free_payload() -> LicensePayload:
    return LicensePayload(
        sub="test@free.com",
        tier="free",
        iat=int(time.time()),
        exp=int(time.time()) + 3600,
    )


class TestTierGate:
    def test_pre_discovery_always_free(self):
        gate = TierGate()
        # pre_discovery should return FREE without checking license
        tier = gate.check(phase="discovery", position="pre")
        assert tier == Tier.FREE

    def test_pre_build_requires_studio(self):
        gate = TierGate()
        with pytest.raises(LicenseError, match="Studio license required"):
            gate.check(phase="build", position="pre")

    def test_studio_license_passes(self):
        validator = MagicMock(spec=LicenseValidator)
        validator.load_from_disk.return_value = _make_studio_payload()
        gate = TierGate(validator=validator)
        tier = gate.check(phase="build", position="pre")
        assert tier == Tier.STUDIO

    def test_free_license_blocks(self):
        validator = MagicMock(spec=LicenseValidator)
        validator.load_from_disk.return_value = _make_free_payload()
        gate = TierGate(validator=validator)
        with pytest.raises(LicenseError):
            gate.check(phase="test", position="post")

    def test_get_tier_studio(self):
        validator = MagicMock(spec=LicenseValidator)
        validator.load_from_disk.return_value = _make_studio_payload()
        gate = TierGate(validator=validator)
        assert gate.get_tier() == Tier.STUDIO
        assert gate.is_studio()

    def test_get_tier_free_when_no_license(self):
        validator = MagicMock(spec=LicenseValidator)
        validator.load_from_disk.return_value = None
        gate = TierGate(validator=validator)
        assert gate.get_tier() == Tier.FREE
        assert not gate.is_studio()

    def test_cached_payload(self):
        validator = MagicMock(spec=LicenseValidator)
        validator.load_from_disk.return_value = _make_studio_payload()
        gate = TierGate(validator=validator)
        gate.check(phase="build", position="pre")
        gate.check(phase="test", position="post")
        # Should only load once due to caching
        validator.load_from_disk.assert_called_once()


class TestRequireStudioDecorator:
    @pytest.mark.asyncio
    async def test_blocks_without_license(self):
        @require_studio
        async def my_hook():
            return "result"

        with pytest.raises(LicenseError):
            await my_hook()

    @pytest.mark.asyncio
    async def test_passes_with_studio_gate(self):
        validator = MagicMock(spec=LicenseValidator)
        validator.load_from_disk.return_value = _make_studio_payload()
        gate = TierGate(validator=validator)

        @require_studio(gate=gate)
        async def my_hook():
            return "result"

        result = await my_hook()
        assert result == "result"

    def test_free_tier_positions_contains_pre_discovery(self):
        assert "pre_discovery" in FREE_TIER_POSITIONS
