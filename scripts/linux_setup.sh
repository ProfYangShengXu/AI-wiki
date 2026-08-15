#!/usr/bin/env bash
# StudyWiki-Agent Linux/WSL 测试环境安装脚本
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[1/5] apt 系统依赖"
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip \
  tesseract-ocr tesseract-ocr-chi-sim poppler-utils

echo "[2/5] 创建 Linux venv"
if [ ! -x ".venv-linux/bin/python" ]; then
  python3 -m venv .venv-linux
fi

echo "[3/5] 升级 pip"
.venv-linux/bin/python -m pip install --upgrade pip

echo "[4/5] 安装 Python 依赖"
.venv-linux/bin/python -m pip install -r requirements.txt

echo "[5/5] 本地化前端 vendor"
.venv-linux/bin/python scripts/download_vendor.py

echo "Linux/WSL 测试环境就绪。"
echo "运行测试: bash scripts/run_tests_linux.sh"
