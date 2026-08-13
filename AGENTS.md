# Project instructions

## Database governance

- Use the `rag-database-governance` skill before any task that creates, renames, deletes, reviews, or
  changes a SQLite table, field, index, foreign key, constraint, migration, schema document, or
  persistence query.
- Physical SQLite fields must use the exact pinyin initials of the Chinese business full name. Write
  the Chinese full name and its character-by-character initials before accepting a new field name.
- Preserve English table names and English Python/API contracts unless the user explicitly requests
  an interface change.
- Never rewrite an already-applied migration to hide a schema error. Add the next numbered migration,
  preserve data, update `DATABASE_SCHEMA_PINYIN.md`, and add upgrade/fresh-database tests.
- When applying a migration to `data/sqlite/rag.db`, create a SQLite online backup first and finish
  with the skill audit, `PRAGMA foreign_key_check`, and `PRAGMA integrity_check`.

## README structure synchronization

- Use the `sync-readme-structure` skill whenever a task creates, deletes, renames, or moves any
  project directory or an architecture-significant file. This includes new top-level business
  directories and changes under `config/`, `evals/`, `migrations/`, `prompts/`, `scripts/`, `src/`,
  `tests/`, or `skills/`.
- After completing such filesystem changes, run:

  ```powershell
  python skills/sync-readme-structure/scripts/sync_readme_structure.py --root .
  python skills/sync-readme-structure/scripts/sync_readme_structure.py --root . --check
  ```

- Do not finish the task while the `--check` command reports that `README.md` is stale.
- The generated script may edit only the marked project-structure block in `README.md`; preserve all
  hand-authored architecture content outside that block.
