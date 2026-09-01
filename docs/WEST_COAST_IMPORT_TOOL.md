# West Coast 4.0 converter (offline program)

This is a local program. It reads `美西仓 - 4.0 (1).xlsx` and writes UTF-8 CSVs. It does **not** write to PostgreSQL or call the WMS API.

The live warehouse system is still started with `START_DLX_WMS.bat`.

## Run (double-click)

1. `git pull` the repo.
2. Double-click `CONVERT_WEST_COAST.bat`.
3. Default workbook path is `%USERPROFILE%\Downloads\美西仓 - 4.0 (1).xlsx`. Drag-drop the xlsx onto the bat to override.
4. Choose inspect, 8-container pilot, or named containers.

Output folder: `import_out\`

| File | Use |
|---|---|
| `01_container_tracking.csv` | Container Tracking |
| `02_ol_inbound.csv` | `WEST_COAST_4_0_OL` |
| `03a_outbound_header.csv` | `WEST_COAST_4_0_OUTBOUND` |
| `03b_ds_lines.csv` | `WEST_COAST_4_0_DS` |
| `reconcile.json` | Pallet / carton / lbs / cbm by container |

## Run (command line)

```powershell
cd C:\Users\XL\dlx-yuki-wms
backend\.venv\Scripts\python.exe tools\west_coast_import\convert_west_coast.py inspect "C:\Users\XL\Downloads\美西仓 - 4.0 (1).xlsx"
backend\.venv\Scripts\python.exe tools\west_coast_import\convert_west_coast.py export "C:\Users\XL\Downloads\美西仓 - 4.0 (1).xlsx" --out import_out --pilot 8
backend\.venv\Scripts\python.exe tools\west_coast_import\convert_west_coast.py export "C:\Users\XL\Downloads\美西仓 - 4.0 (1).xlsx" --out import_out --containers "MSKU1234567,TCLU7654321"
```

Needs `openpyxl` (already in `backend/requirements.txt`).

## After CSVs exist

Sign in to Yuki → `/inbound` or Import Wizard → preview → confirm. Still honor the gates in `docs/WEST_COAST_4_0_IMPORT_CONSOLE.md`.
