@echo off
setlocal
title Reasoner - Starting...
cd /d "%~dp0"

:: Double-click launches this from Explorer, where the window closes the
:: instant the script ends and takes any error message with it. Run from a
:: shell and a pause is just an obstacle, so detect which one this is.
set "INTERACTIVE="
echo %CMDCMDLINE% | find /i "%~nx0" >nul 2>&1 && set "INTERACTIVE=1"

if not exist "start_all.py" (
    echo [ERROR] Run from the project root.
    if defined INTERACTIVE pause
    exit /b 1
)

:: `where python` also matches the Microsoft Store alias in WindowsApps,
:: which is a stub that opens the Store and exits nonzero. Only a python
:: that actually executes counts, and py -3 is the standard fallback.
set "PY="
python -c "import sys" >nul 2>&1 && set "PY=python"
if not defined PY py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"

if not defined PY (
    echo [ERROR] No working Python found in PATH.
    echo         Install Python 3.12+ and re-run, or fix the PATH entry:
    echo         a "python" that opens the Microsoft Store is not one.
    if defined INTERACTIVE pause
    exit /b 1
)

title Reasoner - Running
%PY% start_all.py %*
set EXIT_CODE=%ERRORLEVEL%
title Reasoner - Stopped

:: Ctrl+C is how this is meant to end: the orchestrator stops its children
:: and cmd reports STATUS_CONTROL_C_EXIT. Reporting that as a failure trains
:: the reader to ignore the line that matters when it is a real one.
set "CLEAN_STOP="
if %EXIT_CODE% equ -1073741510 set "CLEAN_STOP=1"
if %EXIT_CODE% equ 3221225786 set "CLEAN_STOP=1"
if not defined CLEAN_STOP if %EXIT_CODE% neq 0 echo [ERROR] Exited with code %EXIT_CODE%.

if defined INTERACTIVE pause
exit /b %EXIT_CODE%
