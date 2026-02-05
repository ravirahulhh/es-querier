"""
低置信度兜底：正则/短语匹配版本、年份、季数、集数等（如 \\d{2}版、\\d{4}年、第X季、X集）。
"""
import re
from typing import Any, Callable, List, Set, Tuple

from query_analysis.ner.base import Entity
from query_analysis.tokenize import Token

# 兜底规则：(pattern, field, value_fn)
# value_fn(match) -> value；若为 None 表示用 group(1)。
_FALLBACK_RULES: List[Tuple[re.Pattern, str, Callable[..., Any]]] = [
    (re.compile(r"(\d{2})版"), "release_year", lambda m: 1900 + int(m.group(1)) if int(m.group(1)) < 100 else int(m.group(1))),
    (re.compile(r"(\d{4})年"), "release_year", lambda m: int(m.group(1))),
    # 季数：第2季、2季（标准化后「第二季」→「第2季」或「2季」）
    (re.compile(r"第(\d+)季"), "season", lambda m: int(m.group(1))),
    (re.compile(r"(\d+)季"), "season", lambda m: int(m.group(1))),
    # 集数：第3集、3集
    (re.compile(r"第(\d+)集"), "episode", lambda m: int(m.group(1))),
    (re.compile(r"(\d+)集"), "episode", lambda m: int(m.group(1))),
    # 末尾单数字表季数，如「疯狂动物城2」→ season=2
    (re.compile(r"(?:^|[^\d])(\d)$"), "season", lambda m: int(m.group(1))),
]


def _span_contained_in(s: int, e: int, added: Set[Tuple[int, int]]) -> bool:
    """若 (s,e) 被某段已添加的 [s0,e0] 真包含则返回 True。"""
    for (s0, e0) in added:
        if s0 <= s and e <= e0 and (s0, e0) != (s, e):
            return True
    return False


def fallback_entities(query: str, tokens: List[Token]) -> List[Entity]:
    """
    对 query 做兜底规则匹配，返回 Entity 列表，source 由调用方标为 fallback。
    重叠 span 只保留较长者（如已有「第2季」则不再添加「2季」）。
    """
    entities: List[Entity] = []
    added_spans: Set[Tuple[int, int]] = set()
    for pattern, field, value_fn in _FALLBACK_RULES:
        for m in pattern.finditer(query):
            # 末尾单数字规则：span 取数字位，避免把前一字也算进去
            if field == "season" and pattern.pattern == r"(?:^|[^\d])(\d)$":
                start, end = m.start(1), m.end(1)
            else:
                start, end = m.start(), m.end()
            if _span_contained_in(start, end, added_spans):
                continue
            try:
                value = value_fn(m)
            except Exception:
                continue
            entities.append(Entity(
                span=(start, end),
                field=field,
                value=value,
                confidence=0.7,
                label="fallback",
            ))
            added_spans.add((start, end))
    return entities
