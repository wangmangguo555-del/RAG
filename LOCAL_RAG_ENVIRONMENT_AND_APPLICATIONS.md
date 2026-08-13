# 纯本地 Git 仓库 RAG——环境与应用安装清单

> 关联方案：[纯本地 Git 仓库 RAG 架构设计与开发方案](./LOCAL_RAG_ARCHITECTURE_AND_DEVELOPMENT_PLAN.md)  
> 文档定位：安装规划、环境准备、软件清单和验收基线  
> 适用平台：Windows 11 开发/单机运行，Ubuntu Server 稳定部署  
> 更新日期：2026-08-11

---

## 1. 执行摘要

本项目最小可运行环境由以下部分组成：

1. **Git**：读取和比较知识源仓库。
2. **Python 3.12 + uv**：运行 RAG API、索引 Worker、CLI、测试及依赖管理。
3. **两个 llama.cpp 服务实例**：一个用于回答生成，一个用于 Embedding；本项目直接复用已经跑通的实例。
4. **Qdrant**：保存和检索稠密向量；Windows 推荐通过 Docker Desktop/WSL2 运行。
5. **SQLite FTS5**：保存元数据、任务状态并提供关键词检索；随 Python 内置，无需安装独立数据库服务。
6. **Tree-sitter 及目标语言 grammar**：按照代码语法结构进行切分；作为 Python 依赖安装。
7. **FastAPI 运行环境**：提供查询、搜索、索引管理和健康检查接口；作为 Python 依赖安装。

不需要安装 Node.js、Java、Elasticsearch、Kafka、Kubernetes 或云端向量数据库。它们都不是首版依赖。

### 1.1 推荐的落地组合

| 使用场景 | 推荐组合 |
|---|---|
| 当前 Windows 开发机 | Windows 11 x64 + PowerShell 7 + Git + uv/Python 3.12 + 原生 llama.cpp + Docker Desktop/WSL2 中的 Qdrant |
| Windows 单机长期运行 | 上述组合 + WinSW/任务计划程序托管 API/Worker + Qdrant 命名卷 + 定期 snapshot |
| Linux 稳定部署 | Ubuntu Server 24.04 LTS x64 + Git + uv/Python 3.12 + llama.cpp + Docker Engine 中的 Qdrant + systemd |
| 严格离线环境 | 上述任一组合 + 离线 wheelhouse + Qdrant 镜像 tar + Git bundle/bare mirror + 模型/二进制 SHA-256 清单 |

---

## 2. 版本管理原则

文档不把“最新版本”当作生产要求。正式环境必须遵循：

- Python 固定到 `3.12.x` 的已验证补丁版本。
- `uv.lock` 提交到项目仓库，生产使用 `uv sync --frozen`。
- Qdrant 使用明确的稳定 tag，并进一步记录容器 image digest；禁止使用 `latest` 部署。
- 两个 llama.cpp 服务记录同一套构建版本或 Git commit、编译后端和启动参数。
- GGUF 模型文件记录 SHA-256、上下文长度、量化类型和用途。
- Tree-sitter runtime 与各语言 grammar 一起锁定版本并做解析回归测试。
- 任一 Embedding 模型、文档/query 前缀、归一化或向量维度变化都视为索引不兼容，必须建立新 collection。

建议建立 `VERSIONS.md` 或制品清单：

```yaml
build_date: 2026-08-11
python: 3.12.x
uv: <exact-version>
git: <exact-version>
llama_cpp:
  version_or_commit: <value>
  backend: cuda|vulkan|metal|cpu
qdrant:
  image: qdrant/qdrant:<pinned-tag>
  digest: sha256:<digest>
models:
  llm:
    file: <llm-model>.gguf
    sha256: <sha256>
  embedding:
    file: <embedding-model>.gguf
    sha256: <sha256>
```

---

## 3. 硬件环境

### 3.1 最低、推荐与扩展规格

以下容量不含模型自身的特殊要求；现有 llama.cpp 能正常运行只是最低前提。最终以目标仓库实测为准。

| 资源 | 开发/PoC | 推荐单机 | 较大仓库/多人使用 | 主要影响 |
|---|---:|---:|---:|---|
| CPU | 4 核 x64 | 8～16 核 x64 | 16～32 核 x64 | Git 扫描、解析、FTS、API 并发 |
| 内存 | 16 GB | 32 GB | 64 GB+ | 模型常驻、Qdrant HNSW、文件批处理 |
| GPU | 可选；已有模型可运行即可 | NVIDIA 12～24 GB VRAM 或现有可用后端 | 24 GB+ 或双 GPU | 生成、Embedding 吞吐和首 token 时延 |
| 系统盘 | 20 GB 可用 | 40 GB 可用 | 80 GB+ 可用 | OS、Python、容器运行时、临时文件 |
| 数据盘 | 50 GB NVMe | 200 GB+ NVMe | 500 GB+ NVMe | 模型、仓库、Qdrant、备份和新旧索引并存 |
| 网络 | 无要求 | 仅本机/内网 | 千兆内网 | 远程 Git 同步或局域网 API；推理不需要外网 |

### 3.2 磁盘规划

建议将程序与数据分离：

```text
E:\RAG-Project\          # 源码、配置模板、uv.lock、测试
E:\RAG-Data\
├─ models\               # GGUF 模型
├─ repos\                # 工作树、bare mirror 或 Git bundle 导入结果
├─ sqlite\               # rag.db、WAL
├─ qdrant\               # 若使用宿主目录挂载；Windows 更推荐 Docker named volume
├─ cache\                 # embedding cache、下载/解析临时缓存
├─ logs\
├─ backups\
└─ tmp\
```

