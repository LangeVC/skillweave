# Dispatching from your harness

SkillWeave's dispatch seam records *which* harness executed a run, and it
arrives at that fact from exactly one signal: the environment variable
`SKILLWEAVE_HARNESS`. The seam is deliberately unguessing. If the variable is
not set, the run records a `DETECTED` harness with an empty name, and that
empty record is never mistaken for a declaration.

Your harness is one of four. To make a run record you as `DECLARED`, set
`SKILLWEAVE_HARNESS` to exactly the name below, at the place your harness
actually reads for environment variables.

| Harness name      | Where its operator looks            | How to set it                                                                 |
|-------------------|-------------------------------------|-------------------------------------------------------------------------------|
| `opencode`        | `~/.config/opencode/opencode.json`  | Add an `"env"` entry under the relevant `mcp` / `agent` block, e.g. `"env": { "SKILLWEAVE_HARNESS": "opencode" }`. OpenCode resolves `${VAR}` via its process environment too, so exporting the variable from the launching shell also works. |
| `claude-code`     | `~/.claude/settings.json`           | Add a top-level `"env"` object: `{ "env": { "SKILLWEAVE_HARNESS": "claude-code" } }`. This is Claude Code's per-project/user settings surface and is read at startup. |
| `codex`           | `~/.codex/config.toml`              | Add to the `[shell_environment_policy.set]` table: `SKILLWEAVE_HARNESS = "codex"`. Codex injects every key in that table into its launched shell. |
| `antigravity`     | `~/.gemini/antigravity/mcp_config.json` (per-server `"env"`) or the launching shell | Antigravity surfaces per-server `"env"` blocks in its MCP config; set `"SKILLWEAVE_HARNESS": "antigravity"` there, or export it from the shell that starts Antigravity so it is inherited. |

Names are exact and case-sensitive. The four canonical names are `opencode`,
`claude-code`, `codex`, and `antigravity`; anything else is an unknown harness
and the seam records it as `DETECTED` with whatever value was supplied, never
as a declaration.

The run itself — launching a role's tool from inside each harness and binding
the result — is verified separately. This file only declares the mechanism;
the proof that a given harness actually sets the variable on a real run is the
next dispatch.
