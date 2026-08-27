# OpenCode Adapter (non-binding example)

> **Non-binding adapter example.** This is *one* way to invoke the skill from a
> specific host. It is retained for reference only and is NOT a default binding.
> SkillWeave assignment is capability-based (`target_agent: any`); a concrete
> host is used only when the user explicitly routes to it. Cross-transport
> parity and fully host-neutral Command/Intent semantics are 1.4.0 scope.

When running inside OpenCode, the skill's commands can be invoked as:

```bash
opencode skillweave-repo-health command="scan" path="./src"
opencode skillweave-repo-health command="classify" path="."
opencode skillweave-repo-health command="report" path="."
opencode skillweave-repo-health command="cleanup" path="."
opencode skillweave-repo-health command="duplicates" path="."
opencode skillweave-repo-health command="archive" path="."
opencode skillweave-repo-health command="restore" path="./archive"
```

These are host-specific and are not required for the skill to work — the same
commands are reachable from any transport via the skill's capability-neutral
interface.
