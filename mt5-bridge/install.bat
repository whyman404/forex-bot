@echo off
REM ===========================================================================
REM install.bat — minimal MT5 Bridge installer (no service, no firewall).
REM Use this for a quick manual run; for production prefer install.ps1.
REM ===========================================================================
setlocal

set ROOT=%~dp0
cd /d "%ROOT%"

where py >NUL 2>&1 || (
    echo Python launcher 'py' not found. Install Python 3.12 from python.org.
    exit /b 1
)

if not exist "%ROOT%.venv" (
    echo Creating venv...
    py -3.12 -m venv "%ROOT%.venv"
)

call "%ROOT%.venv\Scripts\activate.bat"
python -m pip install --upgrade pip setuptools wheel >NUL
python -m pip install -e .

if "%BRIDGE_TOKEN%"=="" (
    echo BRIDGE_TOKEN is not set in this session.
    echo Set it permanently with:
    echo     setx BRIDGE_TOKEN "your-long-random-token-here" /M
    echo and re-open a new cmd window.
    exit /b 1
)

echo Starting bridge on %BRIDGE_BIND% ^(default 0.0.0.0:8500^)...
python -m mt5_bridge.server
endlocal
