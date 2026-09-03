# Yuki Autopilot V1

`YUKI_AUTOPILOT` is a semi-automated Codex development pipeline. It prepares exactly one queued task, allows Codex to implement and validate that task, then stops at a human review and commit gate. V1 never loops through tasks, invokes Codex recursively, commits, pushes, merges, or unlocks the queue automatically.

## Safety levels

- **L1 — AUTO:** read-only analysis, documentation, tests, lint, build, non-destructive Git inspection, gap inventories, and reports.
- **L2 — AUTO_IMPLEMENT_REVIEW_REQUIRED:** ordinary frontend/backend work, API client wiring, page actions, non-database logic, tests, and build. It must stop at `READY_FOR_HUMAN_REVIEW`.
- **L3 — EXPLICIT_APPROVAL_REQUIRED:** migrations, schema/database operations, reset/seed, inventory deduction, allocation consistency architecture, state-machine redesign, authentication/security changes, `.env`, credentials, PDA production enablement, EasyFreight/external production writes, or destructive Git operations. Preparation requires environment variable `APPROVED_L3=YES` and the task still remains subject to human review.

Permanent prohibitions and priorities are defined in `.codex/AGENTS.md`.

## Human workflow

1. Confirm the previous task is committed and its parent branch has been updated/integrated.
2. Inspect the pipeline:

   ```powershell
   .\scripts\codex\yuki-autopilot.ps1 -Status
   ```

3. Prepare the single READY task:

   ```powershell
   .\scripts\codex\yuki-autopilot.ps1 -Prepare
   ```

4. Open a new Codex session.
5. Give Codex this instruction:

   > Read `.codex/AGENTS.md`. Read `.codex/CURRENT_TASK.md`. Execute only the current task prompt. If `ALLOWED_PATHS` contains `DECLARATION_REQUIRED`, replace that token with the exact minimal paths justified by the prompt before application edits. Stop after implementation and validation. Do not commit.

6. After Codex stops, review the task:

   ```powershell
   .\scripts\codex\yuki-autopilot.ps1 -Review
   ```

   If backend files changed and the targeted test runner reports that no relevant test was discoverable, rerun only after deciding a full backend run is appropriate:

   ```powershell
   .\scripts\codex\yuki-autopilot.ps1 -Review -FullBackend
   ```

7. If the result is `FINAL = READY_FOR_HUMAN_REVIEW`, manually check the functionality and semantic business requirements.
8. If approved, advance only to the commit-ready state:

   ```powershell
   .\scripts\codex\yuki-autopilot.ps1 -Finish -ApproveCommit
   ```

   This prints exact recommended Git commands; it does not execute them.
9. Run commit/push in a separately authorized human or Codex task.
10. Only after parent-branch integration and acceptance may the queue unlock the next task.

## Failure workflow

Stop immediately on `FAIL` or `SAFETY_STOP`. Use this follow-up instruction:

> Review failed: `<reason>`. Fix only these failures. Do not start the next task.

Never clean, reset, restore, stash, or overwrite an unexpected path. Diagnose it and obtain human direction.

## Queue unlock policy

V1 documents but does not automate queue mutation. Only after the current task is all of the following:

- `COMMITTED`
- `PUSHED`
- `INTEGRATED_TO_PARENT`
- `HUMAN_ACCEPTED`

may an explicitly approved action set the current task to `STATUS: COMPLETE` and the next blocked task to `STATUS: READY`. Append `.codex/DONE.md` only after that approved completion. Never unlock a task directly after implementation or review.

## Operational notes and limitations

- `-Prepare` requires a completely clean worktree, a local base branch containing `LAST_COMPLETED_SHA`, and an absent task branch or one that still points exactly to the base tip. It is the only mode that may create/switch a task branch.
- Because queue records do not contain per-task application paths, preparation writes `DECLARATION_REQUIRED`. The implementation session must replace it with exact paths before application changes; validation fails closed until then. Pipeline control files remain explicitly allowed.
- `-Review` permits expected unstaged changes, but requires the correct branch, unchanged task-start HEAD, zero staged files, no active Git operation or lock, allowed paths, passing validation, and applicable outbound contract tokens.
- Automated token gates cannot prove full business semantics. The human review remains mandatory.
- Java validation uses Maven only when `mvn` is already available and never installs it.
- No mode performs production database connections or writes, migrations, PDA enablement, or EasyFreight writes.
