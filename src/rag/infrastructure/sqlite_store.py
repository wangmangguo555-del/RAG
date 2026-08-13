from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import aiosqlite
import ulid

from rag.domain.models import (
    Chunk,
    IndexJob,
    JobStatus,
    Repository,
    SearchFilter,
    SearchHit,
    SourceType,
)
from rag.infrastructure.settings import SqliteSettings


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _id() -> str:
    return str(ulid.new())


class SqliteStore:
    def __init__(self, settings: SqliteSettings) -> None:
        self.settings = settings

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self.settings.path) as connection:
            connection.row_factory = aiosqlite.Row
            await connection.execute("PRAGMA foreign_keys=ON")
            await connection.execute(f"PRAGMA busy_timeout={self.settings.busy_timeout_ms}")
            yield connection

    async def initialize(self) -> None:
        self.settings.path.parent.mkdir(parents=True, exist_ok=True)
        async with self._connect() as connection:
            await connection.execute("PRAGMA journal_mode=WAL")
            await connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (bb TEXT PRIMARY KEY, yysj TEXT NOT NULL)"
            )
            columns = {
                str(row["name"])
                for row in await (
                    await connection.execute("PRAGMA table_info(schema_migrations)")
                ).fetchall()
            }
            if "version" in columns:
                await connection.execute(
                    "ALTER TABLE schema_migrations RENAME COLUMN version TO bb"
                )
            if "applied_at" in columns:
                await connection.execute(
                    "ALTER TABLE schema_migrations RENAME COLUMN applied_at TO yysj"
                )
            await connection.commit()
            for migration in sorted(self.settings.migrations_dir.glob("*.sql")):
                cursor = await connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE bb=?", (migration.name,)
                )
                if await cursor.fetchone():
                    continue
                await connection.executescript(migration.read_text(encoding="utf-8"))
                await connection.execute(
                    "INSERT INTO schema_migrations(bb, yysj) VALUES (?, ?)",
                    (migration.name, _now()),
                )
                await connection.commit()

    async def health(self) -> bool:
        try:
            async with self._connect() as connection:
                cursor = await connection.execute("SELECT 1")
                row = await cursor.fetchone()
                return bool(row and row[0] == 1)
        except (aiosqlite.Error, OSError):
            return False

    async def register_repository(self, repository: Repository) -> None:
        now = _now()
        async with self._connect() as connection:
            await connection.execute(
                """
                INSERT INTO repositories(
                    bh,mc,lylx,lydz,mryy,sfqy,bhx_json,pcx_json,cjsj,gxsj
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(bh) DO UPDATE SET
                    mc=excluded.mc, lylx=excluded.lylx, lydz=excluded.lydz,
                    mryy=excluded.mryy, sfqy=excluded.sfqy,
                    bhx_json=excluded.bhx_json, pcx_json=excluded.pcx_json,
                    gxsj=excluded.gxsj
                """,
                (
                    repository.id,
                    repository.name,
                    repository.source_type.value,
                    repository.source_uri,
                    repository.default_ref,
                    int(repository.enabled),
                    json.dumps(repository.include),
                    json.dumps(repository.exclude),
                    now,
                    now,
                ),
            )
            await connection.commit()

    @staticmethod
    def _repository_from_row(row: aiosqlite.Row) -> Repository:
        return Repository(
            id=row["bh"],
            name=row["mc"],
            source_type=SourceType(row["lylx"]),
            source_uri=row["lydz"],
            default_ref=row["mryy"],
            enabled=bool(row["sfqy"]),
            include=tuple(json.loads(row["bhx_json"])),
            exclude=tuple(json.loads(row["pcx_json"])),
        )

    async def get_repository(self, repo_id: str) -> Repository | None:
        async with self._connect() as connection:
            cursor = await connection.execute("SELECT * FROM repositories WHERE bh=?", (repo_id,))
            row = await cursor.fetchone()
            return self._repository_from_row(row) if row else None

    async def list_repositories(self) -> list[Repository]:
        async with self._connect() as connection:
            cursor = await connection.execute("SELECT * FROM repositories ORDER BY bh")
            return [self._repository_from_row(row) for row in await cursor.fetchall()]

    async def create_job(self, repo_id: str, requested_ref: str) -> str:
        job_id = _id()
        async with self._connect() as connection:
            await connection.execute(
                """
                INSERT INTO index_jobs(bh,zsybh,qqyy,zt,cjsj)
                VALUES (?,?,?,?,?)
                """,
                (job_id, repo_id, requested_ref, JobStatus.PENDING.value, _now()),
            )
            await connection.commit()
        return job_id

    @staticmethod
    def _job_from_row(row: aiosqlite.Row | dict[str, Any]) -> IndexJob:
        return IndexJob(
            id=row["bh"],
            repo_id=row["zsybh"],
            requested_ref=row["qqyy"],
            status=JobStatus(row["zt"]),
            resolved_commit_sha=row["yjxbbhs"],
            error_code=row["cwdm"],
            error_message=row["cwxx"],
        )

    async def claim_next_job(self) -> IndexJob | None:
        async with self._connect() as connection:
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT * FROM index_jobs WHERE zt='pending' ORDER BY cjsj LIMIT 1"
            )
            row = await cursor.fetchone()
            if not row:
                await connection.rollback()
                return None
            await connection.execute(
                """
                UPDATE index_jobs SET zt='running', cscs=cscs+1,
                    kssj=?, xtsj=? WHERE bh=? AND zt='pending'
                """,
                (_now(), _now(), row["bh"]),
            )
            await connection.commit()
            updated = dict(row)
            updated["zt"] = JobStatus.RUNNING.value
            return self._job_from_row(updated)

    async def get_job(self, job_id: str) -> IndexJob | None:
        async with self._connect() as connection:
            cursor = await connection.execute("SELECT * FROM index_jobs WHERE bh=?", (job_id,))
            row = await cursor.fetchone()
            return self._job_from_row(row) if row else None

    async def complete_job(
        self,
        job_id: str,
        *,
        success: bool,
        commit_sha: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        status = JobStatus.SUCCEEDED if success else JobStatus.FAILED
        async with self._connect() as connection:
            await connection.execute(
                """
                UPDATE index_jobs SET zt=?, yjxbbhs=?, cwdm=?,
                    cwxx=?, jssj=?, xtsj=? WHERE bh=?
                """,
                (status.value, commit_sha, error_code, error_message, _now(), _now(), job_id),
            )
            await connection.commit()

    async def create_snapshot(self, repo_id: str, commit_sha: str, index_version: str) -> str:
        async with self._connect() as connection:
            cursor = await connection.execute(
                """
                SELECT bh,zt FROM snapshots
                WHERE zsybh=? AND bbhs=? AND sybb=?
                """,
                (repo_id, commit_sha, index_version),
            )
            existing = await cursor.fetchone()
            if existing:
                if existing["zt"] != "failed":
                    raise ValueError(
                        f"snapshot already exists with status {existing['zt']}: {existing['bh']}"
                    )
                snapshot_id = str(existing["bh"])
                await connection.execute("BEGIN IMMEDIATE")
                await connection.execute("DELETE FROM chunks_fts WHERE kzbh=?", (snapshot_id,))
                await connection.execute("DELETE FROM chunks WHERE kzbh=?", (snapshot_id,))
                await connection.execute("DELETE FROM files WHERE kzbh=?", (snapshot_id,))
                await connection.execute(
                    """
                    UPDATE snapshots SET zt='running', tjxx_json=NULL,
                        cwxx=NULL, cjsj=?, fbsj=NULL WHERE bh=?
                    """,
                    (_now(), snapshot_id),
                )
                await connection.commit()
                return snapshot_id
            snapshot_id = _id()
            await connection.execute(
                """
                INSERT INTO snapshots(bh,zsybh,bbhs,sybb,zt,cjsj)
                VALUES (?,?,?,?,?,?)
                """,
                (snapshot_id, repo_id, commit_sha, index_version, "running", _now()),
            )
            await connection.commit()
        return snapshot_id

    async def find_published_snapshot(
        self, repo_id: str, commit_sha: str, index_version: str
    ) -> str | None:
        async with self._connect() as connection:
            cursor = await connection.execute(
                """
                SELECT bh FROM snapshots
                WHERE zsybh=? AND bbhs=? AND sybb=? AND zt='published'
                LIMIT 1
                """,
                (repo_id, commit_sha, index_version),
            )
            row = await cursor.fetchone()
            return row["bh"] if row else None

    async def publish_snapshot(self, snapshot_id: str, stats: dict[str, int]) -> None:
        async with self._connect() as connection:
            cursor = await connection.execute(
                "SELECT zsybh FROM snapshots WHERE bh=?", (snapshot_id,)
            )
            row = await cursor.fetchone()
            if not row:
                raise ValueError(f"snapshot not found: {snapshot_id}")
            await connection.execute("BEGIN IMMEDIATE")
            await connection.execute(
                "UPDATE snapshots SET zt='superseded' WHERE zsybh=? AND zt='published'",
                (row["zsybh"],),
            )
            await connection.execute(
                """
                UPDATE snapshots SET zt='published', tjxx_json=?, fbsj=? WHERE bh=?
                """,
                (json.dumps(stats), _now(), snapshot_id),
            )
            await connection.commit()

    async def fail_snapshot(self, snapshot_id: str, message: str) -> None:
        async with self._connect() as connection:
            await connection.execute(
                "UPDATE snapshots SET zt='failed', cwxx=? WHERE bh=?",
                (message[:2000], snapshot_id),
            )
            await connection.commit()

    async def get_published_snapshot(self, repo_id: str) -> str | None:
        async with self._connect() as connection:
            cursor = await connection.execute(
                """
                SELECT bh FROM snapshots WHERE zsybh=? AND zt='published'
                ORDER BY fbsj DESC LIMIT 1
                """,
                (repo_id,),
            )
            row = await cursor.fetchone()
            return row["bh"] if row else None

    async def save_file(
        self,
        snapshot_id: str,
        *,
        path: str,
        blob_sha: str,
        language: str,
        parse_status: str,
        content_bytes: int,
    ) -> None:
        async with self._connect() as connection:
            await connection.execute(
                """
                INSERT OR REPLACE INTO files(
                    kzbh,lj,dxhs,yy,jxzt,nrzjs
                ) VALUES (?,?,?,?,?,?)
                """,
                (snapshot_id, path, blob_sha, language, parse_status, content_bytes),
            )
            await connection.commit()

    async def save_chunks(self, chunks: Sequence[Chunk]) -> None:
        if not chunks:
            return
        async with self._connect() as connection:
            await connection.execute("BEGIN")
            for chunk in chunks:
                await connection.execute(
                    """
                    INSERT OR REPLACE INTO chunks(
                        bh,xldbh,kzbh,zsybh,bbhs,lj,yy,fh,jdlx,qsh,jsh,nr,xlwb,nrhs,
                        sfcs,ysjj_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        chunk.id,
                        chunk.point_id,
                        chunk.snapshot_id,
                        chunk.repo_id,
                        chunk.commit_sha,
                        chunk.path,
                        chunk.language,
                        chunk.symbol,
                        chunk.node_type,
                        chunk.start_line,
                        chunk.end_line,
                        chunk.content,
                        chunk.embedding_text,
                        chunk.content_hash,
                        int(chunk.is_test),
                        json.dumps(chunk.metadata, ensure_ascii=False),
                    ),
                )
                await connection.execute("DELETE FROM chunks_fts WHERE fpbh=?", (chunk.id,))
                await connection.execute(
                    """
                    INSERT INTO chunks_fts(fpbh,kzbh,zsybh,lj,fh,nr)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (
                        chunk.id,
                        chunk.snapshot_id,
                        chunk.repo_id,
                        chunk.path,
                        chunk.symbol or "",
                        chunk.content,
                    ),
                )
            await connection.commit()

    async def get_chunks(self, chunk_ids: Sequence[str]) -> dict[str, Chunk]:
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" for _ in chunk_ids)
        async with self._connect() as connection:
            cursor = await connection.execute(
                f"SELECT * FROM chunks WHERE bh IN ({placeholders})", tuple(chunk_ids)
            )
            rows = await cursor.fetchall()
        return {row["bh"]: self._chunk_from_row(row) for row in rows}

    @staticmethod
    def _chunk_from_row(row: aiosqlite.Row) -> Chunk:
        return Chunk(
            id=row["bh"],
            point_id=row["xldbh"],
            repo_id=row["zsybh"],
            snapshot_id=row["kzbh"],
            commit_sha=row["bbhs"],
            path=row["lj"],
            language=row["yy"],
            content=row["nr"],
            embedding_text=row["xlwb"],
            content_hash=row["nrhs"],
            start_line=row["qsh"],
            end_line=row["jsh"],
            symbol=row["fh"],
            node_type=row["jdlx"],
            is_test=bool(row["sfcs"]),
            metadata=json.loads(row["ysjj_json"]),
        )

    async def search_lexical(
        self,
        query: str,
        snapshot_ids: Sequence[str],
        filters: SearchFilter,
        limit: int,
    ) -> list[SearchHit]:
        fts_query = _fts_query(query)
        if not fts_query or not snapshot_ids:
            return []
        where = ["chunks_fts MATCH ?"]
        params: list[Any] = [fts_query]
        where.append(f"c.kzbh IN ({','.join('?' for _ in snapshot_ids)})")
        params.extend(snapshot_ids)
        if filters.languages:
            where.append(f"c.yy IN ({','.join('?' for _ in filters.languages)})")
            params.extend(filters.languages)
        if filters.path_prefixes:
            where.append("(" + " OR ".join("c.lj LIKE ?" for _ in filters.path_prefixes) + ")")
            params.extend(f"{prefix}%" for prefix in filters.path_prefixes)
        params.append(limit)
        sql = f"""
            SELECT c.*, bm25(chunks_fts,0.0,0.0,0.0,3.0,5.0,1.0) AS rank
            FROM chunks_fts JOIN chunks c ON c.bh=chunks_fts.fpbh
            WHERE {" AND ".join(where)}
            ORDER BY rank LIMIT ?
        """
        async with self._connect() as connection:
            cursor = await connection.execute(sql, tuple(params))
            rows = await cursor.fetchall()
        return [
            SearchHit(
                chunk_id=row["bh"],
                repo_id=row["zsybh"],
                snapshot_id=row["kzbh"],
                commit_sha=row["bbhs"],
                path=row["lj"],
                start_line=row["qsh"],
                end_line=row["jsh"],
                score=1.0 / (1.0 + max(0.0, float(row["rank"]))),
                source="lexical",
                language=row["yy"],
                symbol=row["fh"],
                content=row["nr"],
                content_hash=row["nrhs"],
                metadata=json.loads(row["ysjj_json"]),
            )
            for row in rows
        ]


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[\w./:@-]+", query, flags=re.UNICODE)
    return " OR ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens[:20])
