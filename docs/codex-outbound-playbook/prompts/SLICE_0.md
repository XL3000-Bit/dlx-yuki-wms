Repo is C:\Users\XL\dlx-yuki-wms.
Follow standing rules: no migrations, no EasyFreight writes, no inventory/state-machine changes.
This session is SLICE 0 only.

# Slice 0 — Read-only reconciliation

Do not implement or fix anything. Inspect the actual repository and create only:

`docs/codex-outbound-playbook/SLICE_0_RECON.md`

## Safety gate

Before reading business code, run:

```powershell
cd "C:\Users\XL\dlx-yuki-wms"
git branch --show-current
git rev-parse HEAD
git status --short --untracked-files=all
git diff --cached --name-status
git diff --check
```

Require a clean worktree, zero staged paths, and a passing diff check. Otherwise make no changes and report `SAFETY_STOP`.

Declare the exact allowed modification scope before writing: only `docs/codex-outbound-playbook/SLICE_0_RECON.md`. Stop if it already contains unexpected user work or if any other changed path appears.

## Reconciliation work

Verify actual code rather than assuming prior briefs are correct. Record file-and-line evidence for:

- Current Outbound Workbench frontend organization and state flow.
- Whether bulk UI actions issue one `POST /api/v1/outbounds/workbench/batch` or loop over individual endpoints.
- The actual batch request and response contract, including `results[].id`, `results[].status`, `results[].reason`, `successful`, and `failed`.
- The actual workbench query contract: `q`, `status`, `ob_type`, `warehouse_id`, `carrier_id`, `page`, `per_page`, `sort_by`, and `sort_order`. Do not invent other filters; note where extra UI search values fold into `q`.
- `GET /api/v1/outbounds/{id}/dispatch-readiness`, the readiness representation, dispatch failure behavior, and whether `blocking_reasons` reaches the UI.
- Existing export, selected export, Create Load, Picking, BOL, allocation, release, selection, and refresh behavior.
- The exact current-code boundaries and proposed exact allowed file paths for Slices 1–5.
- Confirmed facts, discrepancies, and unresolved code-level questions.

Zero backend code diff, zero frontend source diff, and zero migration diff are mandatory. Do not connect to a database, call live APIs, write EasyFreight, or run application workflows.

## Finish

Run:

```powershell
git status --short --untracked-files=all
git diff --name-status
git diff --stat
git diff --check
git diff --cached --name-status
```

Require exactly one changed path, the authorized reconciliation report, and zero staged paths. Apply `03_REVIEW_GATE.md`. Report every changed path, the batch/filter/readiness conclusions, Slice 1–5 boundaries, unresolved questions, and human review commands. Do not commit or push. Do not implement Slices 1–5.

STOP.
