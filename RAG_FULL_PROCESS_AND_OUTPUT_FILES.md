# 网页 RAG 全流程逻辑与阶段结果保存位置

本文档面向以网页为知识源的 RAG 系统，描述从 URL 管理、网页采集、正文解析、清洗切分，到混合检索、答案生成和引用返回的完整流程，并标注每个阶段的结果保存位置。

> 重要说明：项目当前已有 SQLite、Qdrant、切分、检索和生成能力，但现有入库代码仍以 Git 数据源为主，尚未发现网页抓取器和 HTML 正文解析器。本文将网页采集部分标为“待实现的目标目录”，将已经存在的存储位置标为“当前已有”，避免把设计目标误写成已落地能力。

## 1. 全流程概览

```text
离线网页知识库构建
种子 URL / Sitemap
  → URL 规范化与去重
  → robots.txt、域名白名单与访问频率检查
  → 下载网页 HTML
  → 保存原始响应与采集元数据
  → 提取正文、标题、目录与链接
  → 清洗、去重、语言识别
  → 按标题与语义边界切分 Chunk
  → 生成 Embedding
  → 写入 SQLite 全文索引和 Qdrant 向量索引
  → 发布网页知识库快照

在线问答
用户问题
  → 问题预处理与过滤条件
  → 问题向量化
  → 向量检索 + 关键词检索
  → RRF 融合、去重与排序
  → 构建带来源 URL 的证据上下文
  → LLM 生成答案
  → 引用校验
  → 返回答案、网页标题、URL 和引用片段
```

## 2. 建议的数据目录

以下目录均以项目根目录 `E:\RAG-Project` 为基准。

```text
data/
├─ web/
│  ├─ seeds/                  # 种子 URL、Sitemap 和域名规则
│  ├─ crawl_runs/             # 每次采集任务的清单与统计
│  ├─ raw_html/               # 网页原始 HTML 或响应体
│  ├─ extracted/              # 提取后的网页正文和结构化元数据
│  ├─ cleaned/                # 清洗、去重后的标准文档
│  └─ failed/                 # 下载或解析失败记录
├─ sqlite/
│  └─ rag.db                  # 元数据、Chunk 和 FTS5 全文索引
├─ logs/                      # API、采集器、Worker、Qdrant 日志
└─ run/                       # PID 等运行状态文件
```

其中：

