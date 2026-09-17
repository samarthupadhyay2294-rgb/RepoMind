"""Seed a tiny demo repository for the RepoMind walkthrough (docs/demo.md).

Stdlib only. Creates a local folder with a few Python files and a git
history, so acquisition/indexing/chat can be exercised end to end.
Usage:  python scripts/seed_demo_repo.py [destination]
"""

import subprocess
import sys
from pathlib import Path

AUTH_PY = '''"""Login flow."""


def authenticate(username, password):
    """Check credentials against the user store."""
    user = find_user(username)
    return user is not None and user.check_password(password)


def find_user(username):
    """Look up a user by name."""
    return None
'''

MODELS_PY = '''"""Domain models."""


class User:
    """An application user."""

    def __init__(self, name):
        self.name = name

    def check_password(self, password):
        """Compare against the stored hash."""
        return bool(password)
'''

HANDLERS_PY = '''"""API handlers."""

from demo.auth import authenticate


def login_handler(request):
    """Handle a login request."""
    return authenticate(request.user, request.password)
'''


def main() -> int:
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else "demo-repo")
    (dest / "demo").mkdir(parents=True, exist_ok=True)
    (dest / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (dest / "demo" / "auth.py").write_text(AUTH_PY, encoding="utf-8")
    (dest / "demo" / "models.py").write_text(MODELS_PY, encoding="utf-8")
    (dest / "demo" / "handlers.py").write_text(HANDLERS_PY, encoding="utf-8")
    try:
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "add", "-A"], cwd=dest, capture_output=True, check=True)
        subprocess.run(
            ["git", "-c", "user.name=demo", "-c", "user.email=demo@t.t",
             "commit", "-m", "seed demo repo"],
            cwd=dest,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        print("note: git not available; seeded files only", flush=True)
    print(f"seeded demo repository at {dest.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
