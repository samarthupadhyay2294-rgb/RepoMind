"""Parser abstraction: file loading → language → parse → chunk.

Only stdlib parsing today (plain text + Python AST symbols). Tree-sitter
parsers can implement FileParser later without touching the pipeline.
"""

import ast
import logging
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)


class ParserError(Exception):
    pass


@dataclass
class SymbolSpan:
    name: str
    kind: str  # "function" | "class"
    start_line: int
    end_line: int


@dataclass
class ParsedFile:
    content: str
    symbols: list[SymbolSpan] = field(default_factory=list)


class FileParser(Protocol):
    languages: frozenset[str]

    def parse(self, content: str, file_path: str) -> ParsedFile: ...


class PlainTextParser:
    languages = frozenset({"*"})

    def parse(self, content: str, file_path: str) -> ParsedFile:
        return ParsedFile(content=content)


class PythonAstParser:
    """AST symbol spans only — never executes code. Falls back to plain."""

    languages = frozenset({"python"})

    def parse(self, content: str, file_path: str) -> ParsedFile:
        try:
            tree = ast.parse(content, filename=file_path)
        except (SyntaxError, ValueError) as exc:
            raise ParserError(f"Cannot parse {file_path}: {exc}") from exc
        symbols: list[SymbolSpan] = []

        class Visitor(ast.NodeVisitor):
            def _record(
                self,
                node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
                kind: str,
            ) -> None:
                end = getattr(node, "end_lineno", None) or node.lineno
                symbols.append(
                    SymbolSpan(
                        name=node.name, kind=kind, start_line=node.lineno, end_line=end
                    )
                )
                self.generic_visit(node)

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                self._record(node, "function")

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                self._record(node, "function")

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                self._record(node, "class")

        Visitor().visit(tree)
        return ParsedFile(content=content, symbols=symbols)


_PARSERS: list[FileParser] = [PythonAstParser(), PlainTextParser()]


def get_parser(language: str) -> FileParser:
    for parser in _PARSERS:
        if language in parser.languages:
            return parser
    return PlainTextParser()


def parse_file(content: str, file_path: str, language: str) -> ParsedFile:
    """Parse, degrading to plain text when the language parser fails."""
    parser = get_parser(language)
    try:
        return parser.parse(content, file_path)
    except ParserError:
        logger.warning("file_parse_failed file=%s language=%s", file_path, language)
        return ParsedFile(content=content)