- `data/sqlite/rag.db`、`data/logs/` 和 `data/run/` 当前已经存在。
- `data/web/` 是为网页 RAG 建议新增的目标目录，当前项目尚未实现自动写入。
- 向量数据由 Qdrant 管理，当前本机实际位于 `D:\application\qdrant\storage\`。

## 3. 保存位置速查

| 阶段结果 | 建议或实际保存位置 | 当前状态 |
|---|---|---|
| 种子 URL | `data/web/seeds/urls.txt` | 待新增 |
| Sitemap 解析结果 | `data/web/seeds/sitemap_urls.jsonl` | 待新增 |
| 域名、路径与采集策略 | `data/web/seeds/crawl_config.yaml` | 待新增 |
| 单次采集 URL 清单 | `data/web/crawl_runs/{run_id}/manifest.jsonl` | 待新增 |
| 单次采集统计 | `data/web/crawl_runs/{run_id}/summary.json` | 待新增 |
| 原始 HTML | `data/web/raw_html/{source_id}/{content_hash}.html` | 待新增 |
| HTTP 响应元数据 | `data/web/raw_html/{source_id}/{content_hash}.meta.json` | 待新增 |
| 提取后的正文 | `data/web/extracted/{source_id}/{document_id}.json` | 待新增 |
| 清洗后的标准文档 | `data/web/cleaned/{source_id}/{document_id}.json` | 待新增 |
| 失败记录 | `data/web/failed/{run_id}.jsonl` | 待新增 |
| 网页、任务、快照、Chunk、全文索引 | `data/sqlite/rag.db` | 当前已有数据库，需扩展网页字段 |
| Chunk 向量 | `D:\application\qdrant\storage\` | 当前已有 |
| 最终答案 | HTTP/CLI 响应，默认不落盘 | 当前行为 |
| 服务运行日志 | `data/logs/*.log` | 当前已有 |

文件名中的含义：

- `run_id`：一次完整采集任务的唯一 ID。
- `source_id`：网页知识源 ID，通常对应一个站点或业务域。
- `document_id`：规范化 URL 的稳定哈希。
- `content_hash`：响应正文的 SHA-256，用于版本判断和内容去重。

## 4. 离线网页知识库构建

### 阶段 1：配置网页知识源

配置种子 URL、Sitemap、允许域名、允许或排除的路径、最大抓取深度、请求超时、并发数和限速策略。

示例：

```yaml
source_id: product_docs
seed_urls:
  - https://docs.example.com/
allowed_domains:
  - docs.example.com
include_paths:
  - /guide/
  - /reference/
exclude_paths:
  - /login
  - /search
max_depth: 3
requests_per_second: 1
```

- 阶段结果：网页源配置和初始 URL 列表
- 建议保存：`data/web/seeds/crawl_config.yaml`、`data/web/seeds/urls.txt`
- 数据库建议：`data/sqlite/rag.db` → 新增 `web_sources` 表
- 当前状态：尚未实现网页源配置表

### 阶段 2：发现、规范化并去重 URL

从种子页、Sitemap 与页面链接中发现 URL。移除 `#fragment`，统一主机名大小写和结尾斜杠，删除无业务意义的跟踪参数，并阻止跳出允许域名。

需要在规范化前确认业务参数。例如 `?page=2` 可能代表不同内容，不能像 `utm_source` 一样直接删除。

- 阶段结果：规范化 URL、来源页面、抓取深度和发现时间
- Sitemap 结果：`data/web/seeds/sitemap_urls.jsonl`
- 本次任务清单：`data/web/crawl_runs/{run_id}/manifest.jsonl`
- 数据库建议：新增 `web_urls` 表，保存 URL 状态和最后采集时间
- 当前状态：待实现

### 阶段 3：合规与访问控制检查

抓取前检查 `robots.txt`、域名白名单和请求速率。需要登录、验证码、明确禁止自动访问或包含个人敏感信息的页面，应按站点授权策略处理。

- 阶段结果：URL 是否允许采集、拒绝原因和下次允许访问时间
- 建议保存：更新 `data/web/crawl_runs/{run_id}/manifest.jsonl`
- 站点 robots 快照建议：`data/web/raw_html/{source_id}/robots.txt`
- 当前状态：待实现

### 阶段 4：下载网页

请求网页并记录最终 URL、状态码、Content-Type、字符集、响应头、重定向链、ETag、Last-Modified、下载时间和正文哈希。

对依赖 JavaScript 渲染的页面，应使用浏览器渲染后的 DOM；普通静态页面优先直接请求，成本更低、结果更稳定。

- 原始 HTML：`data/web/raw_html/{source_id}/{content_hash}.html`
- 响应元数据：`data/web/raw_html/{source_id}/{content_hash}.meta.json`
- 失败记录：`data/web/failed/{run_id}.jsonl`
- 阶段结果：可复现的原始网页快照
- 当前状态：待实现

响应元数据建议至少包含：

```json
{
  "source_id": "product_docs",
  "requested_url": "https://docs.example.com/guide/start",
  "canonical_url": "https://docs.example.com/guide/start",
  "status_code": 200,
  "content_type": "text/html",
  "fetched_at": "2026-08-13T00:00:00+08:00",
  "etag": null,
  "last_modified": null,
  "content_hash": "sha256..."
}
```

### 阶段 5：解析网页并提取正文

从 HTML 中提取标题、正文、标题层级、列表、表格、代码块、发布日期和 canonical URL，移除导航栏、页脚、侧边栏、Cookie 弹窗、广告与脚本。

- 阶段结果：结构化网页文档
- 建议保存：`data/web/extracted/{source_id}/{document_id}.json`
- 建议字段：`url`、`canonical_url`、`title`、`headings`、`content`、`published_at`、`fetched_at`、`outgoing_links`
- 当前状态：待实现

### 阶段 6：清洗、标准化与去重

统一空白符和编码，保留标题层级、表格语义与代码块；计算正文哈希，删除完全重复内容，并识别站点模板导致的近重复页面。

如果正文哈希未变化，可复用旧索引，避免重复 Embedding。

- 阶段结果：可切分的标准网页文档
- 建议保存：`data/web/cleaned/{source_id}/{document_id}.json`
- 网页文档元数据建议保存：`data/sqlite/rag.db` → 新增 `web_documents` 表
- 当前状态：清洗文件和网页表待实现

### 阶段 7：网页文档切分

优先按 `H1/H2/H3` 标题、段落、列表、表格和代码块切分；超长章节再按 Token 预算二次切分，并保留少量重叠。每个 Chunk 必须继承网页来源信息。

建议每个 Chunk 至少包含：

- `chunk_id`
- `source_id`
- `document_id`
- `url` 与 `canonical_url`
- 网页标题与章节路径
- 正文、语言和 Token 数
- 抓取时间、发布时间和内容哈希

- 阶段结果：Chunk 列表
- 持久化位置：`data/sqlite/rag.db` → `chunks`、`chunks_fts`
- 当前适配点：`src/rag/ingestion/chunkers/structured.py`
- 当前差距：现有 Chunk 模型主要使用 `repo_id`、`commit_sha`、`path`、行号；应改为或扩展为 `source_id`、`document_id`、URL 和章节锚点

### 阶段 8：生成文档向量

将网页标题、章节路径、URL 提示信息与 Chunk 正文组合成 `embedding_text`，批量调用 Embedding 服务。

推荐格式：

```text
[source] product_docs
[title] 快速开始
[section] 安装 > Windows
[url] https://docs.example.com/guide/start#windows

Chunk 正文……
```

- 阶段结果：每个 Chunk 对应的浮点向量
- 生成时：仅在进程内存中
- 最终保存：`D:\application\qdrant\storage\` 中对应的 collection
- SQLite 保存 `embedding_text`，不保存浮点向量
- 当前状态：Embedding 与 Qdrant 写入能力已有，需将 payload 改为网页元数据

### 阶段 9：建立混合索引

每个网页源或索引快照建立独立 Qdrant collection；同时把标题、章节和正文写入 SQLite FTS5，支持精确术语与语义混合检索。

推荐不可变 collection 命名：

```text
web_{source_id}__snap_{snapshot_id}
```

- 向量：`D:\application\qdrant\storage\`
- Chunk 正文与元数据：`data/sqlite/rag.db` → `chunks`
- 关键词索引：`data/sqlite/rag.db` → `chunks_fts`
- 当前实现位置：`src/rag/infrastructure/qdrant_store.py`、`sqlite_store.py`
- 当前差距：现有 collection 命名仍为 `repo_{repo_id}__...`

### 阶段 10：发布网页索引快照

索引成功后在 SQLite 事务中把新快照标记为 `published`、旧快照标记为 `superseded`。
查询根据该状态直接访问对应 collection；失败时保持旧索引可用。

- 发布状态与统计：`data/sqlite/rag.db` → `snapshots`
- 采集任务统计：`data/web/crawl_runs/{run_id}/summary.json`
- Qdrant collection：由 `D:\application\qdrant\storage\` 管理
- 当前状态：快照发布机制已有，但语义仍偏 Git，需改为网页源版本

统计建议包含：

```json
{
  "discovered_urls": 0,
  "fetched_pages": 0,
  "unchanged_pages": 0,
  "failed_pages": 0,
  "skipped_pages": 0,
  "documents": 0,
  "chunks": 0
}
```

## 5. 在线检索与生成

### 阶段 11：接收用户问题

接收问题以及可选的网页源、域名、URL 前缀、语言和时间过滤条件。

- 阶段结果：查询请求与过滤条件
- 保存位置：默认仅在请求内存中
- 当前入口：`src/rag/api/query_routes.py`
- 当前差距：现有过滤条件使用 `repo_ids` 和 `path_prefixes`，网页模式建议使用 `source_ids`、`domains` 和 `url_prefixes`

### 阶段 12：查询预处理

对问题进行去噪、对话补全和必要的查询改写。只有在复杂问题中才需要拆分子查询；简单问题直接检索即可。

- 阶段结果：标准查询或多个子查询
- 保存位置：仅在内存中
- 当前状态：基础查询直接进入 Embedding，尚无独立查询改写模块

### 阶段 13：问题向量化

调用与入库一致的 Embedding 模型生成问题向量。

- 阶段结果：查询向量
- 保存位置：仅在内存中
- 当前代码：`src/rag/infrastructure/llama_client.py`

### 阶段 14：混合召回

并行执行：

1. Qdrant 语义检索，寻找含义相近的网页 Chunk。
2. SQLite FTS5 关键词检索，匹配产品名、错误码、参数名和精确术语。

- 读取向量：`D:\application\qdrant\storage\`
- 读取关键词索引：`data/sqlite/rag.db` → `chunks_fts`、`chunks`
- 阶段结果：稠密候选与关键词候选
- 保存位置：仅在内存中
- 当前代码：`src/rag/application/query_service.py`

### 阶段 15：融合、去重与排序

使用 RRF 融合两路结果，按正文哈希去重，限制同一网页或同一章节占用的候选数量；如后续加入 Reranker，可在此阶段执行精排。

- 阶段结果：最终候选 Chunk
- 保存位置：仅在内存中
- 当前代码：`src/rag/retrieval/fusion.py`
- 当前状态：已有 RRF 和多样化；尚无独立 Reranker

### 阶段 16：构建网页证据上下文

为每个候选分配 `[E1]`、`[E2]` 等证据 ID，并把标题、URL、章节和正文组织为上下文。网页引用应优先使用 canonical URL，并在需要时添加章节锚点。

推荐证据格式：

```xml
<evidence id="E1"
          title="快速开始"
          url="https://docs.example.com/guide/start#windows"
          fetched_at="2026-08-13T00:00:00+08:00">
网页正文片段……
</evidence>
```

- 阶段结果：`context` 和 `evidence_map`
- 保存位置：仅在内存中
- 当前代码：`src/rag/retrieval/context_builder.py`
- 当前差距：证据结构目前使用仓库、文件路径、行号和 commit，应替换为网页标题、URL、章节锚点和采集时间

### 阶段 17：构建 Prompt

将系统提示词、用户问题和网页证据填入模板，要求模型只依据证据回答，并为关键事实附上 `[E#]`。

- 模板：`prompts/answer_system.txt`、`prompts/answer_context.txt`
- 本次实际 Prompt：仅在内存中
- 当前代码：`src/rag/generation/prompt_builder.py`
- 注意：`config/default.yaml` 中 `security.log_prompts: false`，默认不记录 Prompt

### 阶段 18：生成答案与引用校验

LLM 返回答案后，系统校验每个 `[E#]` 是否存在于 `evidence_map`，生成可点击的网页来源信息。无有效证据时，应明确说明资料不足，而不是补写无依据内容。

- 阶段结果：答案、可信度、引用、快照 ID 和耗时
- 保存位置：默认仅在内存中
- 当前代码：`src/rag/generation/citation_validator.py`、`query_service.py`
- 当前差距：引用模型现在返回仓库、commit、路径和行号；网页模式应返回 `title`、`url`、`section`、`snippet` 和 `fetched_at`

### 阶段 19：返回最终结果

网页 RAG 推荐返回：

```json
{
  "answer": "安装步骤如下……[E1]",
  "confidence": "medium",
  "citations": [
    {
      "id": "E1",
      "title": "快速开始",
      "url": "https://docs.example.com/guide/start#windows",
      "section": "安装 > Windows",
      "snippet": "……",
      "fetched_at": "2026-08-13T00:00:00+08:00"
    }
  ],
  "index_snapshots": ["..."],
  "timing_ms": {
    "retrieval": 0,
    "generation": 0,
    "total": 0
  }
}
```

- 输出位置：HTTP JSON 或 CLI 控制台
- 服务端保存位置：默认不保存
- API 日志：`data/logs/rag-api.stdout.log`、`data/logs/rag-api.stderr.log`
- 如需查询留档：建议新增 `query_runs` 表或写入脱敏后的 JSONL

## 6. 增量更新与网页删除

网页内容会变化，增量索引应基于 URL 和内容哈希处理：

| 检查结果 | 行为 | 保存结果 |
|---|---|---|
| 新 URL | 下载、解析、切分并建立索引 | 新网页快照、SQLite、Qdrant |
| URL 未变且内容哈希未变 | 更新检查时间，复用旧 Chunk 和向量 | `web_documents.last_checked_at` |
| URL 未变但内容变化 | 生成新版本并重建相关 Chunk | 原始 HTML、文档版本、SQLite、Qdrant |
| 301/308 | 记录重定向，更新 canonical URL | HTTP 元数据与 URL 映射 |
| 404/410 | 标记失效，发布新快照时移除其 Chunk | 网页状态和新索引快照 |
| 临时网络错误 | 保留旧索引并安排重试 | `data/web/failed/{run_id}.jsonl` |

不要因为一次超时或 5xx 响应立即删除旧知识；只有明确的永久失效或经过重试确认后才应停用网页。

## 7. 日志文件

| 文件 | 内容 |
|---|---|
| `data/logs/rag-api.stdout.log` | API 标准输出与应用日志 |
| `data/logs/rag-api.stderr.log` | API 错误输出 |
| `data/logs/rag-worker.stdout.log` | 索引 Worker 输出 |
| `data/logs/rag-worker.stderr.log` | 索引 Worker 错误 |
| `data/logs/qdrant.stdout.log` | Qdrant 标准输出 |
| `data/logs/qdrant.stderr.log` | Qdrant 错误输出 |
| `data/logs/web-crawler.stdout.log` | 建议新增：网页采集正常日志 |
| `data/logs/web-crawler.stderr.log` | 建议新增：网页采集错误日志 |

日志格式由 `config/logging.yaml` 定义。日志中不应写入登录 Cookie、Authorization、完整个人信息或未经脱敏的 Prompt。

## 8. 默认不会落盘的中间结果

以下结果默认只在内存中流转：

- 用户问题与问题向量
- 两路检索的原始候选列表
- RRF 融合后的中间排名
- 证据上下文与证据映射
- 本次请求实际 Prompt
- LLM 原始答案
- 引用校验前后的差异
- 最终 API 响应

原始 HTML、解析正文和清洗文档则建议落盘，因为它们能支持解析器调试、内容审计和离线重建索引。

## 9. 数据去向总结

```text
种子 URL / Sitemap
  └─ data/web/seeds/

网页原始响应
  ├─ HTML        → data/web/raw_html/{source_id}/
  ├─ HTTP 元数据 → data/web/raw_html/{source_id}/*.meta.json
  └─ 失败记录    → data/web/failed/{run_id}.jsonl

解析和清洗结果
  ├─ 提取正文 → data/web/extracted/{source_id}/
  └─ 标准文档 → data/web/cleaned/{source_id}/

索引结果
  ├─ 网页/Chunk 元数据及 FTS → data/sqlite/rag.db
  └─ Chunk 向量              → D:\application\qdrant\storage\

单次查询
  ├─ 问题、候选、上下文、Prompt → 内存
  └─ 答案和网页引用             → HTTP/CLI 响应，默认不落盘

运行状态
  └─ data/logs/*.log
```

## 10. 当前代码改造清单

要让项目完整支持上述网页 RAG，至少需要完成：

1. 新增网页源、URL 队列、HTTP 下载和失败重试模块。
2. 新增 HTML 正文与结构解析器，保存 raw、extracted 和 cleaned 三层数据。
3. 将领域模型中的 Git 字段扩展为通用来源字段，支持 URL、标题、章节和采集时间。
4. 为 SQLite 增加 `web_sources`、`web_urls`、`web_documents` 等表，或将现有表重构为通用数据源表。
5. 调整 Qdrant collection 命名与 payload，使其保存网页来源元数据。
6. 将检索过滤从仓库和文件路径改为网页源、域名和 URL 前缀。
7. 将上下文和引用输出改为网页标题、URL、章节、摘要和采集时间。
8. 增加基于 ETag、Last-Modified 和内容哈希的增量更新与失效页面处理。
9. 增加抓取合规、域名限制、限速、超时、最大响应大小和 SSRF 防护。

完成这些改造后，网页数据才能从采集到回答形成真正闭环，并且每个阶段都具备清晰、可审计、可恢复的结果文件。
