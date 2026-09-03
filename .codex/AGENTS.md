# DLX Yuki WMS Codex Agent Rules

Repo:

Use the current Git worktree supplied by the invocation. Never redirect work to a
different checkout or worktree.

## Permanent rules

1. One task = one branch = one Codex execution scope.
2. Never execute two READY tasks in one run.
3. Dirty unexpected worktree = stop.
4. Never clean, reset, restore, stash, or overwrite unknown work.
5. Never modify files outside `CURRENT_TASK` allowed paths.
6. Never implement opportunistic fixes.
7. Never proceed to the next task automatically.
8. Every implementation task must run its required validation.
9. Every task ends with a structured result.
10. `FAIL` or `SAFETY_STOP` means stop immediately.
11. `READY_FOR_COMMIT` requires human approval except when Yuki Autopilot V1.6 has
    independently verified every documented L1/L2 auto-approval gate. L3 always
    requires human approval and can never use the auto-approval exception.
12. Never auto-merge long-lived branches.

## Permanent forbidden actions unless explicitly authorized

- Production database writes.
- Database reset or seed.
- `backend/.env` modification.
- Historical migration modification.
- Credential extraction.
- EasyFreight production writes.
- PDA production enablement.
- Force push.
- `git clean`.
- `git reset --hard`.
- Destructive checkout or restore of unknown files.

L3 work additionally requires `APPROVED_L3 = YES` before preparation. L3 includes migrations, schema or database operations, inventory deduction or allocation consistency architecture, state-machine redesign, authentication/security model changes, credentials, PDA production enablement, EasyFreight writes, external production API writes, and destructive Git operations.

## Priority

1. Business correctness
2. Data safety
3. Workflow completeness
4. Automated tests
5. UI polish

For a prepared task, read `.codex/CURRENT_TASK.md` and the referenced prompt before editing. If `ALLOWED_PATHS` contains `DECLARATION_REQUIRED`, replace only that token with the exact minimal paths justified by the prompt before changing application files. Stop after implementation and validation. Do not commit, push, unlock another queue item, or begin another task unless the task is running through the explicitly selected Yuki Autopilot V1.6 `-Run -AutoApprove` L1/L2 flow. That flow may commit and push only the current task branch after all gates pass; it may never integrate the parent, unlock the queue, or begin another task.
