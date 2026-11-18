"""Minimal SPICE netlist parsing: find .model and .subckt definitions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_SUFFIX = {
    "t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3,
    "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15, "a": 1e-18,
}
_NUM = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)(meg|mil|[tgkmunpfa])?", re.I)
_PARAM = re.compile(r"(\w+)\s*=\s*([^\s)=]+)")
_MODEL = re.compile(r"^\.model\s+(\S+)\s+(\w+)\s*\(?(.*?)\)?\s*$", re.I | re.S)


def read_text(data: bytes) -> tuple[str, str]:
    """Decode a library file. Returns (text, encoding to write it back with)."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"


def parse_number(text: str) -> float | None:
    """Parse a SPICE number such as 4.0m, 1e-4, 10meg, 5p. None if not numeric."""
    m = _NUM.match(text.strip())
    if not m:
        return None
    value = float(m.group(1))
    suffix = (m.group(2) or "").lower()
    if suffix == "mil":
        return value * 25.4e-6
    return value * _SUFFIX.get(suffix, 1.0)


@dataclass
class Definition:
    kind: str  # "model" or "subckt"
    name: str
    text: str  # original text, physical lines, no trailing newline
    line: int  # 1-based line in the source
    mtype: str = ""  # NPN, NJF, D, ... (models only)
    params: dict[str, str] = field(default_factory=dict)
    pins: list[str] = field(default_factory=list)  # subckts only

    def number(self, key: str) -> float | None:
        for k, v in self.params.items():
            if k.lower() == key.lower():
                return parse_number(v)
        return None


def _logical_lines(text: str) -> list[tuple[int, int, str]]:
    """Join '+' continuations and drop comments: (first_idx, last_idx, text)."""
    out: list[tuple[int, int, str]] = []
    for idx, raw in enumerate(text.splitlines()):
        stripped = raw.strip()
        if not stripped or stripped.startswith("*"):
            continue
        stripped = stripped.split(";", 1)[0].rstrip()
        if stripped.startswith("+") and out:
            first, _, prev = out[-1]
            out[-1] = (first, idx, prev + " " + stripped[1:].strip())
        elif stripped:
            out.append((idx, idx, stripped))
    return out


def parse_definitions(text: str) -> list[Definition]:
    lines = text.splitlines()
    logical = _logical_lines(text)
    defs: list[Definition] = []
    i = 0
    while i < len(logical):
        first, last, content = logical[i]
        low = content.lower()
        if low.startswith(".model"):
            m = _MODEL.match(content)
            if m:
                name, mtype, rest = m.groups()
                defs.append(Definition(
                    kind="model", name=name, mtype=mtype.upper(), line=first + 1,
                    text="\n".join(lines[first:last + 1]),
                    params={k: v for k, v in _PARAM.findall(rest)},
                ))
        elif low.startswith(".subckt"):
            tokens = content.split()[1:]
            name = tokens[0] if tokens else ""
            pins: list[str] = []
            for tok in tokens[1:]:
                if "=" in tok or tok.lower() == "params:":
                    break
                pins.append(tok)
            depth, j = 1, i + 1
            while j < len(logical) and depth:
                nxt = logical[j][2].lower()
                if nxt.startswith(".subckt"):
                    depth += 1
                elif nxt.startswith(".ends"):
                    depth -= 1
                j += 1
            end_idx = logical[j - 1][1]
            defs.append(Definition(
                kind="subckt", name=name, line=first + 1, pins=pins,
                text="\n".join(lines[first:end_idx + 1]),
            ))
            i = j
            continue
        i += 1
    return defs
