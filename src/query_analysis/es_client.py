"""
Elasticsearch/OpenSearch 查询执行：根据 pipeline 生成的 final_es_query 请求 ES 并返回搜索结果。
配置来自 configs/pipeline.json 的 "es" 段（url、indices、size）。
"""
from typing import Any, Dict, List, Literal, Optional

Domain = Literal["video", "book"]


def _get_client(url: str):
    """延迟导入 Elasticsearch，避免无 ES 依赖时导入失败。"""
    try:
        from elasticsearch import Elasticsearch
    except ImportError:
        raise ImportError("需要安装 elasticsearch: pip install elasticsearch") from None
    return Elasticsearch(url)


class ESClient:
    """执行 ES 查询并返回 hits。"""

    def __init__(
        self,
        url: str,
        indices: Optional[Dict[str, str]] = None,
        *,
        size: int = 10,
        request_timeout: float = 10.0,
    ):
        self._url = url
        self._indices = indices or {"video": "video", "book": "book"}
        self._size = max(1, min(size, 100))
        self._timeout = request_timeout
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            self._client = _get_client(self._url)
        return self._client

    def search(
        self,
        domain: Domain,
        body: Dict[str, Any],
        *,
        size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        执行 ES 查询。body 为 final_es_query（含 query 等）。
        返回 { "hits": [...], "total": int, "error": None } 或 { "hits": [], "total": 0, "error": "..." }。
        """
        index = self._indices.get(domain, domain)
        size = size if size is not None else self._size
        # 注入 size，避免 ES 默认只返回 10 条
        search_body = dict(body)
        if "size" not in search_body:
            search_body["size"] = size
        try:
            client = self._ensure_client()
            # elasticsearch-py 8.x 使用 keyword 参数，不再用 body=
            resp = client.search(index=index, **search_body, request_timeout=self._timeout)
        except Exception as e:
            return {"hits": [], "total": 0, "error": str(e)}

        total = 0
        if "hits" in resp and "total" in resp["hits"]:
            t = resp["hits"]["total"]
            total = t if isinstance(t, int) else t.get("value", 0)
        hits = [h.get("_source", h) for h in resp.get("hits", {}).get("hits", [])]
        return {"hits": hits, "total": total, "error": None}


def search_es(
    domain: Domain,
    final_es_query: Dict[str, Any],
    *,
    url: str,
    indices: Optional[Dict[str, str]] = None,
    size: int = 10,
) -> Dict[str, Any]:
    """
    一次性执行 ES 查询，用于无长期持有 client 的场景。
    返回 { "hits", "total", "error" }。
    """
    client = ESClient(url=url, indices=indices, size=size)
    return client.search(domain, final_es_query, size=size)
