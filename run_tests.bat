@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo [ERROR] Virtual environment not found: "%PY%"
  echo Run setup.bat first.
  pause
  exit /b 1
)

if "%1"=="full" goto full

echo ============================================
echo  StudyWiki-Agent - Quick Tests
echo  bootstrap + settings security
echo ============================================
"%PY%" -m pytest tests\test_bootstrap.py tests\test_settings_security.py tests\test_models.py tests\test_agent.py -q
set "EXIT=%errorlevel%"
goto end

:full
echo ============================================
echo  StudyWiki-Agent - Full Test Suite
echo  (May require API key / local model)
echo ============================================
"%PY%" -m pytest tests -q
set "EXIT=%errorlevel%"

:end
if not "%EXIT%"=="0" (
  echo.
  echo [FAILED] Tests exited with code %EXIT%.
) else (
  echo.
  echo [OK] Tests passed.
)
pause
exit /b %EXIT%
