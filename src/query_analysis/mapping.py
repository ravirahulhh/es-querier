"""
垂类 Field Mapping：语义 field → ES 字段名（按 domain）；
Query Type：语义 field → 搜索方式（match / term / range）。
"""
import json
from pathlib import Path
from typing import Dict, Literal

Domain = Literal["video", "book"]

# query_type: "match" 全文匹配, "term" 强匹配, "range" 支持范围比较
QueryType = Literal["match", "term", "range"]

_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_MAPPING_PATH = _ROOT / "configs" / "field_mapping.json"
_DEFAULT_QUERY_TYPE_PATH = _ROOT / "configs" / "query_type.json"


def load_field_mapping(config_path: str | Path | None = None) -> Dict[str, Dict[str, str]]:
    """加载 configs/field_mapping.json，结构为 { domain: { semantic_field: es_field } }。"""
    path = config_path or _DEFAULT_MAPPING_PATH
    if not path or not Path(path).exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_query_type(config_path: str | Path | None = None) -> Dict[str, Dict[str, str]]:
    """加载 configs/query_type.json，结构为 { domain: { semantic_field: "match"|"term"|"range" } }。"""
    path = config_path or _DEFAULT_QUERY_TYPE_PATH
    if not path or not Path(path).exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_es_field(domain: str, semantic_field: str, mapping: Dict[str, Dict[str, str]] | None = None) -> str | None:
    """根据 domain 和语义 field 返回 ES 字段名；未知则返回 None。"""
    if mapping is None:
        mapping = load_field_mapping()
    domain_map = mapping.get(domain, {})
    return domain_map.get(semantic_field)


def get_query_type(
    domain: str,
    semantic_field: str,
    query_type_config: Dict[str, Dict[str, str]] | None = None,
) -> str:
    """根据 domain 和语义 field 返回搜索方式：match / term / range，缺省为 term。"""
    if query_type_config is None:
        query_type_config = load_query_type()
    domain_map = query_type_config.get(domain, {})
    return domain_map.get(semantic_field, "term")
