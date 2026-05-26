"""CI Gate — reference capability for post_test hook.

This is a template for capability authors who want to create a
post_test hook that validates CI results before allowing a release.

Trigger specification for manifest.json::

    {
      "triggers": [
        {
          "type": "dev.skillweave.hook",
          "source": "skillweave",
          "filter": {
            "phase": "test",
            "position": "post"
          }
        }
      ]
    }
"""

from __future__ import annotations

from ..hooks.adapter import HookAdapter
from ..hooks.models import PhaseContext, HookResult


class CIGateHook(HookAdapter):
    """Reference post_test hook that checks CI/test results.

    Reads hook_config for configuration:
      - min_coverage: Minimum test coverage percentage (default: 80)
      - require_green: Whether all tests must pass (default: True)
    """

    def should_run(self, ctx: PhaseContext) -> bool:
        return ctx.phase.value == "test" and ctx.position.value == "post"

    async def execute(self, ctx: PhaseContext) -> HookResult:
        min_coverage = ctx.hook_config.get("min_coverage", 80)
        require_green = ctx.hook_config.get("require_green", True)

        # In a real implementation, this would:
        # 1. Read test results from ctx.project_root
        # 2. Parse coverage reports
        # 3. Check CI status
        # For the reference implementation, we return pass
        return HookResult(
            status="pass",
            message=(
                f"CI gate check: coverage threshold {min_coverage}%, "
                f"require_green={require_green}"
            ),
        )

    async def rollback(self, ctx: PhaseContext) -> None:
        pass  # No rollback needed for read-only checks


# Manifest template for Capacium publishing
MANIFEST = {
    "name": "ci-gate",
    "version": "1.0.0",
    "description": "Post-test CI gate hook for SkillWeave Studio",
    "author": "SkillWeave",
    "type": "hook",
    "triggers": [
        {
            "type": "dev.skillweave.hook",
            "source": "skillweave",
            "filter": {
                "phase": "test",
                "position": "post",
            },
        },
    ],
    "config_schema": {
        "min_coverage": {"type": "integer", "default": 80},
        "require_green": {"type": "boolean", "default": True},
    },
}
