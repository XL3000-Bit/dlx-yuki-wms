# Review Gate

Apply this gate after every Slice. Review the current Slice only and stop before any next-Slice work.

## Hard failures

Any of the following makes the review fail:

- Changes to unauthorized modules or any path outside the Slice's declared exact scope.
- Changes to Inbound, FBA, Scan/PDA, authentication, or unrelated code.
- Alembic or migration changes.
- Database connections, writes, configuration changes, or credential exposure.
- EasyFreight writes or other live browser writes.
- Incorrect batch response assumptions, including treating the warned-against names in `02_API_CONTRACT.md` as response fields.
- Looped individual calls where the Slice requires exactly one `POST /api/v1/outbounds/workbench/batch`.
- Dispatch blocker reasons not shown through `blocking_reasons`.
- Dead buttons for functional actions within the Slice's acceptance scope.
- Implementation beyond the current Slice.
- A dirty or unexpectedly changed worktree at the start, or unexpected paths at the end.
- A failing build, relevant test, manual workflow check, or `git diff --check`.

## Outcomes

- `PASS`: scope is exact, required checks pass, acceptance criteria are met, and the result is ready for human commit.
- `FAIL`: the Slice changed only recoverable in-scope work but one or more review requirements failed. Use: `Stop. Review failed: <reasons>. Fix only these.` Do not start the next Slice.
- `SAFETY_STOP`: a precondition failed, unexpected/user-owned changes exist, the permitted scope cannot be determined, or proceeding could violate a standing rule. Make no further changes and report the evidence.

## Mandatory human questions

1. Did the Slice modify Inbound, FBA, Scan/PDA, Alembic, database configuration, or unrelated code? If yes, fail unless specifically authorized.
2. Where batching is required, do bulk operations issue exactly one `POST /api/v1/outbounds/workbench/batch` instead of looping individual requests?
3. If dispatch is blocked, can the user see the actual `blocking_reasons`?
4. Are all functional buttons in the current Slice wired to real existing behavior?
5. Is all implementation confined to the current Slice?

## Human commands

```powershell
cd "C:\Users\XL\dlx-yuki-wms\frontend"
npm run build

cd "C:\Users\XL\dlx-yuki-wms"
git diff --check
git status --short
git diff --name-status
git diff --stat
```

Also inspect `git diff --cached --name-status`; Codex-created changes must remain unstaged unless separately authorized.
