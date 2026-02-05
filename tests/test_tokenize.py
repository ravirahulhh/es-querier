import pytest
from query_analysis.tokenize import tokenize, Token


def test_tokenize_empty():
    assert tokenize("") == []


def test_tokenize_has_offsets():
    tokens = tokenize("看西游记")
    assert len(tokens) >= 1
    for t in tokens:
        assert isinstance(t, Token)
        assert t.text
        assert t.start >= 0 and t.end <= len("看西游记")
        assert t.end - t.start == len(t.text) or t.end >= t.start