容量估算：

```text
raw_vector_bytes = chunk_count × embedding_dimension × 4
数据盘规划值 >= 模型文件 + 仓库 + 完整索引实测值 × 2.5 + 备份保留量
```

`× 2.5` 用于覆盖 published collection、待发布 collection、回滚版本和构建临时空间，不是 Qdrant 的固定放大率。

### 3.3 GPU 与驱动

由于 llama.cpp 已经跑通，首版不应主动更换 GPU 软件栈。只需记录当前状态：

- GPU 型号和 VRAM。
- 驱动版本。
- llama.cpp 后端：CUDA、Vulkan、ROCm、Metal 或 CPU。
- 两个服务的 `--n-gpu-layers`、context、batch、threads 和并发参数。

条件性安装：

| 软件 | 是否需要 | 作用 |
|---|---|---|
| NVIDIA Display Driver | 使用 NVIDIA GPU 时必需 | 提供 GPU 运行时和设备访问 |
| CUDA Toolkit | 仅从源码构建 CUDA 版 llama.cpp 时需要 | 编译工具链；使用已编译二进制通常无需单独安装完整 Toolkit |
| Vulkan Runtime/SDK | Vulkan 版 llama.cpp 按发行包说明安装 | GPU 计算后端；SDK 通常只在编译时需要 |
| ROCm | AMD GPU 且使用 HIP/ROCm 后端时需要 | AMD GPU 推理支持；须按操作系统与硬件兼容矩阵确认 |

不要同时升级 GPU 驱动、llama.cpp 和模型后再排查性能；一次只变更一层并保留回滚制品。

---

## 4. 操作系统与基础环境

### 4.1 Windows 基线

推荐：

- Windows 11 64-bit，仍处于微软支持周期内。
- NTFS 数据盘；启用长路径支持，避免深层仓库路径失败。
- PowerShell 7.x 作为脚本与运维终端。
- BIOS/UEFI 开启虚拟化；使用 Docker Desktop 时启用 WSL2。
- 时间同步和正确时区，用于 job、日志和 snapshot 时间关联。

Windows 开发机中，Python API/Worker 与 llama.cpp 原生运行；Qdrant 运行在 Docker Desktop 的 Linux 容器中。该边界最容易维护，也避免在 Python 进程内嵌向量库造成生产并发限制。

### 4.2 Linux 基线

推荐：

- Ubuntu Server 24.04 LTS 64-bit，最小化安装。
- `systemd` 管理 `rag-api`、`rag-worker` 和 llama.cpp 实例。
- Docker Engine/Compose Plugin 管理 Qdrant 单节点容器。
- 数据目录使用 ext4 或 XFS，并启用定期 snapshot/备份。
- 以专用非 root 账号 `rag` 运行应用服务。

### 4.3 文件系统与权限

建议权限边界：

| 目录 | `rag-api` | `rag-worker` | llama.cpp | Qdrant |
|---|---|---|---|---|
| 模型目录 | 无需或只读 | 无需 | 只读 | 无需 |
| 源仓库目录 | 无需直接访问 | 只读 | 无需 | 无需 |
| SQLite | 读写 | 读写 | 无需 | 无需 |
| Qdrant 数据 | 无需直接访问 | 无需直接访问 | 无需 | 读写 |
| prompt/config | 只读 | 只读 | 启动配置只读 | 配置只读 |
| 日志 | 读写 | 读写 | 读写 | 读写 |

Worker 不应拥有源仓库写权限，也不应执行仓库中的 hook、脚本或安装命令。

---

## 5. 必须安装或确认的应用

### 5.1 总清单

| 应用/环境 | 级别 | 部署位置 | 项目作用 | 端口 | 备注 |
|---|---|---|---|---:|---|
| Git | 必需 | 宿主机 | 解析 ref/commit/tree/blob，计算增删改，离线 bundle/mirror | 无 | 建议 2.40+，固定实测版本 |
| Python 3.12 x64 | 必需 | 宿主机 | 运行 API、Worker、CLI、测试和迁移 | 无 | 建议由 uv 管理，不依赖系统 Python |
| uv | 必需/推荐 | 宿主机 | Python 版本、虚拟环境、依赖锁定和离线安装 | 无 | 可换等价工具，但项目只保留一种依赖工作流 |
| llama.cpp LLM 实例 | 必需，已具备 | 宿主机或专用 GPU 主机 | 根据检索证据生成答案 | 8081 | 独立加载生成模型 |
| llama.cpp Embedding 实例 | 必需，已具备 | 宿主机或专用 GPU 主机 | 文档和 query 向量化 | 8082 | 独立加载 Embedding 模型 |
| Qdrant | 必需 | 本机容器/本机服务 | 稠密向量持久化、过滤和 ANN 检索 | 6333/6334 | 只监听 loopback；使用持久卷 |
| SQLite FTS5 | 必需，随 Python | Python 标准库 | 元数据、job、snapshot、关键词检索 | 无 | 必须验证 Python 构建包含 FTS5 |
| Docker Desktop | Windows 条件必需 | Windows + WSL2 | 运行 Qdrant Linux 容器 | 本身无业务端口 | 若已有可靠原生 Qdrant 可不装；注意企业许可 |
| Docker Engine | Linux 条件必需 | Linux | 运行 Qdrant 容器 | 本身无业务端口 | 若采用 Qdrant 原生二进制可不装 |
| WSL2 | Windows 条件必需 | Windows | Docker Desktop Linux 容器后端 | 无 | 不用于运行源码也可以，仅承载容器后端 |

