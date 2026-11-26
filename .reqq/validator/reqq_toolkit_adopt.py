# -*- coding: utf-8 -*-
"""The `adopt` subcommand."""
import argparse, json, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import reqq_common as C  # noqa: E402
import reqq_toolkit_core as T  # noqa: E402
import reqq_toolkit_github as GH  # noqa: E402
import reqq_toolkit_align as AL  # noqa: E402


def cmd_adopt(args) -> int:
    """Generate toolkit.lock from current state. Saves adopted toolkit version.

    `--align` (reqQuestFramework#5) brings a pre-versioning or unanchored repo in line with
    the target release first: every file the release boundary covers is added if absent and
    overwritten if it differs, except `--keep` paths (kept as-is and recorded as
    local_overrides, same as `--local-override`); a local file an EXISTING `toolkit.lock`
    already recorded this toolkit as managing, but that the target release no longer ships,
    is reported as LOCAL_ONLY, never deleted — a path that merely matches the release
    boundary without ever having been in a lock this toolkit wrote is not LOCAL_ONLY and is
    not reported at all (reqQuestFramework#67). The lock is then written exactly like a
    normal adopt of that version.
    """
    ap = argparse.ArgumentParser(prog="reqq_validate.py adopt")
    ap.add_argument("--version", help="Explicit toolkit version (e.g., 1.0.0). If omitted, fetches latest from source.")
    ap.add_argument("--source", default=T.DEFAULT_TOOLKIT_SOURCE, help="GitHub repo URL (default: reqQuestFramework)")
    ap.add_argument("--channel", choices=["stable", "next"], default="stable")
    ap.add_argument("--installed-by", default="manual", help="Who ran adopt (default: manual)")
    ap.add_argument("--local-override", nargs="*", default=[], help="Paths to mark as local overrides (relative to the working directory)")
    ap.add_argument("--format", choices=["plain", "json"], default="plain", help="Output format.")
    ap.add_argument("--align", action="store_true",
                    help="Bring the working tree in line with --version's release boundary "
                         "before writing the lock (reqQuestFramework#5).")
    ap.add_argument("--keep", nargs="*", default=[],
                    help="With --align: paths to leave untouched instead of overwriting with "
                         "the release version (relative to the working directory); recorded "
                         "as local_overrides.")
    ap.add_argument("--payload", help="With --align: path to an already-extracted "
                    "raac-toolkit-<version>/ directory, for offline use — no network calls "
                    "are made and checksum verification is the caller's responsibility.")
    ap.add_argument("--dry-run", action="store_true",
                    help="With --align: report what would change without touching the "
                         "working tree or writing the lock.")
    parsed = ap.parse_args(args)

    def _fail(code: str, message: str) -> int:
        # `plain` keeps the legacy `_die` behaviour (sys.exit) verbatim, so existing
        # callers/tests that rely on the SystemExit are unaffected; `json` returns instead.
        if parsed.format == "json":
            return T._emit_toolkit_error("json", code, message)
        C._die(3, message)
        return 3  # unreachable; _die exits

    if not parsed.align and (parsed.keep or parsed.payload or parsed.dry_run):
        return _fail("INVALID_ARGS", "--keep/--payload/--dry-run require --align")
    if parsed.align and parsed.payload and not parsed.version:
        return _fail("INVALID_ARGS",
                     "--version is required with --align --payload (offline mode has no "
                     "release API to detect it from)")

    version = parsed.version
    if not version:
        try:
            tag = GH._latest_release_tag(parsed.source, parsed.channel)
            version = T._normalize_version(tag)
        except T.ToolkitError as e:
            return _fail(e.code, f"Failed to detect latest version: {e}")

    keep_set: set = set()
    # Hashes of the RELEASE's copy of each kept path, captured while the payload still
    # exists (a downloaded payload lives in a TemporaryDirectory cleaned up before the lock
    # is written). Recorded in the lock instead of the kept local content's own hash — see
    # `_compute_align_plan`'s KEEP docstring for why using the local hash would let the very
    # next upgrade silently clobber the customization (reqQuestFramework#5 review).
    keep_release_hashes: Dict[str, str] = {}
    symlinked_hashes: Dict[str, str] = {}
    align_plan: Optional[List[Dict[str, Any]]] = None
    align_result: Optional[Dict[str, int]] = None
    # Captured while the payload still exists, so the lock-generation boundary_files() call
    # below can keep using the RELEASE's boundary even if `--keep toolkit-manifest.json`
    # left an older manifest on disk (reqQuestFramework#5 review) — that manifest would
    # otherwise silently narrow what the lock hashes, though not what `align` just copied.
    align_boundary_globs: Optional[Tuple[List[str], List[str]]] = None

    if parsed.align:
        with tempfile.TemporaryDirectory() as td:
            try:
                if parsed.payload:
                    payload_root = GH._validate_offline_payload_dir(parsed.payload, "--payload")
                else:
                    tag = f"{T.TOOLKIT_TAG_PREFIX}v{version}"
                    payload_root = GH._download_toolkit_payload(parsed.source, tag, Path(td) / "release")
            except T.ToolkitError as e:
                return _fail(e.code, str(e))

            try:
                align_boundary_globs = T._toolkit_boundary_globs(payload_root)
                release_files = {p.relative_to(payload_root).as_posix()
                                  for p in T._toolkit_boundary_files(payload_root, globs=align_boundary_globs)}
            except T.ToolkitError as e:
                return _fail(e.code, str(e))
            if not release_files:
                return _fail("EMPTY_BOUNDARY",
                             f"Release v{version}'s boundary matched no files — nothing to align to.")

            for raw in (parsed.keep or []):
                rel = T._relativize_to_root(raw)
                if rel not in release_files:
                    print(f"⚠ --keep {raw!r} is not part of the v{version} release boundary "
                          f"— ignored", file=sys.stderr)
                    continue
                keep_set.add(rel)

            # What has this toolkit ever actually shipped/managed in THIS repo, per an
            # existing lock — as opposed to what merely matches the boundary glob on disk
            # (reqQuestFramework#67). A fresh/pre-versioning repo has no lock yet, so
            # `ever_shipped` stays None and every glob match with no release counterpart is
            # treated as genuinely local, not the toolkit's concern. A corrupt lock is
            # treated the same way (best-effort) rather than aborting the align.
            try:
                existing_lock = T.load_toolkit_lock(strict=True)
            except T.ToolkitError as e:
                print(f"⚠ ignoring unreadable {T.TOOLKIT_LOCK.relative_to(C.ROOT)} for align "
                      f"history: {e}", file=sys.stderr)
                existing_lock = None
            ever_shipped = AL._lock_ever_shipped(existing_lock)

            align_plan = AL._compute_align_plan(payload_root, C.ROOT, keep_set,
                                              globs=align_boundary_globs,
                                              ever_shipped=ever_shipped)
            align_result = AL._apply_align_plan(align_plan, C.ROOT, dry_run=parsed.dry_run)
            keep_release_hashes = {a["path"]: T._sha256_file(Path(a["new"]))
                                    for a in align_plan if a["action"] == "KEEP"}
            symlinked_hashes = AL._release_hashes_beyond_glob(payload_root, C.ROOT)

        needs_attention = bool(align_result["local_only"] or align_result["collisions"])

        if parsed.dry_run:
            if parsed.format == "json":
                print(json.dumps({
                    "command": "adopt",
                    "mode": "align",
                    "dry_run": True,
                    "version": version,
                    "source": parsed.source,
                    "channel": parsed.channel,
                    "align": {
                        "files": AL._align_plan_to_json(align_plan),
                        "summary": align_result,
                        "needs_attention": needs_attention,
                    },
                }, indent=2))
            else:
                AL._print_align_report(version, align_plan, align_result, dry_run=True)
            return 2 if needs_attention else 0

        if parsed.format != "json":
            AL._print_align_report(version, align_plan, align_result, dry_run=False)

        if align_result["collisions"]:
            # A collision means the working tree cannot actually be brought in line with
            # this release yet — writing a lock regardless would claim a clean vX.Y.Z
            # baseline while one of its files is still, in fact, a directory (or blocked by
            # one). Leave any existing lock untouched instead of establishing a falsely
            # "clean" one `check` would then have no way to flag (reqQuestFramework#5
            # review).
            if parsed.format == "json":
                print(json.dumps({
                    "command": "adopt",
                    "mode": "align",
                    "dry_run": False,
                    "lock_written": False,
                    "version": version,
                    "source": parsed.source,
                    "channel": parsed.channel,
                    "align": {
                        "files": AL._align_plan_to_json(align_plan),
                        "summary": align_result,
                        "needs_attention": True,
                    },
                }, indent=2))
            else:
                print(f"\n✗ toolkit.lock NOT written — {align_result['collisions']} "
                      f"unresolved file/directory collision(s); resolve them and re-run "
                      f"`adopt --align`", file=sys.stderr)
            return 2

    try:
        # After --align, use the RELEASE's boundary (captured above) rather than
        # re-deriving it from ROOT: if --keep preserved an older toolkit-manifest.json,
        # re-deriving here would silently drop files the release just added from the lock,
        # even though align copied them onto disk.
        boundary_files = T._toolkit_boundary_files(globs=align_boundary_globs) if parsed.align \
            else T._toolkit_boundary_files()
    except T.ToolkitError as e:
        return _fail(e.code, str(e))
    files_dict: Dict[str, str] = {}
    for fpath in boundary_files:
        files_dict[fpath.relative_to(C.ROOT).as_posix()] = T._sha256_file(fpath)
    # The boundary glob does not walk into a symlinked folder: files there come from the release.
    files_dict.update(symlinked_hashes)
    files_dict.update(keep_release_hashes)
    if not files_dict:
        # The usual cause is a tarball unpacked without --strip-components=1, leaving the
        # toolkit one directory below ROOT. Writing `"files": {}` here would report success
        # and leave `check` with nothing to compare against, forever.
        return _fail("EMPTY_BOUNDARY",
                     f"Toolkit boundary matched no files under {C.ROOT} — nothing to adopt. "
                     f"Check that the toolkit was extracted into the repository root "
                     f"(tar xzf raac-toolkit-*.tar.gz --strip-components=1).")

    local_overrides = []
    for raw in (parsed.local_override or []):
        rel = T._relativize_to_root(raw)
        if rel not in files_dict:
            print(f"⚠ --local-override {raw!r} is not inside the toolkit boundary — ignored "
                  f"(it would be silently overwritten on upgrade)", file=sys.stderr)
            continue
        local_overrides.append(rel)
    # --keep paths are already ROOT-relative and validated against the release boundary
    # above — re-running `_relativize_to_root` on them here would resolve a second time
    # against the current working directory and could point at the wrong file.
    for rel in keep_set:
        if rel in files_dict and rel not in local_overrides:
            local_overrides.append(rel)
    local_overrides.sort()

    lock_data = {
        "toolkit_version": version,
        "source": parsed.source,
        "channel": parsed.channel,
        "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "installed_by": parsed.installed_by,
        "files": files_dict,
        "local_overrides": local_overrides,
    }

    T.write_toolkit_lock(lock_data)
    rel_path = T.TOOLKIT_LOCK.relative_to(C.ROOT)
    if parsed.format == "json":
        doc: Dict[str, Any] = {
            "command": "adopt",
            "version": version,
            "source": parsed.source,
            "channel": parsed.channel,
            "installed_by": parsed.installed_by,
            "installed_at": lock_data["installed_at"],
            "lock_path": str(rel_path),
            "files": sorted(files_dict.keys()),
            "local_overrides": local_overrides,
        }
        if parsed.align:
            doc["mode"] = "align"
            doc["align"] = {
                "dry_run": False,
                "files": AL._align_plan_to_json(align_plan),
                "summary": align_result,
                # Collisions never reach here — a collision returns above, before the lock
                # is written at all.
                "needs_attention": bool(align_result["local_only"]),
            }
        print(json.dumps(doc, indent=2))
    else:
        print(f"✓ adopted toolkit v{version} to {rel_path}")
    return 2 if (parsed.align and align_result["local_only"]) else 0
