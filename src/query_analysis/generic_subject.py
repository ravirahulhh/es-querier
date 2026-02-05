"""
通用主体抽取：将「未被规则覆盖的实质性 token」视为搜索主体（ip），支持任意影视/书名等。
不依赖固定词典，实现通用垂类搜索。
"""
from typing import List, Optional, Set, Tuple

from query_analysis.dsl import Constraint
from query_analysis.rules.negation import NEGATION_WORDS
from query_analysis.tokenize import Token

# 不作为主体词的停用词（可配置扩展）
STOPWORDS: Set[str] = {
    "看", "要", "的", "了", "是", "不", "没", "没有", "别", "一点", "什么",
    "啊", "呢", "吗", "吧", "怎么", "可以", "能", "给", "在", "有", "我", "你",
    "他", "她", "它", "这个", "那个", "怎么", "怎样", "哪个", "随便", "规则",
    "点", "一",  # 避免「一点」「高清一点」混入主体；仅「一」作量词停用，保留「三体」等片名
}


def _spans_from_rules(rule_constraints: List[Constraint]) -> List[Tuple[int, int]]:
    """从规则约束中收集已覆盖的 span。"""
    out: List[Tuple[int, int]] = []
    for c in rule_constraints:
        span = getattr(c, "_span", None)
        if span is not None:
            out.append(span)
    return out


def _spans_from_phrases(query: str, phrases: Tuple[str, ...]) -> List[Tuple[int, int]]:
    """在 query 中查找短语出现位置，返回 (start, end) 列表。"""
    out: List[Tuple[int, int]] = []
    for w in phrases:
        start = 0
        while True:
            idx = query.find(w, start)
            if idx < 0:
                break
            out.append((idx, idx + len(w)))
            start = idx + 1
    return out


def _overlaps(span: Tuple[int, int], covered: List[Tuple[int, int]]) -> bool:
    """token 的 (start, end) 是否与任一已覆盖 span 相交。"""
    s, e = span
    for a, b in covered:
        if not (e <= a or s >= b):
            return True
    return False


def get_generic_subject_constraint(
    query: str,
    tokens: List[Token],
    rule_constraints: List[Constraint],
    existing_ner_has_ip: bool,
    ner_constraints: Optional[List[Constraint]] = None,
    stopwords: Optional[Set[str]] = None,
    min_length: int = 1,
) -> Optional[Constraint]:
    """
    当 NER 未提供 ip 时，将「未被规则/NER/否定词覆盖的实质性 token」拼接成主体，产出 field=ip 的约束。

    - 已覆盖 span：规则约束的 _span + NER/fallback 约束的 _span + 否定词在 query 中的出现位置
    - 剩余 token：不与上述 span 重叠，且 text 不在 stopwords，长度 >= min_length
    - 主体 = 剩余 token 按 offset 顺序拼接（中文无空格）
    """
    if existing_ner_has_ip or not tokens:
        return None
    stop = stopwords if stopwords is not None else STOPWORDS
    covered: List[Tuple[int, int]] = _spans_from_rules(rule_constraints)
    if ner_constraints:
        covered.extend(_spans_from_rules(ner_constraints))
    covered.extend(_spans_from_phrases(query, NEGATION_WORDS))

    remaining: List[Token] = []
    for t in tokens:
        if _overlaps((t.start, t.end), covered):
            continue
        if t.text in stop:
            continue
        if len(t.text.strip()) < min_length:
            continue
        # 纯数字不作为主体词（避免「86」「1」「3」混入；「三体」经 normalize 变「3体」时仅保留「体」可接受）
        if t.text.isdigit():
            continue
        remaining.append(t)
    if not remaining:
        return None
    # 按 offset 排序后拼接
    remaining.sort(key=lambda x: x.start)
    subject = "".join(t.text for t in remaining).strip()
    if not subject:
        return None
    span_start = remaining[0].start
    span_end = remaining[-1].end
    c = Constraint(field="ip", op="=", value=subject, source="generic_subject", confidence=0.85)
    setattr(c, "_span", (span_start, span_end))
    return c
