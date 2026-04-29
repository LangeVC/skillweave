"""Faignite model provider for SkillWeave Council.

Routes model queries through Faigate: availability check, credit validation,
model selection by council profile, and query execution.
"""

import json
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


class FaigniteProvider:
    """Model provider that routes through Faigate.

    Handles: availability check, credit validation, model query.
    Does NOT store API keys (Faignite manages auth internally).
    """

    # Council profiles: pre-defined model sets optimized for different use cases
    PROFILES = {
        "default": {
            "models": ["faigate:claude-sonnet-4-5", "faigate:gpt-4o", "faigate:gemini-2-5-pro", "faigate:deepseek-v4-pro"],
            "chairman": "faigate:claude-sonnet-4-5",
            "mode": "standard",
            "temperature": 0.5,
        },
        "quick": {
            "models": ["faigate:gpt-4o-mini", "faigate:claude-haiku-3-5"],
            "chairman": "faigate:gpt-4o-mini",
            "mode": "quick",
            "temperature": 0.3,
        },
        "deep": {
            "models": [
                "faigate:claude-sonnet-4-5", "faigate:gpt-4o", "faigate:gemini-2-5-pro",
                "faigate:deepseek-v4-pro", "faigate:llama-4-maverick", "faigate:mistral-large"
            ],
            "chairman": "faigate:claude-opus-4",
            "mode": "full",
            "temperature": 0.5,
        },
        "expert": {
            "models": ["faigate:claude-opus-4", "faigate:gpt-4o", "faigate:gemini-2-5-pro", "faigate:deepseek-v4-pro"],
            "chairman": "faigate:claude-opus-4",
            "mode": "full",
            "temperature": 0.4,
        },
    }

    def __init__(self, base_url: str = "https://faigate.ai/api/v1", api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _req(self, path: str, method: str = "GET", body: dict | None = None) -> dict:
        """Make HTTP request to Faigate API."""
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
            return {"error": f"HTTP {e.code}: {e.reason}"}
        except Exception as e:
            return {"error": str(e)}

    async def check_availability(self, models: list[str]) -> dict[str, bool]:
        """Check which models are currently available. Returns {model_id: available}."""
        import asyncio
        results = {}
        async def check_one(model_id: str):
            info = self._req(f"/models/{model_id.replace('faigate:', '')}")
            results[model_id] = not info.get("error") and info.get("status") == "available"
        await asyncio.gather(*[check_one(m) for m in models])
        return results

    async def check_credits(self, model: str) -> float:
        """Check remaining credits for a model. Returns credit amount or -1."""
        info = self._req(f"/credits/{model.replace('faigate:', '')}")
        if info.get("error"):
            return -1.0
        return float(info.get("credits_remaining", -1.0))

    async def query(self, model: str, messages: list[dict], temperature: float = 0.5) -> str:
        """Query a model via Faigate. Returns the response text."""
        import asyncio
        body = {
            "model": model.replace("faigate:", ""),
            "messages": messages,
            "temperature": temperature,
        }
        # Run blocking HTTP in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: self._req("/query", "POST", body)
        )
        if result.get("error"):
            raise RuntimeError(f"Faignite query failed: {result['error']}")
        return result.get("content", result.get("response", ""))

    def get_available_models(self) -> list[ModelInfo]:
        """Get list of all available models from Faigate."""
        result = self._req("/models")
        if result.get("error"):
            return []
        models = result.get("models", result.get("data", []))
        return [
            ModelInfo(
                id=f"faigate:{m.get('id', m.get('name', ''))}",
                name=m.get("name", m.get("id", "")),
                provider=m.get("provider", "unknown"),
                available=m.get("status") == "available",
                context_window=m.get("context_window", 128000),
                cost_per_1k=float(m.get("cost_per_1k", 0)),
            )
            for m in models
        ]

    def get_profile(self, profile_name: str = "default") -> dict:
        """Get pre-configured council profile."""
        if profile_name in self.PROFILES:
            return dict(self.PROFILES[profile_name])
        return dict(self.PROFILES["default"])

    def list_profiles(self) -> list[str]:
        """List available profile names."""
        return list(self.PROFILES.keys())
