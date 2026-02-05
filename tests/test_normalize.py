import pytest
from query_analysis.normalize import normalize


def test_normalize_empty():
    assert normalize("") == ""
    assert normalize("   ") == ""


def test_normalize_fullwidth_to_half():
    assert "0" in normalize("０")
    assert normalize("ａｂｃ") == "abc"


def test_normalize_chinese_number():
    # cn2an: 八六 -> 86
    assert "86" in normalize("看西游记 不是八六版的")


def test_normalize_punctuation():
    assert normalize("  hello  world  ") == "hello world"
    assert normalize("hello,,,world") == "hello world"


def test_normalize_lowercase():
    assert normalize("ABC") == "abc"
