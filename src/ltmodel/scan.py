"""Find out whether a part is already defined in LTspice's libraries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .paths import LibDirs
from .spice import Definition, parse_definitions, read_text


@dataclass
class Hit:
    path: Path
    definition: Definition


def scan(libs: LibDirs, name: str) -> list[Hit]:
    """Search lib/cmp and lib/sub (recursively) for .model/.subckt called `name`."""
    wanted = name.lower()
    hits: list[Hit] = []
    for folder in (libs.cmp, libs.sub):
        if not folder.is_dir():
            continue
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            try:
                text, _ = read_text(path.read_bytes())
            except OSError:
                continue
            if wanted not in text.lower():  # cheap prefilter
                continue
            for d in parse_definitions(text):
                if d.name.lower() == wanted:
                    hits.append(Hit(path, d))
    return hits
