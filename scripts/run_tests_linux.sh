#!/usr/bin/env bash
# StudyWiki-Agent Linux/WSL 测试入口
# 用法:
#   bash scripts/run_tests_linux.sh          # 快速测试（推荐）
#   bash scripts/run_tests_linux.sh full     # 全量测试
set -euo pipefail

cd "$(dirname "$0")/.."

PY=".venv-linux/bin/python"
if [ ! -x "$PY" ]; then
  echo "未找到 .venv-linux，请先运行: bash scripts/linux_setup.sh"
  exit 1
fi

if [ "${1:-}" = "full" ]; then
  echo "==> 全量测试"
  "$PY" -m pytest tests -q
else
  echo "==> 快速测试（bootstrap / settings security / models / agent / tools）"
  "$PY" -m pytest \
    tests/test_bootstrap.py \
    tests/test_settings_security.py \
    tests/test_models.py \
    tests/test_agent.py \
    tests/test_tools.py \
    tests/test_tools_ext.py \
    tests/test_tools_layer.py \
    -q
fi