### 5.2 Git

**作用**

- 将 branch/tag 解析为固定 commit SHA。
- 读取 tree/blob SHA，识别未变化文件，减少重复解析和 Embedding。
- 支持本地 clone、bare mirror、Git bundle 和可选受控 fetch。

**Windows 安装**

```powershell
winget install --id Git.Git -e
git --version
```

**Ubuntu 安装**

```bash
sudo apt-get update
sudo apt-get install -y git ca-certificates
git --version
```

**配置要求**

```bash
git config --global core.autocrlf false
git config --global advice.detachedHead false
```

索引按 Git blob 内容和行号工作，建议避免采集进程自动改写换行符。服务进程还应设置 `GIT_TERMINAL_PROMPT=0`，防止远程凭据提示使 Worker 卡死。

**验收**

```bash
git -C <repo-path> rev-parse HEAD
git -C <repo-path> ls-tree -r --full-tree HEAD
```

### 5.3 Python 3.12 与 uv

**作用**

- Python 是 RAG 编排层运行时。
- uv 负责安装固定 Python、创建 `.venv`、解析/锁定依赖并按 lockfile 还原环境。

选择 Python 3.12 是兼容性基线，不代表更新版本不可用。升级到 3.13/3.14 前需确认 Qdrant client、Tree-sitter grammars、SQLite FTS5 和所有二进制 wheel 在目标平台通过测试。

**Windows 安装 uv**

```powershell
winget install --id astral-sh.uv -e
uv --version
uv python install 3.12
uv python pin 3.12
uv venv --python 3.12
```

**Linux 安装 uv**

联网安装可使用官方 standalone installer；正式环境应下载并校验固定版本二进制后再分发：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv --version
uv python install 3.12
uv python pin 3.12
uv venv --python 3.12
```

**项目依赖安装**

项目产生 `pyproject.toml` 和 `uv.lock` 后：

```powershell
uv sync --frozen
uv run python --version
```

首次开发时尚无 lockfile，可使用 `uv lock` 生成；生产环境禁止隐式更新 lockfile。

**SQLite FTS5 验收**

```powershell
uv run python -c "import sqlite3; c=sqlite3.connect(':memory:'); c.execute('CREATE VIRTUAL TABLE t USING fts5(x)'); print('SQLite', sqlite3.sqlite_version, 'FTS5 OK')"
```

### 5.4 llama.cpp LLM 服务

**作用**

- 接收经过引用约束的 prompt 和检索上下文。
- 输出同步或流式答案。
- 仅执行生成任务，不承担文档向量化。

**要求**

- 独立进程，默认 `127.0.0.1:8081`。
- OpenAI 风格 `POST /v1/chat/completions` 可用。
- `GET /health` 可用。
- 模型 chat template 已验证。
- `temperature` 建议 0.0～0.2，保留足够 answer token。
- 默认不启用文件系统、shell、网络或内置工具。

**启动示意**

具体参数以已经跑通的命令为准，以下只表达所需边界：

```powershell
llama-server.exe `
  -m E:\RAG-Data\models\<llm-model>.gguf `
  --host 127.0.0.1 `
  --port 8081 `
  --alias local-chat `
  --ctx-size <verified-context-size>
```

不要直接复制未验证的 context、GPU layer 和并发参数；它们必须与模型和硬件匹配。

**验收**

```powershell
Invoke-RestMethod http://127.0.0.1:8081/health

$requestBody = @{
  model = 'local-chat'
  messages = @(@{ role = 'user'; content = '仅回答：OK' })
  max_tokens = 8
  temperature = 0
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8081/v1/chat/completions `
  -ContentType 'application/json' `
  -Body $requestBody
```

### 5.5 llama.cpp Embedding 服务

**作用**

- 为入库 chunk 批量生成向量。
- 为用户 query 生成同一向量空间的向量。

**要求**

- 独立进程，默认 `127.0.0.1:8082`。
- OpenAI 风格 `POST /v1/embeddings` 可用。
- 使用专用 Embedding 模型和适配的 pooling/normalization。
- 输出向量维度固定；启动时由 RAG 服务探测并与 Qdrant collection 校验。
- query/document 前缀从配置读取，不在代码里写死。

**启动示意**

```powershell
llama-server.exe `
  -m E:\RAG-Data\models\<embedding-model>.gguf `
  --host 127.0.0.1 `
  --port 8082 `
  --alias local-embedding `
  --embedding `
  --pooling <model-required-pooling>
```

**验收**

```powershell
Invoke-RestMethod http://127.0.0.1:8082/health

$embeddingBody = @{
  model = 'local-embedding'
  input = @('embedding health check', 'second document')
} | ConvertTo-Json -Depth 4

$embeddingResponse = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8082/v1/embeddings `
  -ContentType 'application/json' `
  -Body $embeddingBody

$embeddingResponse.data.Count
$embeddingResponse.data[0].embedding.Count
```

应确认返回 2 条向量、维度相同且同一输入重复请求的 cosine 相似度接近 1。

### 5.6 Qdrant

**作用**

