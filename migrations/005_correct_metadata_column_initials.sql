-- “元数据”的拼音首字母为 ysj，格式后缀统一保留为 _json。
-- 002 中的 ysjj_json 在格式后缀前重复了字母 j，本迁移原位更名并保留元数据内容。

ALTER TABLE chunks RENAME COLUMN ysjj_json TO ysj_json;
