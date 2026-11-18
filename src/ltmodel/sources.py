"""Where models come from: a local file/URL you supply, or GitHub code search."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .spice import Definition, parse_definitions, read_text

USER_AGENT = "ltmodel/0.1"  # deliberately generic: no personal or project details


@dataclass
class Candidate:
    definition: Definition
    origin: str  # human-readable: repo/path or file/URL
    kind: str  # vendor | community | derived | user-supplied


class SourceError(Exception):
    pass


def _fetch_url(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()
    except Exception as exc:  # noqa: BLE001 - surface any network failure uniformly
        raise SourceError(f"could not fetch {url}: {exc}") from exc


def candidates_from_text(text: str, name: str, origin: str, kind: str) -> list[Candidate]:
    wanted = name.lower()
    return [
        Candidate(d, origin, kind)
        for d in parse_definitions(text)
        if d.name.lower() == wanted
    ]


def from_file_or_url(location: str, name: str, kind: str = "user-supplied") -> list[Candidate]:
    """Read a model file you downloaded (or a URL) and pull out `name`."""
    if re.match(r"^https?://", location):
        data = _fetch_url(location)
    else:
        path = Path(location).expanduser()
        if not path.is_file():
            raise SourceError(f"no such file: {path}")
        data = path.read_bytes()
    text, _ = read_text(data)
    return candidates_from_text(text, name, location, kind)


def _raw_url(html_url: str) -> str:
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/blob/(.+)$", html_url)
    if not m:
        raise SourceError(f"unexpected GitHub URL: {html_url}")
    owner, repo, rest = m.groups()
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{rest}"


def from_github(name: str, limit: int = 15) -> list[Candidate]:
    """Search public GitHub files for a definition of `name` (needs the `gh` CLI, logged in)."""
    if not shutil.which("gh"):
        raise SourceError("GitHub search needs the `gh` CLI (https://cli.github.com), logged in.")
    proc = subprocess.run(
        ["gh", "api", "-X", "GET", "search/code",
         "-f", f'q="{name}" ".model"', "-f", f"per_page={limit}"],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise SourceError(f"gh search failed: {proc.stderr.strip() or proc.stdout.strip()}")
    items = json.loads(proc.stdout).get("items", [])

    found: list[Candidate] = []
    seen: set[str] = set()
    for item in items:
        origin = f"github.com/{item['repository']['full_name']}/{item['path']}"
        try:
            data = _fetch_url(_raw_url(item["html_url"]))
        except SourceError:
            continue
        text, _ = read_text(data)
        for cand in candidates_from_text(text, name, origin, "community"):
            digest = hashlib.sha1(" ".join(cand.definition.text.split()).encode()).hexdigest()
            if digest not in seen:  # many repos copy the same model
                seen.add(digest)
                found.append(cand)
    return found
