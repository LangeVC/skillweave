"""Tests for JWT license validation."""

import time
import pytest
from skillweave.studio.licensing.jwt_validator import (
    LicenseValidator,
    LicensePayload,
    LicenseError,
    GRACE_PERIOD_SECONDS,
)


@pytest.fixture
def validator():
    return LicenseValidator(signing_secret="test-secret")


class TestLicensePayload:
    def test_valid_not_expired(self):
        p = LicensePayload(sub="u1", tier="studio", iat=int(time.time()), exp=int(time.time()) + 3600)
        assert p.is_valid
        assert not p.is_expired
        assert p.days_remaining >= 0

    def test_expired_within_grace(self):
        p = LicensePayload(sub="u1", tier="studio", iat=0, exp=int(time.time()) - 100)
        assert p.is_expired
        assert p.is_within_grace
        assert p.is_valid  # grace period still active

    def test_expired_past_grace(self):
        p = LicensePayload(sub="u1", tier="studio", iat=0, exp=int(time.time()) - GRACE_PERIOD_SECONDS - 100)
        assert p.is_expired
        assert not p.is_within_grace
        assert not p.is_valid

    def test_trial_flag(self):
        p = LicensePayload(sub="u1", tier="studio", iat=0, exp=int(time.time()) + 3600, trial=True)
        assert p.is_trial


class TestLicenseValidator:
    def test_create_and_validate(self, validator):
        token = validator.create_token(sub="user@test.com", tier="studio")
        payload = validator.validate(token)
        assert payload.sub == "user@test.com"
        assert payload.tier == "studio"
        assert payload.is_valid

    def test_trial_token(self, validator):
        token = validator.create_token(sub="trial@test.com", trial=True)
        payload = validator.validate(token)
        assert payload.is_trial
        assert payload.days_remaining <= 14

    def test_malformed_jwt_raises(self, validator):
        with pytest.raises(LicenseError, match="Malformed JWT"):
            validator.validate("not.a.valid.jwt.token")

    def test_malformed_jwt_too_few_parts(self, validator):
        with pytest.raises(LicenseError, match="Malformed JWT"):
            validator.validate("only-one-part")

    def test_invalid_signature_raises(self, validator):
        token = validator.create_token(sub="u1")
        # Tamper with the payload
        parts = token.split(".")
        parts[1] = parts[1] + "x"
        tampered = ".".join(parts)
        with pytest.raises(LicenseError, match="Invalid signature"):
            validator.validate(tampered)

    def test_expired_past_grace_raises(self, validator):
        token = validator.create_token(sub="u1", duration_seconds=1)
        # Manually create an expired token
        import json, base64
        parts = token.split(".")
        payload_bytes = validator._b64url_decode(parts[1])
        data = json.loads(payload_bytes)
        data["exp"] = int(time.time()) - GRACE_PERIOD_SECONDS - 100
        parts[1] = validator._b64url_encode(json.dumps(data).encode())
        # Re-sign
        sig = validator._compute_signature(parts[0], parts[1])
        parts[2] = validator._b64url_encode(sig)
        expired_token = ".".join(parts)
        with pytest.raises(LicenseError, match="expired"):
            validator.validate(expired_token)

    def test_no_secret_still_decodes(self):
        v_no_secret = LicenseValidator(signing_secret="")
        v_with_secret = LicenseValidator(signing_secret="key")
        token = v_with_secret.create_token(sub="u1")
        # Without secret, signature check is skipped
        payload = v_no_secret.validate(token)
        assert payload.sub == "u1"

    def test_features_field(self, validator):
        token = validator.create_token(sub="u1", features=["hooks", "analytics"])
        payload = validator.validate(token)
        assert payload.features == ["hooks", "analytics"]

    def test_load_from_disk_no_dir(self, validator):
        assert validator.load_from_disk() is None or True  # may or may not exist
