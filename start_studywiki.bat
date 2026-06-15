@echo off
cd /d "C:\Users\45140\OneDrive\Desktop\code\AIwiki2.0"
echo =========================================
echo   StudyWiki-Agent v0.3.0
echo   Starting server...
echo =========================================
echo.
start "SWA" /min cmd /c "python main.py"
timeout /t 10 /nobreak >nul
start "" "http://localhost:8000"
echo.
echo Server started at http://localhost:8000
echo Close this window - server keeps running.
timeout /t 3 /nobreak >nul
