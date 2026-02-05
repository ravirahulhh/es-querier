from query_analysis.dsl import Constraint, IntentDSL
from query_analysis.rewrite import (
    DEFAULT_NEGATIVE_WEIGHT,
    QueryRewriter,
    get_number_synonyms,
)


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


def test_number_synonyms_0_100():
    """0～100 返回 [数值, 数字串, 中文]；超出范围仅 [数值, 数字串]。"""
    syn = get_number_synonyms(2)
    assert 2 in syn
    assert "2" in syn
    assert "二" in syn
    syn3 = get_number_synonyms(3)
    assert "三" in syn3
    syn12 = get_number_synonyms(12)
    assert 12 in syn12 and "12" in syn12
    # 超出 100 不扩展中文
    syn101 = get_number_synonyms(101)
    assert syn101 == [101, "101"]


def test_rewrite_season_episode_synonym_expansion():
    """season/episode 在 0～100 时 ES 子句为 bool should（数字+中文同义）。"""
    intent = IntentDSL(
        constraints=[
            Constraint("season", "=", 2),
            Constraint("episode", "=", 3),
        ],
        raw_query="某剧第2季第3集",
        domain="video",
    )
    # 显式传入 mapping 与 query_type，避免依赖 config 文件是否加载到 season/episode
    rewriter = QueryRewriter(
        mapping={"video": {"season": "season", "episode": "episode"}},
        query_type_config={"video": {"season": "term", "episode": "term"}},
    )
    q, dropped = rewriter.rewrite(intent)
    assert not dropped
    should = q["query"]["bool"]["should"]
    # 同义展开后每个约束为 {"bool": {"should": [{"term": {...}}, ...], "minimum_should_match": 1}}
    bool_clauses = [c for c in should if isinstance(c, dict) and "bool" in c and "should" in c.get("bool", {})]
    assert len(bool_clauses) == 2
    all_values = []
    for clause in bool_clauses:
        terms = clause["bool"]["should"]
        for t in terms:
            val = list(t["term"].values())[0]
            all_values.append(val.get("value", val) if isinstance(val, dict) else val)
        assert clause["bool"]["minimum_should_match"] == 1
    assert 2 in all_values and "2" in all_values and "二" in all_values
    assert 3 in all_values and "3" in all_values and "三" in all_values


def test_rewrite_ip_match_uses_and_operator():
    """ip -> title 的 match 查询使用 operator=and。"""
    intent = IntentDSL(
        constraints=[Constraint("ip", "=", "向往的生活")],
        raw_query="向往的生活",
        domain="video",
    )
    rewriter = QueryRewriter()
    q, dropped = rewriter.rewrite(intent)
    assert not dropped
    must = q["query"]["bool"]["must"]
    # must 中 ip 的 match 子句应带 operator=and
    match_clause = next(c for c in must if "match" in c)
    title_query = match_clause["match"]["title"]
    assert isinstance(title_query, dict)
    assert title_query.get("query") == "向往的生活"
    assert title_query.get("operator") == "and"
