"""
NER 抽象接口：输入 (query, tokens)，输出 Entity 列表。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Tuple

from query_analysis.tokenize import Token


@dataclass
class Entity:
    """单个实体：span、field、value、confidence、label。"""
    span: Tuple[int, int]  # (start, end) 字符级
    field: str
    value: any
    confidence: float = 1.0
    label: str = ""


class NERBase(ABC):
    @abstractmethod
    def extract(self, query: str, tokens: List[Token]) -> List[Entity]:
        """从 query 和 tokens 中抽取实体。"""
        pass
