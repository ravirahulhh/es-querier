from query_analysis.dsl import Constraint, IntentDSL
from query_analysis.rewrite import DEFAULT_NEGATIVE_WEIGHT, QueryRewriter


def test_rewrite_negative_uses_function_score():
    """!= 使用 function_score + negative weight 降权，不放入 must_not。"""
    intent = IntentDSL(
        constraints=[
            Constraint("ip", "=", "西游记"),
            Constraint("release_year", "!=", 1986),
        ],
        raw_query="西游记 不是86版",
        domain="video",
    )
    rewriter = QueryRewriter()
    q, dropped = rewriter.rewrite(intent)
    assert not dropped
    assert "function_score" in q["query"]
    fs = q["query"]["function_score"]
    assert "query" in fs
    assert "must" in fs["query"]["bool"]
    must = fs["query"]["bool"]["must"]
    assert any("西游记" in str(c) for c in must)
    assert "functions" in fs
    assert any("1986" in str(fn.get("filter", {})) for fn in fs["functions"])
    assert all(fn.get("weight") == DEFAULT_NEGATIVE_WEIGHT for fn in fs["functions"])


def test_rewrite_fallback_when_empty():
    intent = IntentDSL(constraints=[], raw_query="随便", domain="video")
    rewriter = QueryRewriter()
    q, dropped = rewriter.rewrite(intent)
    assert "query_string" in str(q)
    assert "随便" in str(q)
