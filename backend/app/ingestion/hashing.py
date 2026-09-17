"""Deterministic SHA-256 content hashes for incremental indexing."""

import hashlib


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_text(content: str) -> str:
    return hash_bytes(content.encode("utf-8"))
