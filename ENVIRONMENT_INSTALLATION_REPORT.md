# 纯本地 Git RAG 环境检查与安装报告

> 执行日期：2026-08-12  
> 执行主机：当前 Windows 本地开发机  
> 依据文档：[环境与应用安装清单](./LOCAL_RAG_ENVIRONMENT_AND_APPLICATIONS.md)  
> 结论：**PoC/开发环境已就绪；正式批量索引前需关注内存容量和服务自启动。**

---

## 1. 最终状态

| 检查项 | 状态 | 实际结果 |
|---|---|---|
| 操作系统 | 通过 | Windows 11 家庭版，64 位，Build 26200 |
| CPU | 通过 | AMD Ryzen 7 9700X，8 核/16 逻辑处理器 |
| GPU | 通过 | NVIDIA GeForce RTX 5060 Ti，16311 MiB，驱动 591.86 |
| 内存 | **告警** | 总计 15.2 GB，检查时空闲约 1.7 GB；仅满足 PoC 下限 |
| 磁盘 | 通过/关注 | C: 26.1 GB 可用；D: 78 GB 可用；E: 120 GB 可用 |
| Git | 通过，原有 | 2.55.0.windows.2 |
| uv | 通过，已安装 | 0.11.32，项目隔离安装 |
| Python | 通过，已安装 | 项目 Python 3.12.13；系统原有 3.14.5 未修改 |
| 虚拟环境 | 通过，已创建 | `E:\RAG-Project\.venv` |
| Python 锁文件 | 通过，已创建 | `uv.lock`，61 个解析包，`uv lock --check` 通过 |
| SQLite FTS5 | 通过 | SQLite 3.50.4，可创建 FTS5 虚拟表 |
| Qdrant | 通过，原有并加固 | 1.19.0，CRUD/search 验证通过，只监听 loopback |
| LLM 服务 | 通过，原有 | `127.0.0.1:8080`，聊天接口验证通过 |
| Embedding 服务 | 通过，原有 | `127.0.0.1:8081`，维度 1024，批量接口验证通过 |
| Tree-sitter runtime | 通过，已安装 | 0.25.2 |
| 语言 grammar | 待目标仓库确认 | 未盲目安装；需根据 GitHub 项目语言选择 |
| Docker/WSL2 | 不需要 | 已有原生 Qdrant，避免重复运行时 |
| PowerShell 7 | 可选未安装 | 当前 Windows PowerShell 可完成安装与验证 |
| Prometheus/Grafana | 可选未安装 | PoC 阶段非运行依赖 |

---

## 2. 已执行的安装与配置

### 2.1 uv

- 版本：`0.11.32`
- 来源：Astral 官方固定版本发布制品。
- 平台：`x86_64-pc-windows-msvc`。
- 安装目录：

```text
E:\RAG-Project\.tools\uv\0.11.32\
```

- 下载压缩包 SHA-256 已与官方校验文件比对：

```text
ACFDE570451CFDB8689FA159A138EE805BA4E241C466432750302C86254B0984
```

`.tools` 已加入 `.gitignore`，不会误提交二进制制品。

### 2.2 Python 3.12

- 安装版本：`CPython 3.12.13 x86_64`。
- 安装方式：uv managed Python。
- 安装目录：

```text
E:\RAG-Project\.tools\python\cpython-3.12-windows-x86_64-none\
```

- 项目版本约束：`>=3.12.13,<3.13`。
- 系统原有 `D:\PythonRuntime\python.exe` 3.14.5 保持不变。
- `.python-version` 已固定为 `3.12.13`。

### 2.3 项目虚拟环境与依赖

已创建：

```text
E:\RAG-Project\.venv\
```

已生成：

- `pyproject.toml`
- `uv.lock`
- `.python-version`
- `.gitignore`
- `scripts/rag-env.ps1`

核心生产依赖：

| 依赖 | 已安装版本 | 作用 |
|---|---:|---|
| FastAPI | 0.141.1 | RAG HTTP API |
| Uvicorn | 0.52.1 | ASGI Server |
| HTTPX | 0.28.1 | llama.cpp HTTP 客户端 |
| Pydantic Settings | 2.15.0 | 配置与环境变量校验 |
| Qdrant Client | 1.19.0 | 向量库访问，与服务端 1.19.0 对齐 |
| Tree-sitter | 0.25.2 | 代码语法树 runtime |
| aiosqlite | 0.22.1 | SQLite 异步访问 |
| PyYAML | 6.0.3 | YAML 配置 |
| orjson | 3.11.9 | JSON 序列化 |
| structlog | 25.5.0 | 结构化日志 |
| tenacity | 9.1.4 | 有界重试 |
| Typer | 0.27.1 | 管理 CLI |
| prometheus-client | 0.26.0 | 本地指标 |

开发依赖已安装：pytest、pytest-asyncio、pytest-cov、Ruff、mypy、respx。

### 2.4 Qdrant 加固

发现时状态：

- 原生 Qdrant 1.19.0 已运行。
- 数据目录：`D:\application\qdrant`。
- 6333/6334 监听 `0.0.0.0`，且未配置认证。
- collection 为空。

已执行：

1. 创建临时 collection。
2. 写入测试向量。
3. 执行 cosine 查询，返回 score 1.0。
4. 清理临时 collection。
5. 在确认 collection 为空后安全重启。
6. 将 REST/gRPC 监听地址收敛为 `127.0.0.1`。
7. 设置 `QDRANT__TELEMETRY_DISABLED=true`。

当前监听：

```text
127.0.0.1:6333  Qdrant REST
127.0.0.1:6334  Qdrant gRPC
```

启动脚本：

```text
E:\RAG-Project\scripts\start-qdrant-local.ps1
```

日志：

