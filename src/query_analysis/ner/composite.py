"""
组合 NER：先跑主 NER，再对低置信度或未覆盖 span 做兜底（如 \\d{2}版、\\d{4}年）。
"""
from typing import List

from query_analysis.ner.base import NERBase, Entity
from query_analysis.ner.fallback import fallback_entities
from query_analysis.tokenize import Token

CONFIDENCE_THRESHOLD = 0.6


class CompositeNER(NERBase):
    """主 NER + 兜底：主 NER 低置信度实体不产出，由兜底规则补充版本/年份等。"""

    def __init__(self, primary: NERBase, confidence_threshold: float = CONFIDENCE_THRESHOLD):
        self.primary = primary
        self.theta = confidence_threshold

    def extract(self, query: str, tokens: List[Token]) -> List[Entity]:
        primary_entities = self.primary.extract(query, tokens)
        fallback = fallback_entities(query, tokens)

        # 高置信度主 NER 实体保留
        result: List[Entity] = [e for e in primary_entities if e.confidence >= self.theta]

        # 兜底：仅当主 NER 未覆盖该 span 时加入（避免重复）
        covered = {(e.span[0], e.span[1]) for e in result}
        for e in fallback:
            if (e.span[0], e.span[1]) not in covered:
                result.append(e)
                covered.add((e.span[0], e.span[1]))

        return result
