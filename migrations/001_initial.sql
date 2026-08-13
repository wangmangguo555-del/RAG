CREATE TABLE IF NOT EXISTS repositories (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_uri TEXT NOT NULL,
  default_ref TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  include_json TEXT NOT NULL DEFAULT '[]',
  exclude_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
  id TEXT PRIMARY KEY,
  repo_id TEXT NOT NULL REFERENCES repositories(id),
  commit_sha TEXT NOT NULL,
  index_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN
    ('pending','running','validating','published','failed','superseded')),
  stats_json TEXT,
  error_message TEXT,
  created_at TEXT NOT NULL,
  published_at TEXT,
  UNIQUE(repo_id, commit_sha, index_version)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_repo_status
  ON snapshots(repo_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS files (
  snapshot_id TEXT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  blob_sha TEXT NOT NULL,
  language TEXT NOT NULL,
  parse_status TEXT NOT NULL,
  content_bytes INTEGER NOT NULL,
  PRIMARY KEY(snapshot_id, path)
);

CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY,
  point_id TEXT NOT NULL UNIQUE,
  snapshot_id TEXT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
  repo_id TEXT NOT NULL,
  commit_sha TEXT NOT NULL,
  path TEXT NOT NULL,
  language TEXT NOT NULL,
  symbol TEXT,
  node_type TEXT NOT NULL,
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  content TEXT NOT NULL,
  embedding_text TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  is_test INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_snapshot ON chunks(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_chunks_repo_path ON chunks(repo_id, path);
CREATE INDEX IF NOT EXISTS idx_chunks_content_hash ON chunks(content_hash);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  chunk_id UNINDEXED,
  snapshot_id UNINDEXED,
  repo_id UNINDEXED,
  path,
  symbol,
  content,
  tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS index_jobs (
  id TEXT PRIMARY KEY,
  repo_id TEXT NOT NULL REFERENCES repositories(id),
  requested_ref TEXT NOT NULL,
  resolved_commit_sha TEXT,
  status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','failed')),
  attempt INTEGER NOT NULL DEFAULT 0,
  error_code TEXT,
  error_message TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  heartbeat_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_created
  ON index_jobs(status, created_at);
