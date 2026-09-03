Repo is C:\Users\XL\dlx-yuki-wms.
Follow standing rules: no migrations, no EasyFreight writes, no inventory/state-machine changes.
This session is SLICE 1 only.

# Slice 1 — Workbench structure, dispatch readiness, and real batch API

## Safety and scope gate

Run the clean-worktree checks from Slice 0, including status, staged diff, and `git diff --check`. Require a clean worktree and confirm the human-committed Slice 0 reconciliation exists. Otherwise report `SAFETY_STOP`.

Before modifying anything, read `SLICE_0_RECON.md`, enumerate the exact frontend/backend/test file paths needed for this Slice as `ALLOWED_PATHS`, and explain each path's purpose. Stop if the reconciliation does not support an exact minimal scope. No other path may change.

## Work

- Apply functional naming/organization to the three workbench regions only where required by the approved design and current code.
- Call `GET /api/v1/outbounds/{id}/dispatch-readiness` before dispatch.
- When dispatch is not ready, show the actual `blocking_reasons`.
- Replace looped multi-select operations covered by this Slice with exactly one request to `POST /api/v1/outbounds/workbench/batch`.
- Use the batch response fields `results[].id`, `results[].status`, `results[].reason`, `successful`, and `failed` exactly as documented in `02_API_CONTRACT.md`.
- Warning: `outbound_id`, `succeeded`, and `total` are incorrect batch response-field assumptions; do not implement them.
- Do not redesign inventory logic or the state machine.

## Acceptance

- Each covered multi-select operation sends exactly one batch POST.
- A not-ready dispatch visibly exposes `blocking_reasons`.
- The three-region changes are functional and minimal, with no unrelated UI polish.
- Relevant tests and the frontend build pass.

## Finish

Run status, unstaged diff name/status and stat, `git diff --check`, and staged diff name/status. Stop on any changed path outside `ALLOWED_PATHS`; do not revert it automatically. Apply `03_REVIEW_GATE.md` and report every changed path, tests/build/manual checks, and acceptance results. Do not commit or push. Do not start Slice 2.

STOP.
