from __future__ import annotations

from pathlib import Path


class PromptBuilder:
    def __init__(self, prompts_dir: Path) -> None:
        self.system = (prompts_dir / "answer_system.txt").read_text(encoding="utf-8").strip()
        self.template = (prompts_dir / "answer_context.txt").read_text(encoding="utf-8")

    def build(self, question: str, context: str) -> tuple[str, str]:
        return self.system, self.template.format(question=question, context=context)