- 保存 chunk 的稠密向量和 repo/path/symbol/snapshot 等 payload。
- 执行 cosine/dot-product 近邻检索及 metadata filter。
- 每个 snapshot 使用独立不可变 collection；由 SQLite `published` 状态完成原子发布和回滚。

**Windows 推荐安装路径**

1. 启用 WSL2。
2. 安装 Docker Desktop，使用 WSL2 backend。
3. Qdrant 使用 Docker named volume，不直接把 Windows/WSL 混合路径挂载为生产数据目录。

WSL2 检查：

```powershell
wsl --version
wsl --status
```

需要安装或更新时，在管理员终端执行：

```powershell
wsl --install
wsl --update
```

Docker 验收：

```powershell
docker version
docker info
```

**Qdrant 启动示意**

将 `<pinned-tag>` 替换为项目验证过的固定 tag：

```powershell
docker pull qdrant/qdrant:<pinned-tag>
docker volume create rag_qdrant_storage
docker run -d `
  --name rag-qdrant `
  --restart unless-stopped `
  -p 127.0.0.1:6333:6333 `
  -p 127.0.0.1:6334:6334 `
  -v rag_qdrant_storage:/qdrant/storage `
  qdrant/qdrant:<pinned-tag>
```

不要在正式部署中直接使用 `qdrant/qdrant:latest`。

**验收**

```powershell
Invoke-RestMethod http://127.0.0.1:6333/healthz
Invoke-RestMethod http://127.0.0.1:6333/collections
docker inspect rag-qdrant --format '{{.Config.Image}}'
```

Qdrant 默认没有适合局域网暴露的安全配置，因此首版只绑定 `127.0.0.1`。如果 RAG API 与 Qdrant 不在同一主机，必须配置网络隔离、API key/TLS 或受控反向代理。

### 5.7 SQLite FTS5

**作用**

- 保存 repositories、snapshots、files、chunks、index_jobs。
- 通过 FTS5 对路径、symbol、错误码、配置键和文本执行关键词检索。
- 记录索引 checkpoint、发布状态和 Embedding cache。

SQLite 由 Python `sqlite3` 提供，不需要额外安装 SQLite Server。应用启动时必须执行：

- `PRAGMA journal_mode=WAL;`
- `PRAGMA foreign_keys=ON;`
- `PRAGMA busy_timeout=5000;`
- migration version 检查。

SQLite 是本系统的状态数据库，不可放到不可靠的网络共享盘；备份时使用 SQLite backup API 或在正确 checkpoint 后复制，不能随意只复制 `.db` 而忽略活跃 WAL。

---

## 6. Python 运行时依赖

以下是首版建议依赖类别。最终包名和版本以 `pyproject.toml`/`uv.lock` 为准，不在服务器上手工逐个安装最新版。

### 6.1 生产依赖

| Python 包/类别 | 级别 | 项目作用 | 备注 |
|---|---|---|---|
| `fastapi` | 必需 | HTTP API、请求校验、OpenAPI | 只暴露 RAG API |
| `uvicorn` | 必需 | ASGI Server | 单机可直接运行；进程数按模型和 SQLite 约束配置 |
| `pydantic` / `pydantic-settings` | 必需 | DTO、配置、环境变量校验 | secret 字段禁止日志输出 |
| `httpx` | 必需 | 异步调用两个 llama.cpp 服务 | 设置连接池、超时、重试边界 |
| `qdrant-client` | 必需 | Qdrant collection、point、filter、snapshot 操作 | 与服务端版本做兼容测试 |
| `tree-sitter` | 必需 | 代码语法树解析 | 仅安装目标仓库所需 grammar |
| Tree-sitter language grammars | 按仓库语言必需 | Python/Java/Go/TS 等语言节点解析 | runtime 与 grammar 一起锁定 |
| `aiosqlite` 或同步 SQLite adapter | 必需 | SQLite 事务、FTS、job 状态 | 首版保持单写者模型 |
| `PyYAML` | 必需 | 读取 application/repository YAML 配置 | 配置 schema 由 Pydantic 校验 |
| `orjson` | 推荐 | 高效 JSON 序列化 | 不可用时可回退标准库 |
| `structlog` | 推荐 | 结构化日志 | 默认不记录 prompt/源码正文 |
| `tenacity` | 推荐 | 对模型 HTTP、Qdrant 的有界重试 | 业务错误不得无限重试 |
| `typer` | 推荐 | `ragctl` 管理 CLI | 索引、评估、诊断 |
| `prometheus-client` | 推荐 | 本地 `/metrics` | 不使用监控时可关闭 endpoint |
| `python-ulid` 或等价 ULID 库 | 推荐 | request/job/snapshot ID | Qdrant point ID仍使用 UUIDv5 |

是否使用 OpenAI Python SDK属于实现选择，不是必需项。直接通过 `httpx` 调用 llama.cpp 的固定接口可以减少依赖和兼容层；如果使用 SDK，必须把 `base_url` 固定为本地地址，并加测试防止误连云端。

### 6.2 开发与测试依赖

| Python 包/工具 | 作用 |
|---|---|
| `pytest` | 单元、集成、端到端测试入口 |
| `pytest-asyncio` | 异步 API/adapter 测试 |
| `pytest-cov` / `coverage` | 覆盖率报告 |
| `ruff` | lint、格式化和 import 检查 |
| `mypy` 或 `pyright` | 静态类型检查 |
| `respx` | 模拟 llama.cpp HTTP 响应和错误 |
| `testcontainers`（可选） | 集成测试临时 Qdrant；无外网环境需预置镜像 |

