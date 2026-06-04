#!/usr/bin/env python3
"""StudyWiki-Agent 启动入口。

用法:
    python main.py                  # 默认 localhost:8000
    python main.py --host 0.0.0.0 --port 8080
"""

import os
import sys

# 确保控制台 UTF-8 输出
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import argparse
import uvicorn

from bobanana.config import HOST, PORT, LOG_LEVEL, DEBUG


def main():
    parser = argparse.ArgumentParser(description="StudyWiki-Agent")
    parser.add_argument("--host", default=HOST, help=f"监听地址 (默认: {HOST})")
    parser.add_argument("--port", type=int, default=PORT, help=f"监听端口 (默认: {PORT})")
    parser.add_argument("--reload", action="store_true", help="热重载 (开发模式)")
    args = parser.parse_args()

    print(f"""
  ┌──────────────────────────────────────┐
  │  StudyWiki-Agent v0.3.0             │
  │  本地 Wiki 知识库 AI Agent           │
  │                                      │
  │  http://{args.host}:{args.port}      │
  │  http://{args.host}:{args.port}/docs │
  └──────────────────────────────────────┘
    """)

    uvicorn.run(
        "bobanana.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=LOG_LEVEL,
    )


if __name__ == "__main__":
    main()
