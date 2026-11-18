"""Locate LTspice's user library folder."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LibDirs:
    root: Path

    @property
    def cmp(self) -> Path:
        return self.root / "cmp"

    @property
    def sub(self) -> Path:
        return self.root / "sub"

    @property
    def sym(self) -> Path:
        return self.root / "sym"

    @property
    def backups(self) -> Path:
        return self.root / ".ltmodel-backups"


def candidate_roots() -> list[Path]:
    home = Path.home()
    env = os.environ.get("LTSPICE_LIB")
    roots = [Path(env).expanduser()] if env else []
    roots += [
        home / "Library/Application Support/LTspice/lib",  # macOS
        home / "AppData/Local/LTspice/lib",  # Windows, LTspice 24+
        home / "Documents/LTspiceXVII/lib",  # Windows, LTspice XVII
    ]
    return roots


def find_lib_dirs(override: str | os.PathLike[str] | None = None) -> LibDirs:
    roots = [Path(override).expanduser()] if override else candidate_roots()
    for root in roots:
        if (root / "cmp").is_dir() or (root / "sub").is_dir():
            return LibDirs(root)
    tried = "\n  ".join(str(r) for r in roots)
    raise FileNotFoundError(
        "Could not find an LTspice lib folder (expected cmp/ and sub/ inside). "
        f"Tried:\n  {tried}\nPass --lib-dir or set LTSPICE_LIB."
    )
