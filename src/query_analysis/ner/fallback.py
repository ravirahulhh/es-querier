"""
低置信度兜底：正则/短语匹配版本、年份等（如 \\d{2}版、\\d{4}年）。
"""
import re
from typing import Any, Callable, List, Tuple

from query_analysis.ner.base import Entity
from query_analysis.tokenize import Token

# 兜底规则：(pattern, field, value_fn)
# value_fn(match) -> value
_FALLBACK_RULES: List[Tuple[re.Pattern, str, Callable[..., Any]]] = [
    (re.compile(r"(\d{2})版"), "release_year", lambda m: 1900 + int(m.group(1)) if int(m.group(1)) < 100 else int(m.group(1))),
    (re.compile(r"(\d{4})年"), "release_year", lambda m: int(m.group(1))),
]


def fallback_entities(query: str, tokens: List[Token]) -> List[Entity]:
    """
    对 query 做兜底规则匹配，返回 Entity 列表，source 由调用方标为 fallback。
    """
    entities: List[Entity] = []
    for pattern, field, value_fn in _FALLBACK_RULES:
        for m in pattern.finditer(query):
            try:
                value = value_fn(m)
            except Exception:
                continue
            entities.append(Entity(
                span=(m.start(), m.end()),
                field=field,
                value=value,
                confidence=0.7,
                label="fallback",
            ))
    return entities
