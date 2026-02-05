#!/usr/bin/env bash
# 创建 .venv 并安装依赖（在项目根执行）
set -e
cd "$(dirname "$0")/.."
if [[ -d .venv ]]; then
  echo ".venv already exists. Activate with: source .venv/bin/activate"
  exit 0
fi
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
echo "Done. Activate with: source .venv/bin/activate"
