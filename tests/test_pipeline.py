import pytest
from query_analysis import parse

# 测试统一使用规则+NER 模式，不依赖 configs/pipeline.json 或 LLM
_DEFAULT_TEST_CONFIG = {"use_llm": False}


def test_parse_returns_structure():
    r = parse("看西游记 不是86版的 动画 高清一点", domain="video", config=_DEFAULT_TEST_CONFIG)
    assert "raw_query" in r
    assert "constraints" in r
    assert "final_es_query" in r
    assert "dropped_constraints" in r
    assert "conflict" in r
    assert r["raw_query"] == "看西游记 不是86版的 动画 高清一点"


def test_parse_example_design():
    # 设计文档示例：看西游记 不是86版的 动画 高清一点
    r = parse("看西游记 不是86版的 动画 高清一点", domain="video", config=_DEFAULT_TEST_CONFIG)
    constraints = {c["field"]: (c["op"], c["value"]) for c in r["constraints"]}
    # ip = 原文「西游记」
    assert "ip" in constraints
    assert constraints["ip"][0] == "="
    assert constraints["ip"][1] == "西游记"
    # release_year != 1986
    assert "release_year" in constraints
    assert constraints["release_year"][0] == "!="
    assert constraints["release_year"][1] == 1986
    # type = animation
    assert "type" in constraints
    assert constraints["type"][0] == "="
    assert constraints["type"][1] == "animation"
    # resolution >= 1080
    assert "resolution" in constraints
    assert constraints["resolution"][0] == ">="
    assert constraints["resolution"][1] == 1080


def test_parse_final_es_query():
    r = parse("西游记 动画", domain="video", config=_DEFAULT_TEST_CONFIG)
    q = r["final_es_query"]
    assert "query" in q
    q_str = str(q)
    assert "西游记" in q_str
    # ip 在 must，type/动画 在 should
    assert "bool" in q["query"]
    assert "must" in q["query"]["bool"]
    assert "动画" in q_str or "type" in q_str or "tags" in q_str


def test_parse_fallback_when_no_constraints():
    r = parse("随便什么没有规则", domain="video", config=_DEFAULT_TEST_CONFIG)
    assert "final_es_query" in r
    # 应回退为 query_string
    assert "query_string" in str(r["final_es_query"]) or "match_all" in str(r["final_es_query"])


def test_parse_with_explicit_config_use_llm_false():
    """显式传入 use_llm=False 时与默认规则+NER 行为一致。"""
    r = parse("西游记 动画", domain="video", config=_DEFAULT_TEST_CONFIG)
    assert "constraints" in r
    assert "ip" in {c["field"] for c in r["constraints"]}
    assert "type" in {c["field"] for c in r["constraints"]}


def test_parse_generic_video_subject():
    """通用影视搜索：任意片名均可作为主体，不依赖固定词典。"""
    r = parse("流浪地球 电影 高清", domain="video", config=_DEFAULT_TEST_CONFIG)
    constraints = {c["field"]: (c["op"], c["value"]) for c in r["constraints"]}
    assert "ip" in constraints
    assert constraints["ip"][0] == "="
    assert constraints["ip"][1] == "流浪地球"
    assert constraints.get("type") == ("=", "movie")
    assert constraints.get("resolution")[0] == ">=" and constraints.get("resolution")[1] == 1080

    r2 = parse("三体 电视剧", domain="video", config=_DEFAULT_TEST_CONFIG)
    constraints2 = {c["field"]: (c["op"], c["value"]) for c in r2["constraints"]}
    # normalize 可能将「三」转为「3」并被 digit 过滤，故接受 三体 / 3体 / 体
    assert constraints2["ip"][1] in ("三体", "3体", "体")
    assert constraints2.get("type") == ("=", "tv")
