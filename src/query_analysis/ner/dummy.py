"""
占位 NER：不识别具体实体，返回空列表。
主体（ip/书名）由 pipeline 的「通用主体抽取」根据剩余 token 统一产出，从而支持任意影视/书名，无需维护词典。
"""
from typing import List

from query_analysis.ner.base import NERBase, Entity
from query_analysis.tokenize import Token


class DummyNER(NERBase):
    """占位实现：不依赖词典，返回空。与 generic_subject 配合实现通用垂类搜索。"""

    def extract(self, query: str, tokens: List[Token]) -> List[Entity]:
        return []
