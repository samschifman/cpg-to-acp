# Repository Rules & Conventions

@AGENTS.md

## Meta-Instructions for Claude Code
- The file referenced above (`AGENTS.md`) is the canonical source of truth for all coding rules, build paths, and architectural boundaries.
- Prioritize the constraints in `AGENTS.md` exactly as if they were written in this file.
- CRITICAL: If you run an automated setup command (like `/init`) or if the user asks you to update project rules, you MUST write those changes to `AGENTS.md`, NOT this file. Keep `CLAUDE.md` as a lightweight bridge.
  - **No Local Divergence**: Do not create conflicting rules within this session. If `AGENTS.md` and any sub-folder rules conflict, `AGENTS.md` takes absolute precedence.
- CRITICAL: **Maintenance**: If codebase changes require updating the global project context, modify `AGENTS.md` directly so that Codex, Cursor, and other agent harnesses stay in sync.
