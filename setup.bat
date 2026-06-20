@echo off
chcp 65001 >nul
title StudyWiki-Agent v0.3.5 安装器
cd /d "%~dp0"

echo.
echo    ╔══════════════════════════════════════════╗
echo    ║     🧠 StudyWiki-Agent v0.3.5           ║
echo    ║     本地知识库 AI Agent 安装器           ║
echo    ╚══════════════════════════════════════════╝
echo.
echo    正在检查环境...
echo.

:: ── 1. 检查 Python ──
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo    [错误] 未找到 Python！
    echo    请访问 https://www.python.org/downloads/ 安装 Python 3.10+
    pause
    exit /b 1
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo    [错误] 需要 Python 3.10+，当前版本：
    python --version
    pause
    exit /b 1
)
echo    [√] Python 就绪

:: ── 2. 创建虚拟环境 ──
if not exist ".venv\" (
    echo.
    echo    正在创建虚拟环境...
    python -m venv .venv >nul 2>&1
    if %errorlevel% neq 0 (
        echo    [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
)
echo    [√] 虚拟环境就绪

:: ── 3. 安装依赖 ──
echo.
echo    正在安装依赖包...
call .venv\Scripts\activate.bat >nul 2>&1
pip install -r requirements.txt --quiet 2>nul
if %errorlevel% neq 0 (
    echo    [警告] 部分依赖安装失败，尝试继续...
)
echo    [√] 依赖就绪

:: ── 4. 下载前端资源 ──
echo.
echo    正在下载前端资源...
if not exist "static\vendor\" mkdir static\vendor >nul
python scripts/download_vendor.py >nul 2>&1
if %errorlevel% neq 0 (
    echo    [警告] 前端资源下载失败（将使用 CDN）
) else (
    echo    [√] 前端资源就绪
)

:: ── 5. 配置 LLM ──
echo.
echo    ═══════════════════════════════════════════
echo              LLM 配置
echo    ═══════════════════════════════════════════
echo.
echo    选择 LLM 供应商:
echo       [1] DeepSeek (推荐，便宜好用)
echo       [2] OpenAI
echo       [3] Ollama (本地模型)
echo       [4] 跳过配置
echo.
set /p PROVIDER_CHOICE="    请输入数字 [1-4]: "

if "%PROVIDER_CHOICE%"=="1" (
    set LLM_PROVIDER=deepseek
    echo.
    echo    请输入 DeepSeek API Key (从 https://platform.deepseek.com 获取):
    set /p API_KEY="    > "
    echo.
    echo    输入模型名 (默认 deepseek-chat):
    set /p MODEL_NAME="    > "
    if "%MODEL_NAME%"=="" set MODEL_NAME=deepseek-chat
    set API_URL=https://api.deepseek.com
    set KEY_NAME=DEEPSEEK_API_KEY
    set MODEL_KEY=DEEPSEEK_MODEL
    set URL_KEY=DEEPSEEK_BASE_URL
)

if "%PROVIDER_CHOICE%"=="2" (
    set LLM_PROVIDER=openai
    echo.
    echo    请输入 OpenAI API Key (从 https://platform.openai.com 获取):
    set /p API_KEY="    > "
    echo.
    echo    输入模型名 (默认 gpt-4o):
    set /p MODEL_NAME="    > "
    if "%MODEL_NAME%"=="" set MODEL_NAME=gpt-4o
    set API_URL=https://api.openai.com/v1
    set KEY_NAME=OPENAI_API_KEY
    set MODEL_KEY=OPENAI_MODEL
    set URL_KEY=
)

if "%PROVIDER_CHOICE%"=="3" (
    set LLM_PROVIDER=ollama
    echo.
    echo    请输入 Ollama 模型名 (默认 llama3):
    set /p MODEL_NAME="    > "
    if "%MODEL_NAME%"=="" set MODEL_NAME=llama3
    set KEY_NAME=OLLAMA_MODEL
    set API_URL=http://localhost:11434
    set MODEL_KEY=OLLAMA_MODEL
    set URL_KEY=OLLAMA_BASE_URL
)

if not "%LLM_PROVIDER%"=="" (
    echo.
    echo    正在写入配置...
    (
        echo LLM_PROVIDER=%LLM_PROVIDER%
        if defined KEY_NAME echo %KEY_NAME%=%API_KEY%
        if defined MODEL_KEY echo %MODEL_KEY%=%MODEL_NAME%
        if defined URL_KEY echo %URL_KEY%=%API_URL%
        echo LLM_TEMPERATURE=0.1
        echo LLM_MAX_TOKENS=4096
        echo LLM_TIMEOUT_SEC=60
        echo EMBEDDING_PROVIDER=sentence-transformers
    ) > .env
    echo    [√] 配置已写入 .env
) else (
    if not exist ".env" (
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
    )
    echo    [√] 使用默认配置 (需手动编辑 .env 填入 API Key)
)

:: ── 6. 创建快捷方式 ──
echo.
echo    ═══════════════════════════════════════════
echo           创建快捷方式
echo    ═══════════════════════════════════════════
echo.
echo    是否创建桌面快捷方式?
echo       [1] 桌面
echo       [2] 当前文件夹
echo       [3] 跳过
echo.
set /p SHORTCUT_CHOICE="    请输入数字 [1-3]: "

if "%SHORTCUT_CHOICE%"=="1" (
    powershell -Command "$ws=New-Object -ComObject WScript.Shell;$sc=$ws.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\StudyWiki-Agent.lnk');$sc.TargetPath='%~dp0start_studywiki.bat';$sc.WorkingDirectory='%~dp0';$sc.IconLocation='%~dp0icon.ico';$sc.Save()" >nul 2>&1
    if exist "%USERPROFILE%\Desktop\StudyWiki-Agent.lnk" (
        echo    [√] 桌面快捷方式已创建
    ) else (
        echo    [警告] 快捷方式创建失败，请手动创建
    )
)

if "%SHORTCUT_CHOICE%"=="2" (
    powershell -Command "$ws=New-Object -ComObject WScript.Shell;$sc=$ws.CreateShortcut('%~dp0StudyWiki-Agent.lnk');$sc.TargetPath='%~dp0start_studywiki.bat';$sc.WorkingDirectory='%~dp0';$sc.Save()" >nul 2>&1
    echo    [√] 快捷方式已创建在当前目录
)

if "%SHORTCUT_CHOICE%"=="3" (
    echo    已跳过快捷方式创建
)

:: ── 7. 完成 ──
echo.
echo    ╔══════════════════════════════════════════╗
echo    ║        🎉 安装完成！                     ║
echo    ╚══════════════════════════════════════════╝
echo.
echo    启动方式:
echo      1. 双击桌面上的 StudyWiki-Agent 快捷方式
echo      2. 或在此目录运行:
echo         .venv\Scripts\activate.bat
echo         python main.py
echo.
echo    打开浏览器访问: http://localhost:8000
echo.
echo    (可选) 检查 Tesseract OCR:
echo      如果处理扫描版 PDF，请安装 Tesseract OCR
echo      下载: https://github.com/UB-Mannheim/tesseract/releases/tag/5.4.0
echo.
pause
