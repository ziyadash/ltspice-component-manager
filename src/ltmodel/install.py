"""Install and uninstall models (and generated symbols) in LTspice's lib folders.

Discrete models (.model) are appended to LTspice's own standard.* files so that
the stock `npn`/`njf`/... symbols find them by name. Each install is wrapped in
marker comments so it can be replaced or removed cleanly. Subcircuits get their
own file in lib/sub plus a generated symbol in lib/sym/ltmodel.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .paths import LibDirs
from .spice import Definition, read_text

STANDARD_FILE = {
    "NPN": "standard.bjt", "PNP": "standard.bjt",
    "NJF": "standard.jft", "PJF": "standard.jft",
    "NMOS": "standard.mos", "PMOS": "standard.mos",
    "D": "standard.dio",
}
GENERIC_SYMBOL = {
    "NPN": "npn", "PNP": "pnp", "NJF": "njf", "PJF": "pjf",
    "NMOS": "nmos", "PMOS": "pmos", "D": "diode",
}
SYMBOL_DIR = "ltmodel"


@dataclass
class Report:
    actions: list[str] = field(default_factory=list)
    hint: str = ""


def _markers(name: str) -> tuple[str, str]:
    return f"* >>> ltmodel:{name} >>>", f"* <<< ltmodel:{name} <<<"


def _block_re(name: str) -> re.Pattern[str]:
    begin, end = (re.escape(m) for m in _markers(name))
    return re.compile(rf"^{begin}[^\n]*\n.*?^{end}[^\n]*\n?", re.S | re.M | re.I)


def _backup(libs: LibDirs, path: Path, dry_run: bool, report: Report) -> None:
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = libs.backups / f"{path.name}.{stamp}"
    report.actions.append(f"backup {path} -> {dest}")
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)


def _header(origin: str, kind: str) -> str:
    return (f"* source: {origin}\n* provenance: {kind}\n"
            f"* installed: {datetime.now():%Y-%m-%d} by ltmodel\n")


def _write(path: Path, text: str, encoding: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode(encoding))


def _read(path: Path) -> tuple[str, str, str]:
    """(text, encoding, eol) with the text normalised to \\n."""
    if not path.exists():
        return "", "utf-8", "\n"
    text, enc = read_text(path.read_bytes())
    eol = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), enc, eol


def with_metadata(d: Definition, kind: str, meta: dict[str, str] | None = None) -> str:
    """Model text with the fields LTspice's part picker shows (mfg, Vceo, Icrating).

    Existing values in the model are never overwritten. `mfg` defaults to the
    provenance tag so the picker shows where a model came from; Vceo/Icrating
    are only added when you supply them (we never invent ratings).
    """
    meta = dict(meta or {})
    meta.setdefault("mfg", kind.replace("-", "_"))
    wanted = {"mfg": meta["mfg"]}
    if d.mtype in {"NPN", "PNP"}:
        for key, canon in (("vceo", "Vceo"), ("icrating", "Icrating")):
            if key in {k.lower() for k in meta}:
                wanted[canon] = next(v for k, v in meta.items() if k.lower() == key)

    text = d.text.rstrip()
    missing = [f"{k}={v}" for k, v in wanted.items()
               if not re.search(rf"\b{k}\s*=", text, re.I)]
    if not missing:
        return text
    extra = " ".join(missing)
    if "(" in text and text.endswith(")"):
        return f"{text[:-1]} {extra})"
    return f"{text} {extra}"


def install(libs: LibDirs, d: Definition, origin: str, kind: str,
            force: bool = False, dry_run: bool = False,
            meta: dict[str, str] | None = None) -> Report:
    if d.kind == "subckt":
        return _install_subckt(libs, d, origin, kind, force, dry_run)
    return _install_model(libs, d, origin, kind, force, dry_run, meta)


def _install_model(libs, d, origin, kind, force, dry_run, meta=None) -> Report:
    report = Report()
    fname = STANDARD_FILE.get(d.mtype)
    if fname is None:  # unusual type: keep it in its own file, user must .include it
        path = libs.sub / f"{d.name}.lib"
        report.hint = f"Add the directive `.lib {d.name}.lib` to your schematic."
    else:
        path = libs.cmp / fname
        sym = GENERIC_SYMBOL[d.mtype]
        report.hint = (f"Place the stock `{sym}` symbol, right-click it and set "
                       f"its Value to {d.name}.")

    text, enc, eol = _read(path)
    block_re = _block_re(d.name)
    existing = block_re.search(text)
    if existing and not force:
        raise FileExistsError(f"{d.name} was already installed by ltmodel in {path} (use --force)")

    begin, end = _markers(d.name)
    block = f"{begin}\n{_header(origin, kind)}{with_metadata(d, kind, meta)}\n{end}\n"
    if existing:
        new = text[:existing.start()] + block + text[existing.end():]
    else:
        new = text + ("" if text.endswith("\n") or not text else "\n") + block

    _backup(libs, path, dry_run, report)
    report.actions.append(f"{'replace' if existing else 'append'} {d.name} in {path}")
    if not dry_run:
        _write(path, new.replace("\n", eol), enc)
    return report


def _install_subckt(libs, d, origin, kind, force, dry_run) -> Report:
    report = Report()
    lib_path = libs.sub / f"{d.name}.lib"
    asy_path = libs.sym / SYMBOL_DIR / f"{d.name}.asy"
    if lib_path.exists() and not force:
        raise FileExistsError(f"{lib_path} already exists (use --force)")

    _backup(libs, lib_path, dry_run, report)
    _backup(libs, asy_path, dry_run, report)
    report.actions.append(f"write {lib_path}")
    report.actions.append(f"write {asy_path} (generated symbol)")
    if not dry_run:
        _write(lib_path, f"{_header(origin, kind)}{d.text.strip()}\n", "utf-8")
        _write(asy_path, make_symbol(d), "utf-8")
    report.hint = (f"In LTspice press F2, browse to the `{SYMBOL_DIR}` folder and place "
                   f"`{d.name}`.")
    return report


def make_symbol(d: Definition) -> str:
    """A plain rectangular .asy: first half of the pins on the left, rest on the right."""
    pins = d.pins
    n_left = (len(pins) + 1) // 2
    n_right = len(pins) - n_left
    rows = max(n_left, n_right, 1)
    height = 16 * rows + 16
    lines = [
        "Version 4", "SymbolType CELL",
        f"RECTANGLE Normal -48 0 48 {height}",
        "WINDOW 0 0 -8 Bottom 2", f"WINDOW 3 0 {height + 8} Top 2",
        "SYMATTR Prefix X", "SYMATTR InstName U",
        f"SYMATTR Value {d.name}", f"SYMATTR ModelFile {d.name}.lib",
    ]
    for i, pin in enumerate(pins, start=1):
        if i <= n_left:
            x, y, side, off = -48, 16 * i, "LEFT", 8
        else:
            x, y, side, off = 48, 16 * (i - n_left), "RIGHT", 8
        lines += [f"PIN {x} {y} {side} {off}", f"PINATTR PinName {pin}",
                  f"PINATTR SpiceOrder {i}"]
    return "\n".join(lines) + "\n"


def uninstall(libs: LibDirs, name: str, dry_run: bool = False) -> Report:
    """Remove only what ltmodel installed (marker blocks / its own sub + sym files)."""
    report = Report()
    for fname in sorted(set(STANDARD_FILE.values())):
        path = libs.cmp / fname
        if not path.exists():
            continue
        text, enc, eol = _read(path)
        m = _block_re(name).search(text)
        if m:
            _backup(libs, path, dry_run, report)
            report.actions.append(f"remove {name} block from {path}")
            if not dry_run:
                _write(path, (text[:m.start()] + text[m.end():]).replace("\n", eol), enc)

    lib_path = libs.sub / f"{name}.lib"
    asy_path = libs.sym / SYMBOL_DIR / f"{name}.asy"  # our own folder, so always ours
    owned = [asy_path] if asy_path.exists() else []
    if lib_path.exists() and "by ltmodel" in lib_path.read_text(errors="ignore")[:400]:
        owned.append(lib_path)
    for path in owned:
        _backup(libs, path, dry_run, report)
        report.actions.append(f"delete {path}")
        if not dry_run:
            path.unlink()
    if not report.actions:
        raise FileNotFoundError(f"nothing installed by ltmodel found for {name}")
    return report
