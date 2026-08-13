from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from itertools import pairwise

from rag.domain.models import Chunk, DocumentNode, SourceDocument

_NAMESPACE = uuid.UUID("5ca4bddd-1288-4887-8e8b-d1fae75559be")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_CODE_SYMBOL = re.compile(
    r"^\s*(?:async\s+)?(?:def|class|function|interface|enum|struct|func|fn)\s+([A-Za-z_$][\w$]*)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ChunkingOptions:
    target_tokens: int = 500
    max_tokens: int = 900
    min_tokens: int = 80
    overlap_tokens: int = 80
    version: str = "code-v1"


class StructuredChunker:
    def __init__(self, options: ChunkingOptions) -> None:
        self.options = options

    def chunk(self, document: SourceDocument, snapshot_id: str) -> list[Chunk]:
        nodes = self._nodes(document)
        result: list[Chunk] = []
        for node in nodes:
            for split in self._split_node(node):
                normalized = split.text.replace("\r\n", "\n").strip()
                if not normalized:
                    continue
                key = "|".join(
                    (
                        document.repo_id,
                        document.commit_sha,
                        document.path,
                        str(split.start_line),
                        str(split.end_line),
                        self.options.version,
                    )
                )
                chunk_id = hashlib.sha256(key.encode()).hexdigest()
                content_hash = hashlib.sha256(normalized.encode()).hexdigest()
                point_id = str(uuid.uuid5(_NAMESPACE, chunk_id))
                header = (
                    f"[repo] {document.repo_id}\n[path] {document.path}\n"
                    f"[symbol] {split.symbol or ''}\n[lines] {split.start_line}-{split.end_line}\n"
                    f"[language] {document.language}\n\n"
                )
                result.append(
                    Chunk(
                        id=chunk_id,
                        point_id=point_id,
                        repo_id=document.repo_id,
                        snapshot_id=snapshot_id,
                        commit_sha=document.commit_sha,
                        path=document.path,
                        language=document.language,
                        content=normalized,
                        embedding_text=header + normalized,
                        content_hash=content_hash,
                        start_line=split.start_line,
                        end_line=split.end_line,
                        symbol=split.symbol,
                        node_type=split.node_type,
                        is_test=self._is_test(document.path),
                    )
                )
        return result

    def _nodes(self, document: SourceDocument) -> list[DocumentNode]:
        lines = document.content.splitlines()
        if not lines:
            return []
        if document.language == "markdown":
            return self._markdown_nodes(lines)
        return self._code_or_text_nodes(lines, document.language)

    def _markdown_nodes(self, lines: list[str]) -> list[DocumentNode]:
        starts = [index for index, line in enumerate(lines) if _HEADING.match(line)]
        if not starts or starts[0] != 0:
            starts.insert(0, 0)
        starts.append(len(lines))
        nodes = []
        for left, right in pairwise(starts):
            text = "\n".join(lines[left:right])
            match = _HEADING.match(lines[left])
            nodes.append(
                DocumentNode(
                    text=text,
                    start_line=left + 1,
                    end_line=right,
                    node_type="section",
                    symbol=match.group(2) if match else None,
                )
            )
        return nodes

    def _code_or_text_nodes(self, lines: list[str], language: str) -> list[DocumentNode]:
        starts = [index for index, line in enumerate(lines) if _CODE_SYMBOL.match(line)]
        if not starts:
            return [
                DocumentNode(
                    text="\n".join(lines), start_line=1, end_line=len(lines), node_type="text"
                )
            ]
        if starts[0] != 0:
            starts.insert(0, 0)
        starts.append(len(lines))
        nodes = []
        for left, right in pairwise(starts):
            match = _CODE_SYMBOL.match(lines[left])
            nodes.append(
                DocumentNode(
                    text="\n".join(lines[left:right]),
                    start_line=left + 1,
                    end_line=right,
                    node_type="symbol" if match else "preamble",
                    symbol=match.group(1) if match else None,
                )
            )
        return nodes

    def _split_node(self, node: DocumentNode) -> list[DocumentNode]:
        max_lines = max(20, self.options.max_tokens // 3)
        overlap_lines = max(0, self.options.overlap_tokens // 3)
        lines = node.text.splitlines()
        if len(lines) <= max_lines:
            return [node]
        chunks = []
        cursor = 0
        while cursor < len(lines):
            end = min(cursor + max_lines, len(lines))
            chunks.append(
                DocumentNode(
                    text="\n".join(lines[cursor:end]),
                    start_line=node.start_line + cursor,
                    end_line=node.start_line + end - 1,
                    node_type=node.node_type,
                    symbol=node.symbol,
                )
            )
            if end == len(lines):
                break
            cursor = max(cursor + 1, end - overlap_lines)
        return chunks

    @staticmethod
    def _is_test(path: str) -> bool:
        normalized = f"/{path.lower()}/"
        return any(marker in normalized for marker in ("/test/", "/tests/", "_test.", ".spec."))
