from __future__ import annotations

import argparse
import sys
from pathlib import Path

BEGIN = "<!-- BEGIN AUTO-GENERATED: PROJECT-STRUCTURE -->"
END = "<!-- END AUTO-GENERATED: PROJECT-STRUCTURE -->"

ROOT_FILES = (
    "AGENTS.md",
    ".env.example",
    ".ragignore.example",
    "pyproject.toml",
    "README.md",
    "start.bat",
    "start.ps1",
)
IGNORED_NAMES = {
    ".cache",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tools",
    ".venv",
    "__pycache__",
    "data",
    "htmlcov",
    "node_modules",
}

DESCRIPTIONS = {
    "config": "应用配置与日志配置",
    "evals": "评估问题和预期证据",
    "migrations": "SQLite schema 与迁移",
    "prompts": "回答约束与 evidence 模板",
    "scripts": "Windows/Linux 启动和运维脚本",
    "skills": "项目专用 Codex 技能",
    "src/rag": "RAG 主程序包",
    "src/rag/api": "FastAPI 路由、DTO、依赖和异常映射",
    "src/rag/application": "索引与查询应用用例",
    "src/rag/cli": "ragctl 命令入口",
    "src/rag/domain": "领域模型、端口和错误",
    "src/rag/generation": "Prompt 构建与引用校验",
    "src/rag/infrastructure": "模型、Qdrant、SQLite 和配置 adapter",
    "src/rag/ingestion": "知识源、过滤与结构化切分",
    "src/rag/retrieval": "RRF 融合、多样性与证据上下文",
    "src/rag/worker": "SQLite 索引任务消费者",
    "tests": "单元测试、集成测试和 fixtures",
    "AGENTS.md": "项目级 Codex 执行规则",
    "pyproject.toml": "项目元数据、依赖与工具配置",
    "README.md": "项目入口与架构说明",
    "start.bat": "Windows 一键启动入口",
    "start.ps1": "Windows 启动编排脚本",
}


def _included(path: Path) -> bool:
    return not any(part in IGNORED_NAMES or part.startswith(".") for part in path.parts)


def _children(path: Path) -> list[Path]:
    return sorted(
        (child for child in path.iterdir() if _included(Path(child.name))),
        key=lambda item: (item.is_file(), item.name.casefold()),
    )


def _description(relative: str) -> str:
    value = DESCRIPTIONS.get(relative)
    return f"  # {value}" if value else ""


def _render_entry(root: Path, path: Path, prefix: str, is_last: bool, lines: list[str]) -> None:
    relative = path.relative_to(root).as_posix()
    connector = "└─ " if is_last else "├─ "
    suffix = "/" if path.is_dir() else ""
    lines.append(f"{prefix}{connector}{path.name}{suffix}{_description(relative)}")
    if not path.is_dir():
        return
    children = _children(path)
    next_prefix = prefix + ("   " if is_last else "│  ")
    for index, child in enumerate(children):
        _render_entry(root, child, next_prefix, index == len(children) - 1, lines)


def render_tree(root: Path) -> str:
    entries = [child for child in root.iterdir() if child.is_dir() and _included(Path(child.name))]
    entries.extend(root / name for name in ROOT_FILES if (root / name).exists())
    entries.sort(key=lambda item: (item.is_file(), item.name.casefold()))
    lines = [f"{root.name}/"]
    for index, entry in enumerate(entries):
        _render_entry(root, entry, "", index == len(entries) - 1, lines)
    return "\n".join(lines)


def managed_block(root: Path) -> str:
    return f"{BEGIN}\n```text\n{render_tree(root)}\n```\n{END}"


def update_readme(root: Path, *, check: bool) -> int:
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8")
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        print("README structure markers must each occur exactly once.", file=sys.stderr)
        return 2
    start = text.index(BEGIN)
    finish = text.index(END, start) + len(END)
    expected = text[:start] + managed_block(root) + text[finish:]
    if expected == text:
        print("README project structure is up to date.")
        return 0
    if check:
        print("README project structure is stale.", file=sys.stderr)
        return 1
    readme.write_text(expected, encoding="utf-8", newline="\n")
    print("Updated README project structure.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize README project structure.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Workspace root")
    parser.add_argument("--check", action="store_true", help="Check without writing")
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root / "README.md").is_file():
        parser.error(f"README.md not found under {root}")
    return update_readme(root, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
