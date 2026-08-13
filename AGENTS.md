# Project instructions

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
