"""Multi-provider model routing for SkillWeave Council.

Auto-detection of available routers:
- Faigate (local, brew-installed at 127.0.0.1:$(FAIGATE_PORT, default 8090)/v1)
- OpenRouter (cloud, api.openrouter.ai)
- ClawRouter (local/cloud, clawrouter.ai)
- KiloRouter (local/cloud, kilorouter.com)
- OmniRoute (local, localhost:20128/v1)
- 9router (local/cloud, 9router)
- SingleModel (fallback — no router needed)

Architecture:
  CouncilEngine → CouncilProvider (interface)
    ├── FaigateProvider     (GET /v1/models → {"object":"list","data":[▶]})
    ├── OpenRouterProvider  (GET /models → {"data":[▶]})
    ├── GenericRouterProvider  (Kilo/Claw/OmniRoute/9router via /chat/completions)
    └── SingleModelProvider (fallback — no router needed)
"""

import asyncio
import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional


@dataclass
class ModelInfo:
    id: str
    name: str
    provider: str
    available: bool
    credits_remaining: float = -1.0
    context_window: int = 128000
    cost_per_1k: float = 0.0


class CouncilProvider:
    """Abstract base: all providers implement query + availability."""

    async def query(self, model: str, messages: list[dict], temperature: float = 0.5) -> str:
        raise NotImplementedError

    async def check_availability(self, models: list[str]) -> dict[str, bool]:
        return {m: True for m in models}

    async def check_credits(self, model: str) -> float:
        return -1.0

    def provider_name(self) -> str:
        return "generic"


# ── Router Profiles ────────────────────────────────────────────────

ROUTER_PROFILES = {
    "default": {
        "models": ["sonnet", "gpt-4o", "gemini-pro", "deepseek-v4"],
        "chairman": "sonnet",
        "mode": "standard",
        "temperature": 0.5,
    },
    "quick": {
        "models": ["gpt-4o-mini", "haiku"],
        "chairman": "gpt-4o-mini",
        "mode": "quick",
        "temperature": 0.3,
    },
    "deep": {
        "models": ["sonnet", "gpt-4o", "gemini-pro", "deepseek-v4", "llama-4", "mistral"],
        "chairman": "opus",
        "mode": "full",
        "temperature": 0.5,
    },
    "expert": {
        "models": ["opus", "gpt-4o", "gemini-pro", "deepseek-v4"],
        "chairman": "opus",
        "mode": "full",
        "temperature": 0.4,
    },
}


# ── Provider Detection ──────────────────────────────────────────────

def detect_providers() -> dict[str, CouncilProvider]:
    """Auto-detect all available router providers.

    Checks environment variables, local config files, and default endpoints:
    - Faigate (FAIGATE_API_KEY or ~/.faigate or ~/.config/faigate/tokens.json)
    - OpenRouter (OPENROUTER_API_KEY)
    - ClawRouter (CLAWROUTER_API_KEY)
    - KiloRouter (KILO_API_KEY or KILO_BASE_URL)
    - OmniRoute (OMNIROUTE_API_KEY or localhost:20128)
    - 9router (NINEROUTER_API_KEY)

    Returns dict of {router_name: CouncilProvider}.
    """
    providers = {}

    # Faigate — check port + config files
    faigate_port = int(os.environ.get("FAIGATE_PORT", FAIGATE_DEFAULT_PORT))
    faigate_available = (
        os.environ.get("FAIGATE_API_KEY") or
        os.path.exists(os.path.expanduser("~/.faigate")) or
        os.path.exists(os.path.expanduser("~/.config/faigate/tokens.json")) or
        _check_port_open(FAIGATE_DEFAULT_HOST, faigate_port)
    )
    if faigate_available:
        providers["faigate"] = FaigateProvider()

    # OpenRouter
    if os.environ.get("OPENROUTER_API_KEY"):
        providers["openrouter"] = OpenRouterProvider()

    # ClawRouter
    if os.environ.get("CLAWROUTER_API_KEY"):
        providers["claw"] = GenericRouterProvider(
            base_url=os.environ.get("CLAWROUTER_BASE_URL", "https://api.clawrouter.ai/v1"),
            api_key=os.environ.get("CLAWROUTER_API_KEY"),
        )

    # KiloRouter
    if os.environ.get("KILO_API_KEY") or os.environ.get("KILO_BASE_URL"):
        providers["kilo"] = GenericRouterProvider(
            base_url=os.environ.get("KILO_BASE_URL", "https://api.kilorouter.com/v1")
        )

    # OmniRoute — local (default port 20128) or cloud
    omniroute_available = (
        os.environ.get("OMNIROUTE_API_KEY") or
        _check_port_open("localhost", int(os.environ.get("OMNIROUTE_PORT", "20128")))
    )
    if omniroute_available:
        providers["omniroute"] = GenericRouterProvider(
            base_url=os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128/v1"),
            api_key=os.environ.get("OMNIROUTE_API_KEY", "any-string"),
        )

    # 9router
    if os.environ.get("NINEROUTER_API_KEY"):
        providers["9router"] = GenericRouterProvider(
            base_url=os.environ.get("NINEROUTER_BASE_URL", "http://localhost:9200/v1"),
            api_key=os.environ.get("NINEROUTER_API_KEY"),
        )

    return providers


