"""
LLM 分析：当配置启用时替代 NER + 规则匹配，从用户查询中直接抽取约束（field/op/value）。
要求 OpenAI 兼容 API（POST /chat/completions），可选依赖：pip install httpx
"""
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from query_analysis.dsl import Constraint
from query_analysis.mapping import load_field_mapping

Domain = Literal["video", "book"]

_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_PIPELINE_CONFIG = _ROOT / "configs" / "pipeline.json"
_DEFAULT_TAGS_PATH = _ROOT / "tags.ele"

# 资源类型（视频）枚举，用于 prompt
VIDEO_TYPE_VALUES = ("电影", "动画片", "电视剧", "综艺", "小说")


def load_pipeline_config(config_path: str | Path | None = None) -> Dict[str, Any]:
    """加载 configs/pipeline.json。若不存在或无效则返回 use_llm=False 的默认配置。"""
    path = config_path or _DEFAULT_PIPELINE_CONFIG
    if not path or not Path(path).exists():
        return {"use_llm": False, "llm": {}, "es": {}}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "use_llm": data.get("use_llm", False),
        "llm": data.get("llm", {}),
        "es": data.get("es", {}),
    }


def load_tags(tags_path: str | Path | None = None) -> List[str]:
    """加载 tags.ele 中的标签列表，每行一个或多个逗号分隔的标签，合并去重后返回。"""
    path = tags_path or _DEFAULT_TAGS_PATH
    if not path or not Path(path).exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        tags: List[str] = []
        for line in f:
            for part in line.strip().split(","):
                t = part.strip()
                if t and t not in tags:
                    tags.append(t)
        return tags


def _get_llm_client():
    try:
        import httpx
        return httpx
    except ImportError:
        raise ImportError(
            "LLM 分析需要 httpx。请安装: pip install httpx 或 pip install query-analysis[llm]"
        ) from None


def _build_prompt(normalized: str, domain: Domain) -> str:
    mapping = load_field_mapping()
    domain_map = mapping.get(domain, {})
    fields_desc = ", ".join(f"{k} ({v})" for k, v in domain_map.items()) if domain_map else ""

    # 视频领域：补充语义说明与枚举
    field_meaning = ""
    if domain == "video":
        field_meaning = """
语义字段说明（field 请用英文）:
- ip: 名称/片名/剧名，value 为字符串
- actor: 演员，value 为字符串
- director: 导演，value 为字符串
- release_year: 时间/年份，value 为数字（如 2020）
- type: 资源类型，value 必须为以下之一: 电影, 动画片, 电视剧, 综艺, 小说
- tags: 标签，value 为字符串（单个标签）或数组（多个标签时用 op "in"）；标签请从下方允许的标签中选取或用户原意相近的词语
"""
        tags_list = load_tags()
        if tags_list:
            field_meaning += f"\n允许的标签参考（可从中选取或使用用户说的近义词）: {', '.join(tags_list)}\n"

    return f"""你是一个影视/图书垂类搜索的查询解析器。从用户查询中抽取结构化约束。

领域(domain): {domain}
允许的语义字段及对应 ES 字段: {fields_desc}
{field_meaning}
操作符: =（等于）, !=（不等于）, >, <, >=, <=, in（多值属于，value 为数组时使用）

请仅输出一个 JSON 数组，每项为 {{ "field": "字段名", "op": "操作符", "value": 值 }}。
- value 可以是字符串、数字、布尔或数组（多选时用 op "in" 且 value 为数组）。
- 若用户明确否定某条件（如「不要老版」「不是86版」），用 op "!=" 和对应 value。
- 主体/片名/剧名 用 field "ip"，value 为提取出的名称字符串。
- 不要输出解释，只输出 JSON 数组。

用户查询(已标准化): {normalized}

JSON 数组:"""


def _parse_llm_response(text: str) -> List[Dict[str, Any]]:
    """从 LLM 回复中解析 JSON 数组；兼容被 markdown 代码块包裹的情况。"""
    text = text.strip()
    # 去掉可能的 markdown 代码块
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()
    # 找第一个 [ 到最后一个 ] 的区间
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        arr = json.loads(text[start : end + 1])
        if not isinstance(arr, list):
            return []
        return arr
    except json.JSONDecodeError:
        return []


def analyze(
    normalized: str,
    domain: Domain,
    *,
    config: Optional[Dict[str, Any]] = None,
    config_path: str | Path | None = None,
) -> Tuple[List[Constraint], List[Dict[str, Any]]]:
    """
    使用 LLM 从标准化查询中抽取约束，替代 NER + 规则匹配。
    返回 (constraints, entities_for_debug)。
    """
    if config is None:
        config = load_pipeline_config(config_path)
    llm_cfg = config.get("llm") or {}
    api_base = (llm_cfg.get("api_base") or "https://api.openai.com/v1").rstrip("/")
    api_key_env_name = llm_cfg.get("api_key_env") or "OPENAI_API_KEY"
    model = llm_cfg.get("model") or "gpt-4o-mini"
    # API Key 来源（按优先级）：1）llm.api_key  2）llm.api_key_env 若以 sk- 开头则视为密钥  3）环境变量 api_key_env  4）OpenRouter 时再试 OPENROUTER_API_KEY
    api_key = (llm_cfg.get("api_key") or "").strip()
    if not api_key and api_key_env_name.startswith(("sk-", "sk_")):
        api_key = api_key_env_name.strip()  # 兼容：密钥直接写在 api_key_env
    if not api_key:
        api_key = (os.environ.get(api_key_env_name) or "").strip()
    if not api_key and "openrouter" in api_base.lower():
        api_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        raise ValueError(
            f"LLM 分析需要 API Key。请在 configs/pipeline.json 的 llm 下设置 api_key，或设置 api_key_env 为环境变量名（如 OPENROUTER_API_KEY）后 export 该变量。"
        )

    prompt = _build_prompt(normalized, domain)
    httpx = _get_llm_client()

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{api_base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    items = _parse_llm_response(content)

    constraints: List[Constraint] = []
    entities: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        op = item.get("op", "=")
        value = item.get("value")
        if field is None or value is None:
            continue
        c = Constraint(field=str(field), op=str(op), value=value, source="llm", confidence=0.9)
        constraints.append(c)
        entities.append({"field": field, "op": op, "value": value, "source": "llm"})
    return constraints, entities
