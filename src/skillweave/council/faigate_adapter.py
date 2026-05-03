"""Multi-provider model routing for SkillWeave Council.

Auto-detection of available routers: Faigate, OpenRouter, KiloRouter, ClawRouter, LlmAI.
Single-model fallback: council roles work with just 1 model (no peer review, chairman=model).

Architecture:
  CouncilEngine → CouncilProvider (interface)
    ├── FaigateProvider
    ├── OpenRouterProvider
    ├── GenericRouterProvider (kilo, claw, llmai)
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

    def get_available_models(self) -> list[ModelInfo]:
        return []

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
    
    Checks environment variables and default endpoints for:
    -     Faigate (FAGIATE_API_KEY or ~/.faigate or ~/.config/faigate/tokens.json)
    - OpenRouter (OPENROUTER_API_KEY)
    - KiloRouter (KILO_API_KEY or KILO_BASE_URL)
    - ClawRouter (CLAWROUTER_API_KEY)
    - LlmAI (LLMAI_API_KEY)
    
    Returns dict of {router_name: CouncilProvider}.
    """
    providers = {}
    
    # Faigate — check multiple config sources
    faigate_available = (
        os.environ.get("FAGIATE_API_KEY") or
        os.path.exists(os.path.expanduser("~/.faigate")) or
        os.path.exists(os.path.expanduser("~/.config/faigate/tokens.json"))
    )
    if faigate_available:
        providers["faigate"] = FaigateProvider()
    
    # OpenRouter
    if os.environ.get("OPENROUTER_API_KEY"):
        providers["openrouter"] = OpenRouterProvider()
    
    # KiloRouter
    if os.environ.get("KILO_API_KEY") or os.environ.get("KILO_BASE_URL"):
        providers["kilo"] = GenericRouterProvider(
            base_url=os.environ.get("KILO_BASE_URL", "https://api.kilorouter.com/v1")
        )
    
    # ClawRouter
    if os.environ.get("CLAWROUTER_API_KEY"):
        providers["claw"] = GenericRouterProvider(
            base_url=os.environ.get("CLAWROUTER_BASE_URL", "https://api.clawrouter.ai/v1"),
            api_key=os.environ.get("CLAWROUTER_API_KEY"),
        )
    
    # LlmAI
    if os.environ.get("LLMAI_API_KEY"):
        providers["llmai"] = GenericRouterProvider(
            base_url=os.environ.get("LLMAI_BASE_URL", "https://api.llmai.com/v1"),
            api_key=os.environ.get("LLMAI_API_KEY"),
        )
    
    return providers


def get_best_provider() -> CouncilProvider:
    """Return the best available provider, or SingleModelProvider as fallback."""
    providers = detect_providers()
    # Priority: faigate > openrouter > kilo > claw > llmai
    for name in ["faigate", "openrouter", "kilo", "claw", "llmai"]:
        if name in providers:
            return providers[name]
    return SingleModelProvider()


# ── FaigateProvider ────────────────────────────────────────────────

class FaigateProvider(CouncilProvider):
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.environ.get("FAGIATE_BASE_URL", "https://faigate.ai/api/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("FAGIATE_API_KEY")
        # If no explicit key, try reading from ~/.config/faigate/tokens.json
        if not self.api_key:
            token_file = os.path.expanduser("~/.config/faigate/tokens.json")
            if os.path.exists(token_file):
                try:
                    tokens = json.loads(open(token_file).read())
                    # Use the first available access token
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
            return {"error": f"HTTP {e.code}"}
        except Exception as e:
            return {"error": str(e)}

    async def check_availability(self, models: list[str]) -> dict[str, bool]:
        """Check model availability via Faigate GET /models (single call, not per-model)."""
        info = self._req("/models")
        if info.get("error"):
            # Fallback: assume all available
            return {m: True for m in models}
        # Response format: {"models": [{"id": "...", "status": "available"}, ...]} or list
        available_ids = set()
        model_list = info if isinstance(info, list) else info.get("models", info.get("data", []))
        for entry in model_list:
            if isinstance(entry, dict):
                mid = entry.get("id", "") or entry.get("model", "")
                status = entry.get("status", "available")
                if mid and status == "available":
                    available_ids.add(mid)
            elif isinstance(entry, str):
                available_ids.add(entry)
        return {m: (m.replace('faigate:', '') in available_ids or m in available_ids) for m in models}

    async def check_credits(self, model: str) -> float:
        info = self._req(f"/credits/{model.replace('faigate:', '')}")
        return float(info.get("credits_remaining", -1.0)) if not info.get("error") else -1.0

    async def query(self, model: str, messages: list[dict], temperature: float = 0.5) -> str:
        body = {"model": model.replace("faigate:", ""), "messages": messages, "temperature": temperature}
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: self._req("/query", "POST", body))
        if result.get("error"):
            raise RuntimeError(f"Faigate query failed: {result['error']}")
        return result.get("content", result.get("response", ""))

    def provider_name(self) -> str:
        return "faigate"


# ── OpenRouterProvider ──────────────────────────────────────────────

class OpenRouterProvider(CouncilProvider):
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if self.api_key is None:
            raise ValueError("OPENROUTER_API_KEY not set")

    def _req(self, path: str, body: dict, method: str = "POST") -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode()
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
            body = {}
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: self._req("/models", body, "GET"))
            available_ids = {m.get("id", "") for m in result.get("data", [])}
            return {m: (m in available_ids or any(m in a for a in available_ids)) for m in models}
        except Exception:
            return {m: True for m in models}  # fail open

    def provider_name(self) -> str:
        return "openrouter"


# ── GenericRouterProvider (Kilo, Claw, LlmAI) ──────────────────────

class GenericRouterProvider(CouncilProvider):
    """OpenAI-compatible router: Kiro, ClawRouter, LlmAI, and any /v1 endpoint."""
    
    def __init__(self, base_url: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _req(self, path: str, body: dict, method: str = "POST") -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode()
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
        """Generic: try /models endpoint, fall back to assuming all available."""
        try:
            body = {}
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: self._req("/models", body, "GET"))
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
    
    Works with any OpenAI-compatible API via OPENAI_API_KEY or ANTHROPIC_API_KEY.
    """
    
    def __init__(self, model: str | None = None, base_url: str | None = None, api_key: str | None = None):
        self.model = model or os.environ.get("COUNCIL_MODEL", os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo"))
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
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
        # Single-model mode: ignore the model param, always use self.model
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
