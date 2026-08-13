# Local RAG 项目计划清单

> 更新日期：2026-08-13  
> 排序原则：先保证发布与恢复正确性，再建设可信评测、索引效率和可信回答。

## 标识说明

- ✅ 已完成
- ⬜ 未完成
- ⏸ 暂缓
- 🔴 核心正确性或发布阻塞项
- 🟠 高优先级
- 🟡 中优先级
- ⚪ 后续候选

## 已完成计划

- ✅ 🔴 SQLite `published snapshot` 成为唯一查询事实源，查询与 Qdrant collection 版本一致。
- ✅ 🔴 发布前校验 chunk、向量点数和向量维度，失败时不污染已发布快照。
- ✅ 🔴 Worker heartbeat、stale job 恢复、有界重试和指数退避。
- ✅ 🔴 多仓库 dense 结果全局排序，移除项目特定路径硬编码。
- ✅ 🔴 快照保留策略与安全的 `gc --dry-run` 计划。
- ✅ 🔴 SQLite 拼音字段治理、前向迁移、数据库审计和完整性验证。
- ✅ 🟠 评测指标修正为 Hit@K、Target Recall@K、MRR@K、nDCG@K。
- ✅ 🟠 增加不可回答候选率，暴露无答案问题仍返回证据的情况。
- ✅ 🟠 增加评测污染检测，并绑定实际 published snapshot commit。
- ✅ 🟠 保留旧 `evidence_recall_at_k` 兼容字段。
- ✅ 🟠 通用 symbol/path/class 排序特征。
- ✅ 🟠 建立 50 条本项目开发集：45 条可回答、5 条不可回答。
- ✅ 🟡 支持 hybrid、dense-only、lexical-only 三种检索评测模式。
- ✅ 🟡 Git 与 HTTPS 单页摄取、确定性切分、Qdrant + SQLite FTS5 混合检索。
- ✅ 🟡 引用 ID 合法性校验、API、CLI、Worker 和基础健康检查。
- ✅ 🟡 全量质量门禁通过：35 项测试、Ruff、mypy、锁文件、README 和数据库审计。

## 未完成计划

### 第一优先级：阶段 A 最终验收

- ⬜ 🔴 在真实 Qdrant 环境执行发布故障演练，确认旧 published snapshot 始终可查询。
- ⬜ 🔴 执行真实 Worker 强杀与重启恢复演练，验证任务幂等恢复。
- ⬜ 🔴 演练 published collection 缺失、Qdrant 中断和部分写入失败。
- ⬜ 🔴 固化上述演练记录、命令、结果和恢复步骤。

### 第二优先级：阶段 B 评测可信度

- ⬜ 🔴 选择至少一个不同于本项目的真实代码仓库。
- ⬜ 🔴 建立不参与调参的跨仓库留出集，目标 100～150 条问题。
- ⬜ 🟠 建立挑战集，覆盖多文件、同名符号、中文问题、无答案、长文件和提示注入。
- ⬜ 🟠 分别输出开发集、留出集和挑战集报告，不能混合汇总。
- ⬜ 🟠 冻结 Hit@10、Target Recall@10、MRR@10 和 nDCG@10 基线。
- ⬜ 🟠 建立不可回答识别的 Precision、Recall、F1；当前只有检索候选率。
- ⬜ 🟠 根据留出集 MRR 决定是否批准轻量 reranker，暂不应直接引入。
- ⬜ 🟡 对父块/邻接扩展进行 A/B 评测。
- ⬜ 🟡 对中文 FTS tokenizer 进行 A/B 评测。

### 第三优先级：阶段 C 索引效率与结构理解

- ⬜ 🟠 实现 `embedding_fingerprint + embedding_profile + content_hash` 向量缓存。
- ⬜ 🟠 记录缓存命中率、Embedding 调用数和索引耗时。
- ⬜ 🟠 实现 Git blob 级解析和 chunk 复用。
- ⬜ 🟠 正确传播文件删除、重命名和内容变更。
- ⬜ 🟡 建立 Parser Registry，优先 Python。
- ⬜ 🟡 随后支持 TypeScript、JavaScript 和 Vue grammar。
- ⬜ 🟡 增加 parent、neighbor、parser version 和解析状态元数据。
- ⬜ 🟡 增加 AST/fallback 引用行号回归测试。

### 第四优先级：阶段 D 可信回答

- ⬜ 🔴 实现确定性的引用覆盖校验和 `evidence_status`。
- ⬜ 🔴 建立 claim—citation 支持关系验证。
- ⬜ 🔴 建立拒答策略和无答案评测集。
- ⬜ 🟠 达到引用合法率 100%、引用支持率 ≥ 0.95、无答案 F1 ≥ 0.90。
- ⬜ 🟠 完成备份恢复演练，恢复 SQLite published snapshot 及对应 collection。
- ⬜ 🟡 增加基础 Prometheus 业务指标。
- ⬜ 🟡 增加非 loopback 启动安全门禁。
- ⬜ ⚪ 指标达标后增加 SSE 流式输出和轻量 UI。

## 暂缓事项

- ⏸ ⚪ Office/PDF/OCR 等更多数据源。
- ⏸ ⚪ 多租户、RBAC 和仓库级权限体系。
- ⏸ ⚪ Redis、PostgreSQL、消息队列和 Kubernetes。
- ⏸ ⚪ 24×7 WinSW/systemd 部署与完整告警体系。

## 推荐执行顺序

```text
真实故障演练
  → 跨仓库留出集与挑战集
  → 检索 A/B
  → 缓存与解析
  → 引用覆盖与拒答
```

## 当前状态备注

- 阶段 A 的核心业务代码与自动化故障测试已经完成，剩余真实服务故障演练。
- 阶段 B 已完成指标口径修正和评测污染检测，下一项是跨仓库留出集与挑战集。
- 当前工作区存在尚未提交的阶段 B 修改。
