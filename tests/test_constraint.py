from query_analysis.dsl import Constraint
from query_analysis.constraint import build_constraints, normalize_constraints


def test_build_constraints_rule_overrides_ner():
    ner = [Constraint("type", "=", "movie", source="ner")]
    rule = [Constraint("type", "=", "animation", source="rule")]
    out = build_constraints(ner, rule)
    # 规则优先，应只有 animation
    types = [c for c in out if c.field == "type"]
    assert len(types) == 1
    assert types[0].value == "animation"


def test_normalize_conflict_same_field_different_eq():
    c1 = Constraint("year", "=", 2010, source="ner")
    c2 = Constraint("year", "=", 2000, source="rule")
    out, conflict = normalize_constraints([c1, c2])
    assert conflict is True
    assert not any(c.field == "year" for c in out)


def test_normalize_dedup():
    c1 = Constraint("type", "=", "movie", source="ner")
    c2 = Constraint("type", "=", "movie", source="rule")
    out, conflict = normalize_constraints([c1, c2])
    assert conflict is False
    types = [c for c in out if c.field == "type"]
    assert len(types) == 1
