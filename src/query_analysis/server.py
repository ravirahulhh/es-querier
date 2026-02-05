"""
FastAPI 解析服务：POST /parse，请求体 { "query", "domain", "config_path"? }，响应可观测 JSON。
若 configs/pipeline.json 中 use_llm=true（或请求传入 config_path），则使用 LLM 分析替代 NER 与规则匹配。
当配置了 es.url 且 execute_es=true 时，会访问 ES 执行查询并将搜索结果放入 response。
GET / 提供简易测试页面，便于填写请求并查看解析结果。
"""
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from query_analysis import parse
from query_analysis.es_client import search_es
from query_analysis.llm_analyzer import load_pipeline_config

app = FastAPI(title="Query Analysis", description="影视/图书垂类搜索意图解析 POC")

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/", include_in_schema=False)
def serve_test_page():
    """返回简易测试页面，便于填写 query/domain 并查看解析结果。"""
    index = _STATIC_DIR / "index.html"
    if not index.exists():
        return {"message": "Test page not found. Run from installed package."}
    return FileResponse(index)


class ParseRequest(BaseModel):
    query: str = Field(..., description="用户查询")
    domain: Literal["video", "book"] = Field(default="video", description="垂类")
    config_path: Optional[str] = Field(default=None, description="可选，pipeline 配置文件路径，用于启用 LLM 等")
    execute_es: bool = Field(default=True, description="是否执行 ES 查询并返回搜索结果（需配置 es.url）")


class ParseResponse(BaseModel):
    raw_query: str
    normalized: str | None = None
    constraints: list[dict[str, Any]]
    final_es_query: dict[str, Any]
    dropped_constraints: list[dict[str, Any]]
    conflict: bool
    entities: list[dict[str, Any]] | None = None
    search_results: list[dict[str, Any]] | None = None
    search_total: int | None = None
    es_error: str | None = None
    error: str | None = None  # 解析/LLM 等错误时填入，便于测试页展示


def _run_es_if_configured(domain: Literal["video", "book"], final_es_query: dict, config_path: Optional[str]) -> dict:
    """若 pipeline 配置了 es.url 则执行查询，返回 { hits, total, error }。"""
    config = load_pipeline_config(config_path)
    es_cfg = config.get("es") or {}
    url = (es_cfg.get("url") or "").strip()
    if not url:
        return {"hits": None, "total": None, "error": None}
    indices = es_cfg.get("indices")
    size = int(es_cfg.get("size", 10))
    out = search_es(
        domain,
        final_es_query,
        url=url,
        indices=indices,
        size=size,
    )
    return out


def _parse_error_message(exc: Exception) -> str:
    """将解析/LLM 异常转为用户可读说明。"""
    msg = str(exc).strip()
    if "401" in msg or "Unauthorized" in msg:
        return (
            "LLM 调用失败: API 返回 401（密钥无效或已失效）。"
            "若已在 configs/pipeline.json 中填写了 llm.api_key 或 llm.api_key_env 的密钥，可能是该密钥已被 OpenRouter 撤销（例如曾提交到仓库）。"
            "请到 https://openrouter.ai/keys 重新创建密钥，然后用环境变量传入：在 config 中设置 \"api_key_env\": \"OPENROUTER_API_KEY\"，启动服务前执行 export OPENROUTER_API_KEY=你的新密钥。"
        )
    if "429" in msg or "rate limit" in msg.lower():
        return "LLM 调用失败: 请求过于频繁 (429)，请稍后重试。"
    if "500" in msg or "502" in msg or "503" in msg:
        return f"LLM 服务暂时不可用: {msg}"
    return f"解析失败: {msg}"


@app.post("/parse", response_model=ParseResponse)
def api_parse(req: ParseRequest) -> ParseResponse:
    try:
        result = parse(
            req.query,
            domain=req.domain,
            include_debug=True,
            config_path=req.config_path,
        )
    except Exception as e:
        err_msg = _parse_error_message(e)
        return ParseResponse(
            raw_query=req.query,
            normalized=None,
            constraints=[],
            final_es_query={},
            dropped_constraints=[],
            conflict=False,
            entities=None,
            search_results=None,
            search_total=None,
            es_error=None,
            error=err_msg,
        )

    search_results = None
    search_total = None
    es_error = None
    if req.execute_es:
        es_out = _run_es_if_configured(req.domain, result["final_es_query"], req.config_path)
        if es_out.get("error"):
            es_error = es_out["error"]
            search_results = []
            search_total = 0
        elif es_out.get("hits") is not None:
            search_results = es_out["hits"]
            search_total = es_out.get("total", 0)

    return ParseResponse(
        raw_query=result["raw_query"],
        normalized=result.get("normalized"),
        constraints=result["constraints"],
        final_es_query=result["final_es_query"],
        dropped_constraints=result["dropped_constraints"],
        conflict=result["conflict"],
        entities=result.get("entities"),
        search_results=search_results,
        search_total=search_total,
        es_error=es_error,
        error=None,
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