### 6.3 Tree-sitter grammar 安装策略

不要一开始安装所有语言 grammar。先扫描目标仓库后建立映射，例如：

| 文件 | grammar |
|---|---|
| `*.py` | Python |
| `*.js`, `*.jsx` | JavaScript |
| `*.ts`, `*.tsx` | TypeScript/TSX |
| `*.java` | Java |
| `*.go` | Go |
| `*.rs` | Rust |
| `*.c`, `*.h` | C |
| `*.cpp`, `*.hpp`, `*.cc` | C++ |

每个 grammar 都需要夹具测试，验证函数/类边界和字节偏移到 UTF-8 行号的转换。未支持语言必须回退到文本切分，并记录 `parse_status=fallback`。

---

## 7. 推荐安装的辅助应用

这些工具不是 RAG 运行硬依赖，但能显著提升开发、运维或安全质量。

| 应用 | 推荐级别 | 项目作用 | 注意事项 |
|---|---|---|---|
| PowerShell 7 | Windows 推荐 | 统一启动、诊断、备份和离线安装脚本 | 不要依赖 Windows PowerShell 5 特有行为 |
| VS Code/PyCharm | 开发推荐 | Python 调试、测试、配置和 Markdown 查看 | 不参与生产运行 |
| Gitleaks 或 detect-secrets | 安全推荐 | 入库前发现私钥、token、密码等 | 命中日志只记摘要，不记 secret 原文 |
| WinSW | Windows 24×7 推荐 | 将 `rag-api`、`rag-worker`、llama.cpp 托管为 Windows Service | 固定版本；服务账号最小权限 |
| Prometheus | 可选 | 抓取 RAG/Qdrant 指标 | 单机 PoC 可先不装 |
| Grafana | 可选 | 性能、错误、索引趋势仪表盘 | 不应公网暴露 |
| Fluent Bit/Vector | 可选 | 结构化日志轮转与采集 | 严格本地时写本机日志目标 |
| jq | Linux 推荐 | API 诊断和 JSON 查看 | Windows 可用 PowerShell 原生 JSON 命令 |
| curl | Linux 推荐 | 健康检查 | Windows 使用 `Invoke-RestMethod` 或 `curl.exe` |

### 7.1 不应作为首版依赖的应用

| 应用 | 首版不采用原因 |
|---|---|
| Elasticsearch/OpenSearch | 已有 SQLite FTS5 + Qdrant，增加服务和内存成本没有必要 |
| PostgreSQL | 单机、单写 Worker 下 SQLite 足够；多实例写入再迁移 |
| Redis | 没有必须的分布式缓存或队列需求 |
| Kafka/RabbitMQ | 单 Worker 的 SQLite job queue 足够，避免过度设计 |
| Kubernetes | 首版为单机纯本地，不需要编排集群 |
| LangChain/LlamaIndex | 可借鉴但非必需；核心数据流和引用必须由项目掌控 |
| Node.js | 首版无正式 Web UI；API/CLI 足够 |
| 云端模型 SDK | 违反默认纯本地边界，且存在误传数据风险 |

---

## 8. 端口、进程与资源分配

### 8.1 端口表

| 端口 | 进程 | 是否暴露 | 用途 |
|---:|---|---|---|
| 8000 | `rag-api` | 默认仅 `127.0.0.1`；按需经认证代理提供内网访问 | 查询、搜索、管理、健康检查、指标 |
| 8081 | `llama-server-llm` | 仅本机/受控内网 | 聊天生成 |
| 8082 | `llama-server-embedding` | 仅本机/受控内网 | Embedding |
| 6333 | Qdrant | 仅本机 | REST、健康检查、dashboard |
| 6334 | Qdrant | 仅本机 | gRPC；Python 客户端按配置使用 |
| 9090 | Prometheus（可选） | 仅运维网/本机 | 指标查询 |
| 3000 | Grafana（可选） | 仅运维网/本机 | 仪表盘 |

首版不开放 Qdrant 6335 分布式集群端口。

### 8.2 进程资源建议

- `rag-worker` 默认并发 1；Embedding 批量从 16 开始压测。
- `rag-api` 不在请求线程中执行全量索引。
- 单 GPU 同时运行生成和 Embedding 时，索引任务安排在低峰期，并限制 Embedding 并发。
- 双 GPU 环境优先将 LLM 和 Embedding 分配到不同设备。
- API 查询可以并行执行 Qdrant 和 FTS，但模型生成并发受 llama.cpp slots 和内存限制。
- SQLite 保持一个主要写入 Worker，API 主要读取，降低写锁竞争。

### 8.3 Windows 进程托管

开发阶段使用三个终端即可：

```text
终端 1：llama-server LLM
终端 2：llama-server Embedding
终端 3：uv run rag-api / uv run rag-worker
Qdrant：Docker Desktop 后台容器
```

长期运行时：

- llama.cpp、`rag-api`、`rag-worker` 使用 WinSW 或任务计划程序托管。
- 为每个服务配置工作目录、专用日志、重启上限和启动依赖。
- Docker Desktop 自动启动后再启动依赖 Qdrant 的服务。
- 不要让同一个 wrapper 无限制快速重启，避免日志和 GPU 资源抖动。

### 8.4 Linux systemd 托管

建议 unit：

