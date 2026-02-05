"""
影视/图书垂类搜索 - 多规则意图解析与查询重写 POC.
"""
from pathlib import Path

# 从项目根目录加载 .env（HTTP 服务与 CLI 均生效）
def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        root = Path(__file__).resolve().parent.parent.parent
        load_dotenv(root / ".env")
    except Exception:
        pass

_load_dotenv()

from query_analysis.pipeline import Pipeline, parse

__all__ = ["Pipeline", "parse"]
