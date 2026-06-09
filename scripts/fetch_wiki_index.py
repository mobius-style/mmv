#!/usr/bin/env python3
"""Fetch the Wikipedia / Box W ME5 index from the configured mirror.

Reads `config/wiki_index_source.yaml` and downloads each declared file
into the target destination (default: `Wiki/` at repo root). Each
download is checksum-verified against the SHA256 in the config; a file
that already exists locally with a matching SHA256 is skipped.

Supports two source kinds:
  - `huggingface_dataset`  : pulls from `{base_url}/resolve/{rev}/{name}`
  - `http_base`            : pulls from `{base_url}/{name}` (any HTTP mirror)

Usage:
    python scripts/fetch_wiki_index.py                 # default config
    python scripts/fetch_wiki_index.py --dry-run       # plan only
    python scripts/fetch_wiki_index.py --source-url URL --kind http_base
    python scripts/fetch_wiki_index.py --config path/to/source.yaml

Exit codes:
    0 = all required files present and verified
    1 = checksum mismatch or download failure (left .partial behind)
    2 = config / argument error
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

CHUNK_BYTES = 1 << 20  # 1 MiB
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "wiki_index_source.yaml"


@dataclass
class FileSpec:
    name: str
    dest: Path
    bytes: int
    sha256: str
    required: bool
    description: str


def _human(n: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    f = float(n)
    for u in units:
        if f < 1024 or u == units[-1]:
            return f"{f:.1f} {u}" if u != "B" else f"{int(f)} {u}"
        f /= 1024
    return f"{f:.1f} TiB"


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_BYTES), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_url(kind: str, base_url: str, revision: str, name: str) -> str:
    if kind == "huggingface_dataset":
        return f"{base_url.rstrip('/')}/resolve/{revision}/{name}"
    if kind == "http_base":
        return f"{base_url.rstrip('/')}/{name}"
    raise ValueError(f"Unknown source kind: {kind!r} (expected 'huggingface_dataset' or 'http_base')")


def _download(url: str, dest: Path, expected_bytes: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".partial")
    if partial.exists():
        partial.unlink()
    req = urllib.request.Request(url, headers={"User-Agent": "mobius-mmv-fetch/1.0"})
    written = 0
    last_report = 0
    try:
        with urllib.request.urlopen(req) as resp, partial.open("wb") as out:
            while True:
                buf = resp.read(CHUNK_BYTES)
                if not buf:
                    break
                out.write(buf)
                written += len(buf)
                if expected_bytes > 0 and written - last_report >= 16 * CHUNK_BYTES:
                    pct = 100.0 * written / expected_bytes
                    print(f"      {pct:5.1f}%  ({_human(written)} / {_human(expected_bytes)})", flush=True)
                    last_report = written
    except urllib.error.HTTPError as e:
        if partial.exists():
            partial.unlink()
        raise RuntimeError(f"HTTP {e.code} fetching {url}") from e
    except (urllib.error.URLError, ConnectionError) as e:
        if partial.exists():
            partial.unlink()
        raise RuntimeError(f"Network error fetching {url}: {e}") from e

    partial.replace(dest)


def _load_specs(config_path: Path, dest_root: Path) -> tuple[dict, list[FileSpec]]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    with config_path.open() as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict) or "source" not in cfg or "files" not in cfg:
        raise ValueError(f"Malformed config at {config_path}: needs top-level 'source' and 'files'")
    cfg_dest_root = Path(cfg.get("dest_root", ".")) if cfg.get("dest_root") else Path(".")
    if not cfg_dest_root.is_absolute():
        cfg_dest_root = (config_path.parent.parent / cfg_dest_root).resolve()
    effective_root = dest_root if dest_root != Path(".") else cfg_dest_root

    specs: list[FileSpec] = []
    for entry in cfg["files"]:
        dest = Path(entry["dest"])
        if not dest.is_absolute():
            dest = (effective_root / dest).resolve()
        specs.append(
            FileSpec(
                name=entry["name"],
                dest=dest,
                bytes=int(entry.get("bytes", 0)),
                sha256=str(entry["sha256"]).lower(),
                required=bool(entry.get("required", True)),
                description=str(entry.get("description", "")).strip(),
            )
        )
    return cfg["source"], specs


def fetch(
    *,
    config_path: Path = DEFAULT_CONFIG,
    dest_root: Path = Path("."),
    source_url: str | None = None,
    source_kind: str | None = None,
    revision: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    source_cfg, specs = _load_specs(config_path, dest_root)

    kind = source_kind or source_cfg.get("kind", "huggingface_dataset")
    base_url = source_url or source_cfg["base_url"]
    rev = revision or source_cfg.get("revision", "main")

    print(f"Wiki index source : {kind} @ {base_url}")
    if kind == "huggingface_dataset":
        print(f"Revision          : {rev}")
    print(f"Config            : {config_path}")
    print(f"Files declared    : {len(specs)} ({sum(1 for s in specs if s.required)} required)")
    print()

    failures: list[str] = []
    skipped = 0
    downloaded = 0

    for spec in specs:
        print(f"→ {spec.name}  ({_human(spec.bytes)})")
        if spec.dest.exists() and not force:
            local_sha = _sha256_of(spec.dest)
            if local_sha == spec.sha256:
                print(f"  ✓ already present, sha256 matches  [{spec.dest}]")
                skipped += 1
                continue
            print(f"  ! local file present but sha256 mismatch (have {local_sha[:12]}…, want {spec.sha256[:12]}…)")
            if dry_run:
                print(f"  (dry-run) would re-download")
                continue

        url = _resolve_url(kind, base_url, rev, spec.name)
        print(f"  URL: {url}")
        if dry_run:
            print(f"  (dry-run) would download to {spec.dest}")
            continue

        try:
            _download(url, spec.dest, spec.bytes)
        except RuntimeError as e:
            print(f"  ✗ {e}")
            if spec.required:
                failures.append(f"{spec.name}: {e}")
            continue

        actual = _sha256_of(spec.dest)
        if actual != spec.sha256:
            print(f"  ✗ sha256 mismatch after download: got {actual}, expected {spec.sha256}")
            spec.dest.rename(spec.dest.with_suffix(spec.dest.suffix + ".badsha"))
            if spec.required:
                failures.append(f"{spec.name}: sha256 mismatch")
            continue

        print(f"  ✓ downloaded and verified  [{spec.dest}]")
        downloaded += 1

    print()
    print(f"Summary: downloaded={downloaded}, skipped={skipped}, required-failures={len(failures)}")
    if failures:
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Path to source.yaml")
    p.add_argument("--dest-root", type=Path, default=Path("."), help="Override dest_root from config")
    p.add_argument("--source-url", default=None, help="Override base_url from config")
    p.add_argument("--kind", default=None, choices=["huggingface_dataset", "http_base"], help="Override source kind")
    p.add_argument("--revision", default=None, help="HF dataset revision (default: main)")
    p.add_argument("--dry-run", action="store_true", help="Show plan, do not download")
    p.add_argument("--force", action="store_true", help="Re-download even if local sha256 matches")
    args = p.parse_args(argv)

    if shutil.which("python") is None:  # noqa: SIM103 — sanity guard, harmless on all platforms
        pass

    try:
        return fetch(
            config_path=args.config,
            dest_root=args.dest_root,
            source_url=args.source_url,
            source_kind=args.kind,
            revision=args.revision,
            dry_run=args.dry_run,
            force=args.force,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
