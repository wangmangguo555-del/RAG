# Local Git RAG 项目架构搭建报告

> 完成日期：2026-08-12  
> 依据：[纯本地 Git 仓库 RAG 架构设计与开发方案](./LOCAL_RAG_ARCHITECTURE_AND_DEVELOPMENT_PLAN.md)  
> 状态：可运行 MVP 架构已完成并通过真实本地端到端验证

## 1. 已交付模块

| 架构层 | 实现 |
|---|---|
| Domain | Repository、Snapshot、Chunk、SearchHit、Citation、Job 模型；Git/Embedding/Generation/Vector/Metadata 端口 |
| Application | 索引任务和查询问答用例 |
| Ingestion | 本地 Git commit/tree/blob、安全过滤、`.ragignore`、语言检测、确定性 chunk |
| Infrastructure | SQLite WAL/FTS5、Qdrant snapshot collection/alias、llama.cpp chat/embedding 客户端 |
| Retrieval | Dense + FTS5、RRF、content hash 去重、每文件多样性限制、context budget |
| Generation | evidence prompt、prompt injection 边界、引用 ID 校验与结构化映射 |
| API | FastAPI query/search/admin/live/ready/OpenAPI |
| Worker | SQLite job queue 单 Worker 消费与失败记录 |
| CLI | init-db、register-repo、index、worker、doctor、search、query |
| Operations | Windows/Linux 开发脚本、Qdrant loopback 启动脚本、环境加载脚本 |
| Quality | Ruff、strict mypy、pytest、fixture、可执行检索评估与示例标注 |

## 2. 已验证链路

使用本地 fixture Git 仓库执行：

```text
Git commit
  → 读取 2 个 blob
  → 生成 6 个 chunk
  → llama.cpp Embedding（1024 维）
  → Qdrant + SQLite FTS5
  → RRF 混合搜索
  → Qwen3.5 本地生成
  → [E1]/[E4] 引用校验
  → path:start-end@commit 输出
```

实际问答正确返回了刷新令牌被撤销/过期的两条规则，并引用：

```text
README.md:5-8@commit
src/auth.py:15-21@commit
```

同一 commit 第二次索引命中 published snapshot，返回 `reused_snapshot=1`，没有重复调用 Embedding。

## 3. 最终质量结果

```text
uv lock --check       通过
ruff check            通过
ruff format --check   通过
mypy src              通过（35 个源码文件）
pytest                通过（8 个测试）
ragctl doctor         SQLite/Qdrant/LLM/Embedding 全部 OK
Uvicorn smoke         live=200、ready=200、OpenAPI 正常
```

检索评估入口已使用当前项目自身建立 50 条专属问题，其中 45 条可回答、5 条明确无答案。
评估支持 dense-only、lexical-only 和 hybrid 三种模式，并记录 Evidence Recall@K、MRR@K、
逐题候选及配置指纹，作为后续切分、召回和排序优化的可复现基线。

2026-08-13 在本地 `rag-project` 已发布快照上得到的 Recall@10 / MRR@10 为：

| 模式 | Recall@10 | MRR@10 |
|---|---:|---:|
| Dense-only | 0.756 | 0.402 |
| Lexical-only | 0.778 | 0.450 |
| Hybrid + 精确路径/符号/类模块提升 | 0.956 | 0.619 |

Hybrid 已达到 Recall@10 ≥ 0.85 的建议门槛，但 MRR@10 尚未达到 0.65。下一轮应优先检查
剩余低排名题，并评估邻接扩展或轻量 reranker；不应仅为提高指标放宽 secret 过滤。

初始端到端 smoke 使用的临时 collection、alias、仓库注册和 fixture `.git` 均已清理；
当前 SQLite/Qdrant 已保存 `rag-project` 与 `vue-guide-cn` 的正式本地索引。

## 4. 关键设计结果

- 固定 commit SHA 读取，不索引未提交工作树状态。
- 仓库代码不执行，不运行 hook，不跟随网络。
- 二进制、超大文件、常见生成目录、密钥和 `.ragignore` 路径默认排除。
- `chunk_id` 基于 repo/commit/path/line/chunker version，point ID 使用确定性 UUIDv5。
- 每个 snapshot 使用独立 Qdrant collection，通过 per-repo alias 发布。
- SQLite 负责事实状态和 FTS5，Qdrant 负责稠密向量。
- 查询结果只使用 published snapshot；模型引用由服务端映射，不信任模型手写路径。
- 配置禁止非 loopback 模型地址，避免纯本地模式误连外部服务。

## 5. 待目标仓库确认后实施

以下能力需要真实 GitHub 项目 URL/路径及语言后继续：

1. 安装目标语言 Tree-sitter grammar，实现精确 AST Parser Registry。
2. 根据真实目录生成 `.ragignore`、include/exclude 和 secret 策略。
3. 将现有评估入口和示例标注扩充为 50～100 条仓库专属评估问题，并冻结 Recall/MRR 基线。
4. 加入跨 snapshot Embedding cache 和 blob/chunk 复制，减少变更索引成本。
5. 根据检索评估决定是否安装本地 reranker。
6. 若要求 24×7，配置 WinSW/systemd、备份与定期健康监控。
7. 若需要多人访问，增加正式认证、TLS、审计和 repo 权限过滤。

## 6. 启动入口

```powershell
Set-Location E:\RAG-Project
.\scripts\rag-env.ps1
uv sync --frozen
uv run ragctl doctor
.\start.bat
```

完整使用方式见 [README](./README.md)。
