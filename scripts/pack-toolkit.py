#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pack-toolkit.py — build the reqQuest Framework toolkit release asset.

Reads `toolkit-manifest.json` (ADR-TOOLKIT-001 D1), collects exactly the files it
declares, and writes a deterministic tarball plus a coreutils-style `SHA256SUMS`:

    dist/raac-toolkit-<version>.tar.gz     # contents under a raac-toolkit-<version>/ dir
    dist/SHA256SUMS                         # "<sha256>  raac-toolkit-<version>.tar.gz"

`.reqq/validator/reqq_validate_stdlib.py upgrade` downloads this asset and verifies it
against the `SHA256SUMS` block in the GitHub Release body, so the two must agree on the
asset name and the on-disk layout (`_find_payload_root` descends one wrapping directory).

stdlib only. Deterministic: members sorted, ownership zeroed, timestamps pinned to
SOURCE_DATE_EPOCH (default 1980-01-01, the earliest a tar/zip timestamp can express).

Usage:
    python3 scripts/pack-toolkit.py --version 1.0.0
    python3 scripts/pack-toolkit.py --version 1.0.0 --out dist --repo-root .
    python3 scripts/pack-toolkit.py --list          # print the resolved file list, pack nothing
"""
import argparse
import fnmatch
import gzip
import hashlib
import os
import sys
import tarfile
from pathlib import Path

MANIFEST_NAME = "toolkit-manifest.json"
DEFAULT_SOURCE_DATE_EPOCH = 315532800  # 1980-01-01T00:00:00Z


def _load_manifest(repo_root: Path):
    manifest_path = repo_root / MANIFEST_NAME
    if not manifest_path.is_file():
        sys.exit(f"error: {MANIFEST_NAME} not found under {repo_root}")
    import json
    try:
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as e:
        sys.exit(f"error: {MANIFEST_NAME} is not valid JSON: {e}")
    boundary = doc.get("boundary")
    if not isinstance(boundary, list) or not all(isinstance(x, str) for x in boundary):
        sys.exit(f"error: {MANIFEST_NAME}: `boundary` must be a list of glob strings")
    exclude = doc.get("exclude") or []
    if not isinstance(exclude, list) or not all(isinstance(x, str) for x in exclude):
        sys.exit(f"error: {MANIFEST_NAME}: `exclude` must be a list of glob strings")
    return doc, boundary, exclude


def resolve_files(repo_root: Path, boundary, exclude):
    """Expand `boundary` globs under repo_root, drop `exclude` matches, return sorted
    ROOT-relative POSIX paths. Same glob semantics as the validator's _toolkit_boundary_files."""
    picked = set()
    for pat in boundary:
        for p in repo_root.glob(pat):
            if not p.is_file():
                continue
            rel = p.relative_to(repo_root).as_posix()
            if any(rel == ex or fnmatch.fnmatch(rel, ex) for ex in exclude):
                continue
            picked.add(rel)
    return sorted(picked)


def build_tarball(repo_root: Path, rel_paths, out_tar: Path, top_dir: str, mtime: int):
    out_tar.parent.mkdir(parents=True, exist_ok=True)

    def _reset(ti: tarfile.TarInfo) -> tarfile.TarInfo:
        ti.uid = ti.gid = 0
        ti.uname = ti.gname = ""
        ti.mtime = mtime
        if ti.isdir():
            ti.mode = 0o755
        else:
            ti.mode = 0o755 if (ti.mode & 0o100) else 0o644
        return ti

    # Drive gzip directly so its header carries a pinned mtime and no source filename —
    # tarfile's own "w:gz" stamps wall-clock time into the gzip header and breaks
    # byte-for-byte reproducibility across runs.
    seen_dirs = set()
    with open(out_tar, "wb") as raw, \
         gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=mtime, compresslevel=9) as gz, \
         tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for rel in rel_paths:
            parts = rel.split("/")
            for i in range(1, len(parts)):
                d = "/".join(parts[:i])
                if d in seen_dirs:
                    continue
                seen_dirs.add(d)
                di = tarfile.TarInfo(f"{top_dir}/{d}")
                di.type = tarfile.DIRTYPE
                tar.addfile(_reset(di))
            src = repo_root / rel
            ti = tar.gettarinfo(str(src), arcname=f"{top_dir}/{rel}")
            with open(src, "rb") as fh:
                tar.addfile(_reset(ti), fh)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", help="Bare SemVer of the release, e.g. 1.0.0 (no leading v).")
    ap.add_argument("--out", default="dist", help="Output directory (default: dist).")
    ap.add_argument("--repo-root", default=".", help="Framework repo root (default: .).")
    ap.add_argument("--list", action="store_true", dest="list_only",
                    help="Print the resolved file list and exit without packing.")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    _doc, boundary, exclude = _load_manifest(repo_root)
    rel_paths = resolve_files(repo_root, boundary, exclude)
    if not rel_paths:
        return _fail("manifest resolved to zero files — nothing to pack")

    if args.list_only:
        print("\n".join(rel_paths))
        return 0

    version = (args.version or "").lstrip("v").strip()
    if not version:
        return _fail("--version is required (bare SemVer, e.g. 1.0.0)")

    mtime = int(os.environ.get("SOURCE_DATE_EPOCH", DEFAULT_SOURCE_DATE_EPOCH))
    top_dir = f"raac-toolkit-{version}"
    out_dir = Path(args.out)
    tar_path = out_dir / f"{top_dir}.tar.gz"

    build_tarball(repo_root, rel_paths, tar_path, top_dir, mtime)
    digest = sha256_of(tar_path)
    sums_path = out_dir / "SHA256SUMS"
    sums_path.write_text(f"{digest}  {tar_path.name}\n", encoding="utf-8")

    print(f"packed {len(rel_paths)} files → {tar_path} ({tar_path.stat().st_size} bytes)")
    print(f"sha256 {digest}")
    print(f"wrote  {sums_path}")
    return 0


def _fail(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
