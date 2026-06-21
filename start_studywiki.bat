@echo off
cd /d "%~dp0"
echo Starting StudyWiki-Agent...
echo.
call .venv\Scripts\activate.bat 2>nul
start "SWA" /min cmd /c "cd /d \"%~dp0\" && .venv\Scripts\python.exe main.py"
echo Waiting for server to start...
timeout /t 10 /nobreak >nul
start "" "http://localhost:8000"
echo.
echo Server: http://localhost:8000
echo Close this window - server runs in background.
timeout /t 3 /nobreak >nul