def get_best_provider() -> CouncilProvider:
    """Return the best available provider, or SingleModelProvider as fallback."""
    providers = detect_providers()
    # Priority: faigate > openrouter > omniroute > claw > kilo > 9router
    for name in ["faigate", "openrouter", "omniroute", "claw", "kilo", "9router"]:
        if name in providers:
            return providers[name]
    return SingleModelProvider()


def _check_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a TCP port is open (for local providers like OmniRoute/faigate)."""
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


# ── FaigateProvider ────────────────────────────────────────────────

FAIGATE_DEFAULT_HOST = "127.0.0.1"
FAIGATE_DEFAULT_PORT = "8090"


class FaigateProvider(CouncilProvider):
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.environ.get(
            "FAIGATE_BASE_URL",
            f"http://{os.environ.get('FAIGATE_HOST', FAIGATE_DEFAULT_HOST)}:"
            f"{os.environ.get('FAIGATE_PORT', FAIGATE_DEFAULT_PORT)}/v1"
        )).rstrip("/")
        self.api_key = api_key or os.environ.get("FAIGATE_API_KEY")
        # If no explicit key, try reading from ~/.config/faigate/tokens.json
        if not self.api_key:
            token_file = os.path.expanduser("~/.config/faigate/tokens.json")
            if os.path.exists(token_file):
                try:
                    tokens = json.loads(open(token_file).read())
                    for provider, config in tokens.items():
                        if "access_token" in config:
                            self.api_key = config["access_token"]
                            break
                except Exception:
                    pass

    def _req(self, path: str, method: str = "GET", body: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body else None
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            return {"error": f"HTTP {e.code} at {url}: {error_body}"}
        except urllib.error.URLError as e:
            return {"error": f"URL Error at {url}: {e.reason}"}
        except Exception as e:
            return {"error": f"{str(e)} (at {url})"}

    async def check_availability(self, models: list[str]) -> dict[str, bool]:
        """Check model availability via Faigate GET /v1/models (single call)."""
        info = self._req("/models")
        if info.get("error"):
            return {m: True for m in models}  # fail open

        # Faigate returns: {"object": "list", "data": [{"id": "...", ...}, ...]}
        available_ids = set()
        model_list = info if isinstance(info, list) else info.get("data", [])
        for entry in model_list:
            if isinstance(entry, dict):
                mid = entry.get("id", "")
                if mid:
                    available_ids.add(mid)
            elif isinstance(entry, str):
                available_ids.add(entry)

        result = {}
        for m in models:
            clean = m.replace("faigate:", "")
            result[m] = clean in available_ids or any(clean in aid for aid in available_ids)
        return result

    async def check_credits(self, model: str) -> float:
        return -1.0  # Faigate doesn't expose credit checking — defer to availability

    async def query(self, model: str, messages: list[dict], temperature: float = 0.5) -> str:
        clean_model = model.replace("faigate:", "")
        body = {"model": clean_model, "messages": messages, "temperature": temperature}
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: self._req("/chat/completions", "POST", body))
        if result.get("error"):
            raise RuntimeError(f"Faigate query failed: {result['error']}")
        return result["choices"][0]["message"]["content"]

    def provider_name(self) -> str:
        return "faigate"


# ── OpenRouterProvider ──────────────────────────────────────────────

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class OpenRouterProvider(CouncilProvider):
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or OPENROUTER_BASE).rstrip("/")
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if self.api_key is None:
            raise ValueError("OPENROUTER_API_KEY not set")

    def _req(self, path: str, body: dict | None = None, method: str = "POST") -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body else None
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": os.environ.get("OR_SITE_URL", "https://github.com/typelicious/SkillWeave"),
            "X-Title": os.environ.get("OR_APP_NAME", "SkillWeave Council"),
        }
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                if "error" in result:
                    return {"error": result["error"].get("message", json.dumps(result["error"]))}
                return result
        except Exception as e:
            return {"error": str(e)}

    async def query(self, model: str, messages: list[dict], temperature: float = 0.5) -> str:
        body = {"model": model, "messages": messages, "temperature": temperature}
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: self._req("/chat/completions", body))
        if result.get("error"):
            raise RuntimeError(f"OpenRouter query failed: {result['error']}")
        return result["choices"][0]["message"]["content"]

    async def check_availability(self, models: list[str]) -> dict[str, bool]:
        """OpenRouter: check model availability via /models endpoint."""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._req("/models", method="GET")
            )
            available_ids = {m.get("id", "") for m in result.get("data", [])}
            return {m: (m in available_ids or any(m in a for a in available_ids)) for m in models}
        except Exception:
            return {m: True for m in models}

    def provider_name(self) -> str:
        return "openrouter"


# ── GenericRouterProvider (Kilo, Claw, OmniRoute, 9router) ────────

class GenericRouterProvider(CouncilProvider):
    """OpenAI-compatible router: works with any /v1 endpoint."""

    def __init__(self, base_url: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _req(self, path: str, body: dict | None = None, method: str = "POST") -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body else None
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                if "error" in result:
                    return {"error": result["error"].get("message", str(result["error"]))}
                return result
        except Exception as e:
            return {"error": str(e)}

    async def query(self, model: str, messages: list[dict], temperature: float = 0.5) -> str:
        body = {"model": model, "messages": messages, "temperature": temperature}
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: self._req("/chat/completions", body))
        if result.get("error"):
            raise RuntimeError(f"Router query failed: {result['error']}")
        return result["choices"][0]["message"]["content"]

    async def check_availability(self, models: list[str]) -> dict[str, bool]:
        """Try /models endpoint, fall back to assuming all available."""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._req("/models", method="GET")
            )
            available_ids = {m.get("id", "") for m in result.get("data", [])}
            return {m: (m in available_ids or any(m in a for a in available_ids)) for m in models}
        except Exception:
            return {m: True for m in models}

    def provider_name(self) -> str:
        return "generic_router"


# ── SingleModelProvider (Fallback — no router, 1 model) ─────────────

class SingleModelProvider(CouncilProvider):
    """No router detected — use a single model for all council roles.

    Council modes adapt:
    - quick/standard: model answers solo (no peer review)
    - full: model acts as both council + chairman (solo deliberation)

    Works with any OpenAI-compatible API via:
    - OPENAI_API_KEY → https://api.openai.com/v1
    - COUNCIL_MODEL / OPENAI_MODEL for model name
    """

    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None):
        self.model = model or os.environ.get(
            "COUNCIL_MODEL",
            os.environ.get("OPENAI_MODEL", os.environ.get("DEFAULT_MODEL", "gpt-3.5-turbo"))
        )
        self.base_url = (base_url or os.environ.get(
            "OPENAI_BASE_URL",
            "https://api.openai.com/v1"
        )).rstrip("/")
        self.api_key = (
            api_key or
            os.environ.get("OPENAI_API_KEY") or
            os.environ.get("ANTHROPIC_API_KEY")
        )
        self._single_model_mode = True

    def _req(self, body: dict) -> dict:
        url = f"{self.base_url}/chat/completions"
        data = json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
                if "error" in result:
                    return {"error": result["error"].get("message", str(result["error"]))}
                return result
        except Exception as e:
            return {"error": str(e)}

    async def query(self, model: str, messages: list[dict], temperature: float = 0.5) -> str:
        body = {"model": self.model, "messages": messages, "temperature": temperature}
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: self._req(body))
        if result.get("error"):
            raise RuntimeError(f"Model query failed: {result['error']}")
        return result["choices"][0]["message"]["content"]

    async def check_availability(self, models: list[str]) -> dict[str, bool]:
        return {m: True for m in models}

    def provider_name(self) -> str:
        return "single_model"

    @property
    def is_single_model(self) -> bool:
        return True


# ── Profile Helpers ─────────────────────────────────────────────────

def get_profile(profile_name: str = "default") -> dict:
    if profile_name in ROUTER_PROFILES:
        return dict(ROUTER_PROFILES[profile_name])
    return dict(ROUTER_PROFILES["default"])


def list_profiles() -> list[str]:
    return list(ROUTER_PROFILES.keys())


def list_detected_providers() -> dict[str, str]:
    return {name: p.provider_name() for name, p in detect_providers().items()}


def known_model_ids() -> frozenset[str]:
    """Return every model id Faigate can resolve, across all router presets.

    This is the deterministic "is a model available" surface: it is derived
    from ``ROUTER_PROFILES``, not from a live provider probe, so it never does
    network I/O and never flakes. A model id outside this set cannot be resolved
    by Faigate and must be reported, not silently ignored (AK 10).
    """
    ids = {model for preset in ROUTER_PROFILES.values() for model in preset["models"]}
    return frozenset(ids)


def resolve_tier(profile: "RoutingProfile") -> "ResolutionRecord":
    """Resolve a profile's tier into the models that will actually run (AK 8+9).

    The tier names *intent*, not a model. Faigate's ``ROUTER_PROFILES`` decide
    the concrete model pool and council mode, so the profile stays valid when a
    preset's models change. A profile MAY pin a single concrete model id; in that
    case the pinned model is what runs, and the returned record is marked
    ``pinned`` so a later run can tell the difference between "what was
    requested" and "what really ran".

    A role that declares a ``model`` (or ``pin``) id Faigate cannot resolve is
    refused here with an error naming BOTH the profile and the role — no silent
    fallback (AK 10).

    Returns a :class:`~skillweave.routing.profile.ResolutionRecord` carrying the
    requested tier, the router preset name, the council mode, the resolved model
    ids, and any pin.
    """
    from .profile import ResolutionRecord, RoutingProfileError, tier_to_router

    router_name, mode = tier_to_router(profile.tier)
    preset = ROUTER_PROFILES.get(router_name, ROUTER_PROFILES["default"])

    _check_unavailable_models(profile)

    pin = _profile_pin(profile)
    resolved_models = [pin] if pin else list(preset["models"])

    return ResolutionRecord(
        tier=profile.tier,
        router_name=router_name,
        mode=mode,
        resolved_models=resolved_models,
        pinned=pin,
    )


def _check_unavailable_models(profile: "RoutingProfile") -> None:
    """Refuse roles whose declared model or pin Faigate cannot resolve.

    A role's ``model`` and ``pin`` name a concrete model id. If that id is not
    in any router preset, Faigate cannot supply it, so we fail loudly — naming
    the profile and the role — instead of silently substituting another model.
    """
    from .profile import RoutingProfileError

    available = known_model_ids()
    for key, role in profile.roles.items():
        for field, value in (("model", role.model), ("pin", role.pin)):
            if value is not None and value not in available:
                raise RoutingProfileError(
                    f"profile '{profile.name}' role '{key}' names {field} "
                    f"'{value}' which Faigate cannot resolve "
                    f"(available: {sorted(available)})"
                )


def _profile_pin(profile: "RoutingProfile") -> Optional[str]:
    """Return the single pinned model id for a profile, if any role pins one.

    Pinning is per-role data (each ``RoleDefinition`` may carry ``pin``). A
    profile where exactly one role pins a model is treated as pinned. If
    several roles pin *different* models, there is no single resolution — that
    contradiction is reported, not silently collapsed, so the caller can see it.
    """
    pins = {r.pin for r in profile.roles.values() if r.is_pinned}
    if not pins:
        return None
    if len(pins) == 1:
        return next(iter(pins))
    return None
