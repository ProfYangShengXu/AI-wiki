@echo off
chcp 65001 >nul
title StudyWiki-Agent Installer
cd /d "%~dp0"

echo =========================================
echo   StudyWiki-Agent v0.3.0 Installer
echo =========================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.10+ from:
    echo   https://www.python.org/downloads/
    pause
    exit /b 1
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 3.10+ required. Current:
    python --version
    pause
    exit /b 1
)
echo [OK] Python found: 
python --version

:: Create virtual env
if not exist ".venv\" (
    echo.
    echo Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
)

:: Install dependencies
echo.
echo Installing dependencies...
call .venv\Scripts\activate.bat
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)
echo [OK] Dependencies installed

:: Download vendor frontend assets
echo.
echo Downloading frontend assets...
if not exist "static\vendor\" mkdir static\vendor
python scripts/download_vendor.py >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Vendor download failed, will use CDN
) else (
    echo [OK] Frontend assets downloaded
)

:: Create .env if not exists
if not exist ".env" (
    echo.
    echo Creating .env configuration file...
    (
        echo LLM_PROVIDER=deepseek
        echo DEEPSEEK_API_KEY=
        echo DEEPSEEK_MODEL=deepseek-chat
        echo DEEPSEEK_BASE_URL=https://api.deepseek.com
        echo LLM_TEMPERATURE=0.1
        echo LLM_MAX_TOKENS=4096
        echo LLM_TIMEOUT_SEC=60
        echo EMBEDDING_PROVIDER=sentence-transformers
    ) > .env
    if exist ".env.example" copy /Y .env.example .env >nul 2>&1
    echo [OK] .env created
    echo.
    echo [IMPORTANT] Please edit .env to set your API key:
    echo   notepad .env
)

:: Create desktop shortcut
set SHORTCUT_PATH=%USERPROFILE%\Desktop\StudyWiki-Agent.bat
if not exist "%SHORTCUT_PATH%" (
    echo.
    echo Creating desktop shortcut...
    (
        echo @echo off
        echo cd /d "%~dp0"
        echo echo Starting StudyWiki-Agent...
        echo call .venv\Scripts\activate.bat
        echo start "SWA" /min cmd /c "python main.py"
        echo timeout /t 10 /nobreak ^>nul
        echo start "" "http://localhost:8000"
        echo echo Server running at http://localhost:8000
        echo timeout /t 3 /nobreak ^>nul
    ) > "%SHORTCUT_PATH%"
    if exist "%SHORTCUT_PATH%" (
        echo [OK] Shortcut created: %SHORTCUT_PATH%
    ) else (
        echo [WARNING] Failed to create shortcut
    )
)

echo.
echo =========================================
echo   Installation complete!
echo =========================================
echo.
echo To start:
echo   Double-click the desktop shortcut:
echo   %SHORTCUT_PATH%
echo.
echo Or run manually:
echo   .venv\Scripts\activate.bat
echo   python main.py
echo   http://localhost:8000
echo.
pause
