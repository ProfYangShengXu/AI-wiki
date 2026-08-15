@echo off
cd /d "%~dp0"
echo Starting StudyWiki-Agent...
echo.
set "PY=%~dp0.venv\Scripts\python.exe"
start "SWA" /min "%PY%" "%~dp0main.py"
echo Waiting for server to start...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(30); $ok=$false; while((Get-Date) -lt $deadline){ try { $r=Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 1; if($r.status -eq 'ok'){ $ok=$true; break } } catch {}; Start-Sleep -Milliseconds 500 }; if(-not $ok){ Write-Host '[ERROR] Service did not become ready in 30s' -ForegroundColor Red; exit 1 }"
if errorlevel 1 (echo [ERROR] Service failed to start. Check logs\ & timeout /t 5 >nul & exit /b 1) else (start "" "http://127.0.0.1:8000")
echo.
echo Server: http://127.0.0.1:8000
echo Close this window - server runs in background.
timeout /t 1 /nobreak >nul
