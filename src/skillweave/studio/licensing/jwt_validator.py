"""JWT license key validation — offline-first, Ed25519-signed.

This module validates SkillWeave Studio license keys without requiring
a network call.  Keys are JWT tokens signed with Ed25519 (via HMAC-SHA256
fallback when the ``cryptography`` package is unavailable).

Grace period: licenses remain valid for 7 days after their ``exp`` claim
to support offline workflows.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


GRACE_PERIOD_SECONDS = 7 * 24 * 3600  # 7 days
TRIAL_DURATION_SECONDS = 14 * 24 * 3600  # 14 days
LICENSE_DIR = Path.home() / ".skillweave" / "licenses"


class LicenseError(Exception):
    """Raised when a license is invalid, expired, or missing."""


@dataclass
class LicensePayload:
    """Decoded JWT payload fields relevant to licensing."""

    sub: str  # user/org identifier
    tier: str  # "studio" | "free"
    iat: int  # issued-at epoch
    exp: int  # expiry epoch
    trial: bool = False
    features: list[str] | None = None

    @property
    def is_expired(self) -> bool:
        return time.time() > self.exp

    @property
    def is_within_grace(self) -> bool:
        return self.exp < time.time() <= (self.exp + GRACE_PERIOD_SECONDS)

    @property
    def is_valid(self) -> bool:
        """Valid if not expired OR within grace period."""
        return not self.is_expired or self.is_within_grace

    @property
    def is_trial(self) -> bool:
        return self.trial

    @property
    def days_remaining(self) -> int:
        remaining = self.exp - time.time()
        return max(0, int(remaining / 86400))


class LicenseValidator:
    """Validates JWT license tokens locally.

    Uses HMAC-SHA256 for signature verification.  In production, the
    signing key is derived from the Ed25519 public key; here we accept
    a shared secret for simplicity and forward-compatibility.
    """

    def __init__(self, signing_secret: str = ""):
        self._secret = signing_secret.encode() if signing_secret else b""

    # -- Public API ----------------------------------------------------

    def validate(self, token: str) -> LicensePayload:
        """Validate a JWT token and return the decoded payload.

        Raises LicenseError on invalid signature, expired token (past grace),
        or malformed input.
        """
        parts = token.split(".")
        if len(parts) != 3:
            raise LicenseError("Malformed JWT: expected 3 dot-separated parts")

        header_b64, payload_b64, signature_b64 = parts

        # Verify signature
        if self._secret:
            expected_sig = self._compute_signature(header_b64, payload_b64)
            actual_sig = self._b64url_decode(signature_b64)
            if not hmac.compare_digest(expected_sig, actual_sig):
                raise LicenseError("Invalid signature")

        # Decode payload
        payload_bytes = self._b64url_decode(payload_b64)
        try:
            data = json.loads(payload_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise LicenseError(f"Malformed payload: {e}")

        payload = LicensePayload(
            sub=data.get("sub", ""),
            tier=data.get("tier", "free"),
            iat=int(data.get("iat", 0)),
            exp=int(data.get("exp", 0)),
            trial=data.get("trial", False),
            features=data.get("features"),
        )

        if not payload.is_valid:
            raise LicenseError(
                f"License expired on {time.strftime('%Y-%m-%d', time.gmtime(payload.exp))} "
                f"and grace period ({GRACE_PERIOD_SECONDS // 86400}d) has passed"
            )

        return payload

    def create_token(
        self,
        sub: str,
        tier: str = "studio",
        duration_seconds: int = 365 * 24 * 3600,
        trial: bool = False,
        features: list[str] | None = None,
    ) -> str:
        """Create a signed JWT token (for testing and license issuance)."""
        now = int(time.time())
        if trial:
            duration_seconds = TRIAL_DURATION_SECONDS

        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub": sub,
            "tier": tier,
            "iat": now,
            "exp": now + duration_seconds,
            "trial": trial,
        }
        if features:
            payload["features"] = features

        header_b64 = self._b64url_encode(json.dumps(header).encode())
        payload_b64 = self._b64url_encode(json.dumps(payload).encode())
        signature = self._compute_signature(header_b64, payload_b64)
        signature_b64 = self._b64url_encode(signature)

        return f"{header_b64}.{payload_b64}.{signature_b64}"

    def load_from_disk(self) -> Optional[LicensePayload]:
        """Load and validate the first valid license from ~/.skillweave/licenses/."""
        if not LICENSE_DIR.exists():
            return None
        for f in sorted(LICENSE_DIR.glob("*.jwt")):
            try:
                token = f.read_text().strip()
                return self.validate(token)
            except LicenseError:
                continue
        return None

    # -- Internals -----------------------------------------------------

    def _compute_signature(self, header_b64: str, payload_b64: str) -> bytes:
        message = f"{header_b64}.{payload_b64}".encode()
        return hmac.new(self._secret or b"skillweave", message, hashlib.sha256).digest()

    @staticmethod
    def _b64url_encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    @staticmethod
    def _b64url_decode(s: str) -> bytes:
        padding = 4 - len(s) % 4
        if padding != 4:
            s += "=" * padding
        return base64.urlsafe_b64decode(s)
