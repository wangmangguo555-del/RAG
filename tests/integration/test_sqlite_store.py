import sqlite3
from pathlib import Path

import pytest

from rag.domain.models import Chunk, Repository, SearchFilter, SourceType
from rag.infrastructure.settings import SqliteSettings
from rag.infrastructure.sqlite_store import SqliteStore

EXPECTED_PINYIN_COLUMNS = {
    "schema_migrations": {"bb", "yysj"},
    "repositories": {
        "bh",
        "mc",
        "lylx",
        "lydz",
        "mryy",
        "sfqy",
        "bhx_json",
        "pcx_json",
        "cjsj",
        "gxsj",
    },
    "snapshots": {"bh", "zsybh", "bbhs", "sybb", "zt", "tjxx_json", "cwxx", "cjsj", "fbsj"},
    "files": {"kzbh", "lj", "dxhs", "yy", "jxzt", "nrzjs"},
    "chunks": {
        "bh",
        "xldbh",
        "kzbh",
        "zsybh",
        "bbhs",
        "lj",
        "yy",
        "fh",
        "jdlx",
        "qsh",
        "jsh",
        "nr",
        "xlwb",
        "nrhs",
        "sfcs",
        "ysjj_json",
    },
    "chunks_fts": {"fpbh", "kzbh", "zsybh", "lj", "fh", "nr"},
    "index_jobs": {
        "bh",
        "zsybh",
        "qqyy",
        "yjxbbhs",
        "zt",
        "cscs",
        "cwdm",
        "cwxx",
        "cjsj",
        "kssj",
        "jssj",
        "xtsj",
    },
}


def _columns(database: Path, table: str) -> set[str]:
    with sqlite3.connect(database) as connection:
        return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


@pytest.mark.asyncio
async def test_repository_snapshot_chunk_and_fts(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[2] / "migrations"
    store = SqliteStore(SqliteSettings(path=tmp_path / "rag.db", migrations_dir=migrations))
    await store.initialize()
    repo = Repository("demo", "Demo", SourceType.WORKING_TREE, str(tmp_path), "HEAD")
    await store.register_repository(repo)
    snapshot = await store.create_snapshot("demo", "a" * 40, "v1")
    chunk = Chunk(
        id="chunk-1",
        point_id="00000000-0000-0000-0000-000000000001",
        repo_id="demo",
        snapshot_id=snapshot,
        commit_sha="a" * 40,
        path="src/auth.py",
        language="python",
        content="def refresh_token(): return True",
        embedding_text="def refresh_token(): return True",
        content_hash="hash-1",
        start_line=1,
        end_line=1,
        symbol="refresh_token",
    )
    await store.save_chunks([chunk])
    await store.publish_snapshot(snapshot, {"files": 1, "chunks": 1})

    hits = await store.search_lexical(
        "refresh_token", [snapshot], SearchFilter(repo_ids=("demo",)), 5
    )
    assert len(hits) == 1
    assert hits[0].chunk_id == "chunk-1"
    assert await store.get_published_snapshot("demo") == snapshot
    assert await store.find_published_snapshot("demo", "a" * 40, "v1") == snapshot


@pytest.mark.asyncio
async def test_failed_snapshot_can_be_retried(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[2] / "migrations"
    store = SqliteStore(SqliteSettings(path=tmp_path / "rag.db", migrations_dir=migrations))
    await store.initialize()
    await store.register_repository(
        Repository("demo", "Demo", SourceType.WORKING_TREE, str(tmp_path), "HEAD")
    )
    first = await store.create_snapshot("demo", "b" * 40, "v1")
    await store.fail_snapshot(first, "temporary model failure")
    retried = await store.create_snapshot("demo", "b" * 40, "v1")
    assert retried == first


@pytest.mark.asyncio
async def test_schema_uses_pinyin_initial_columns(tmp_path: Path) -> None:
    migrations = Path(__file__).resolve().parents[2] / "migrations"
    database = tmp_path / "rag.db"
    store = SqliteStore(SqliteSettings(path=database, migrations_dir=migrations))
    await store.initialize()
    for table, expected in EXPECTED_PINYIN_COLUMNS.items():
        assert _columns(database, table) == expected


@pytest.mark.asyncio
async def test_english_schema_migrates_to_pinyin_without_data_loss(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    database = tmp_path / "rag.db"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            (project_root / "migrations" / "001_initial.sql").read_text(encoding="utf-8")
        )
        connection.execute(
            "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO schema_migrations(version,applied_at) VALUES (?,?)",
            ("001_initial.sql", "2026-01-01T00:00:00+00:00"),
        )
        connection.execute(
            """
            INSERT INTO repositories(
                id,name,source_type,source_uri,default_ref,enabled,
                include_json,exclude_json,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "demo",
                "Demo",
                "working_tree",
                ".",
                "HEAD",
                1,
                "[]",
                "[]",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO snapshots(
                id,repo_id,commit_sha,index_version,status,created_at,published_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                "snapshot-1",
                "demo",
                "a" * 40,
                "v1",
                "published",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:01:00+00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO chunks(
                id,point_id,snapshot_id,repo_id,commit_sha,path,language,node_type,
                start_line,end_line,content,embedding_text,content_hash,is_test,metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "chunk-1",
                "00000000-0000-0000-0000-000000000001",
                "snapshot-1",
                "demo",
                "a" * 40,
                "README.md",
                "markdown",
                "section",
                1,
                2,
                "保留内容",
                "保留内容",
                "hash-1",
                0,
                "{}",
            ),
        )
        connection.execute(
            """
            INSERT INTO chunks_fts(chunk_id,snapshot_id,repo_id,path,symbol,content)
            VALUES (?,?,?,?,?,?)
            """,
            ("chunk-1", "snapshot-1", "demo", "README.md", "", "保留内容"),
        )
        connection.commit()

    store = SqliteStore(SqliteSettings(path=database, migrations_dir=project_root / "migrations"))
    await store.initialize()

    repository = await store.get_repository("demo")
    chunks = await store.get_chunks(["chunk-1"])
    hits = await store.search_lexical(
        "保留内容", ["snapshot-1"], SearchFilter(repo_ids=("demo",)), 5
    )
    assert repository is not None and repository.name == "Demo"
    assert chunks["chunk-1"].content == "保留内容"
    assert hits and hits[0].chunk_id == "chunk-1"
    for table, expected in EXPECTED_PINYIN_COLUMNS.items():
        assert _columns(database, table) == expected
