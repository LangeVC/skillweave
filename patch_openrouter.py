import re
with open("src/skillweave/routing/faigate_adapter.py", "r") as f:
    code = f.read()

# For OpenRouter query
code = code.replace(
    'body = {"model": model, "messages": messages, "temperature": temperature}',
    'clean_model = OPENROUTER_MAP.get(model, model)\n        body = {"model": clean_model, "messages": messages, "temperature": temperature}'
)

# For OpenRouter check_availability
old_openrouter_avail = """
    async def check_availability(self, models: list[str]) -> dict[str, bool]:
        \"\"\"OpenRouter: check model availability via /models endpoint.\"\"\"
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._req("/models", method="GET")
            )
            available_ids = {m.get("id", "") for m in result.get("data", [])}
            return {m: (m in available_ids or any(m in a for a in available_ids)) for m in models}
"""

new_openrouter_avail = """
    async def check_availability(self, models: list[str]) -> dict[str, bool]:
        \"\"\"OpenRouter: check model availability via /models endpoint.\"\"\"
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._req("/models", method="GET")
            )
            available_ids = {m.get("id", "") for m in result.get("data", [])}
            results = {}
            for m in models:
                clean_m = OPENROUTER_MAP.get(m, m)
                results[m] = (clean_m in available_ids or any(clean_m in a for a in available_ids))
            return results
"""

if old_openrouter_avail in code:
    code = code.replace(old_openrouter_avail, new_openrouter_avail)

with open("src/skillweave/routing/faigate_adapter.py", "w") as f:
    f.write(code)
