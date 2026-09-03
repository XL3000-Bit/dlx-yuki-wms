# Yuki Review Gate

Every task must pass all applicable checks below.

## A. Git

- Expected branch.
- Expected base.
- No unexpected worktree changes.
- Staged paths = 0 before review.
- `git diff --check` = `PASS`.
- `HEAD` still equals the task start SHA before commit.

## B. Scope

Every changed path must be allowed by `.codex/CURRENT_TASK.md`. An unexpected path produces `RESULT = SAFETY_STOP`. Never automatically restore it.

## C. Protected areas

Unless an authorized task scope explicitly permits them, changes must be zero under:

- `backend/alembic/**`
- `alembic/**`
- `migrations/**`
- `backend/.env`
- PDA paths
- Unrelated inbound files
- Unrelated FBA files
- Authentication or security files

## D. Backend

When backend code changes, run relevant pytest, applicable safety tests, and Python syntax/import checks. If relevant tests cannot be discovered, fail closed and use the explicitly requested full-backend mode or document an authorized test command.

## E. Frontend

When frontend code changes, run `npm run build` from `frontend`. Run relevant lint/test scripts when configured; otherwise report `NOT_CONFIGURED`.

## F. Business-specific gates

Outbound Slice tasks must additionally verify, when required by their prompt:

1. Batch operations use `POST /api/v1/outbounds/workbench/batch`.
2. The actual response uses `results[{id,status,reason}]`, `successful`, and `failed`.
3. Dispatch blocked state surfaces `blocking_reasons`.
4. No unauthorized inventory or state-machine changes occurred.

Automated token checks support but do not replace the human semantic review.

## G. Result states

- `PASS`
- `FAIL`
- `SAFETY_STOP`
- `READY_FOR_HUMAN_REVIEW`
- `READY_FOR_COMMIT`

Never automatically convert `READY_FOR_HUMAN_REVIEW` to `READY_FOR_COMMIT`.
