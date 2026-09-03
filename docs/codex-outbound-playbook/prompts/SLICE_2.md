Repo is C:\Users\XL\dlx-yuki-wms.
Follow standing rules: no migrations, no EasyFreight writes, no inventory/state-machine changes.
This session is SLICE 2 only.

# Slice 2 — Create auto-selection and allocation/release refresh

## Safety and scope gate

Run the clean-worktree checks from Slice 0, including status, staged diff, and `git diff --check`. Require a clean worktree and the human-committed prior Slice. Otherwise report `SAFETY_STOP`.

Before modifying anything, use `SLICE_0_RECON.md` and current code to enumerate exact frontend/test files as `ALLOWED_PATHS`, with a reason for each. Stop if an exact minimal scope cannot be established. No other path may change.

## Work

- After successful Outbound creation, automatically select the newly created record.
- Make the middle and right workbench regions follow that selection.
- After allocation, refresh the relevant detail and source panels.
- After release allocation, refresh the relevant panels.
- Prevent stale selection or detail state without redesigning inventory or workflow state.

## Acceptance

- Creating an Outbound selects it automatically.
- Dependent workbench regions update immediately.
- Allocate and release outcomes are immediately reflected in all relevant panels.
- Relevant tests and the frontend build pass.

## Finish

Run status, diff name/status and stat, `git diff --check`, and staged diff name/status. Stop on unexpected paths and do not revert them automatically. Apply `03_REVIEW_GATE.md`; report all changed paths and verification results. Do not commit or push. Do not start Slice 3.

STOP.
