"""LangChain tool adapters (plan v2 §8/§10).

Each Part 6 tool exposed as a schema-validated ``StructuredTool`` so a
future planner can bind them to a chat model. The active Part 7 agent
does NOT use native model tool-calling: it plans via plain string
prompts through :class:`AgentDeps.invoke_llm` (local Ollama) and
dispatches the Part 6 implementations in code. The Part 6
implementations stay the single source of truth — these are thin,
read-only wrappers bound to one :class:`ToolContext` (repository
isolation preserved).
"""

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.tools import deps, files, git, search, symbols, validation
from app.tools.context import ToolContext


class SearchCodeInput(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    path_prefix: str | None = None
    language: str | None = None
    max_results: int | None = Field(default=None, ge=1)


class ReadFileInput(BaseModel):
    path: str = Field(min_length=1)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class ListDirectoryInput(BaseModel):
    path: str = "."
    recursive: bool = False
    max_entries: int | None = Field(default=None, ge=1)


class GetSymbolInput(BaseModel):
    symbol: str = Field(min_length=1, max_length=500)
    path: str | None = None
    max_results: int | None = Field(default=None, ge=1)


class GitLogInput(BaseModel):
    path: str | None = None
    max_entries: int | None = Field(default=None, ge=1)


class GitBlameInput(BaseModel):
    path: str = Field(min_length=1)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)


class FindReferencesInput(BaseModel):
    symbol: str = Field(min_length=1, max_length=500)
    max_results: int | None = Field(default=None, ge=1)


class DependencyGraphInput(BaseModel):
    path: str | None = None


class RunValidationInput(BaseModel):
    validation_id: str = Field(min_length=1, max_length=64)


def build_langchain_tools(ctx: ToolContext) -> list[StructuredTool]:
    """Bind all nine investigation tools to one repository context."""

    def _json(result: BaseModel) -> str:
        return result.model_dump_json()

    return [
        StructuredTool.from_function(
            func=lambda query, path_prefix=None, language=None, max_results=None: _json(
                search.search_code(ctx, query, path_prefix, language, max_results)
            ),
            name="search_code",
            description="Find lines containing a query string in this repository.",
            args_schema=SearchCodeInput,
        ),
        StructuredTool.from_function(
            func=lambda path, start_line=None, end_line=None: _json(
                files.read_file(ctx, path, start_line, end_line)
            ),
            name="read_file",
            description="Read a line range of one repository file.",
            args_schema=ReadFileInput,
        ),
        StructuredTool.from_function(
            func=lambda path=".", recursive=False, max_entries=None: _json(
                files.list_directory(ctx, path, recursive, max_entries)
            ),
            name="list_directory",
            description="List one repository directory (sorted, bounded).",
            args_schema=ListDirectoryInput,
        ),
        StructuredTool.from_function(
            func=lambda symbol, path=None, max_results=None: _json(
                symbols.get_symbol(ctx, symbol, path, max_results)
            ),
            name="get_symbol",
            description="Find class/function/method definitions by name.",
            args_schema=GetSymbolInput,
        ),
        StructuredTool.from_function(
            func=lambda path=None, max_entries=None: _json(
                git.git_log(ctx, path, max_entries)
            ),
            name="git_log",
            description="List recent commits, optionally touching a path. Read-only.",
            args_schema=GitLogInput,
        ),
        StructuredTool.from_function(
            func=lambda path, start_line=None, end_line=None: _json(
                git.git_blame(ctx, path, start_line, end_line)
            ),
            name="git_blame",
            description="Per-line authorship for a bounded range of a file. Read-only.",
            args_schema=GitBlameInput,
        ),
        StructuredTool.from_function(
            func=lambda symbol, max_results=None: _json(
                symbols.find_references(ctx, symbol, max_results)
            ),
            name="find_references",
            description="Find word-boundary usages of a symbol.",
            args_schema=FindReferencesInput,
        ),
        StructuredTool.from_function(
            func=lambda path=None: _json(deps.dependency_graph(ctx, path)),
            name="dependency_graph",
            description="Static import graph. Never executes code.",
            args_schema=DependencyGraphInput,
        ),
        StructuredTool.from_function(
            func=lambda validation_id: _json(
                validation.run_validation(ctx, validation_id)
            ),
            name="run_validation",
            description="Run one allowlisted check (pytest|ruff_check|mypy). No arbitrary commands.",
            args_schema=RunValidationInput,
        ),
    ]
