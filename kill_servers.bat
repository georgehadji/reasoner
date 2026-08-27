@echo off
setlocal
title Reasoner - Stopping...
cls

echo.
echo  ============================================================
echo    Reasoner  -  Stop All Servers
echo  ============================================================
echo.

:: Switch to the batch file's directory.
cd /d "%~dp0"

:: Pause only when launched from Explorer. --quiet suppresses the pause as
:: well, for scripted callers.
set "INTERACTIVE="
echo %CMDCMDLINE% | find /i "%~nx0" >nul 2>&1 && set "INTERACTIVE=1"

:: Working directory guard.
if not exist "kill_servers.py" (
    echo  [ERROR] Run from the project root ^(where kill_servers.py lives^).
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

:: Parse arguments: --quiet is ours, everything else goes to the script.
set "QUIET_FLAG="
set "EXTRA_ARGS="

:PARSE_LOOP
if "%~1"=="" goto :PARSE_DONE
if "%~1"=="--quiet" (
    set "QUIET_FLAG=1"
    shift
    goto :PARSE_LOOP
)
set "EXTRA_ARGS=%EXTRA_ARGS% %1"
shift
goto :PARSE_LOOP
:PARSE_DONE

:: Port status. This used to be an inline PowerShell block carrying its own
:: copy of the port list - identical to the one in restart_servers.bat, and
:: a third copy of TARGET_PORTS in kill_servers.py. One source now, and no
:: PowerShell dependency.
if not defined QUIET_FLAG (
    %PY% kill_servers.py --status
    echo.
)

%PY% kill_servers.py%EXTRA_ARGS%
set EXIT_CODE=%ERRORLEVEL%

title Reasoner - Stopped
echo.
if %EXIT_CODE% neq 0 (
    echo  [ERROR] Stop script exited with code %EXIT_CODE%.
) else (
    echo  [OK]  All servers stopped.
)
echo.

if defined QUIET_FLAG exit /b %EXIT_CODE%
if defined INTERACTIVE pause
exit /b %EXIT_CODE%
