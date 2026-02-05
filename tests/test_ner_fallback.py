"""Tests for NER fallback rules (release_year, season, episode)."""
import pytest

from query_analysis.ner.fallback import fallback_entities
from query_analysis.tokenize import Token


def _tokens_empty():
    return []


def test_fallback_season_episode():
    # 第2季、3集（标准化后「第二季」→「第2季」）
    entities = fallback_entities("向往的生活第2季3集", _tokens_empty())
    by_field = {e.field: e.value for e in entities}
    assert by_field.get("season") == 2
    assert by_field.get("episode") == 3


def test_fallback_season_only_trailing_digit():
    # 疯狂动物城2 → 末尾单数字表季数
    entities = fallback_entities("疯狂动物城2", _tokens_empty())
    seasons = [e for e in entities if e.field == "season"]
    assert len(seasons) == 1
    assert seasons[0].value == 2


def test_fallback_season_no_double_ji():
    # 第2季 与 2季 重叠时只保留一处
    entities = fallback_entities("某剧第2季", _tokens_empty())
    seasons = [e for e in entities if e.field == "season"]
    assert len(seasons) == 1
    assert seasons[0].value == 2
