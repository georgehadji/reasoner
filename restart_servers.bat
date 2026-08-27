@echo off
setlocal
title Reasoner - Restarting...
cls

echo.
echo  ============================================================
echo    Reasoner  -  Restart All Servers
echo  ============================================================
echo.

:: Switch to the batch file's directory.
cd /d "%~dp0"

:: Pause only when launched from Explorer, where the window would otherwise
:: close over the error.
set "INTERACTIVE="
echo %CMDCMDLINE% | find /i "%~nx0" >nul 2>&1 && set "INTERACTIVE=1"

:: Working directory guard.
if not exist "kill_servers.py" (
    echo  [ERROR] Run from the project root ^(where kill_servers.py lives^).
    echo.
    if defined INTERACTIVE pause
    exit /b 1
)
if not exist "start_all.py" (
    echo  [ERROR] Run from the project root ^(where start_all.py lives^).
    echo.
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
    echo  [ERROR] No working Python found in PATH.
    echo          Install Python 3.12+ and re-run, or fix the PATH entry:
    echo          a "python" that opens the Microsoft Store is not one.
    echo.
    if defined INTERACTIVE pause
    exit /b 1
)

:: Port status before the stop. This used to be an inline PowerShell block
:: with its own copy of the port list, duplicated byte for byte in
:: kill_servers.bat and already a third copy of TARGET_PORTS in
:: kill_servers.py. One source now, and no PowerShell dependency.
%PY% kill_servers.py --status
echo.

:: Step 1: stop.
echo  [1/2] Stopping all servers...
%PY% kill_servers.py --force
set KILL_CODE=%ERRORLEVEL%

if %KILL_CODE% neq 0 (
    echo  [ERROR] Stop script exited with code %KILL_CODE%.
    echo.
    if defined INTERACTIVE pause
    exit /b %KILL_CODE%
)
echo  [OK]  All servers stopped.
echo.

:: Brief pause to let ports fully release.
timeout /t 2 /nobreak >nul

:: Step 2: start. This blocks until the servers are stopped again, so the
:: title and the closing message both belong on the far side of it - the
:: old version announced "Running" and "restarted" only once they were not.
echo  [2/2] Starting all servers...
echo.
title Reasoner - Running
%PY% start_all.py %*
set START_CODE=%ERRORLEVEL%
title Reasoner - Stopped

:: Ctrl+C is the intended way out of the run above, and cmd reports
:: STATUS_CONTROL_C_EXIT for it. That is not a failure to report.
set "CLEAN_STOP="
if %START_CODE% equ -1073741510 set "CLEAN_STOP=1"
if %START_CODE% equ 3221225786 set "CLEAN_STOP=1"

echo.
if not defined CLEAN_STOP if %START_CODE% neq 0 (
    echo  [ERROR] Start script exited with code %START_CODE%.
    echo.
    if defined INTERACTIVE pause
    exit /b %START_CODE%
)

echo  [OK]  Servers stopped. Restart cycle complete.
echo.
if defined INTERACTIVE pause
exit /b 0
