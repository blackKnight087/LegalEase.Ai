@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0"

REM ------------------------------------------------------------------
REM LegalEase.AI launcher (Windows)
REM   - Detects/repairs a stale .venv_win
REM   - Uses --system-site-packages so already-installed deps are reused
REM   - Defaults LM Studio to localhost; override LM_STUDIO_URL in .env
REM ------------------------------------------------------------------

set "VENV_DIR=.venv_win"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

REM ---- Sanity-check the venv ---------------------------------------
set "REBUILD_VENV=0"
if not exist "%VENV_PY%" set "REBUILD_VENV=1"

if exist "%VENV_DIR%\pyvenv.cfg" (
    findstr /B /C:"home" "%VENV_DIR%\pyvenv.cfg" > "%TEMP%\legalease_venv_home.txt" 2>nul
    set /p VENV_HOME_LINE=<"%TEMP%\legalease_venv_home.txt"
    REM Rebuild if the venv references a Python install that no longer exists.
    for /f "tokens=2,* delims==" %%A in ("!VENV_HOME_LINE!") do (
        set "VENV_HOME=%%A"
        set "VENV_HOME=!VENV_HOME: =!"
        if not exist "!VENV_HOME!\python.exe" set "REBUILD_VENV=1"
    )
    del "%TEMP%\legalease_venv_home.txt" >nul 2>&1
)

if "%REBUILD_VENV%"=="1" (
    echo [setup] Rebuilding Python virtual environment...
    if exist "%VENV_DIR%" rmdir /S /Q "%VENV_DIR%"
    py -3 -m venv --system-site-packages "%VENV_DIR%"
    if errorlevel 1 (
        echo [setup] Failed to create venv. Install Python 3.10+ from python.org and retry.
        exit /b 1
    )
)

REM ---- Best-effort dependency check (does NOT block on missing pip)
"%VENV_PY%" -c "import streamlit, faiss, langchain, requests, dotenv" 1>nul 2>nul
if errorlevel 1 (
    echo [setup] Installing dependencies (one-time, can take a few minutes)...
    "%VENV_PY%" -m ensurepip --upgrade 1>nul 2>nul
    "%VENV_PY%" -m pip install --upgrade pip wheel setuptools
    "%VENV_PY%" -m pip install -r requirements.txt
)

REM ---- LM Studio defaults ------------------------------------------
if "%LM_STUDIO_URL%"=="" set "LM_STUDIO_URL=http://127.0.0.1:1234"
if "%LM_STUDIO_MODEL%"=="" set "LM_STUDIO_MODEL=meta-llama-3.1-8b-instruct"

echo.
echo === LegalEase.AI ===
echo Python:        %VENV_PY%
echo LM Studio URL: %LM_STUDIO_URL%   (override in .env if needed)
echo LM Studio Mdl: %LM_STUDIO_MODEL%
echo.

"%VENV_PY%" -m streamlit run app.py

endlocal
