"""
4.4.1 否定规则：否定词只作用于紧跟其后的一个实体或短语，对应约束 op 改为 !=。
"""
import re
from typing import List

from query_analysis.dsl import Constraint
from query_analysis.tokenize import Token

NEGATION_WORDS = ("不是", "非", "不要", "排除", "不看")
# 标点/停用（用于判断“紧跟”）
_PUNCT_OR_STOP = re.compile(r"^[\s\.,，。、；：:]+$")


def _is_only_punct_or_stop(s: str) -> bool:
    """Empty or only whitespace/punctuation counts as 'tightly after' for negation scope."""
    if not s:
        return True
    return bool(_PUNCT_OR_STOP.match(s))


class NegationRule:
    """对规则约束应用否定：根据 query 中否定词位置，将紧跟其后的约束改为 !=。"""

    def __init__(self, negation_words: tuple = NEGATION_WORDS):
        self.negation_words = negation_words

    def apply(
        self,
        rule_constraints: List[Constraint],
        query: str,
        tokens: List[Token],
    ) -> List[Constraint]:
        """
        在 rule_constraints 中，找出被否定词修饰的项（紧跟否定词后的 span），将其 op 改为 !=。
        约束若带 _span 则用 _span，否则不参与否定（保留原样）。
        """
        if not query or not rule_constraints:
            return list(rule_constraints)

        # 收集所有否定词在 query 中的 (start, end)
        neg_spans: List[tuple] = []
        for w in self.negation_words:
            start = 0
            while True:
                idx = query.find(w, start)
                if idx < 0:
                    break
                neg_spans.append((idx, idx + len(w)))
                start = idx + 1

        # 收集所有约束的 span（带 _span 的）
        constraint_spans: List[tuple] = []
        for c in rule_constraints:
            span = getattr(c, "_span", None)
            if span is not None:
                constraint_spans.append(span)

        # 对每个否定词，找“紧跟其后”的第一个实体/短语 span
        negated_spans: set = set()
        for n_start, n_end in sorted(neg_spans):
            # 紧跟：下一个 span 与否定词之间无其他“非标点/停用”内容
            best_next: tuple | None = None
            best_dist = -1
            for span in constraint_spans:
                s_start, s_end = span
                if s_end <= n_end:
                    continue  # 在否定词左侧，不算
                if s_start < n_end:
                    continue  # 必须完全在否定词右侧，否则会误伤主体（如 西游记…一点 的整段 span）
                gap_start = n_end
                gap_end = s_start
                gap = query[gap_start:gap_end]
                if _is_only_punct_or_stop(gap):
                    dist = s_start - n_end
                    if best_dist < 0 or dist < best_dist:
                        best_dist = dist
                        best_next = span
            if best_next is not None:
                negated_spans.add(best_next)

        # 应用否定
        out: List[Constraint] = []
        for c in rule_constraints:
            span = getattr(c, "_span", None)
            if span in negated_spans:
                out.append(Constraint(
                    field=c.field,
                    op="!=",
                    value=c.value,
                    source=c.source,
                    confidence=c.confidence,
                ))
            else:
                out.append(c)
        return out
