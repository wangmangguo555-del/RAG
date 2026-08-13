from __future__ import annotations

from collections.abc import Sequence

from rag.domain.models import Chunk


def build_context(chunks: Sequence[Chunk], token_budget: int) -> tuple[str, dict[str, Chunk]]:
    evidence: list[str] = []
    mapping: dict[str, Chunk] = {}
    used_tokens = 0
    for index, chunk in enumerate(chunks, start=1):
        evidence_id = f"E{index}"
        block = (
            f'<evidence id="{evidence_id}" repo="{chunk.repo_id}" path="{chunk.path}" '
            f'lines="{chunk.start_line}-{chunk.end_line}" commit="{chunk.commit_sha}">\n'
            f"{chunk.content}\n</evidence>"
        )
        estimated_tokens = max(1, len(block) // 3)
        if evidence and used_tokens + estimated_tokens > token_budget:
            break
        evidence.append(block)
        mapping[evidence_id] = chunk
        used_tokens += estimated_tokens
    return "\n\n".join(evidence), mapping
