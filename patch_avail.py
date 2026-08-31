import re
with open("src/skillweave/routing/faigate_adapter.py", "r") as f:
    code = f.read()

faigate_query = """
    async def query(self, model: str, messages: list[dict], temperature: float = 0.5, timeout: float | None = None) -> str:
        clean_model = FAIGATE_MAP.get(model.replace("faigate:", ""), model.replace("faigate:", ""))
"""

if "clean_model = FAIGATE_MAP" not in code:
    code = code.replace(
        'clean_model = model.replace("faigate:", "")',
        'clean_model = FAIGATE_MAP.get(model.replace("faigate:", ""), model.replace("faigate:", ""))'
    )

faigate_avail = """
    async def check_availability(self, models: list[str]) -> dict[str, bool]:
        \"\"\"Check model availability via Faigate GET /v1/models (single call).\"\"\"
        info = self._req("/models")
        if info.get("error"):
            return {m: True for m in models}  # fail open

        # Faigate returns: {"object": "list", "data": [{"id": "...", ...}, ...]}
        available_ids = set()
        model_list = info if isinstance(info, list) else info.get("data", [])
        for entry in model_list:
            if isinstance(entry, dict):
                iid = entry.get("id")
                if iid:
                    available_ids.add(iid)

        results = {}
        for m in models:
            clean_m = FAIGATE_MAP.get(m.replace("faigate:", ""), m.replace("faigate:", ""))
            results[m] = (clean_m in available_ids or any(clean_m in a for a in available_ids))
        return results
"""

# I need to replace the body of FaigateProvider.check_availability.
# I'll just find the exact string.

old_avail = """
    async def check_availability(self, models: list[str]) -> dict[str, bool]:
        \"\"\"Check model availability via Faigate GET /v1/models (single call).\"\"\"
        info = self._req("/models")
        if info.get("error"):
            return {m: True for m in models}  # fail open

        # Faigate returns: {"object": "list", "data": [{"id": "...", ...}, ...]}
        available_ids = set()
        model_list = info if isinstance(info, list) else info.get("data", [])
        for entry in model_list:
            if isinstance(entry, dict):
                iid = entry.get("id")
                if iid:
                    available_ids.add(iid)

        return {m: (m in available_ids or any(m in a for a in available_ids)) for m in models}
"""

if old_avail in code:
    code = code.replace(old_avail, faigate_avail)

with open("src/skillweave/routing/faigate_adapter.py", "w") as f:
    f.write(code)
