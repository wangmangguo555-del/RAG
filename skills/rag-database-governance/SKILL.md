---
name: rag-database-governance
description: Govern this project's SQLite schema, physical field naming, constraints, indexes, migrations, runtime database upgrades, schema documentation, and persistence adapter changes. Use whenever a task creates, renames, removes, reviews, or changes a database table, column, index, foreign key, CHECK constraint, migration SQL file, SQLite query, schema document, or database-backed domain field.
---

# RAG Database Governance

Apply database changes as a DBA-managed migration, not as an isolated SQL or Python edit.

## Required context

Before designing or changing a schema, read all of:

1. [references/database-rules.md](references/database-rules.md)
2. `DATABASE_SCHEMA_PINYIN.md`
3. Every migration in `migrations/`, in filename order
4. The affected code in `src/rag/infrastructure/sqlite_store.py`, domain models/ports, and tests

Do not infer a physical field name until its Chinese business full name and initials have been
written explicitly. For example, `下次重试时间 → xccssj`, not `xcchs`.

## Workflow

1. Inspect the configured database path and current schema/migration history read-only.
2. Define the business meaning, Chinese full name, physical field name, type, nullability, default,
   key/constraint, index need, deletion behavior, and compatibility impact.
3. Check the proposed field name character by character against the naming rules. Preserve English
   table names and public Python/API names unless the task explicitly changes those contracts.
4. Add a new sequential migration. Never edit the effect of a migration already recorded in a real
   database; repair mistakes with a later migration.
5. Update the SQLite adapter, domain model/ports, configuration, schema document, and tests in the
   same change. Rebuild FTS5 deliberately when its physical columns change.
6. Run unit/integration tests, Ruff, strict MyPy, and the audit script:

   ```powershell
   .\.venv\Scripts\python.exe skills/rag-database-governance/scripts/audit_database.py `
     --database data/sqlite/rag.db
   ```

7. When the request includes applying the database change and the configured database exists:
   create a SQLite online backup, check migration preconditions, run the normal `ragctl init-db`
   entry point, then rerun the audit. Never apply a migration directly without a recoverable backup.
8. Invoke `sync-readme-structure` after adding or renaming migrations, scripts, tests, or skill files.

## Release gate

Do not report completion unless all applicable conditions hold:

- the migration is forward-only and idempotently tracked by `schema_migrations`;
- physical names match the Chinese initials rule exactly;
- primary keys, foreign keys, CHECK constraints, unique constraints, indexes, and delete behavior are
  explicit and tested;
- `PRAGMA foreign_key_check` is empty and `PRAGMA integrity_check` returns `ok`;
- existing row counts and serialized JSON remain valid after migration;
- current and fresh databases converge to the same final schema;
- `DATABASE_SCHEMA_PINYIN.md` and README's managed project tree are current;
- no previous migration file was rewritten to hide a production migration mistake.

If a live database is intentionally not upgraded, state that clearly and provide the exact pending
migration and validation command.
