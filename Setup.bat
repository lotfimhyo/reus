REM Project: Reus
REM Founder: Lotfi Mahiddine
REM Organization: Reulink
REM Contact: Contact@reulink.app

@echo off
REM ============================================================================
REM  Setup.bat -- run this ONCE before the first use of Run.bat.
REM  Pure Windows: no Docker, no Docker Compose, no WSL, no Linux tools needed.
REM  Uses the "memory" storage/event-bus backends (config.py's own defaults)
REM  so nothing else needs to be installed separately (no Postgres, no Redis).
REM ============================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo  Reus-Veritas OS -- one-time setup
echo ============================================
echo.

REM --- 1. Check Python is installed and is a real enough version -------------
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found on PATH.
    echo.
    echo Install Python 3.11 or newer from https://www.python.org/downloads/
    echo IMPORTANT during install: check the box "Add Python to PATH" on the
    echo first installer screen -- this is the single most common reason
    echo Python "isn't found" afterwards.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VERSION=%%v
echo Found Python %PY_VERSION%

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo [ERROR] Python %PY_VERSION% is too old. This project needs Python 3.11 or newer.
    echo Download a newer version from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM --- 2. Create the virtual environment if it doesn't exist yet -------------
if exist "venv\Scripts\python.exe" (
    echo Virtual environment already exists -- skipping creation.
) else (
    echo Creating a virtual environment in .\venv ...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create the virtual environment.
        pause
        exit /b 1
    )
)

REM --- 3. Activate it and install/upgrade dependencies ------------------------
call venv\Scripts\activate.bat

echo.
echo Upgrading pip...
python -m pip install --upgrade pip -q

echo Installing project dependencies (this can take a few minutes the first time)...
if exist requirements-dev.lock (
    pip install -r requirements-dev.lock -q
) else (
    pip install -r requirements-dev.txt -q
)
if errorlevel 1 (
    echo [ERROR] Dependency installation failed. Scroll up for the actual pip error.
    echo A common cause: no internet connection, or an outdated pip.
    pause
    exit /b 1
)
echo Dependencies installed successfully.

REM --- 4. Create .env from .env.example if it doesn't exist yet --------------
if exist ".env" (
    echo .env already exists -- leaving it untouched.
) else (
    if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
        echo Created .env from .env.example.
    ) else (
        echo [ERROR] Neither .env nor .env.example was found. Cannot continue.
        pause
        exit /b 1
    )
)

REM --- 5. Generate a real random admin/user API key on first setup only ------
REM Only replaces the value if it's still the shipped placeholder -- never
REM overwrites a key you already set yourself on a later Setup.bat re-run.
for /f "delims=" %%k in ('python -c "import secrets; print(secrets.token_urlsafe(24))"') do set NEW_ADMIN_KEY=%%k
for /f "delims=" %%k in ('python -c "import secrets; print(secrets.token_urlsafe(24))"') do set NEW_USER_KEY=%%k

python -c "import re; path='.env'; content=open(path, encoding='utf-8').read(); content=re.sub(r'^REUS_API_KEY=change-me-in-production$', 'REUS_API_KEY=%NEW_ADMIN_KEY%', content, flags=re.M); content=re.sub(r'^REUS_USER_API_KEY=change-me-in-production-user$', 'REUS_USER_API_KEY=%NEW_USER_KEY%', content, flags=re.M); open(path, 'w', encoding='utf-8').write(content)"
echo Generated real random API keys in .env (only if they were still placeholders).

REM --- 6. Create data directories the app may write to ------------------------
if not exist "data" mkdir data

REM --- 7. Check port 8000 is free ---------------------------------------------
netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul
if not errorlevel 1 (
    echo [WARNING] Port 8000 already appears to be in use by another program.
    echo Run.bat may fail to start, or you may need to close whatever else
    echo is using that port first.
)

REM --- 8. Real smoke test: does the app actually import and build correctly? -
echo.
echo Running a smoke test (importing the app, no server start yet)...
python -c "from api.main import app; print('OK: the app imports and builds successfully.')"
if errorlevel 1 (
    echo [ERROR] The application failed to import. This usually means a
    echo dependency didn't install correctly. Scroll up for the real error.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Setup complete.
echo  Next: double-click Run.bat to start the app.
echo ============================================
echo.
echo Note: by default this runs with an in-memory database (nothing
echo installed separately, but data is lost when you stop the app) and no
echo AI provider configured yet -- the server will start and its API docs
echo page will work, but /chat will return a clear error until you set
echo REUS_TASK_EXECUTOR=ollama or model_router (plus an API key) in .env.
echo See README.md for details.
echo.
pause