```text
llama-llm.service
llama-embedding.service
rag-api.service
rag-worker.service
docker.service + rag-qdrant container
```

`rag-api` 在 Qdrant 和模型尚未 ready 时可以启动但保持 readiness 失败；Worker 应等待 Embedding/Qdrant 就绪后再领取任务。

---

## 9. 环境变量与配置

### 9.1 必需配置

建议使用项目自有前缀，避免任何默认云端 fallback：

```text
RAG_ENV=local
RAG_DATA_DIR=E:\RAG-Data
RAG_LLM_BASE_URL=http://127.0.0.1:8081/v1
RAG_LLM_MODEL=local-chat
RAG_EMBEDDING_BASE_URL=http://127.0.0.1:8082/v1
RAG_EMBEDDING_MODEL=local-embedding
RAG_QDRANT_URL=http://127.0.0.1:6333
RAG_SQLITE_PATH=E:\RAG-Data\sqlite\rag.db
RAG_ALLOW_REMOTE_GIT=false
RAG_LOG_PROMPTS=false
```

secret 类配置：

```text
RAG_ADMIN_TOKEN=<random-local-secret>
RAG_LLM_API_KEY=<only-if-llama-server-enabled-auth>
RAG_EMBEDDING_API_KEY=<only-if-llama-server-enabled-auth>
RAG_QDRANT_API_KEY=<only-if-qdrant-enabled-auth>
```

即使 llama.cpp 客户端库要求非空 API key，也只能使用本地占位值，且 `base_url` 必须经过启动校验：host 若不是 allowlist 中的 loopback/内网地址则拒绝启动。

### 9.2 配置优先级

建议从低到高：

```text
default.yaml < environment yaml < 本机 .env < 进程环境变量 < CLI 显式参数
```

- `.env` 不提交 Git。
- `.env.example` 只包含键名和无敏感默认值。
- 每次索引把影响索引兼容性的配置计算为 fingerprint。
- 修改 Embedding 模型、维度、前缀或 chunker/parser 版本时拒绝写入旧 collection。

---

## 10. 推荐安装顺序

### 阶段 A：盘点现有模型服务

1. 记录 llama.cpp 版本/commit、启动命令、模型路径和 SHA-256。
2. 验证 `/health`、聊天和批量 Embedding。
3. 记录向量维度、模型 context、最大批量和单次时延。
4. 备份已跑通的启动脚本，不在本阶段升级。

### 阶段 B：安装基础工具

1. Git。
2. uv 和 Python 3.12。
3. PowerShell 7（Windows 推荐）。
4. 验证 Python SQLite FTS5。

### 阶段 C：安装向量数据库

1. Windows：WSL2 → Docker Desktop → Qdrant named volume/container。
2. Linux：Docker Engine/Compose Plugin → Qdrant volume/container。
3. 固定 Qdrant image tag/digest。
4. 验证 `/healthz`、collection CRUD 和按 snapshot ID 直接检索。

### 阶段 D：创建项目环境

1. 创建 `pyproject.toml`。
2. 安装生产与开发依赖。
3. 只安装目标仓库语言需要的 Tree-sitter grammars。
4. 生成并提交 `uv.lock`。
5. 创建 `data` 目录、migration 和配置文件。

### 阶段 E：联调

1. RAG readiness 同时检查 SQLite、Qdrant、LLM 和 Embedding。
2. 导入 sample repo，完成首次索引。
3. 验证 dense、FTS、RRF 和引用行号。
4. 再接入真实 GitHub 项目的本地 clone/mirror。

### 阶段 F：运维加固

1. 服务托管和有上限重启。
2. 管理 token、loopback/firewall 和最小权限。
3. Qdrant snapshot、SQLite backup 和配置/模型清单。
4. 离线恢复演练。

---

## 11. Windows 一次性准备清单

以下是安装步骤模板，不应在不确认企业策略和 Docker Desktop 许可的情况下自动执行。

```powershell
# 1. 基础工具
winget install --id Git.Git -e
winget install --id astral-sh.uv -e

# 2. Python 项目环境
Set-Location E:\RAG-Project
uv python install 3.12
uv python pin 3.12
uv venv --python 3.12

# 3. WSL2 / Docker Desktop 的前置检查
wsl --version
wsl --status
docker version

# 4. Qdrant（替换固定 tag）
docker volume create rag_qdrant_storage
docker run -d `
  --name rag-qdrant `
  --restart unless-stopped `
  -p 127.0.0.1:6333:6333 `
  -p 127.0.0.1:6334:6334 `
  -v rag_qdrant_storage:/qdrant/storage `
  qdrant/qdrant:<pinned-tag>

# 5. 基础验证
git --version
uv run python --version
Invoke-RestMethod http://127.0.0.1:6333/healthz
Invoke-RestMethod http://127.0.0.1:8081/health
Invoke-RestMethod http://127.0.0.1:8082/health
```

Docker Desktop 需要单独按组织许可和官方安装流程部署；不要把下载执行脚本直接固化到生产部署脚本中。

---

## 12. Linux 一次性准备清单

```bash
# 1. 基础包
sudo apt-get update
sudo apt-get install -y git curl ca-certificates jq

# 2. uv / Python
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12

# 3. 进入项目并还原锁定环境
cd /opt/rag-project
uv python pin 3.12
uv venv --python 3.12
uv sync --frozen

# 4. 验证
git --version
uv run python --version
curl -fsS http://127.0.0.1:6333/healthz
curl -fsS http://127.0.0.1:8081/health
curl -fsS http://127.0.0.1:8082/health
```

