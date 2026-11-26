@echo off
rem Rendered from thehub-pr/federation-templates/PRII-APP.bat - do not hand-edit.
rem Double-click launcher (Windows). Finds a Python and hands over to
rem desktop\setup.py, which sets the app up on first run and starts it.
rem Options are passed through: run with --help to see them.
setlocal
cd /d "%~dp0"

rem Newest Python first; every candidate is checked against the 3.10 floor,
rem because a bare "py -3" or "python" can be an older install. Written
rem without call/goto labels, which cmd can misread in a file with LF endings.
set "PYCHECK=import sys; raise SystemExit(sys.version_info < (3, 10))"
set "PYTHON="
for %%C in ("py -3.14" "py -3.13" "py -3.12" "py -3.11" "py -3.10" "py -3" "python") do (
  if not defined PYTHON (
    %%~C -c "%PYCHECK%" >nul 2>nul && set "PYTHON=%%~C"
  )
)
if not defined PYTHON (
  echo Python 3.10 or newer is required.
  echo Se requiere Python 3.10 o posterior.
  echo Opening the Python download page - run the installer it offers, then
  echo double-click this launcher again.
  echo Abriendo la pagina de descarga de Python - ejecute el instalador y
  echo vuelva a abrir este lanzador.
  start "" "https://www.python.org/downloads/"
  pause
  exit /b 1
)

%PYTHON% desktop\setup.py --launch %*
if errorlevel 1 pause
