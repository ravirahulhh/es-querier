"""
4.4.2 短语规则表：从 config 加载 phrase -> { field, value, op? }，在 query 中匹配并产出 Constraint。
"""
import json
from pathlib import Path
from typing import Any, Dict, List

from query_analysis.dsl import Constraint
from query_analysis.tokenize import Token

# 默认配置路径：项目根 configs/（可被覆盖）
# __file__: .../src/query_analysis/rules/phrase_table.py -> parents[2]=src
_ROOT = Path(__file__).resolve().parents[2].parent
_DEFAULT_CONFIG = _ROOT / "configs" / "phrase_rules.json"


class PhraseTable:
    """短语 -> Constraint 映射表；匹配时返回带 span 信息的约束（供否定规则使用）。"""

    def __init__(self, config_path: str | Path | None = None):
        path = config_path or _DEFAULT_CONFIG
        self._rules: Dict[str, Dict[str, Any]] = {}
        if path and Path(path).exists():
            with open(path, "r", encoding="utf-8") as f:
                self._rules = json.load(f)
        # 按长度降序，优先长匹配
        self._sorted_phrases = sorted(self._rules.keys(), key=len, reverse=True)

    def match(self, query: str, tokens: List[Token]) -> List[Constraint]:
        """
        在 query 中匹配短语，返回 Constraint 列表。
        每个 constraint 不携带 span；span 由 phrase 在 query 中的出现位置推断（用于否定作用域）。
        """
        result: List[Constraint] = []
        used_start_end: set = set()  # (start, end) 已匹配，避免重叠
        for phrase in self._sorted_phrases:
            rule = self._rules.get(phrase)
            if not rule:
                continue
            start = 0
            while True:
                idx = query.find(phrase, start)
                if idx < 0:
                    break
                end = idx + len(phrase)
                if (idx, end) in used_start_end:
                    start = end
                    continue
                field = rule.get("field")
                value = rule.get("value")
                op = rule.get("op", "=")
                if field is not None and value is not None:
                    c = Constraint(field=field, op=op, value=value, source="rule")
                    # 附加 span 供 negation 使用
                    setattr(c, "_span", (idx, end))
                    result.append(c)
                    used_start_end.add((idx, end))
                start = end
        return result