```text
E:\RAG-Project\data\logs\qdrant.stdout.log
E:\RAG-Project\data\logs\qdrant.stderr.log
```

Qdrant 二进制 SHA-256：

```text
369C562EAE3D89333A13ABFDB522FA209E3F587C1217A1059D817E80814EA9D4
```

---

## 3. 现有 llama.cpp 服务核验

### 3.1 实际端口

原环境清单使用 8081/8082 作为示例。当前机器的实际配置为：

| 服务 | 实际地址 | 状态 |
|---|---|---|
| LLM | `http://127.0.0.1:8080/v1` | 健康 |
| Embedding | `http://127.0.0.1:8081/v1` | 健康 |

后续项目配置必须使用实际端口，不能照抄文档示例端口。

### 3.2 LLM

模型：

```text
E:\LLM_Model\Qwen3.5-9B-Q5_K_M.gguf
```

模型信息：

- 参数量：约 8.95B。
- 量化：Q5_K_M。
- 当前 server context：32768。
- `/health`：通过。
- `/v1/chat/completions`：通过。
- 使用 `chat_template_kwargs.enable_thinking=false` 时，测试请求返回 `OK` 且正常 stop。

模型 SHA-256：

```text
DC2A39AEF291F91A9116AD214058DA0D86EB648743A124BD8C333787C4B9C91C
```

### 3.3 Embedding

模型：

```text
E:\LLM_Model\Qwen3-Embedding-0.6B-Q8_0.gguf
```

模型信息：

- 参数量：约 596M。
- 量化：Q8_0。
- 向量维度：1024。
- 批量输入：通过。
- 相同文本重复向量化：结果一致性检查通过。

模型 SHA-256：

```text
06507C7B42688469C4E7298B0A1E16DEFF06CAF291CF0A5B278C308249C3E439
```

### 3.4 llama.cpp 二进制

```text
E:\llama.cpp\build\bin\Release\llama-server.exe
```

- 编译器：MSVC 19.51.36248.0 x64。
- 二进制内置 version 返回 `0 (unknown)`。
- `E:\llama.cpp` 不是 Git checkout，无法恢复构建 commit。
- 二进制 SHA-256：

```text
4E049170D07D3BCBDA77465380B061BE7BCE65A03EF47E946B0AA4942727DB28
```

SHA-256 可以保证当前制品可识别，但建议下次构建时保留正式 release tag 或 Git commit。

---

## 4. 环境验证结果

已通过：

- `uv lock --check`。
- Python 3.12.13 虚拟环境启动。
- FastAPI、HTTPX、Uvicorn、Qdrant Client、Tree-sitter 导入。
- SQLite FTS5 虚拟表创建。
- Qdrant health、collection CRUD、vector upsert/search/delete。
- LLM health、models 和 chat completions。
- Embedding health、models、批量 Embedding 和 1024 维校验。
- Qdrant 最终无残留测试 collection。
- Qdrant 6333/6334 仅监听 loopback。

---

## 5. 容量风险

当前物理内存总量 15.2 GB，检查时空闲约 1.7 GB。两个 llama-server 的私有内存统计约为：

| 进程 | Private Memory |
|---|---:|
| Qwen3.5-9B LLM server | 约 11.59 GB |
| Qwen3 Embedding server | 约 2.45 GB |
| Qdrant 空库 | 约 0.05 GB |

Windows 的 private memory 不等同于全部物理驻留内存，但该状态已经说明系统余量很低。随着 Qdrant HNSW、Embedding 批量和 Parser 并发增长，可能出现换页、超时或 OOM。

建议：

1. 正式使用前将内存升级到至少 32 GB。
2. 升级前将 `rag-worker` 并发固定为 1，Embedding batch 从 8 开始压测，而不是直接使用 16。
3. 索引任务安排在交互问答低峰期。
4. 监控 commit charge、page file、Qdrant 内存和模型首 token 时延。
5. 大规模索引前确认 D:/E: 至少保留两份 collection 加备份的空间。

当前磁盘足以进行 PoC；尚不足以在未知仓库规模下承诺生产容量。

---

## 6. 未安装项及原因

| 项目 | 原因 | 何时安装 |
|---|---|---|
| Docker Desktop/WSL2 | 已有健康的原生 Qdrant，属于替代路径而非叠加依赖 | 需要容器化交付或原生 Qdrant 无法维护时 |
| 具体 Tree-sitter grammars | 尚未提供目标 GitHub 仓库和语言 | 确认仓库后按语言最小安装 |
| Gitleaks/detect-secrets | 推荐安全工具，不是运行阻塞项 | 开始真实仓库采集前 |
| WinSW/Windows Service | 目前未确认是否要求 24×7/开机启动 | 进入长期运行阶段 |
| Prometheus/Grafana | PoC 非必需 | 需要长期指标、告警和趋势时 |
| PowerShell 7 | 当前脚本可在现有 PowerShell 运行 | 团队要求统一跨平台脚本时 |

---

## 7. 尚需用户提供的信息

1. 目标 GitHub 项目 URL 或本地 clone 路径。
2. 要索引的 branch/tag/commit。
3. 主要语言和应排除的目录。
4. 是否需要严格离线运行。
5. 是否需要服务开机自启动和局域网访问。

收到目标仓库后，下一步应执行语言扫描、安装最小 grammar 集、生成 `.ragignore`，然后开始 sample/真实仓库索引实现。

---

## 8. 常用命令

加载项目环境：

```powershell
Set-Location E:\RAG-Project
.\scripts\rag-env.ps1
uv sync --frozen
uv run python --version
```

启动 Qdrant：

```powershell
.\scripts\start-qdrant-local.ps1
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:6333/healthz
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8081/health
```

验证锁文件：

```powershell
uv lock --check
uv sync --frozen
```
