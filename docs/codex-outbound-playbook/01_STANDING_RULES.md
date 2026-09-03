# Standing Rules

These rules apply to every Slice:

- One Slice equals one Codex session; never execute multiple Slices in one session.
- A dirty or unexpectedly changed worktree is a safety stop.
- Identify the exact allowed file scope before modifying anything. Stop if an unexpected path is present or becomes changed.
- Do not begin the next Slice.
- No migrations or Alembic changes.
- No EasyFreight writes or browser operations.
- No database connections or writes and no database configuration changes.
- No inventory logic changes and no state-machine redesign.
- No Inbound changes.
- No FBA changes.
- No Scan/PDA changes.
- No authentication changes.
- No unrelated refactoring.
- No UI polish unless explicitly required by the current Slice's functional task.
- Do not modify requirements, package files, or environment files unless a future instruction separately authorizes an exact path and purpose.
- Do not read or modify `backend/.env`; never expose secrets or credentials.
- Do not commit or push unless separately authorized.
- Do not merge, rebase, reset, clean, stash, restore, or overwrite user work.
- After each Slice, a human performs build/manual review and applies `03_REVIEW_GATE.md`.
- Do not start the next Slice until the previous Slice is committed by a human and the worktree is clean.
- Run `git diff --check` and report every changed path before stopping.

The primary functional target is Outbound Workbench parity and workflow completeness. Work outside that target is forbidden unless explicitly authorized in a later instruction.
