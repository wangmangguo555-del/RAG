from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

EXPECTED_COLUMNS: dict[str, set[str]] = {
    "schema_migrations": {"bb", "yysj"},
    "repositories": {
        "bh", "mc", "lylx", "lydz", "mryy", "sfqy", "bhx_json", "pcx_json", "cjsj", "gxsj"
    },
    "snapshots": {
        "bh", "zsybh", "bbhs", "sybb", "zt", "tjxx_json", "cwxx", "cjsj", "fbsj"
    },
    "files": {"kzbh", "lj", "dxhs", "yy", "jxzt", "nrzjs"},
    "chunks": {
        "bh", "xldbh", "kzbh", "zsybh", "bbhs", "lj", "yy", "fh", "jdlx", "qsh", "jsh",
        "nr", "xlwb", "nrhs", "sfcs", "ysj_json"
    },
    "chunks_fts": {"fpbh", "kzbh", "zsybh", "lj", "fh", "nr"},
    "index_jobs": {
        "bh", "zsybh", "qqyy", "yjxbbhs", "zt", "cscs", "cwdm", "cwxx", "cjsj", "kssj",
        "jssj", "xtsj", "xccssj", "kzbh"
    },
}

REQUIRED_INDEXES = {
    "idx_jobs_status_created",
    "idx_jobs_status_retry_created",
    "idx_snapshots_one_published_per_repo",
}


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def audit(database: Path) -> list[str]:
    errors: list[str] = []
    if not database.is_file():
        return [f"Database does not exist: {database}"]

    with sqlite3.connect(database) as connection:
        for table, expected in EXPECTED_COLUMNS.items():
            actual = _columns(connection, table)
            if actual != expected:
                errors.append(
                    f"{table} column mismatch: missing={sorted(expected - actual)}, "
                    f"unexpected={sorted(actual - expected)}"
                )

        indexes = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name IS NOT NULL"
            )
        }
        missing_indexes = REQUIRED_INDEXES - indexes
        if missing_indexes:
            errors.append(f"Missing indexes: {sorted(missing_indexes)}")

        duplicate_published = list(
            connection.execute(
                """
                SELECT zsybh, COUNT(*) FROM snapshots
                WHERE zt='published' GROUP BY zsybh HAVING COUNT(*) > 1
                """
            )
        )
        if duplicate_published:
            errors.append(f"Duplicate published snapshots: {duplicate_published}")

        missing_fts = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM chunks c
                LEFT JOIN chunks_fts f ON f.fpbh=c.bh
                WHERE f.fpbh IS NULL
                """
            ).fetchone()[0]
        )
        orphan_fts = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM chunks_fts f
                LEFT JOIN chunks c ON c.bh=f.fpbh
                WHERE c.bh IS NULL
                """
            ).fetchone()[0]
        )
        duplicate_fts = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT fpbh FROM chunks_fts GROUP BY fpbh HAVING COUNT(*) <> 1
                )
                """
            ).fetchone()[0]
        )
        if missing_fts or orphan_fts or duplicate_fts:
            errors.append(
                "FTS consistency failed: "
                f"missing={missing_fts}, orphan={orphan_fts}, duplicate={duplicate_fts}"
            )

        foreign_key_errors = list(connection.execute("PRAGMA foreign_key_check"))
        if foreign_key_errors:
            errors.append(f"Foreign key check failed: {foreign_key_errors[:20]}")

        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            errors.append(f"Integrity check failed: {integrity}")

        invalid_json = 0
        for (raw_metadata,) in connection.execute("SELECT ysj_json FROM chunks"):
            try:
                value = json.loads(str(raw_metadata))
            except (TypeError, json.JSONDecodeError):
                invalid_json += 1
                continue
            if not isinstance(value, dict):
                invalid_json += 1
        if invalid_json:
            errors.append(f"chunks.ysj_json has {invalid_json} invalid JSON objects")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Local RAG SQLite schema and integrity")
    parser.add_argument(
        "--database", type=Path, default=Path("data/sqlite/rag.db"),
        help="SQLite database path to audit"
    )
    args = parser.parse_args()
    database = args.database.resolve()
    errors = audit(database)
    if errors:
        print(f"Database audit failed: {database}", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Database audit passed: {database}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
