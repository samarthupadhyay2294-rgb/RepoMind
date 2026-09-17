"""Per-file accept/reject decisions: binary, secrets, size, support.

Security restrictions here always win — .gitignore can never re-allow them.
"""

from pathlib import Path

# Extensions never sent to the text pipeline (plus NUL-byte content sniffing).
BINARY_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".bmp",
        ".svg",
        ".pdf",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".o",
        ".a",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".mp3",
        ".mp4",
        ".avi",
        ".mov",
        ".wav",
        ".flac",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
        ".pyc",
        ".pyo",
        ".class",
        ".jar",
        ".war",
        ".db",
        ".sqlite",
        ".sqlite3",
        ".bin",
        ".dat",
        ".lock",
    }
)

# Exact filenames that may hold credentials (conservative on purpose).
SECRET_FILENAMES = frozenset(
    {".env", "id_rsa", "id_ed25519", "id_ecdsa", "credentials", "secrets"}
)
SECRET_EXTENSIONS = frozenset({".pem", ".key", ".p12", ".pfx"})
SECRET_PREFIXES = (".env.",)

# Directories pruned before any other rule is consulted.
DEFAULT_IGNORED_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "dist",
        "build",
        "coverage",
        ".cache",
        ".next",
        "target",
        "vendor",
        ".idea",
        ".vscode",
        ".tox",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "out",
        "_build",
        "eggs",
    }
)

_SNIFF_BYTES = 8192


def is_secret_file(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered in SECRET_FILENAMES
        or lowered.startswith(SECRET_PREFIXES)
        or any(lowered.endswith(ext) for ext in SECRET_EXTENSIONS)
    )


def looks_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with open(path, "rb") as handle:
            return b"\x00" in handle.read(_SNIFF_BYTES)
    except OSError:
        return True  # Unreadable → treat as unprocessable, never crash on it.


def file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None
