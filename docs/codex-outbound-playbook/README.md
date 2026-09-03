# Outbound Codex Playbook

`PLAYBOOK_PROVENANCE = RECONSTRUCTED_FROM_APPROVED_USER_RULES`

This documentation playbook governs the staged completion of Outbound Workbench parity. It was reconstructed from rules and contracts explicitly approved by the user after the original package could not be located. It is not, and must not be represented as, byte-identical to the missing original package.

## Sequence

Run the work in order, using exactly one Codex session per Slice:

1. Slice 0: read-only reconciliation and `SLICE_0_RECON.md`; no business-code changes.
2. Slice 1: workbench structure, dispatch readiness, blocker display, and the real batch API.
3. Slice 2: create auto-selection and allocation/release refresh.
4. Slice 3: filters and columns using existing fields only.
5. Slice 4: export, Create Load, and batch Picking/BOL.
6. Slice 5: gap and changelog closeout; no new functionality.

Never execute more than one Slice in a session. Do not start the next Slice until the prior Slice has passed human review, has been committed by a human, and the worktree is clean.

## Recommended branch flow

Start from the approved clean baseline. A human may create a parent branch such as `feature/outbound-ef-parity`, then a dedicated branch for each Slice (for example `feature/outbound-ef-parity-slice-0`). Codex must not create branches, commit, push, merge, rebase, reset, clean, stash, restore, or otherwise rewrite Git state unless separately authorized.

## Human review flow

For each Slice:

1. Run only that Slice prompt.
2. Inspect its changed-path report and apply `03_REVIEW_GATE.md`.
3. Run the frontend build when the Slice touches frontend source.
4. Manually exercise the affected workflow.
5. If review fails, instruct: `Stop. Review failed: <reasons>. Fix only these.`
6. After review passes, a human commits the Slice and confirms a clean worktree before starting the next session.

The API facts in `02_API_CONTRACT.md` are the approved baseline, but Slice 0 must still verify the actual repository code and record discrepancies rather than assuming the brief is correct.
