REM Project: Reus
REM Founder: Lotfi Mahiddine
REM Organization: Reulink
REM Contact: Contact@reulink.app

@echo off
REM ============================================================================
REM  Run.bat -- double-click this to start Reus-Veritas OS. No typing needed.
REM  If the environment isn't set up yet, this calls Setup.bat automatically.
REM  On every run after that, it only checks for dependency updates (fast),
REM  not a full reinstall.
REM ============================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo  Reus-Veritas OS
echo ============================================
echo.

REM --- 1. If the environment doesn't exist yet, set it up automatically ------
if not exist "venv\Scripts\python.exe" (
    echo No environment found yet -- running Setup.bat first...
    echo.
    call Setup.bat
    if not exist "venv\Scripts\python.exe" (
        echo [ERROR] Setup did not complete successfully. See the messages above.
        pause
        exit /b 1
    )
    echo.
    echo Setup finished -- continuing to start the server now.
    echo.
)

call venv\Scripts\activate.bat

REM --- 2. Fast dependency check only (not a full reinstall every time) -------
REM pip is a fast no-op if everything is already satisfied, so this is safe
REM and quick to run on every single start -- it only actually installs
REM anything if requirements.txt/requirements-dev.txt changed since setup.
if exist requirements-dev.lock (
    pip install -r requirements-dev.lock -q
) else (
    pip install -r requirements-dev.txt -q
)

REM --- 3. Check .env exists (Setup.bat should have created it already) -------
if not exist ".env" (
    echo [ERROR] .env is missing. Delete the venv folder and run Setup.bat again.
    pause
    exit /b 1
)

REM --- 4. Load .env into this script's environment ----------------------------
REM Each line is already KEY=VALUE, which is exactly what `set "..."` expects
REM directly -- deliberately not using `for /f tokens=1,* delims==`, which has
REM a known quirk of silently reusing a stale value from the previous line for
REM any KEY= with an empty value (this project's .env.example has several,
REM e.g. REUS_ANTHROPIC_API_KEY=). eol=# skips comment lines; blank lines are
REM skipped by FOR /F automatically.
for /f "usebackq eol=# delims=" %%L in (".env") do (
    set "%%L"
)

REM --- 5. Warn about unsafe default keys --------------------------------------
if "%REUS_API_KEY%"=="change-me-in-production" (
    echo [WARNING] REUS_API_KEY is still the default placeholder value.
    echo Setup.bat should have replaced this automatically -- if you're
    echo seeing this, edit .env and set it manually, or delete .env and
    echo re-run Setup.bat.
)

REM --- 6. Warn if /chat will not actually work with the current executor -----
REM Found via live testing, not assumed: DefaultTaskExecutor (the actual
REM default) requires a pre-registered agent per task, and CognitiveTaskExecutor
REM requires a specific capability target -- neither works for free-text /chat.
REM Only "ollama" or "model_router" genuinely handle a bare prompt payload.
if "%REUS_TASK_EXECUTOR%"=="" set REUS_TASK_EXECUTOR=default
if "%REUS_TASK_EXECUTOR%"=="default" (
    echo [WARNING] REUS_TASK_EXECUTOR="default" -- /chat will return an error on every request.
    echo To enable /chat, edit .env and set REUS_TASK_EXECUTOR to "ollama" or "model_router"
    echo ^(plus REUS_ANTHROPIC_API_KEY / REUS_OPENAI_API_KEY / REUS_GOOGLE_API_KEY for model_router^).
    echo The rest of the app ^(the API docs at /docs, agent/workflow management^) works regardless.
)
if "%REUS_TASK_EXECUTOR%"=="cognitive" (
    echo [WARNING] REUS_TASK_EXECUTOR="cognitive" does not support /chat either
    echo ^(it needs a specific capability target, not free-text chat^). Use "ollama"
    echo or "model_router" instead if you want /chat to work.
)

REM --- 7. Start the server -----------------------------------------------------
echo.
echo Starting the server at http://localhost:8000
echo Interactive API docs: http://localhost:8000/docs
echo Press CTRL+C in this window to stop the server.
echo.

uvicorn api.main:app --host 0.0.0.0 --port 8000

echo.
echo Server stopped.
pause
