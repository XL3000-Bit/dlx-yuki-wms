@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "PY="
if exist "backend\.venv\Scripts\python.exe" set "PY=backend\.venv\Scripts\python.exe"
if not defined PY (
  where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  echo Python not found. Install Python 3.12+ or create backend\.venv first.
  pause
  exit /b 1
)

set "WB=%~1"
if "%WB%"=="" set "WB=%USERPROFILE%\Downloads\美西仓 - 4.0 (1).xlsx"

echo Workbook: %WB%
echo.
echo [1] Inspect only
echo [2] Export 8-container pilot CSVs
echo [3] Export named containers
echo.
set /p CHOICE=Choose 1-3: 

if "%CHOICE%"=="1" (
  %PY% tools\west_coast_import\convert_west_coast.py inspect "%WB%"
  goto END
)
if "%CHOICE%"=="2" (
  %PY% tools\west_coast_import\convert_west_coast.py export "%WB%" --out import_out --pilot 8
  echo.
  echo Files written to import_out\
  goto END
)
if "%CHOICE%"=="3" (
  set /p CNS=Container numbers, comma separated:
  %PY% tools\west_coast_import\convert_west_coast.py export "%WB%" --out import_out --containers "!CNS!"
  echo.
  echo Files written to import_out\
  goto END
)
echo Invalid choice.

:END
echo.
pause
endlocal
