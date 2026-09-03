Repo is C:\Users\XL\dlx-yuki-wms.
Follow standing rules: no migrations, no EasyFreight writes, no inventory/state-machine changes.
This session is SLICE 4 only.

# Slice 4 — Export, Create Load, and batch Picking/BOL

## Safety and scope gate

Run the clean-worktree checks from Slice 0, including status, staged diff, and `git diff --check`. Require a clean worktree and the human-committed prior Slice. Otherwise report `SAFETY_STOP`.

Before modifying anything, use `SLICE_0_RECON.md` and current code to enumerate exact frontend/backend/test files as `ALLOWED_PATHS`, with a reason for each. Stop if an exact minimal scope cannot be established. No other path may change.

## Work

Wire functional actions to existing behavior so their buttons are not dead:

- Filtered export through `GET /api/v1/outbounds/files/export.xlsx`.
- Selected export through `POST /api/v1/outbounds/workbench/export-selected`.
- Create Load through `POST /api/v1/loads`.
- Picking through the existing single-record endpoint where appropriate and the approved batch mechanism for multi-select.
- BOL through the existing single-record endpoint where appropriate and the approved batch mechanism for multi-select.
- Multi-select Picking and BOL must use exactly one `POST /api/v1/outbounds/workbench/batch`, whose supported actions include `picking` and `bol`.

Use existing backend functionality where available. Do not redesign BOL generation, inventory logic, or the state machine.

## Acceptance

- Filtered export, selected export, Create Load, batch Picking, and batch BOL perform real existing business actions.
- There are no dead buttons within this Slice's functional scope.
- Batch Picking/BOL use one approved batch request rather than looped single-record calls.
- Relevant tests and the frontend build pass.

## Finish

Run status, diff name/status and stat, `git diff --check`, and staged diff name/status. Stop on unexpected paths and do not revert them automatically. Apply `03_REVIEW_GATE.md`; report all changed paths, requests observed, and verification results. Do not commit or push. Do not start Slice 5.

STOP.
