-- 阶段 A：为单 Worker 增加可恢复重试时间。
-- 心跳字段 xtsj 已存在；xcchs 用于防止模型故障时立即形成忙循环。

ALTER TABLE index_jobs ADD COLUMN xcchs TEXT;
ALTER TABLE index_jobs ADD COLUMN kzbh TEXT REFERENCES snapshots(bh) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_jobs_status_retry_created
  ON index_jobs(zt, xcchs, cjsj);

-- 数据库层兜底保证每个知识源最多只有一个 published 快照。
CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshots_one_published_per_repo
  ON snapshots(zsybh) WHERE zt='published';
