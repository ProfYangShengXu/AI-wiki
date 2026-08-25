#!/usr/bin/env python3
"""StudyWiki-Agent 启动入口。

用法:
    python main.py                  # 默认 localhost:8000
    python main.py --host 0.0.0.0 --port 8080
"""

import os
import sys

# PyInstaller 打包后多进程安全(Windows 必需)
import multiprocessing

# 确保控制台 UTF-8 输出
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import uvicorn

from bobanana.config import HOST, PORT, LOG_LEVEL


def main():
    parser = argparse.ArgumentParser(description="StudyWiki-Agent")
    parser.add_argument("--host", default=HOST, help=f"监听地址 (默认: {HOST})")
    parser.add_argument("--port", type=int, default=PORT, help=f"监听端口 (默认: {PORT})")
    parser.add_argument("--reload", action="store_true", help="热重载 (开发模式)")
    args = parser.parse_args()

    print(f"""
  ┌──────────────────────────────────────┐
  │  StudyWiki-Agent v0.25.0             │
  │  本地 Wiki 知识库 AI Agent           │
  │                                      │
  │  http://{args.host}:{args.port}      │
  │  http://{args.host}:{args.port}/docs │
  └──────────────────────────────────────┘
    """)

    # 直接导入 app 对象,避免 uvicorn 的字符串导入在 PyInstaller 冻结环境下
    # 报 "Could not import module bobanana.app" 且吞掉内部 traceback。
    # 若 bobanana.app 导入失败,异常会带完整堆栈直接抛出,便于诊断打包缺失。
    from bobanana.app import app

    uvicorn.run(
        app if not args.reload else "bobanana.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=LOG_LEVEL,
    )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
