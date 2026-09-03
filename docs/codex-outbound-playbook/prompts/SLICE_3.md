Repo is C:\Users\XL\dlx-yuki-wms.
Follow standing rules: no migrations, no EasyFreight writes, no inventory/state-machine changes.
This session is SLICE 3 only.

# Slice 3 — Filters and columns using existing fields only

## Safety and scope gate

Run the clean-worktree checks from Slice 0, including status, staged diff, and `git diff --check`. Require a clean worktree and the human-committed prior Slice. Otherwise report `SAFETY_STOP`.

Before modifying anything, use `SLICE_0_RECON.md` and current code to enumerate exact frontend/test files as `ALLOWED_PATHS`, with a reason for each. Stop if an exact minimal scope cannot be established. No other path may change.

## Contract

The existing workbench parameters are exactly:

- `q`
- `status`
- `ob_type`
- `warehouse_id`
- `carrier_id`
- `page`
- `per_page`
- `sort_by`
- `sort_order`

Do not invent unsupported dedicated backend filter parameters. Extra search inputs must continue feeding `q` where applicable. Do not add empty Team/Notify columns or other columns without existing real data. Backend expansion may only be proposed, not silently added, and only if this Slice proves it is required.

## Acceptance

- Filters operate through the actual backend contract.
- Columns are backed by real existing data.
- No dead or permanently blank business columns are introduced.
- Relevant tests and the frontend build pass.

## Finish

Run status, diff name/status and stat, `git diff --check`, and staged diff name/status. Stop on unexpected paths and do not revert them automatically. Apply `03_REVIEW_GATE.md`; report all changed paths, actual query parameters exercised, and verification results. Do not commit or push. Do not start Slice 4.

STOP.
