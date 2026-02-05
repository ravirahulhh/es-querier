# Query Analysis（影视/图书垂类搜索意图解析 POC）

基于 [design.md](design.md) 的多规则意图解析与查询重写 Pipeline：Normalize → Tokenize → NER → Rule Match → Constraint Builder → Query Rewrite，输出统一 Intent DSL 与 ES/OpenSearch 查询。

## 环境：使用 venv

建议使用 Python 3.10+ 与 venv 管理依赖。

```bash
# 在项目根目录
cd query-analysis

# 创建虚拟环境（.venv）
python3 -m venv .venv

# 激活
# macOS/Linux:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate

# 安装依赖（可编辑安装，便于开发）
pip install -e ".[dev]"

# 或仅安装运行依赖
pip install -r requirements.txt
```

后续在项目目录下工作前先执行 `source .venv/bin/activate`（或 Windows 下激活脚本）。

## 测试

```bash
# 确保已激活 venv
pytest tests/
```

## 启动 HTTP 服务

```bash
# 从项目根执行，且 PYTHONPATH 包含 src
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)/src"
uvicorn query_analysis.server:app --host 0.0.0.0 --port 8000 --reload
```

或使用脚本（会自动 cd 到项目根并设置 PYTHONPATH）：

```bash
./scripts/serve.sh
```

启动时会自动从**项目根目录**的 `.env` 加载环境变量（如 `OPENROUTER_API_KEY`），无需再在终端 `export`。

**测试页面**：启动服务后请在浏览器中访问 **http://127.0.0.1:8000/** 或 **http://localhost:8000/** 打开简易测试页（不要使用 `http://0.0.0.0:8000/`，`0.0.0.0` 仅表示服务监听所有网卡，浏览器访问会报 502）。在测试页填写 query、选择 domain 后点击「解析」即可查看 constraints、final_es_query、search 等关键信息。

示例请求与响应：

**请求**（`POST /parse`）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | 是 | 用户查询 |
| domain | "video" \| "book" | 否 | 垂类，默认 "video" |
| config_path | string | 否 | 可选，pipeline 配置文件路径 |
| execute_es | boolean | 否 | 是否执行 ES 查询并返回搜索结果，默认 true（需在 pipeline.json 中配置 es.url） |

```bash
curl -X POST http://127.0.0.1:8000/parse \
  -H "Content-Type: application/json" \
  -d '{"query": "看西游记 不是86版的 动画 高清一点", "domain": "video", "execute_es": true}'
```

**响应示例**（含 ES 搜索结果时）：

```json
{
  "raw_query": "看西游记 不是86版的 动画 高清一点",
  "normalized": "看西游记 不是86版的 动画 高清一点",
  "constraints": [
    {"field": "ip", "op": "=", "value": "西游记", "source": "ner"},
    {"field": "type", "op": "=", "value": "animation", "source": "rule"},
    {"field": "resolution", "op": "=", "value": "hd", "source": "rule"}
  ],
  "final_es_query": {
    "query": {
      "bool": {
        "must": [
          {"match": {"title": "西游记"}},
          {"term": {"tags": "animation"}},
          {"term": {"resolution": "hd"}}
        ]
      }
    },
    "size": 10
  },
  "dropped_constraints": [],
  "conflict": false,
  "entities": [...],
  "search_results": [
    {"title": "西游记 动画版", "year": 1999, "tags": ["animation"], ...}
  ],
  "search_total": 42,
  "es_error": null
}
```

未配置 `es.url` 或 `execute_es: false` 时，`search_results`、`search_total` 为 `null`，`es_error` 为 `null`；ES 请求失败时 `es_error` 为错误信息，`search_results` 为空数组。

## 作为库 / CLI 使用

```python
from query_analysis import parse

result = parse("看西游记 不是86版的 动画 高清一点", domain="video")
# result["constraints"], result["final_es_query"], ...
```

```bash
python -m query_analysis "看西游记 不是86版的 动画 高清一点" --domain video
```

## 配置

- `configs/phrase_rules.json`：短语 → 约束映射（类型、清晰度等）
- `configs/field_mapping.json`：垂类 → ES 字段映射（video/book）
- `configs/pipeline.json`：Pipeline 开关、LLM 与 ES 配置（见下）

### 使用 LLM 分析替代 NER + 规则匹配

若在 `configs/pipeline.json` 中设置 `"use_llm": true`，则 Pipeline 将使用大模型从查询中直接抽取约束，替代 NER 与短语/否定规则。

1. 安装可选依赖：`pip install -e ".[llm]"`（或 `pip install httpx`）
2. 在 `configs/pipeline.json` 中配置：
   - `use_llm`: `true`
   - `llm.api_base`：OpenAI 兼容 API 地址（默认 `https://api.openai.com/v1`）
   - `llm.api_key_env`：环境变量名（如 `OPENROUTER_API_KEY`），或直接写以 `sk-` 开头的密钥（勿提交到仓库）
   - `llm.model`：模型名（默认 `gpt-4o-mini`）
3. 配置 API 密钥（二选一）：
   - **推荐：项目根目录建 `.env` 文件**（已加入 .gitignore，勿提交）：
     ```bash
     # 复制示例并填写
     cp .env.example .env
     # 编辑 .env，填入：
     OPENROUTER_API_KEY=sk-or-v1-你的密钥
     ```
   - 或启动前在终端设置：`export OPENROUTER_API_KEY=sk-or-v1-你的密钥`
   若曾在配置里写死密钥仍报 401，多为密钥已失效，请用上述方式并重新在 [OpenRouter Keys](https://openrouter.ai/keys) 创建密钥。
4. 调用方式不变：`parse("看西游记 动画 高清", domain="video")` 或 `POST /parse`；若需请求级指定配置，可传 `config_path` 或 `config` 覆盖。

HTTP 请求可传可选字段 `config_path` 指定 pipeline 配置文件路径。

### 执行 ES 查询并返回搜索结果

在 `configs/pipeline.json` 中配置 `es` 后，`POST /parse` 默认会访问 ES 执行 `final_es_query` 并将结果放入响应的 `search_results`、`search_total`：

```json
"es": {
  "url": "http://localhost:9200",
  "indices": { "video": "video", "book": "book" },
  "size": 10
}
```

- `url`：Elasticsearch/OpenSearch 地址（必填才执行查询）
- `indices`：按 domain 的索引名，不配则用 domain 名作为索引
- `size`：单次返回条数（默认 10，最大 100）

请求体中传 `"execute_es": false` 可仅做意图解析、不请求 ES。

## 交付物约定

- **库**：`from query_analysis import parse` / `Pipeline`
- **HTTP**：FastAPI `POST /parse`
- **CLI**：`python -m query_analysis "查询" --domain video`
- 热词动态更新本 POC 不做，后续可扩展。
