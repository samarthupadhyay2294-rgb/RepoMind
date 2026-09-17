"""Extension/filename → language mapping. Unknown → None (skipped safely)."""

EXTENSION_LANGUAGES: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "json",
    ".md": "markdown",
    ".markdown": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "css",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".php": "php",
    ".rb": "ruby",
    ".sql": "sql",
    ".sh": "shell",
    ".bash": "shell",
    ".txt": "text",
    ".xml": "xml",
    ".dockerfile": "dockerfile",
}

FILENAME_LANGUAGES: dict[str, str] = {
    "dockerfile": "dockerfile",
    "makefile": "makefile",
    "license": "text",
    "gemfile": "ruby",
}


def detect_language(filename: str) -> str | None:
    lowered = filename.lower()
    if lowered in FILENAME_LANGUAGES:
        return FILENAME_LANGUAGES[lowered]
    suffix = "." + lowered.rpartition(".")[2] if "." in lowered else ""
    return EXTENSION_LANGUAGES.get(suffix)


def chunk_type_for(language: str) -> str:
    if language in ("markdown", "text"):
        return "doc"
    if language in ("json", "yaml", "toml", "ini", "xml"):
        return "data"
    return "code"
