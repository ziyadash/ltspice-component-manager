"""Command-line interface: ltmodel find|install|uninstall|check|where."""

from __future__ import annotations

import argparse
import sys

from . import check as checker
from . import install as installer
from . import scan, sources
from .paths import find_lib_dirs
from .spice import parse_number


def _describe(d) -> str:
    if d.kind == "model":
        return f".model {d.name} {d.mtype}"
    return f".subckt {d.name} ({len(d.pins)} pins)"


def cmd_where(args, libs) -> int:
    print(f"LTspice lib folder: {libs.root}")
    for label, p in (("models  (cmp)", libs.cmp), ("subckts (sub)", libs.sub), ("symbols (sym)", libs.sym)):
        print(f"  {label}: {p}  {'ok' if p.is_dir() else 'missing'}")
    return 0


def cmd_find(args, libs) -> int:
    hits = scan.scan(libs, args.name)
    if not hits:
        print(f"{args.name}: not found in {libs.root}")
        return 1
    for h in hits:
        print(f"{_describe(h.definition)}  {h.path}:{h.definition.line}")
    return 0


def _pick(cands, args):
    print(f"Found {len(cands)} candidate(s):")
    for i, c in enumerate(cands, 1):
        print(f"  [{i}] {_describe(c.definition)}  <- {c.origin}  ({c.kind})")
    if args.pick is not None:
        choice = args.pick
    elif sys.stdin.isatty() and not args.dry_run:
        raw = input("Install which one? [number, Enter to cancel] ").strip()
        if not raw:
            return None
        choice = int(raw)
    else:
        print("Re-run with --pick N to choose one.")
        return None
    if not 1 <= choice <= len(cands):
        raise SystemExit(f"--pick must be between 1 and {len(cands)}")
    return cands[choice - 1]


def cmd_install(args, libs) -> int:
    existing = scan.scan(libs, args.name)
    if existing and not args.force:
        h = existing[0]
        print(f"{args.name} is already available: {_describe(h.definition)} in {h.path}")
        print("Use `ltmodel check` to inspect it, or --force to install another copy anyway.")
        return 0

    try:
        cands = (sources.from_file_or_url(args.source, args.name, args.kind or "user-supplied")
                 if args.source else sources.from_github(args.name))
    except sources.SourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not cands:
        print(f"No definition of {args.name} found. Try `--from <file or URL>` with a model "
              "you downloaded from the manufacturer.")
        return 1

    cand = _pick(cands, args)
    if cand is None:
        return 2
    kind = args.kind or cand.kind
    try:
        report = installer.install(libs, cand.definition, cand.origin, kind,
                                   force=args.force, dry_run=args.dry_run)
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    prefix = "[dry run] " if args.dry_run else ""
    for a in report.actions:
        print(f"{prefix}{a}")
    if report.hint and not args.dry_run:
        print(report.hint)
    if kind == "community":
        print("Note: community model, not from the manufacturer. Run `ltmodel check` and "
              "compare with the datasheet before trusting it.")
    return 0


def cmd_uninstall(args, libs) -> int:
    try:
        report = installer.uninstall(libs, args.name, dry_run=args.dry_run)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for a in report.actions:
        print(("[dry run] " if args.dry_run else "") + a)
    return 0


def cmd_check(args, libs) -> int:
    hits = scan.scan(libs, args.name)
    if not hits:
        print(f"{args.name}: not found")
        return 1
    rng = None
    if args.idss:
        lo, hi = (parse_number(x) for x in args.idss)
        if lo is None or hi is None:
            raise SystemExit("--idss needs two SPICE numbers, e.g. --idss 8m 20m")
        rng = (lo, hi)
    bad = False
    for h in hits:
        print(f"{_describe(h.definition)}  {h.path}")
        for f in checker.check(h.definition, rng):
            print(f"  {'ok  ' if f.ok else 'WARN'} {f.message}")
            bad |= not f.ok
    return 3 if bad else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ltmodel", description=__doc__)
    p.add_argument("--lib-dir", help="LTspice lib folder (default: auto-detect, or $LTSPICE_LIB)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("where", help="show the detected LTspice folders").set_defaults(fn=cmd_where)

    s = sub.add_parser("find", help="is this part already in LTspice?")
    s.add_argument("name")
    s.set_defaults(fn=cmd_find)

    s = sub.add_parser("install", help="fetch a model and install it (skips if already present)")
    s.add_argument("name")
    s.add_argument("--from", dest="source", metavar="FILE_OR_URL",
                   help="read the model from this file/URL instead of searching GitHub")
    s.add_argument("--pick", type=int, help="candidate number to install (non-interactive)")
    s.add_argument("--kind", choices=["vendor", "community", "derived", "user-supplied"],
                   help="provenance tag written next to the model")
    s.add_argument("--force", action="store_true", help="install even if already present")
    s.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    s.set_defaults(fn=cmd_install)

    s = sub.add_parser("uninstall", help="remove something ltmodel installed")
    s.add_argument("name")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_uninstall)

    s = sub.add_parser("check", help="sanity-check an installed model's parameters")
    s.add_argument("name")
    s.add_argument("--idss", nargs=2, metavar=("MIN", "MAX"),
                   help="datasheet IDSS range for JFETs, e.g. 8m 20m")
    s.set_defaults(fn=cmd_check)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        libs = find_lib_dirs(args.lib_dir)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return args.fn(args, libs)
