-- “下次重试时间”的完整拼音首字母应为 xccssj。
-- 003 中的 xcchs 遗漏“时”的首字母 s，本迁移保留原字段数据并原位更名。

ALTER TABLE index_jobs RENAME COLUMN xcchs TO xccssj;
