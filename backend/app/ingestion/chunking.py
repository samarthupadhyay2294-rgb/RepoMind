"""Deterministic line-preserving chunking with symbol attribution."""

from app.config import settings
from app.ingestion import hashing
from app.ingestion.language import chunk_type_for
from app.ingestion.models import IngestedChunk
from app.ingestion.parsers import ParsedFile, SymbolSpan


def symbol_for(symbols: list[SymbolSpan], line: int) -> str | None:
    """Innermost symbol span containing the line (stable on ties)."""
    best: str | None = None
    best_span = 0
    for symbol in symbols:
        if symbol.start_line <= line <= symbol.end_line:
            span = symbol.end_line - symbol.start_line
            if best is None or span < best_span:
                best, best_span = symbol.name, span
    return best


def chunk_parsed_file(
    parsed: ParsedFile,
    *,
    repository_id: str,
    commit_sha: str | None,
    file_path: str,
    file_hash: str,
    language: str,
    max_lines: int | None = None,
    max_chars: int | None = None,
) -> list[IngestedChunk]:
    limit_lines = settings.MAX_CHUNK_LINES if max_lines is None else max_lines
    limit_chars = settings.MAX_CHUNK_SIZE if max_chars is None else max_chars
    lines = parsed.content.splitlines()
    if not lines:
        return []
    chunk_kind = chunk_type_for(language)

    # Greedy line groups bounded by both limits; never an empty chunk.
    groups: list[tuple[int, int]] = []
    start = 1
    size = 0
    for lineno, line in enumerate(lines, start=1):
        size += len(line) + 1
        overflow = (lineno - start + 1) > limit_lines or size > limit_chars
        if overflow and lineno > start:
            groups.append((start, lineno - 1))
            start, size = lineno, len(line) + 1
    groups.append((start, len(lines)))

    chunks: list[IngestedChunk] = []
    for group_start, group_end in groups:
        content = "\n".join(lines[group_start - 1 : group_end])
        chunks.append(
            IngestedChunk(
                repository_id=repository_id,
                commit_sha=commit_sha,
                file_path=file_path,
                file_hash=file_hash,
                language=language,
                chunk_type=chunk_kind,
                symbol=symbol_for(parsed.symbols, group_start),
                start_line=group_start,
                end_line=group_end,
                content=content,
                content_hash=hashing.hash_text(
                    f"{file_path}:{group_start}:{group_end}\n{content}"
                ),
            )
        )
    return chunks
