@echo off
title StudyWiki-Agent v0.3.6 Installer
cd /d "%~dp0"

echo.
echo    =========================================
echo      StudyWiki-Agent v0.3.6
echo      Local Knowledge Base AI Installer
echo    =========================================
echo.

:: -- 1. Check Python --
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo    [ERROR] Python not found. Install from:
    echo    https://www.python.org/downloads/
    pause
    exit /b 1
)
echo    [OK] Python found

:: -- 2. Create venv --
if not exist ".venv\" (
    echo    Creating virtual environment...
    python -m venv .venv >nul 2>&1
)
echo    [OK] Virtual environment

:: -- 3. Install deps --
echo    Installing dependencies...
call .venv\Scripts\activate.bat >nul 2>&1
pip install -r requirements.txt --quiet 2>nul
echo    [OK] Dependencies

:: -- 4. Vendor assets --
echo    Downloading frontend assets...
if not exist "static\vendor\" mkdir static\vendor >nul
python scripts/download_vendor.py >nul 2>&1
echo    [OK] Frontend assets

:: -- 5. Create .env if missing --
if not exist ".env" (
    (
        echo # LLM Configuration
        echo LLM_PROVIDER=deepseek
        echo DEEPSEEK_API_KEY=your-api-key-here
        echo DEEPSEEK_MODEL=deepseek-chat
        echo DEEPSEEK_BASE_URL=https://api.deepseek.com
        echo.
        echo # OpenAI (uncomment to use)
        echo #OPENAI_API_KEY=sk-...
        echo #OPENAI_MODEL=gpt-4o
        echo.
        echo # Ollama (uncomment to use)
        echo #OLLAMA_MODEL=llama3
        echo #OLLAMA_BASE_URL=http://localhost:11434
        echo.
        echo LLM_TEMPERATURE=0.1
        echo LLM_MAX_TOKENS=4096
        echo LLM_TIMEOUT_SEC=60
        echo EMBEDDING_PROVIDER=sentence-transformers
    ) > .env
    echo    [OK] .env created - edit to set API key
) else (
    echo    [OK] .env exists
)

:: -- 6. Shortcut --
echo.
echo    Create shortcut?
echo    [1] Desktop
echo    [2] Current folder
echo    [3] Skip
set /p SC="    Enter [1-3]: "

if "%SC%"=="1" (
    del "%USERPROFILE%\Desktop\StudyWiki-Agent.lnk" 2>nul
    powershell -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\StudyWiki-Agent.lnk');$s.TargetPath='%~dp0start_studywiki.bat';$s.WorkingDirectory='%~dp0';$s.Save()" >nul 2>&1
    echo    [OK] Desktop shortcut created
)
if "%SC%"=="2" (
    powershell -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%~dp0StudyWiki-Agent.lnk');$s.TargetPath='%~dp0start_studywiki.bat';$s.WorkingDirectory='%~dp0';$s.Save()" >nul 2>&1
    echo    [OK] Shortcut created
)

:: -- 7. Done --
echo.
echo    =========================================
echo      Installation Complete!
echo    =========================================
echo.
echo    Configure:  notepad .env  (set API key)
echo    Start:      Double-click desktop shortcut
echo    Browser:    http://localhost:8000
echo.
echo    Or use frontend Settings to configure.
echo.
pause
