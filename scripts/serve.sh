#!/usr/bin/env bash
# 启动 Query Analysis HTTP 服务（从项目根执行；建议先 source .venv/bin/activate）
set -e
cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)/src"
if [[ -d .venv ]]; then
  exec .venv/bin/uvicorn query_analysis.server:app --host 0.0.0.0 --port 8000 --reload
else
  exec uvicorn query_analysis.server:app --host 0.0.0.0 --port 8000 --reload
fi
