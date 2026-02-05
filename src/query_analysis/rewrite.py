"""
4.9 Query Rewrite：根据 Intent DSL + Field Mapping + Query Type 生成 ES/OpenSearch bool query。
搜索方式可配置：match（全文）、term（强匹配）、range（范围）。
"""
from typing import Any, Dict, List, Tuple

from query_analysis.dsl import Constraint, IntentDSL
from query_analysis.mapping import (
    get_es_field,
    get_query_type,
    load_field_mapping,
    load_query_type,
)


# 用于 function_score 的负向权重：匹配 "!=" 的文档得分乘以此值（降权，不硬排除）
DEFAULT_NEGATIVE_WEIGHT = 0.1


class QueryRewriter:
    """将 constraints 转为 ES bool query；!= 用 function_score + 负向权重降权，不用 must_not。"""

    def __init__(
        self,
        mapping: Dict[str, Dict[str, str]] | None = None,
        query_type_config: Dict[str, Dict[str, str]] | None = None,
        negative_weight: float = DEFAULT_NEGATIVE_WEIGHT,
    ):
        self._mapping = mapping or load_field_mapping()
        self._query_type = query_type_config if query_type_config is not None else load_query_type()
        self._negative_weight = negative_weight

    def rewrite(self, intent: IntentDSL) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        返回 (final_es_query, dropped_constraints)。
        仅 ip 放入 must（强制）；其余约束放入 should（加分项）。"!=" 用 function_score 负向权重降权。
        """
        dropped: List[Dict[str, Any]] = []
        must_clauses: List[Dict[str, Any]] = []
        should_clauses: List[Dict[str, Any]] = []
        negative_filters: List[Dict[str, Any]] = []

        domain = intent.domain
        for c in intent.constraints:
            es_field = get_es_field(domain, c.field, self._mapping)
            if es_field is None:
                dropped.append({**c.to_dict(), "reason": "unknown_field"})
                continue
            qtype = get_query_type(domain, c.field, self._query_type)
            clause = _constraint_to_es_clause(es_field, c, qtype)
            if clause is None:
                dropped.append({**c.to_dict(), "reason": "type_mismatch"})
                continue
            if c.op == "!=":
                negative_filters.append(clause)
            else:
                if c.field == "ip":
                    must_clauses.append(clause)
                else:
                    should_clauses.append(clause)

        if not must_clauses and not should_clauses and not negative_filters:
            query = {
                "query": {
                    "query_string": {"query": intent.raw_query or "*"}
                }
            }
        else:
            bool_query: Dict[str, Any] = {}
            if must_clauses:
                bool_query["must"] = must_clauses
            if should_clauses:
                bool_query["should"] = should_clauses
                # should 仅作加分，不要求至少匹配数
                bool_query.setdefault("minimum_should_match", 0)
            if not bool_query:
                inner_query: Dict[str, Any] = {"query_string": {"query": intent.raw_query or "*"}}
            else:
                inner_query = {"bool": bool_query}

            if negative_filters:
                query = {
                    "query": {
                        "function_score": {
                            "query": inner_query,
                            "functions": [
                                {"filter": f, "weight": self._negative_weight}
                                for f in negative_filters
                            ],
                            "score_mode": "multiply",
                            "boost_mode": "multiply",
                        }
                    }
                }
            else:
                query = {"query": inner_query}

        return query, dropped


def _constraint_to_es_clause(es_field: str, c: Constraint, query_type: str = "term") -> Dict[str, Any] | None:
    """单条约束转为 ES 子句；query_type: match（全文）/ term（强匹配）/ range（支持范围）；类型不匹配返回 None。"""
    op, value = c.op, c.value

    # 范围比较：仅当配置为 range 或 op 本身是范围符时走 range
    if op in (">", ">=", "<", "<="):
        try:
            num = int(value) if isinstance(value, (int, float)) else int(value)
        except (TypeError, ValueError):
            return None
        if op == ">=":
            range_op = {"gte": num}
        elif op == ">":
            range_op = {"gt": num}
        elif op == "<=":
            range_op = {"lte": num}
        else:
            range_op = {"lt": num}
        return {"range": {es_field: range_op}}

    if op == "in":
        if not isinstance(value, list):
            return None
        if query_type == "match":
            # 多值全文：用 bool should 多个 match
            return {"bool": {"should": [{"match": {es_field: v}} for v in value], "minimum_should_match": 1}}
        return {"terms": {es_field: value}}

    if op == "=" or op == "!=":
        if query_type == "match":
            # 全文匹配：value 应为字符串
            if isinstance(value, (list, dict)):
                return None
            return {"match": {es_field: value if isinstance(value, str) else str(value)}}
        if query_type == "range":
            # 等/不等用 term（精确年份或数值）
            try:
                num = int(value) if isinstance(value, (int, float)) else int(value)
            except (TypeError, ValueError):
                return None
            return {"term": {es_field: num}}
        # term 强匹配
        return {"term": {es_field: value}}

    return None
