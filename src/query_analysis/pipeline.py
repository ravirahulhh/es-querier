"""
主 Pipeline 编排：Normalize → Tokenize → (NER + Rule Match) 或 LLM 分析 → Constraint Builder → Normalizer → Intent DSL → Query Rewrite.
若配置 use_llm=true，则使用 LLM 分析替代 NER 与规则匹配。
"""
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from query_analysis.normalize import normalize
from query_analysis.tokenize import tokenize, Token
from query_analysis.dsl import Constraint, IntentDSL, Domain
from query_analysis.constraint import build_constraints, normalize_constraints
from query_analysis.generic_subject import get_generic_subject_constraint
from query_analysis.llm_analyzer import load_pipeline_config, analyze as llm_analyze


def _default_pipeline(
    domain: Domain,
    *,
    config: Optional[Dict[str, Any]] = None,
    config_path: Optional[Union[str, Path]] = None,
) -> "Pipeline":
    """构建默认 Pipeline。若配置 use_llm=true 则使用 LLM 分析替代 NER/规则。"""
    from query_analysis.rules.phrase_table import PhraseTable
    from query_analysis.rules.negation import NegationRule
    from query_analysis.ner.dummy import DummyNER
    from query_analysis.ner.composite import CompositeNER
    from query_analysis.rewrite import QueryRewriter

    if config is None:
        config = load_pipeline_config(config_path)
    use_llm = config.get("use_llm", False)

    p = Pipeline(domain=domain, config=config, config_path=config_path)
    p._use_llm = use_llm
    p._rewrite = QueryRewriter()
    if use_llm:
        p._ner = None
        p._phrase_table = None
        p._negation = None
    else:
        p._phrase_table = PhraseTable()
        p._negation = NegationRule()
        p._ner = CompositeNER(DummyNER())
    return p


def parse(
    raw_query: str,
    domain: Domain = "video",
    *,
    include_debug: bool = True,
    config: Optional[Dict[str, Any]] = None,
    config_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    解析查询，返回可观测结构（含 constraints、final_es_query、raw_query 等）。
    若 config 或 configs/pipeline.json 中 use_llm=true，则使用 LLM 分析替代 NER 与规则匹配。
    """
    pipeline = _default_pipeline(domain, config=config, config_path=config_path)
    return pipeline.run(raw_query, include_debug=include_debug)


class Pipeline:
    """解析 Pipeline，可注入 NER、规则表等。若 use_llm 则用 LLM 分析替代 NER + 规则。"""

    def __init__(
        self,
        domain: Domain = "video",
        *,
        config: Optional[Dict[str, Any]] = None,
        config_path: Optional[Union[str, Path]] = None,
    ):
        self.domain = domain
        self._config = config
        self._config_path = config_path
        self._ner = None   # 延迟注入
        self._phrase_table = None
        self._negation = None
        self._rewrite = None
        self._use_llm = False

    def run(self, raw_query: str, *, include_debug: bool = True) -> Dict[str, Any]:
        normalized = normalize(raw_query or "")
        tokens: List[Token] = tokenize(normalized)

        ner_constraints: List[Constraint] = []
        rule_constraints: List[Constraint] = []
        entities: List[Dict[str, Any]] = []

        if getattr(self, "_use_llm", False):
            # LLM 分析替代 NER + 规则匹配
            ner_constraints, entities = llm_analyze(
                normalized,
                self.domain,
                config=self._config,
                config_path=self._config_path,
            )
        else:
            # NER（占位：无实现时返回 []）
            if self._ner is not None:
                entities_raw = self._ner.extract(normalized, tokens)
                entities = [_entity_to_dict(e) for e in entities_raw]
                ner_constraints = _entities_to_constraints(entities_raw)

            # 规则匹配（短语）
            if self._phrase_table is not None:
                rule_constraints = self._phrase_table.match(normalized, tokens)

            # 通用主体：当 NER 未提供 ip 时，用「未被规则覆盖的实质性 token」作为搜索主体
            has_ip = any(c.field == "ip" for c in ner_constraints)
            generic = get_generic_subject_constraint(
                normalized, tokens, rule_constraints, existing_ner_has_ip=has_ip, ner_constraints=ner_constraints
            )
            if generic is not None:
                ner_constraints = list(ner_constraints) + [generic]

            # 否定：作用于紧跟其后的一个实体或短语（合并 NER + 规则 span 后统一处理）
            all_with_span = ner_constraints + rule_constraints
            if self._negation is not None and all_with_span:
                all_with_span = self._negation.apply(all_with_span, normalized, tokens)
                ner_constraints = [c for c in all_with_span if getattr(c, "source", None) in ("ner", "fallback", "generic_subject")]
                rule_constraints = [c for c in all_with_span if getattr(c, "source", None) == "rule"]

        # 约束构建与规范化
        constraints = build_constraints(ner_constraints, rule_constraints)
        constraints, conflict = normalize_constraints(constraints)

        intent = IntentDSL(
            constraints=constraints,
            raw_query=raw_query or "",
            domain=self.domain,
            conflict=conflict,
            entities=entities,
        )

        # Query Rewrite
        final_es_query: Dict[str, Any] = {}
        dropped_constraints: List[Dict[str, Any]] = []
        if self._rewrite is not None:
            final_es_query, dropped_constraints = self._rewrite.rewrite(intent)
            intent.dropped_constraints = dropped_constraints
        else:
            # 占位：无 rewrite 时仅结构
            final_es_query = {"query": {"match_all": {}}}

        out: Dict[str, Any] = {
            "raw_query": raw_query,
            "constraints": [c.to_dict() for c in intent.constraints],
            "final_es_query": final_es_query,
            "dropped_constraints": intent.dropped_constraints,
            "conflict": intent.conflict,
        }
        if include_debug:
            out["normalized"] = normalized
            out["entities"] = intent.entities
        return out


def _entity_to_dict(e: Any) -> Dict[str, Any]:
    if hasattr(e, "__dict__"):
        return {k: v for k, v in vars(e).items() if not k.startswith("_")}
    return {"span": getattr(e, "span", ()), "field": getattr(e, "field", ""), "value": getattr(e, "value", None)}


def _entities_to_constraints(entities: List[Any]) -> List[Constraint]:
    out: List[Constraint] = []
    for e in entities:
        field = getattr(e, "field", None)
        value = getattr(e, "value", None)
        confidence = getattr(e, "confidence", None)
        span = getattr(e, "span", None)
        source = "fallback" if getattr(e, "label", None) == "fallback" else "ner"
        if field is not None and value is not None:
            c = Constraint(field=field, op="=", value=value, source=source, confidence=confidence)
            if span is not None:
                setattr(c, "_span", span)
            out.append(c)
    return out
