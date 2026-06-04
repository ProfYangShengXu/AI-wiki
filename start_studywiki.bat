@echo off
title StudyWiki-Agent
cd /d "C:\Users\45140\OneDrive\Desktop\code\AIwiki2.0"
echo.
echo  ========================================
echo    StudyWiki-Agent v0.2.0
echo    本地 Wiki 知识库 AI Agent
echo  ========================================
echo.
echo  [1/2] 正在启动服务...
python main.py
if %errorlevel% neq 0 (
    echo.
    echo  [!] 启动失败，请确保已安装依赖:
    echo     pip install -r requirements.txt
    pause
)
