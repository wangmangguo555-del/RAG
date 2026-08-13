from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_script() -> ModuleType:
    script = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "sync-readme-structure"
        / "scripts"
        / "sync_readme_structure.py"
    )
    spec = importlib.util.spec_from_file_location("sync_readme_structure", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_structure_sync_detects_and_updates_new_directory(tmp_path: Path) -> None:
    module = _load_script()
    (tmp_path / "README.md").write_text(
        f"# Demo\n\n{module.BEGIN}\n```text\nold\n```\n{module.END}\n\nHand-authored text.\n",
        encoding="utf-8",
    )
    (tmp_path / "services" / "api").mkdir(parents=True)
    (tmp_path / "services" / "api" / "main.py").write_text("", encoding="utf-8")

    assert module.update_readme(tmp_path, check=True) == 1
    assert module.update_readme(tmp_path, check=False) == 0
    assert module.update_readme(tmp_path, check=True) == 0

    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "services/" in readme
    assert "main.py" in readme
    assert "Hand-authored text." in readme


def test_structure_sync_rejects_missing_markers(tmp_path: Path) -> None:
    module = _load_script()
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    assert module.update_readme(tmp_path, check=False) == 2
