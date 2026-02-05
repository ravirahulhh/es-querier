"""
4.8 Intent DSL：统一中间态结构（constraints + raw_query + domain）。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Union

# 语义 field 名
Domain = Literal["video", "book"]

# 约束操作符
ConstraintOp = Literal["=", "!=", ">", "<", ">=", "<=", "in", "boost"]


@dataclass
class Constraint:
    """单条约束：field、op、value；可选 source、confidence。"""
    field: str
    op: str  # =, !=, >, <, >=, <=, in, boost
    value: Any
    source: Optional[str] = None   # "ner" | "rule" | "fallback"
    confidence: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"field": self.field, "op": self.op, "value": self.value}
        if self.source is not None:
            d["source"] = self.source
        if self.confidence is not None:
            d["confidence"] = self.confidence
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Constraint":
        return cls(
            field=d["field"],
            op=d["op"],
            value=d["value"],
            source=d.get("source"),
            confidence=d.get("confidence"),
        )


@dataclass
class IntentDSL:
    """统一中间态：constraints、raw_query、domain；可选调试字段。"""
    constraints: List[Constraint]
    raw_query: str
    domain: Domain = "video"
    conflict: bool = False
    dropped_constraints: List[Dict[str, Any]] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "constraints": [c.to_dict() for c in self.constraints],
            "raw_query": self.raw_query,
            "domain": self.domain,
            "conflict": self.conflict,
            "dropped_constraints": self.dropped_constraints,
            "entities": self.entities,
        }
