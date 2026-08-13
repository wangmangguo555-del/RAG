-- 将 SQLite 物理字段名统一调整为中文业务含义的拼音首字母。
-- 表名保持不变，避免破坏数据库对象边界；领域模型和 HTTP API 不受影响。

BEGIN IMMEDIATE;

DROP TABLE chunks_fts;

ALTER TABLE repositories RENAME COLUMN id TO bh;
ALTER TABLE repositories RENAME COLUMN name TO mc;
ALTER TABLE repositories RENAME COLUMN source_type TO lylx;
ALTER TABLE repositories RENAME COLUMN source_uri TO lydz;
ALTER TABLE repositories RENAME COLUMN default_ref TO mryy;
ALTER TABLE repositories RENAME COLUMN enabled TO sfqy;
ALTER TABLE repositories RENAME COLUMN include_json TO bhx_json;
ALTER TABLE repositories RENAME COLUMN exclude_json TO pcx_json;
ALTER TABLE repositories RENAME COLUMN created_at TO cjsj;
ALTER TABLE repositories RENAME COLUMN updated_at TO gxsj;

ALTER TABLE snapshots RENAME COLUMN id TO bh;
ALTER TABLE snapshots RENAME COLUMN repo_id TO zsybh;
ALTER TABLE snapshots RENAME COLUMN commit_sha TO bbhs;
ALTER TABLE snapshots RENAME COLUMN index_version TO sybb;
ALTER TABLE snapshots RENAME COLUMN status TO zt;
ALTER TABLE snapshots RENAME COLUMN stats_json TO tjxx_json;
ALTER TABLE snapshots RENAME COLUMN error_message TO cwxx;
ALTER TABLE snapshots RENAME COLUMN created_at TO cjsj;
ALTER TABLE snapshots RENAME COLUMN published_at TO fbsj;

ALTER TABLE files RENAME COLUMN snapshot_id TO kzbh;
ALTER TABLE files RENAME COLUMN path TO lj;
ALTER TABLE files RENAME COLUMN blob_sha TO dxhs;
ALTER TABLE files RENAME COLUMN language TO yy;
ALTER TABLE files RENAME COLUMN parse_status TO jxzt;
ALTER TABLE files RENAME COLUMN content_bytes TO nrzjs;

ALTER TABLE chunks RENAME COLUMN id TO bh;
ALTER TABLE chunks RENAME COLUMN point_id TO xldbh;
ALTER TABLE chunks RENAME COLUMN snapshot_id TO kzbh;
ALTER TABLE chunks RENAME COLUMN repo_id TO zsybh;
ALTER TABLE chunks RENAME COLUMN commit_sha TO bbhs;
ALTER TABLE chunks RENAME COLUMN path TO lj;
ALTER TABLE chunks RENAME COLUMN language TO yy;
ALTER TABLE chunks RENAME COLUMN symbol TO fh;
ALTER TABLE chunks RENAME COLUMN node_type TO jdlx;
ALTER TABLE chunks RENAME COLUMN start_line TO qsh;
ALTER TABLE chunks RENAME COLUMN end_line TO jsh;
ALTER TABLE chunks RENAME COLUMN content TO nr;
ALTER TABLE chunks RENAME COLUMN embedding_text TO xlwb;
ALTER TABLE chunks RENAME COLUMN content_hash TO nrhs;
ALTER TABLE chunks RENAME COLUMN is_test TO sfcs;
ALTER TABLE chunks RENAME COLUMN metadata_json TO ysjj_json;

CREATE VIRTUAL TABLE chunks_fts USING fts5(
  fpbh UNINDEXED,
  kzbh UNINDEXED,
  zsybh UNINDEXED,
  lj,
  fh,
  nr,
  tokenize='unicode61'
);

INSERT INTO chunks_fts(fpbh,kzbh,zsybh,lj,fh,nr)
SELECT bh,kzbh,zsybh,lj,COALESCE(fh,''),nr FROM chunks;

ALTER TABLE index_jobs RENAME COLUMN id TO bh;
ALTER TABLE index_jobs RENAME COLUMN repo_id TO zsybh;
ALTER TABLE index_jobs RENAME COLUMN requested_ref TO qqyy;
ALTER TABLE index_jobs RENAME COLUMN resolved_commit_sha TO yjxbbhs;
ALTER TABLE index_jobs RENAME COLUMN status TO zt;
ALTER TABLE index_jobs RENAME COLUMN attempt TO cscs;
ALTER TABLE index_jobs RENAME COLUMN error_code TO cwdm;
ALTER TABLE index_jobs RENAME COLUMN error_message TO cwxx;
ALTER TABLE index_jobs RENAME COLUMN created_at TO cjsj;
ALTER TABLE index_jobs RENAME COLUMN started_at TO kssj;
ALTER TABLE index_jobs RENAME COLUMN finished_at TO jssj;
ALTER TABLE index_jobs RENAME COLUMN heartbeat_at TO xtsj;

COMMIT;