Docker Engine 的仓库配置和安装应遵循目标 Ubuntu 版本的官方流程；正式环境不要使用通用 convenience script。若服务器完全离线，应导入已校验的 deb/rpm 包与 Qdrant image tar。

---

## 13. 严格离线安装方案

### 13.1 联网制品准备机

准备机必须与离线目标机具有相同的操作系统、CPU 架构和 Python 次版本，以确保 wheel 可用。

需要收集：

```text
offline-bundle/
├─ manifest.sha256
├─ installers/
│  ├─ git/
│  ├─ uv/
│  ├─ python/             # 如不用 uv 管理 Python
│  ├─ docker/             # 条件需要
│  └─ llama-cpp/
├─ wheels/
├─ containers/
│  └─ qdrant_<tag>.tar
├─ models/
│  ├─ llm.gguf
│  └─ embedding.gguf
├─ repos/
│  └─ source-repo.bundle
├─ config/
│  ├─ uv.lock
│  ├─ pyproject.toml
│  └─ versions.yaml
└─ licenses/
```

### 13.2 Python wheelhouse

在与目标平台相同的准备环境中，根据锁定依赖下载 wheels：

```bash
uv export --frozen --no-dev --output-file requirements.lock.txt
python -m pip download --only-binary=:all: \
  --requirement requirements.lock.txt \
  --dest wheels
```

如果某个依赖没有对应 wheel，应在准备机预先构建并测试；不要到离线生产机临时安装 Rust/C++ 编译链解决。

离线安装：

```bash
uv pip install --offline \
  --find-links wheels \
  --requirement requirements.lock.txt
```

### 13.3 Qdrant 镜像

联网准备：

```bash
docker pull qdrant/qdrant:<pinned-tag>
docker image inspect qdrant/qdrant:<pinned-tag>
docker save --output qdrant_<tag>.tar qdrant/qdrant:<pinned-tag>
```

离线导入：

```bash
docker load --input qdrant_<tag>.tar
```

### 13.4 Git 仓库

联网准备：

```bash
git clone --mirror <github-url> source-repo.git
git -C source-repo.git bundle create ../source-repo.bundle --all
git bundle verify source-repo.bundle
```

离线导入：

```bash
git clone source-repo.bundle source-repo
git -C source-repo rev-parse HEAD
```

### 13.5 完整性清单

Windows 可使用：

```powershell
Get-ChildItem -File -Recurse .\offline-bundle |
  Get-FileHash -Algorithm SHA256 |
  Select-Object Hash,Path
```

Linux 可使用：

```bash
find offline-bundle -type f -print0 | sort -z | xargs -0 sha256sum > manifest.sha256
sha256sum --check manifest.sha256
```

制品交付时同时保存许可证、来源 URL、版本、构建日期和签名/摘要验证结果。

---

## 14. 健康检查与安装验收

### 14.1 基础验收表

| 检查项 | 通过标准 |
|---|---|
| Git | 能对目标 repo 执行 `rev-parse` 和 `ls-tree`，无交互凭据等待 |
| Python | `3.12.x`，虚拟环境路径正确 |
| uv | `uv sync --frozen` 无依赖变更 |
| SQLite | 可以创建 FTS5 虚拟表，WAL 可启用 |
| LLM | `/health` 为 ready，chat endpoint 返回内容 |
| Embedding | `/health` 为 ready，批量输入返回等长固定维度向量 |
| Qdrant | `/healthz` 正常，可创建 collection、upsert、按 snapshot collection search |
| Tree-sitter | 目标语言 fixture 能产生预期函数/类节点和行号 |
| RAG API | `/health/live` 与 `/health/ready` 正常 |
| Worker | 能对 sample repo 完成 job 并发布 snapshot |

### 14.2 一键诊断应输出的内容

未来的 `ragctl doctor` 应输出：

```text
OS/architecture
Python/uv/Git 版本
llama.cpp 两实例 health、model alias、可用 endpoint
Embedding dimension 和探针结果
Qdrant 版本、published snapshots 对应 collection、磁盘状态
SQLite 版本、FTS5、migration、WAL
目标仓库路径、commit、可读性
解析器/grammar 版本
数据盘剩余空间
最终 READY / NOT READY 以及修复建议
```

诊断输出不得包含 API key、完整 prompt、模型敏感路径、源码正文或 secret 原文。

---

## 15. 备份、升级与回滚需要的工具环境

### 15.1 必须备份

- SQLite 的一致性备份。
- Qdrant collection snapshot 或受支持的持久化备份。
- `pyproject.toml`、`uv.lock`、配置、prompt 和 migration。
- llama.cpp 版本、启动参数和模型 SHA-256。
- 当前仓库 commit；严格离线时保存 bare mirror/bundle。
- 当前 SQLite published snapshot 与 Qdrant collection 对应关系。

### 15.2 升级顺序

1. 在测试数据目录恢复一份备份。
2. 固定一套评估问题和性能基线。
3. 一次只升级一个组件。
4. 运行 migration、索引兼容检查和完整评估。
5. Embedding/切分器变化时构建新 collection，不原地覆盖。
6. 保留旧 Python lock、Qdrant image、llama.cpp 二进制和旧 published collection，直到观察期结束。

### 15.3 不兼容变更判断

