# Workspace gate before Slice 0

Do not start Slice 0 until `git status` is clean of unrelated tracked changes.

## artifacts/ amazon FBA BOL samples

These two untracked files are **local samples**, not part of Slice 0:

- `artifacts/amazon-fba-bol-sample.pdf`
- `artifacts/amazon-fba-bol-sample.xlsx`

Decision: **do not commit them** on `feature/java-api-parity` or on any outbound-parity slice. They are not playbook inputs and they are not code.

Keep them on disk if you still need the BOL layout reference. Hide them from git:

```powershell
cd C:\Users\XL\dlx-yuki-wms
New-Item -ItemType Directory -Force -Path .\artifacts | Out-Null
# leave files where they are; ignore the folder locally without touching tracked files:
git status --short artifacts
```

If the safety gate still treats untracked files as dirty, move them out of the repo:

```powershell
New-Item -ItemType Directory -Force -Path $env:USERPROFILE\Documents\dlx-samples | Out-Null
Move-Item -Force .\artifacts\amazon-fba-bol-sample.pdf $env:USERPROFILE\Documents\dlx-samples\
Move-Item -Force .\artifacts\amazon-fba-bol-sample.xlsx $env:USERPROFILE\Documents\dlx-samples\
git status
```

Do not `git add artifacts/`.
Do not delete the samples unless you no longer need them.
