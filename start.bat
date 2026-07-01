@echo off
setlocal enabledelayedexpansion
title OraVision AWR Pro
color 0B
cls

echo.
echo  ============================================================
echo.
echo       AAAAA   WW      WW  RRRRR    PPPPPP  RRRRRR   OOOOO
echo      AA   AA  WW      WW  RR   RR  PP   PP RR   RR OO   OO
echo      AAAAAAA  WW  WW  WW  RRRRRR   PPPPPP  RRRRRR  OO   OO
echo      AA   AA  WW WW WW WW RR  RR   PP      RR  RR  OO   OO
echo      AA   AA   WW    WW   RR   RR  PP      RR   RR  OOOOO
echo.
echo  ============================================================
echo       OraVision AWR Pro  --  Oracle RCA Engine v3.0
echo  ============================================================
echo.
echo    Upload Oracle AWR HTML reports to instantly detect
echo    performance bottlenecks, SQL regressions, wait event
echo    spikes, and get a full root cause analysis with
echo    prioritised recommendations -- all in one dashboard.
echo.
echo    NOTE: First launch may take 1-2 minutes to install
echo          dependencies. Subsequent starts are instant.
echo.
echo  ============================================================
echo.

:: ── Anchor working directory to the script's own folder ──────────────
cd /d "%~dp0"

:: ── Step 0: Find Python ─────────────────────────────────────────────
set PYTHON=
where py >nul 2>&1
if not errorlevel 1 ( set PYTHON=py& goto :python_found )
where python >nul 2>&1
if not errorlevel 1 ( set PYTHON=python& goto :python_found )
where python3 >nul 2>&1
if not errorlevel 1 ( set PYTHON=python3& goto :python_found )

color 0C
echo.
echo  ============================================================
echo   [ERROR] Python was not found on this machine.
echo  ============================================================
echo   Please install Python 3.10 or later:
echo     https://www.python.org/downloads/
echo   IMPORTANT: During install, tick [x] Add Python to PATH
echo  ============================================================
echo.
pause
exit /b 1

:python_found
echo  [OK] Python found: using "%PYTHON%"
echo.

:: ── Step 1: Kill EVERY leftover OraVision / uvicorn server ─────────
echo  [..] Stopping any previous OraVision / uvicorn servers...
del /q "%~dp0.oravision_port" >nul 2>&1
:: Robust (wmic-free) kill: any python running "uvicorn main:app" on any port.
:: This prevents stale servers piling up on old ports and serving outdated pages.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%%'\" | Where-Object { $_.CommandLine -match 'uvicorn\s+main:app' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {} }" >nul 2>&1
timeout /t 2 /nobreak >nul
echo  [OK] Old servers stopped.
echo.

:: ── Step 2: Install dependencies ─────────────────────────────────────
echo  [1/3] Checking and installing dependencies...
%PYTHON% -m pip install -r "%~dp0backend\requirements.txt" --disable-pip-version-check --no-warn-script-location --trusted-host pypi.org --trusted-host files.pythonhosted.org -q 2>nul
:: Reset errorlevel — pip warnings are not fatal
set "PIPERR=0"
%PYTHON% -c "import fastapi, uvicorn, jinja2, multipart, bs4, pydantic" >nul 2>&1
if errorlevel 1 (
    color 0C
    echo.
    echo  [ERROR] Dependencies are missing. Check internet or run manually:
    echo    %PYTHON% -m pip install -r backend\requirements.txt
    echo.
    pause
    exit /b 1
)
echo  [1/3] All dependencies ready.
echo.

:: ── Step 3: Find a free port ──────────────────────────────────────────
echo  [2/3] Finding available port...
echo import socket>"%TEMP%\_ovp.py"
echo for p in range(8000,8010):>>"%TEMP%\_ovp.py"
echo  try: s=socket.socket(); s.bind(('127.0.0.1',p)); s.close(); print(p); break>>"%TEMP%\_ovp.py"
echo  except: pass>>"%TEMP%\_ovp.py"
echo else: print(8000)>>"%TEMP%\_ovp.py"
set PORT=8000
for /f %%p in ('%PYTHON% "%TEMP%\_ovp.py"') do set PORT=%%p
del "%TEMP%\_ovp.py" >nul 2>&1
echo  [2/3] Using port !PORT!
echo.

:: ── Step 4: Launch browser after 3-second delay (non-blocking) ───────
echo  [3/3] Starting dashboard server...
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:!PORT!"
echo.
echo  ============================================================
echo    Dashboard URL  :  http://localhost:!PORT!
echo    Stop server    :  Press Ctrl+C in this window
echo    Restart        :  Just run start.bat again
echo  ============================================================
echo.

:: ── Final safety net: free the chosen port in case anything still holds it ─
powershell -NoProfile -Command ^
  "Get-NetTCPConnection -LocalPort !PORT! -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }" >nul 2>&1

:: ── Start uvicorn with auto-reload (blocks here until Ctrl+C) ────────
:: --reload re-applies .py edits; Jinja2 already re-reads index.html per request,
:: so a browser refresh always shows the latest dashboard — no stale pages.
cd /d "%~dp0backend"
%PYTHON% -m uvicorn main:app --host 127.0.0.1 --port !PORT! ^
  --reload --reload-dir routers --reload-dir services --reload-dir templates --reload-dir static --reload-include "*.html"

:: ── Server stopped ───────────────────────────────────────────────────
echo.
echo  ============================================================
echo    Server has stopped. To restart: run start.bat again
echo  ============================================================
echo.
pause
