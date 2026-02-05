"""
4.9 Query Rewrite：根据 Intent DSL + Field Mapping + Query Type 生成 ES/OpenSearch bool query。
搜索方式可配置：match（全文）、term（强匹配）、range（范围）。
season/episode 在 0～100 范围内会扩展为数字与中文同义（如 2 → 2、"2"、"二"），便于匹配标题等文本。
"""
from typing import Any, Dict, List, Tuple, Union

from query_analysis.dsl import Constraint, IntentDSL
from query_analysis.mapping import (
    get_es_field,
    get_query_type,
    load_field_mapping,
    load_query_type,
)


# 用于 function_score 的负向权重：匹配 "!=" 的文档得分乘以此值（降权，不硬排除）
DEFAULT_NEGATIVE_WEIGHT = 0.1

# should 子句的 boost，作为明确的排序信号
SHOULD_BOOST = 5

# 0～100 数字同义词表：阿拉伯数字 → 中文形式，用于 season/episode 同义扩展
_NUM_TO_CN_0_100: Dict[int, str] = {}
try:
    import cn2an
    def _an2cn(n: int) -> str:
        if hasattr(cn2an, "an2cn"):
            return cn2an.an2cn(n)
        return cn2an.transform(str(n), "an2cn")
    for i in range(101):
        try:
            _NUM_TO_CN_0_100[i] = _an2cn(i)
        except Exception:
            _NUM_TO_CN_0_100[i] = str(i)
except Exception:
    # 无 cn2an 时使用简单映射：0-10 + 11-19 + 20,30,...,90 + 21-29,31-39,...,99 + 100
    _CN_DECADE = ("", "一", "二", "三", "四", "五", "六", "七", "八", "九")
    for i in range(101):
        if i == 0:
            _NUM_TO_CN_0_100[i] = "零"
        elif i < 10:
            _NUM_TO_CN_0_100[i] = _CN_DECADE[i]
        elif i == 10:
            _NUM_TO_CN_0_100[i] = "十"
        elif i < 20:
            _NUM_TO_CN_0_100[i] = "十" + _CN_DECADE[i - 10]
        elif i < 100:
            hi, lo = divmod(i, 10)
            _NUM_TO_CN_0_100[i] = _CN_DECADE[hi] + "十" + (_CN_DECADE[lo] if lo else "")
        else:
            _NUM_TO_CN_0_100[i] = "一百"


def _with_boost(clause: Dict[str, Any], boost: float) -> Dict[str, Any]:
    """将 boost 正确写入子句内部（ES 不允许 match/term 与 boost 并列）。"""
    if "match" in clause:
        # match: boost 必须在字段对象内 {"match": {"field": {"query": "...", "boost": 5}}}
        (field,) = clause["match"].keys()
        val = clause["match"][field]
        if isinstance(val, dict):
            inner = {**val, "boost": boost}
        else:
            inner = {"query": val, "boost": boost}
        return {"match": {field: inner}}
    if "term" in clause:
        # term: boost 必须在字段对象内 {"term": {"field": {"value": v, "boost": 5}}}
        (field,) = clause["term"].keys()
        val = clause["term"][field]
        if isinstance(val, dict):
            inner = {**val, "boost": boost}
        else:
            inner = {"value": val, "boost": boost}
        return {"term": {field: inner}}
    if "range" in clause:
        # range: boost 放在 range 的字段对象内
        (field,) = clause["range"].keys()
        inner = {**clause["range"][field], "boost": boost}
        return {"range": {field: inner}}
    if "bool" in clause:
        # bool 的 boost 必须写在 bool 对象内部，不能与 "bool" 并列
        return {"bool": {**clause["bool"], "boost": boost}}
    return {**clause, "boost": boost}


def get_number_synonyms(n: int) -> List[Union[int, str]]:
    """0～100 的整数返回同义形式列表：[数值, 数字串, 中文]，用于 season/episode 的 term 同义扩展。"""
    if not (0 <= n <= 100):
        return [n, str(n)]
    cn = _NUM_TO_CN_0_100.get(n, str(n))
    return [n, str(n), cn]


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
                bool_query["should"] = [_with_boost(clause, SHOULD_BOOST) for clause in should_clauses]
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
            return {"bool": {"should": [_with_boost({"match": {es_field: v}}, SHOULD_BOOST) for v in value], "minimum_should_match": 1}}
        return {"terms": {es_field: value}}

    if op == "=" or op == "!=":
        if query_type == "match":
            # 全文匹配：value 应为字符串
            if isinstance(value, (list, dict)):
                return None
            # season/episode 0～100：match 也做数字+中文同义展开（如 3 → "3" 与 "三"）
            if c.field in ("season", "episode"):
                try:
                    num = int(value) if isinstance(value, (int, float)) else int(value)
                except (TypeError, ValueError):
                    num = None
                if num is not None and 0 <= num <= 100:
                    synonyms = get_number_synonyms(num)
                    str_vals = list(dict.fromkeys(str(v) for v in synonyms))  # 去重且保持顺序
                    return {
                        "bool": {
                            "should": [_with_boost({"match": {es_field: s}}, SHOULD_BOOST) for s in str_vals],
                            "minimum_should_match": 1,
                        }
                    }
            # ip（片名）要求分词后全部命中，用 match operator=and
            match_query: Any = value if isinstance(value, str) else str(value)
            if c.field == "ip":
                match_query = {"query": match_query, "operator": "and"}
            return {"match": {es_field: match_query}}
        if query_type == "range":
            # 等/不等用 term（精确年份或数值）
            try:
                num = int(value) if isinstance(value, (int, float)) else int(value)
            except (TypeError, ValueError):
                return None
            return {"term": {es_field: num}}
        # term 强匹配；season/episode 在 0～100 时扩展为数字+中文同义
        if c.field in ("season", "episode"):
            try:
                num = int(value) if isinstance(value, (int, float)) else int(value)
            except (TypeError, ValueError):
                num = None
            if num is not None and 0 <= num <= 100:
                synonyms = get_number_synonyms(num)
                return {
                    "bool": {
                        "should": [_with_boost({"term": {es_field: v}}, SHOULD_BOOST) for v in synonyms],
                        "minimum_should_match": 1,
                    }
                }
        return {"term": {es_field: value}}

    return None
