# Yuki Autopilot V1.6

Yuki Autopilot executes exactly one prepared task. V1.6 can run Codex non-interactively and, only when every independent gate passes, auto-approve, commit, and push an L1 or L2 task branch. It never merges or rebases a parent branch, marks integration complete, unlocks the queue, or starts another task.

## Capability matrix

```text
AUTO_IMPLEMENT = YES
AUTO_TEST = YES
AUTO_REVIEW = YES
AUTO_APPROVE_L1_L2 = YES
AUTO_APPROVE_L3 = NO
AUTO_COMMIT_L1_L2 = YES
AUTO_PUSH_TASK_BRANCH = YES
AUTO_PARENT_INTEGRATION = NO
AUTO_NEXT_TASK = NO
AUTO_MULTI_TASK_LOOP = NO
```

## Commands

Inspect current state without mutation:

```powershell
.\scripts\codex\yuki-autopilot.ps1 -Status
.\scripts\codex\yuki-autopilot.ps1 -Next
.\scripts\codex\yuki-autopilot.ps1 -DryRun
```

Preserved manual workflow:

```powershell
.\scripts\codex\yuki-autopilot.ps1 -Prepare
.\scripts\codex\yuki-autopilot.ps1 -Review
.\scripts\codex\yuki-autopilot.ps1 -Finish -ApproveCommit
```

`-Finish -ApproveCommit` remains a human gate. It advances to `READY_FOR_COMMIT` and prints recommended Git commands; it does not commit or push.

Run one task and stop for human review:

```powershell
.\scripts\codex\yuki-autopilot.ps1 -Run
```

Run one task with independently gated L1/L2 approval, exact-path commit, and current-task-branch push:

```powershell
.\scripts\codex\yuki-autopilot.ps1 -Run -AutoApprove
```

`-Run` prepares one READY task only when no task is active, invokes `codex exec` non-interactively, validates scope, runs required tests/build, and applies the review gate. It does not loop.

## Auto-approval gates

Every condition must be true:

- Level is L1 or L2; L3 always stops at human review.
- Review result is exactly `READY_FOR_HUMAN_REVIEW`.
- Scope, tests, business gate, and `git diff --check` pass.
- Unauthorized paths, protected paths, staged paths, database connections, database writes, and EasyFreight writes are all zero.
- No migration or PDA/Scan paths changed.
- The exact `COMMIT_MESSAGE` is present in `CURRENT_TASK.md`.

Any missing or failed gate refuses approval. Commit staging uses only the validated changed-path list—never `git add .`, `-A`, or `--all`. Push targets only the current task branch and never uses force.

After successful commit and push, the state is `COMPLETE_PENDING_INTEGRATION`. Parent integration, acceptance, queue unlock, and the next task remain separate human-authorized work.

## Locking and failure behavior

`-Run` uses a per-worktree Git lock. An existing lock causes an immediate safety stop. The process removes only the lock it successfully created.

Failures stop the run. The scripts never clean, restore, reset, stash, merge, rebase, pull, force-push, connect to a database, write EasyFreight, or redesign inventory/state-machine behavior. Diagnose unexpected changes without altering them.

## Codex CLI requirement

Use `invoke-codex.ps1 -DetectOnly` or `-DryRun` to report CLI availability, version, and non-interactive support. If non-interactive `codex exec` is unavailable, `-Run` fails closed before implementation.
