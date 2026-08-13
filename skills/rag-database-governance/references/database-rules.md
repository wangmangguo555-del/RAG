# Local RAG 数据库治理规则

## 1. 权威边界

- SQLite 是 Repository、Job、Snapshot、File、Chunk 和 FTS5 的事实数据源。
- 表名保持职责清晰的英文复数：`repositories`、`snapshots`、`files`、`chunks`、
  `chunks_fts`、`index_jobs`；迁移控制表为 `schema_migrations`。
- SQLite 物理字段使用中文业务全称的拼音首字母；Python 领域模型、CLI 和 HTTP API 保持
  语义清晰的英文名称。
- `DATABASE_SCHEMA_PINYIN.md` 是物理结构说明；迁移 SQL 和实际数据库是最终执行事实。

## 2. 字段命名算法

1. 先写中文业务全称，不得从英文列名反推随意缩写。
2. 按中文全称逐字取规范拼音的首字母，不能漏字、重复或交换顺序。
3. 使用小写 ASCII；除格式后缀外不使用下划线。
4. JSON 字段在中文首字母后追加 `_json`，后缀不参与首字母计算。
5. 同义字段在全项目使用相同中文全称和相同物理名。

典型映射：

| 中文业务全称 | 物理字段 | 说明 |
|---|---|---|
| 编号 | `bh` | 业务主键默认名 |
| 知识源编号 | `zsybh` | 指向 `repositories.bh` |
| 快照编号 | `kzbh` | 指向 `snapshots.bh` |
| 分片编号 | `fpbh` | FTS 回填 `chunks.bh` |
| 向量点编号 | `xldbh` | Qdrant point ID |
| 创建时间 | `cjsj` | UTC ISO 8601 文本 |
| 更新时间 | `gxsj` | UTC ISO 8601 文本 |
| 开始时间 | `kssj` | UTC ISO 8601 文本 |
| 结束时间 | `jssj` | UTC ISO 8601 文本 |
| 心跳时间 | `xtsj` | UTC ISO 8601 文本 |
| 下次重试时间 | `xccssj` | 不能缩写为 `xcchs` |
| 元数据 JSON | `ysj_json` | 不能写成 `ysjj_json` |
| 是否启用 | `sfqy` | SQLite INTEGER 0/1 |
| 是否测试 | `sfcs` | SQLite INTEGER 0/1 |
| 状态 | `zt` | 必须配置 CHECK 或受控枚举 |

命名审查时必须把名称拆开复述，例如：

```text
下(x) 次(c) 重(c) 试(s) 时(s) 间(j) → xccssj
元(y) 数(s) 据(j) + _json → ysj_json
```

## 3. 类型与约束

- ID、ULID、Git SHA、SHA-256、URL、路径、枚举和 ISO 8601 时间使用 `TEXT`。
- 计数、行号、字节数和布尔值使用 `INTEGER`；布尔值限定为 `0/1`。
- JSON 使用 `TEXT NOT NULL` 时提供合法 JSON 默认值，例如 `[]` 或 `{}`。
- 必填业务字段使用 `NOT NULL`；只有真实存在“未知/不适用/尚未产生”的字段可空。
- 状态字段使用 `CHECK` 限制合法状态；唯一业务不变量优先用数据库约束兜底。
- 每个外键明确 `ON DELETE`：事实数据通常 `RESTRICT`，快照从属数据可 `CASCADE`，可选
  追踪引用可 `SET NULL`。不得依赖 SQLite 默认行为而不记录设计理由。
- 外键连接列、队列领取条件、查询过滤和唯一性判断需要有与访问模式匹配的索引。
- 索引名使用稳定英文结构：`idx_<table-or-domain>_<columns-or-purpose>`。

## 4. 迁移规则

- 文件名使用三位递增序号：`NNN_<english_description>.sql`。
- 已被任一真实数据库登记的迁移视为不可变历史。修复字段名或约束时创建下一条迁移。
- 迁移注释使用中文，说明业务原因、兼容策略和数据保留方式。
- 能原位安全重命名时使用 `ALTER TABLE ... RENAME COLUMN`，不得丢弃已有数据。
- SQLite 需要重建表时，显式执行：新表建模、数据复制、行数核对、旧表替换、索引/触发器
  重建和外键检查；先在临时数据库验证。
- FTS5 是可重建派生索引。字段变化时从 `chunks` 事实表全量重建，并验证检索结果。
- 为已有数据增加唯一约束前，先查询重复项；发现冲突时停止并报告，不能静默删除或合并。
- 迁移通过应用的 `SqliteStore.initialize()` / `ragctl init-db` 执行并登记，不手工只执行一半。

## 5. 运行库升级

1. 从 `config/default.yaml` 和环境覆盖确认实际数据库路径。
2. 只读检查 `schema_migrations`、`PRAGMA table_info`、重复数据和 `foreign_key_check`。
3. 使用 SQLite Backup API 创建带时间戳的同目录备份；不要在 WAL 活跃时只复制主 `.db`。
4. 运行正常初始化入口应用迁移。
5. 核对迁移记录、字段、索引 SQL、外键、行数、JSON 可解析性、FTS 检索和业务查询。
   `chunks` 与 `chunks_fts` 必须按分片编号一一对应，不得存在缺失、孤儿或重复 FTS 行。
6. 执行 `PRAGMA foreign_key_check` 与 `PRAGMA integrity_check`。
7. 明确报告实际库路径、备份路径、迁移版本和验证结果。

## 6. 代码与测试同步

数据库变更至少审查：

- `src/rag/domain/models.py` 和 `ports.py`
- `src/rag/infrastructure/sqlite_store.py`
- `migrations/`
- `DATABASE_SCHEMA_PINYIN.md`
- `tests/integration/test_sqlite_store.py`
- API/CLI/Worker 中使用该字段的业务流程

测试必须覆盖新建空库、从上一版本升级、数据保留、约束拒绝、索引存在、外键完整性和关键
业务不变量。物理字段集合应使用精确集合断言，防止错误字段长期残留。
