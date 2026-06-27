@echo off
REM ============================================================
REM  Quant AI / ArthaVest backend launcher
REM  ALWAYS launches with the project venv interpreter, which has
REM  the Phoenix/Arize stack installed. Launching from the base
REM  Anaconda python (no phoenix) silently disables tracing,
REM  /improve, and breaks the eval — so this pins the right one.
REM ============================================================
setlocal
set "HERE=%~dp0"
set "VENV_PY=%HERE%..\venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
  echo [ERROR] venv python not found at %VENV_PY%
  echo Create it / install requirements first:  pip install -r requirements.txt
  exit /b 1
)

echo Launching backend with venv python: %VENV_PY%
REM No --reload: the reloader spawns a child process that can orphan and hold
REM port 8000 after Ctrl-C, causing "address already in use" on the next start.
"%VENV_PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
endlocal
