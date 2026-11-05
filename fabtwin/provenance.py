"""Content hashes and stable project-relative paths."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_CHUNK = 1024 * 1024


def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 of a byte string."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Return the SHA-256 of a file without loading it all into memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_path(path: str | Path) -> str:
    """Use a project-relative POSIX path when the file is inside the repo."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def source_tree_sha256(directories: tuple[str, ...] = ("fabtwin", "gpdk")) -> str:
    """Hash the source files that define the runner and its first engine.

    A git commit is better provenance when one exists.  The workspace this was
    built in has no usable git metadata, so the code fingerprint is explicit
    and does not pretend otherwise.
    """
    digest = hashlib.sha256()
    files: list[Path] = []
    for name in directories:
        base = ROOT / name
        if not base.is_dir():
            continue
        files.extend(
            path
            for path in base.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    for path in sorted(files, key=lambda item: display_path(item)):
        digest.update(display_path(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
