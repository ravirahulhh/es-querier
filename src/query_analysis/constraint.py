"""
4.6 约束构建 + 4.7 约束规范化。
"""
from typing import Any, Dict, List, Tuple

from query_analysis.dsl import Constraint


def build_constraints(
    ner_constraints: List[Constraint],
    rule_constraints: List[Constraint],
) -> List[Constraint]:
    """
    合并 NER + 规则约束。同 field 多源保留全部；规则优先于 NER（冲突时以规则为准）。
    """
    by_key: Dict[Tuple[str, str, Any], Constraint] = {}
    rule_by_field: Dict[str, Constraint] = {}
    for c in rule_constraints:
        key = (c.field, c.op, _norm_value(c.value))
        by_key[key] = c
        rule_by_field[c.field] = c
    for c in ner_constraints:
        key = (c.field, c.op, _norm_value(c.value))
        if c.field in rule_by_field:
            # 规则已存在该 field：以规则为准，不覆盖
            continue
        if key not in by_key:
            by_key[key] = c
    return list(by_key.values())


def _norm_value(v: Any) -> Any:
    """用于去重比较的值规范化。"""
    if isinstance(v, list):
        return tuple(sorted(v))
    return v


def normalize_constraints(constraints: List[Constraint]) -> Tuple[List[Constraint], bool]:
    """
    约束规范化：
    - 同一 (field, op, value) 去重
    - 同一 field 多个 =：value 同合并，不同标记冲突并丢弃该 field 全部约束
    - 同一 field 逻辑不可满足（如 year>2010 且 year<2000）：该 field 整体丢弃，conflict=True
    返回 (规范化后的约束列表, 是否发生冲突)。
    """
    if not constraints:
        return [], False
    conflict = False
    # 按 field 分组
    by_field: Dict[str, List[Constraint]] = {}
    for c in constraints:
        by_field.setdefault(c.field, []).append(c)
    result: List[Constraint] = []
    for field_name, group in by_field.items():
        deduped = _dedupe_same_constraints(group)
        # 检查同一 field 多个 = 是否 value 不同
        eq_constraints = [c for c in deduped if c.op == "="]
        if len(eq_constraints) >= 2:
            values = {_norm_value(c.value) for c in eq_constraints}
            if len(values) > 1:
                conflict = True
                continue  # 丢弃该 field
        # 检查 range 逻辑冲突：同一 field 既有 >/>= 又有 </<= 且区间不交
        if _has_range_conflict(deduped):
            conflict = True
            continue
        result.extend(deduped)
    return result, conflict


def _dedupe_same_constraints(group: List[Constraint]) -> List[Constraint]:
    """同一 (field, op, value) 只保留一条。"""
    seen: set = set()
    out: List[Constraint] = []
    for c in group:
        key = (c.field, c.op, _norm_value(c.value))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _has_range_conflict(constraints: List[Constraint]) -> bool:
    """同一 field 是否存在不可满足的 range（如 year>2010 且 year<2000）。"""
    lower_bound = None  # (op, value) for >= or >
    upper_bound = None  # (op, value) for <= or <
    for c in constraints:
        if c.op in (">", ">="):
            try:
                v = float(c.value) if isinstance(c.value, (int, float)) else None
                if v is not None:
                    if lower_bound is None or v > lower_bound[1]:
                        lower_bound = (c.op, v)
            except (TypeError, ValueError):
                pass
        elif c.op in ("<", "<="):
            try:
                v = float(c.value) if isinstance(c.value, (int, float)) else None
                if v is not None:
                    if upper_bound is None or v < upper_bound[1]:
                        upper_bound = (c.op, v)
            except (TypeError, ValueError):
                pass
    if lower_bound is None or upper_bound is None:
        return False
    low_val = lower_bound[1]
    up_val = upper_bound[1]
    if low_val > up_val:
        return True
    if low_val == up_val and (lower_bound[0] == ">" or upper_bound[0] == "<"):
        return True
    return False