| 变更 | 是否需要重建索引 |
|---|---|
| LLM 生成模型更换 | 通常不需要；需重跑回答评估 |
| Embedding 模型或模型文件更换 | 必须 |
| Embedding 前缀/归一化/维度变化 | 必须 |
| chunker/parser 影响边界的变化 | 必须 |
| prompt 变化 | 不需要；需重跑回答评估 |
| RRF/top-k 参数变化 | 不需要；需重跑检索评估 |
| Qdrant 小版本升级 | 依据官方兼容说明；先 snapshot 和测试 |
| SQLite schema migration | 依据 migration；升级前一致性备份 |

---

## 16. 安全与合规注意事项

- 所有业务端口默认绑定 `127.0.0.1`。
- Docker socket 权限近似主机高权限，只授予实际需要的账号。
- Docker Desktop 在部分企业规模下涉及商业订阅要求，安装前由组织确认许可。
- llama.cpp 不启用内置文件、shell、agent 或网络工具。
- Worker 以只读方式访问知识源，不运行 Git hooks 和仓库代码。
- Qdrant 默认部署不应直接暴露到局域网或公网。
- `.env`、模型路径、日志、缓存和索引都视为敏感资产。
- 目标 GitHub 项目的许可证必须允许本地复制、处理和展示必要代码片段。
- secret scanner 是入库防线，但不能保证找出全部机密；仓库自身仍需执行密钥治理。

---

## 17. 项目启动前待确认信息

以下信息确认后才能生成最终 `pyproject.toml`、grammar 清单和可执行安装脚本：

1. 目标 GitHub 项目 URL、本地 clone 路径、commit/ref 和许可证。
2. 主要编程语言及需要索引的文件类型。
3. 当前操作系统版本、CPU、内存、GPU/VRAM 和数据盘空间。
4. 两个 llama.cpp 服务的版本、启动命令、端口、模型 alias 和 SHA-256。
5. Embedding 维度、最大输入 token、pooling、归一化及 query/document 前缀。
6. Docker Desktop 是否已安装、组织是否允许使用及数据盘位置。
7. 单用户还是局域网多人使用，是否需要认证和 TLS。
8. 严格离线还是允许受控 `git fetch`。
9. 是否需要 24×7 服务托管、Prometheus/Grafana 和备份保留周期。

---

## 18. 最终安装清单

### 18.1 必需

- [ ] 受支持的 Windows 11 x64 或 Ubuntu Server 24.04 LTS x64。
- [ ] 足够的内存、NVMe 数据空间和现有模型所需 GPU/CPU。
- [ ] Git。
- [ ] uv 和固定 Python 3.12.x。
- [ ] 已验证的 llama.cpp LLM 独立实例。
- [ ] 已验证的 llama.cpp Embedding 独立实例。
- [ ] 固定版本/digest 的 Qdrant。
- [ ] Python SQLite FTS5 支持。
- [ ] FastAPI、Qdrant client、Tree-sitter 等锁定 Python 依赖。
- [ ] 目标语言 grammar。
- [ ] 本地 Git clone、bare mirror 或 bundle。

### 18.2 条件必需

- [ ] Windows 使用 Qdrant 容器时：WSL2 + Docker Desktop。
- [ ] Linux 使用 Qdrant 容器时：Docker Engine + Compose Plugin。
- [ ] GPU 推理：匹配当前 llama.cpp 后端的驱动/运行时。
- [ ] 严格离线：wheelhouse、容器 tar、模型、Git bundle 和 SHA-256 manifest。
- [ ] 局域网访问：认证、TLS/反向代理和防火墙规则。

### 18.3 推荐

- [ ] PowerShell 7 或标准 Bash 工具环境。
- [ ] secret scanner。
- [ ] Windows WinSW 或 Linux systemd 服务托管。
- [ ] Qdrant/SQLite 自动备份和恢复演练。
- [ ] 本地结构化日志、磁盘告警和可选 Prometheus/Grafana。

---

## 19. 参考资料

- [llama.cpp HTTP Server 官方文档](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)：`/health`、聊天、Embedding 和服务启动参数。
- [Qdrant Local Quickstart](https://qdrant.tech/documentation/quick-start/)：本地容器、REST/gRPC 端口和持久化目录。
- [Qdrant Installation](https://qdrant.tech/documentation/installation/)：容器/二进制安装、持久存储、网络与安全注意事项。
- [uv 官方安装文档](https://docs.astral.sh/uv/getting-started/installation/)：Windows、Linux、WinGet 和固定版本安装方式。
- [Docker Desktop for Windows 官方文档](https://docs.docker.com/desktop/setup/install/windows-install/)：WSL2 前置条件、安装模式及许可提示。
- [SQLite FTS5 官方文档](https://www.sqlite.org/fts5.html)：FTS5 虚拟表、tokenizer 和全文检索能力。
- [Tree-sitter 官方文档](https://tree-sitter.github.io/tree-sitter/)：语法树解析和语言绑定。

---

## 20. 架构师建议

当前阶段先保留已经跑通的 llama.cpp 软件栈，只新增 Git、Python/uv、Qdrant 和项目 Python 依赖。Windows 上优先使用 Docker named volume 承载 Qdrant，并将正式数据与源码目录分开。等目标 GitHub 仓库和主要语言确认后，再精确生成 Tree-sitter grammar 清单、`pyproject.toml`、`uv.lock`、Qdrant Compose 文件和一键诊断脚本；这样安装范围最小，也避免提前引入无用运行时。
