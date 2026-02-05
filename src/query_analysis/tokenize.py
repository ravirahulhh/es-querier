"""
4.2 分词：jieba 切分，输出带 (text, start, end) 的 token 列表。
"""
from dataclasses import dataclass
from typing import List

import jieba


@dataclass
class Token:
    """单个 token，含字符级 offset。"""
    text: str
    start: int
    end: int

    def __post_init__(self):
        if self.end < self.start:
            self.end = self.start + len(self.text)


def tokenize(query: str) -> List[Token]:
    """
    对 query 分词，返回 Token 列表，每项含 text、start、end（字符级 offset）。
    """
    if not query:
        return []
    # jieba.tokenize 返回 (word, start, end)
    gen = jieba.tokenize(query, mode="default")
    return [Token(text=w, start=s, end=e) for w, s, e in gen]
