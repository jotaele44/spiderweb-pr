@echo off
rem Double-click launcher (Windows). First run installs dependencies (needs
rem internet once); later runs start the app directly and work offline.
setlocal
cd /d "%~dp0"

rem Newest Python that meets the project's 3.11 floor. A bare "py -3" or
rem "python" can be an older install, so every candidate is checked. (Written
rem without call/goto labels, which cmd can misread in a file with LF endings.)
set "PYCHECK=import sys; raise SystemExit(sys.version_info < (3, 11))"
set "PYTHON="
for %%C in ("py -3.14" "py -3.13" "py -3.12" "py -3.11" "py -3" "python") do (
  if not defined PYTHON (
    %%~C -c "%PYCHECK%" >nul 2>nul && set "PYTHON=%%~C"
  )
)
if not defined PYTHON (
  echo Python 3.11 or newer is required.
  echo Opening the Python download page - run the installer it offers, then
  echo double-click this launcher again.
  start "" "https://www.python.org/downloads/"
  pause
  exit /b 1
)

%PYTHON% desktop\setup.py --ensure
if errorlevel 1 (
  echo.
  echo Setup did not finish; the last lines above say which step stopped.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" desktop\launch.py %*
if errorlevel 1 pause
