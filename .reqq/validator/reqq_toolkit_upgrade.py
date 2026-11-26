# -*- coding: utf-8 -*-
"""The `upgrade` subcommand and its reports."""
import argparse, json, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import reqq_common as C  # noqa: E402
import reqq_toolkit_core as T  # noqa: E402
import reqq_toolkit_github as GH  # noqa: E402
import reqq_toolkit_align as AL  # noqa: E402
import reqq_toolkit_merge as ME  # noqa: E402


# reqQuestFramework#7: base-fetch failures that mean "genuinely gone" rather than "in doubt".
# CHECKSUM_MISMATCH is deliberately excluded — a byte mismatch against a still-published
# SHA256SUMS entry looks like tampering or a corrupt transfer, not a missing release, and
# should fail loudly for investigation rather than silently fall back.
_BASE_MISSING_CODES = {"RELEASE_NOT_FOUND", "ASSET_MISSING", "CHECKSUM_MISSING"}


_UPGRADE_STATE_LABELS = [
    ("REPLACE",              "State 1 — replaced (unchanged locally)"),
    ("MERGE",                "State 2 — 3-way merged (local_overrides)"),
    ("REPLACE_WITH_WARNING", "State 3 — replaced, UNDECLARED LOCAL CHANGE OVERWRITTEN"),
    ("ADD",                  "State 4 — added"),
    ("ADD_COLLISION",        "State 4 — collision, local file kept, added to local_overrides"),
    ("PATH_BLOCKED",         "State 4 — a local directory, a file above it or a symlink blocks the path, left untouched"),
    ("KEEP",                 "Override reached through a symlink — local file kept, not written"),
    ("REMOVE",               "State 5 — removed"),
    ("REMOVE_KEPT",          "State 5 — removal blocked, local file kept"),
    ("KEEP_SEED",            "Seed now toolkit-managed — local file kept, added to local_overrides"),
    ("REGENERATE",           "State 6 — toolkit.lock regenerated"),
]


def _print_upgrade_report(from_v: str, to_v: str, channel: str,
                          plan: List[Dict[str, Any]], result: Dict[str, Any],
                          dry_run: bool, changelog_delta: str) -> None:
    """Emit the file-table-by-state + CHANGELOG delta that `ci-pr` turns into a PR body."""
    verb = "Would upgrade" if dry_run else "Upgraded"
    print(f"\n{verb} toolkit v{from_v} → v{to_v} (channel: {channel})\n")

    by_action: Dict[str, List[str]] = {}
    for a in plan:
        by_action.setdefault(a["action"], []).append(a["path"])
    for action, label in _UPGRADE_STATE_LABELS:
        paths = by_action.get(action)
        if not paths:
            continue
        print(f"{label}: {len(paths)}")
        for p in sorted(paths):
            print(f"  - {p}")

    warnings = [
        (result["conflicts"],
         "file(s) contain merge conflict markers — resolve before merging the PR"),
        (result["merge_failed"],
         "merge(s) failed — local content kept"),
        (result["overwritten_changes"],
         "undeclared local change(s) overwritten — add to local_overrides and redo if intentional"),
        (result["collisions"],
         "new upstream file(s) collided with local files — reconcile by hand"),
        (result["removal_blocked"],
         "upstream removal(s) blocked by local edits"),
    ]
    emitted = [f"⚠ {n} {msg}" for n, msg in warnings if n]
    if emitted:
        print("\n" + "\n".join(emitted))

    print("\n--- CHANGELOG delta ---")
    print(changelog_delta if changelog_delta is not None
          else "(changelog delta skipped — offline mode, no network access)")


def _upgrade_plan_files_for_json(plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Project an upgrade plan to the `files` shape of the `--format json` document:
    `path` + `action` always, `conflict` only on MERGE entries that ran, `restored` only
    on ADD, `error` only on a MERGE whose 3-way merge could not run at all (e.g. `git`
    unavailable) — mutually exclusive with `conflict` on the same entry, `release_changed`
    only on KEEP and PATH_BLOCKED."""
    files = []
    for a in plan:
        entry = {"path": a["path"], "action": a["action"]}
        if "conflict" in a:
            entry["conflict"] = a["conflict"]
        if "restored" in a:
            entry["restored"] = a["restored"]
        if "error" in a:
            entry["error"] = a["error"]
        if "release_changed" in a:
            entry["release_changed"] = a["release_changed"]
        files.append(entry)
    return files


def _upgrade_result_to_json(from_v: str, to_v: str, channel: str, source: str, dry_run: bool,
                            plan: List[Dict[str, Any]], result: Dict[str, Any],
                            needs_attention: bool, changelog_delta: Optional[str],
                            already_up_to_date: bool = False,
                            lock_written: Optional[bool] = None) -> Dict[str, Any]:
    """Build the `upgrade --format json` success document (contract: docstring of `reqq_toolkit_core`)."""
    return {
        "command": "upgrade",
        "dry_run": dry_run,
        "from_version": from_v,
        "to_version": to_v,
        "channel": channel,
        "source": source,
        "major": T._semver_tuple(to_v)[0] > T._semver_tuple(from_v)[0],
        "already_up_to_date": already_up_to_date,
        "files": _upgrade_plan_files_for_json(plan),
        "summary": result,
        "needs_attention": needs_attention,
        "changelog_delta": changelog_delta,
        "lock_written": (not dry_run and not already_up_to_date) if lock_written is None else lock_written,
    }


def _regenerate_lock_after_upgrade(old_lock: Dict[str, Any], version: str,
                                   channel: str, source: str,
                                   override_hashes: Optional[Dict[str, str]] = None,
                                   globs: Optional[Tuple[List[str], List[str]]] = None,
                                   new_overrides: Optional[List[str]] = None,
                                   release_root: Optional[Path] = None,
                                   blocked: Optional[List[str]] = None) -> None:
    """D6 state 6: rewrite `toolkit.lock` from the upgraded working tree.

    New `toolkit_version` / `installed_at` / recomputed hashes; `local_overrides` and
    `installed_by` carry over — the adopter's intent survives an upgrade. An override
    that no longer names a boundary file (upstream dropped it) is quietly discarded.

    `override_hashes` (reqQuestFramework#7 review, REQQF#79): release hashes to record instead
    of hashing the working tree, for paths whose local content was kept or merged — the
    fallback's KEEP, and the normal path's MERGE, ADD_COLLISION, KEEP_SEED and KEEP. Recording
    the kept local content's OWN hash would make it read as "unchanged since lock" on the very
    next upgrade and get silently REPLACEd before `local_overrides` is ever consulted — the
    same class of bug `adopt --align`'s KEEP handling already guards against.

    `globs` (reqQuestFramework#8 review): the boundary (include, exclude) to hash against,
    already derived from the TARGET release's own `toolkit-manifest.json` by the
    full-alignment-fallback caller. Re-deriving it here from ROOT would read the adopter's
    own `toolkit-manifest.json` instead — if that path was itself `--keep`/`local_overrides`
    and so left untouched by the alignment, the lock would silently miss any file the new
    boundary added, even though alignment just copied it onto disk. The normal 3-way path
    passes the target release's boundary only when the merge of an overridden manifest left
    conflict markers. `None` re-derives from ROOT, the boundary `check` reads.

    `new_overrides` (REQQF#77 review, REQQF#79): paths to add to `local_overrides` — former
    seed files the target release now manages, and adopter files kept on a collision, both
    paired with their release hash in `override_hashes`, so the next upgrade 3-way merges
    instead of replacing them.

    `release_root` (the target payload) and `blocked` (paths left blocked that the release
    did not change): the release hash is recorded for a file the boundary glob misses or
    cannot be trusted for — one reached through a symlink, and a blocked path whether or not
    a file is there, so `check` still reports its drift. The payload is expanded with the
    boundary the lock follows, so nothing outside it is recorded.
    """
    files_dict = {p.relative_to(C.ROOT).as_posix(): T._sha256_file(p)
                  for p in T._toolkit_boundary_files(globs=globs)}
    if release_root is not None:
        lock_globs = globs if globs is not None else T._toolkit_boundary_globs(C.ROOT)
        files_dict.update(AL._release_hashes_beyond_glob(release_root, C.ROOT, lock_globs,
                                                         blocked or []))
    for rel, digest in (override_hashes or {}).items():
        if rel in files_dict:
            files_dict[rel] = digest
    kept_overrides = sorted(o for o in set(old_lock.get("local_overrides", [])) | set(new_overrides or [])
                            if o in files_dict)
    T.write_toolkit_lock({
        "toolkit_version": version,
        "source": source,
        "channel": channel,
        "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "installed_by": old_lock.get("installed_by", "manual"),
        "files": files_dict,
        "local_overrides": kept_overrides,
    })


def cmd_upgrade(args) -> int:
    """Upgrade the adopted toolkit to a newer release via 3-way merge (REQQF-ADR-TOOLKIT-100 D6).

    Downloads the vA (currently adopted) and vB (target) `raac-toolkit-*.tar.gz` assets,
    verifies them against the release-body SHA256SUMS, then drives the per-file state
    machine (states 1–6) over the working tree and regenerates `.reqq/toolkit.lock`. The
    report on stdout is what the `ci-pr` workflow turns into a PR body.

    Offline mode (reqQuestFramework#3): `--base-payload DIR --target-payload DIR` point at
    already-extracted `raac-toolkit-<version>/` directories — an orchestrator that has
    already downloaded and checksum-verified both payloads. No network calls are made
    (the CHANGELOG delta is skipped too, since fetching it also needs the network);
    `--version` must be given explicitly since there is no release API to ask. Checksum
    verification is the caller's responsibility in this mode.

    Missing-base fallback (reqQuestFramework#7): the target (vB) release/asset must always
    resolve — that failure is fatal (exit 3). The BASE (vA, the currently-adopted version)
    is allowed to be genuinely gone: its release or asset was deleted, or its release body
    never got a SHA256SUMS entry (`_BASE_MISSING_CODES`). Online mode only — `--base-payload`
    hands a base in directly, so there is nothing to fall back from. When it happens, there
    is no vA to diff against for a 3-way merge, so this falls back to the same full-alignment
    plan `adopt --align` uses for a repo with no captured baseline, reports the fallback
    loudly (never silently), and always exits 2. A base that fails checksum verification
    against a *published* SHA256SUMS entry (`CHECKSUM_MISMATCH`) is NOT treated as missing —
    that looks like tampering or a corrupt transfer and fails hard (exit 3) for investigation.

    Exit: 0 = clean upgrade / already newest, 2 = applied but needs a human (including every
    missing-base fallback), 3 = not adopted / release or asset missing / checksum mismatch /
    bad arguments.
    """
    ap = argparse.ArgumentParser(prog="reqq_validate.py upgrade")
    ap.add_argument("--version", help="Target toolkit version (default: latest on channel; "
                    "required with --base-payload/--target-payload)")
    ap.add_argument("--channel", choices=["stable", "next"],
                    help="Override the channel from config.yaml / toolkit.lock.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute and report the plan without touching the working tree.")
    ap.add_argument("--format", choices=["plain", "json"], default="plain", help="Output format.")
    ap.add_argument("--base-payload", help="Path to an already-extracted vA (currently "
                    "adopted) payload directory. Requires --target-payload and --version; "
                    "makes no network calls. Checksum verification is the caller's "
                    "responsibility.")
    ap.add_argument("--target-payload", help="Path to an already-extracted vB (target) "
                    "payload directory. Requires --base-payload and --version.")
    parsed = ap.parse_args(args)

    if bool(parsed.base_payload) != bool(parsed.target_payload):
        return T._emit_toolkit_error(parsed.format, "INVALID_ARGS",
            "--base-payload and --target-payload must be given together")
    offline = bool(parsed.base_payload and parsed.target_payload)
    if offline and not parsed.version:
        return T._emit_toolkit_error(parsed.format, "INVALID_ARGS",
            "--version is required with --base-payload/--target-payload "
            "(offline mode has no release API to detect it from)")

    if offline:
        try:
            offline_base_root = GH._validate_offline_payload_dir(parsed.base_payload, "--base-payload")
            offline_target_root = GH._validate_offline_payload_dir(parsed.target_payload, "--target-payload")
        except T.ToolkitError as e:
            return T._emit_toolkit_error(parsed.format, e.code, str(e))

    try:
        lock = T.load_toolkit_lock(strict=True)
    except T.ToolkitError as e:
        return T._emit_toolkit_error(parsed.format, e.code, str(e))
    if lock is None:
        return T._emit_toolkit_error(parsed.format, "NOT_ADOPTED",
            "toolkit not adopted — run `reqq_validate.py adopt` first")
    current_version = lock.get("toolkit_version")
    if not current_version:
        return T._emit_toolkit_error(parsed.format, "LOCK_MISSING_VERSION",
            f"{T.TOOLKIT_LOCK.relative_to(C.ROOT)} has no 'toolkit_version' — re-run `adopt`")

    source = lock.get("source", T.DEFAULT_TOOLKIT_SOURCE)
    tk_cfg = C.load_config().get("toolkit") or {}
    channel = parsed.channel or tk_cfg.get("update_channel") or lock.get("channel", "stable")
    if channel not in ("stable", "next"):
        print(f"⚠ unknown update channel {channel!r} — falling back to 'stable'", file=sys.stderr)
        channel = "stable"

    try:
        if parsed.version:
            target_version = T._normalize_version(parsed.version)
        else:
            target_version = T._normalize_version(GH._latest_release_tag(source, channel))
    except T.ToolkitError as e:
        return T._emit_toolkit_error(parsed.format, e.code,
                                   f"cannot determine the target release: {e}")

    try:
        already_up_to_date = not T._semver_lt(current_version, target_version)
    except T.ToolkitError as e:
        # An explicit --version that isn't valid SemVer (or a hand-edited lock's
        # toolkit_version) reaches here — _normalize_version above does not itself
        # validate, it only strips known prefixes.
        return T._emit_toolkit_error(parsed.format, e.code, str(e))

    if already_up_to_date:
        if parsed.format == "json":
            print(json.dumps(_upgrade_result_to_json(
                current_version, target_version, channel, source, parsed.dry_run,
                [], ME._empty_upgrade_result(), False, None,
                already_up_to_date=True), indent=2))
        else:
            print(f"✓ already on toolkit v{current_version} "
                  f"(target v{target_version} is not newer) — nothing to upgrade")
        return 0

    fallback_reason: Optional[str] = None
    with tempfile.TemporaryDirectory() as td:
        try:
            if offline:
                new_root = offline_target_root
            else:
                target_tag = f"{T.TOOLKIT_TAG_PREFIX}v{target_version}"
                new_root = GH._download_toolkit_payload(source, target_tag, Path(td) / "vB")
        except T.ToolkitError as e:
            return T._emit_toolkit_error(parsed.format, e.code, str(e))

        base_root: Optional[Path] = None
        if offline:
            base_root = offline_base_root
        else:
            current_tag = f"{T.TOOLKIT_TAG_PREFIX}v{T._normalize_version(current_version)}"
            try:
                base_root = GH._download_toolkit_payload(source, current_tag, Path(td) / "vA")
            except T.ToolkitError as e:
                if e.code not in _BASE_MISSING_CODES:
                    return T._emit_toolkit_error(parsed.format, e.code, str(e))
                # reqQuestFramework#7: the merge base is genuinely gone — its release/tag or
                # asset was deleted, or the release body never got a SHA256SUMS entry. A
                # 3-way merge has nothing trustworthy to diff against, and guessing which
                # local files "changed since vA" without vA would risk a silently wrong
                # merge. Fall back to the same full-alignment machinery `adopt --align` uses
                # for a repo with no captured baseline at all, and say so loudly.
                fallback_reason = f"{e.code}: {e}"

        keep_release_hashes: Dict[str, str] = {}
        unchanged_blocked: List[str] = []
        new_overrides: List[str] = []
        try:
            if fallback_reason is not None:
                keep_set = set(lock.get("local_overrides", []))
                align_globs = T._toolkit_boundary_globs(new_root)
                # Without vA's payload, the adopted manifest still on disk says which files
                # were seeds (REQQF#77 review): keep them like overrides rather than let the
                # alignment overwrite an adopter-owned file the target now manages.
                adopted_seed = T._toolkit_seed_globs(C.ROOT)
                seed_keep = {p.relative_to(new_root).as_posix()
                             for p in T._toolkit_boundary_files(new_root, globs=align_globs)
                             if T._matches_any(p.relative_to(new_root).as_posix(), adopted_seed)}
                keep_set |= seed_keep
                # `lock` (the adopted toolkit's own record) is the source of truth for what
                # this toolkit ever actually shipped/managed in this repo — a path that only
                # matches the boundary glob without ever being in `lock["files"]` is not the
                # toolkit's concern (reqQuestFramework#67). `lock` reaching this point is
                # already known to be a JSON object (`cmd_upgrade` loaded it via
                # `load_toolkit_lock(strict=True)` above), but its `files` field could still
                # be malformed by hand — `_lock_ever_shipped()` treats that as "no history"
                # instead of crashing on `.keys()`.
                ever_shipped = AL._lock_ever_shipped(lock)
                plan = AL._compute_align_plan(new_root, C.ROOT, keep_set, globs=align_globs,
                                            ever_shipped=ever_shipped)
                result = AL._apply_align_plan(plan, C.ROOT, dry_run=parsed.dry_run)
                # Same fix as `adopt --align`'s KEEP handling (reqQuestFramework#5 review):
                # record the RELEASE's hash for a kept path, not the (untouched-by-definition)
                # local content's own hash — otherwise the very next upgrade reads it as
                # "unchanged since lock" and REPLACEs it before local_overrides is ever
                # consulted, silently discarding the customization one run later.
                keep_release_hashes = {a["path"]: T._sha256_file(Path(a["new"]))
                                        for a in plan if a["action"] == "KEEP"}
                new_overrides = [a["path"] for a in plan
                                 if a["action"] == "KEEP" and a["path"] in seed_keep]
            else:
                plan = ME._compute_upgrade_plan(lock, base_root, new_root, C.ROOT)
                result = ME._apply_upgrade_plan(plan, C.ROOT, dry_run=parsed.dry_run)
                # The lock follows ROOT's manifest, as `check` does, unless the merge of an
                # overridden one left conflict markers: that is not JSON, so the release's
                # own manifest decides instead.
                align_globs = T._toolkit_boundary_globs(new_root) if any(
                    a["path"] == T.TOOLKIT_MANIFEST_REL and a.get("conflict")
                    for a in plan) else None
                # Local content kept or merged gets the release hash, and is (or becomes) an
                # override (REQQF#77, REQQF#79): the next upgrade 3-way merges it instead of
                # reading it as untouched and replacing it.
                keep_release_hashes = {Path(a["path"]).as_posix(): T._sha256_file(Path(a["new"]))
                                       for a in plan
                                       if a["action"] in ("KEEP_SEED", "ADD_COLLISION", "MERGE", "KEEP")}
                new_overrides = list(keep_release_hashes)
                unchanged_blocked = [Path(a["path"]).as_posix() for a in plan
                                     if a["action"] == "PATH_BLOCKED" and not a["release_changed"]]
        except T.ToolkitError as e:
            return T._emit_toolkit_error(parsed.format, e.code, str(e))

        # A collision during the fallback means the working tree cannot actually be brought in
        # line with the target release yet — same reasoning `adopt --align` already applies
        # (reqQuestFramework#5 review): writing the lock regardless would advance
        # toolkit_version to a release whose boundary is not fully realized on disk, and the
        # very next run would read the repo as already up to date, permanently hiding the
        # unresolved collision instead of letting a re-run pick it up once resolved by hand.
        # A PATH_BLOCKED release file is not on disk either, so a normal upgrade keeps the lock
        # for the same reason — unless the release did not change it: then there is nothing
        # to install.
        blocked = sum(a["action"] == "PATH_BLOCKED" and a["release_changed"] for a in plan)
        lock_blocked_by_collision = (
            (fallback_reason is not None and bool(result.get("collisions"))) or bool(blocked))
        lock_written = not parsed.dry_run and not lock_blocked_by_collision
        not_written = "would not be written" if parsed.dry_run else "NOT written"
        if lock_written:
            _regenerate_lock_after_upgrade(
                lock, target_version, channel, source,
                override_hashes=keep_release_hashes,
                globs=align_globs,
                new_overrides=new_overrides,
                release_root=new_root,
                blocked=unchanged_blocked)

    changelog_delta = None if (offline or fallback_reason is not None) else \
        GH._changelog_delta(source, channel, current_version, target_version)

    if fallback_reason is not None:
        # The fallback itself is always worth a human's attention, regardless of whether the
        # alignment also hit its own local_only/collision cases.
        needs_attention = True
        if parsed.format == "json":
            print(json.dumps({
                "command": "upgrade",
                "mode": "full_alignment_fallback",
                "dry_run": parsed.dry_run,
                "already_up_to_date": False,
                "lock_written": lock_written,
                "from_version": current_version,
                "to_version": target_version,
                "channel": channel,
                "source": source,
                "major": T._semver_tuple(target_version)[0] > T._semver_tuple(current_version)[0],
                "fallback_reason": fallback_reason,
                "files": AL._align_plan_to_json(plan),
                "summary": result,
                "needs_attention": True,
                "changelog_delta": changelog_delta,
            }, indent=2))
        else:
            print(f"\n⚠ merge base v{current_version} unavailable ({fallback_reason}) — "
                  f"falling back to FULL ALIGNMENT against v{target_version} instead of a "
                  f"3-way merge; review overwritten files by hand", file=sys.stderr)
            AL._print_align_report(target_version, plan, result, dry_run=parsed.dry_run)
            if lock_blocked_by_collision:
                print(f"\n✗ toolkit.lock {not_written} — {result['collisions']} unresolved "
                      f"file/directory collision(s); resolve them and re-run `upgrade`",
                      file=sys.stderr)
            print("\n--- CHANGELOG delta ---")
            print(changelog_delta if changelog_delta is not None
                  else "(changelog delta skipped)")
    else:
        needs_attention = bool(result["conflicts"] or result["merge_failed"]
                               or result["overwritten_changes"] or result["collisions"]
                               or result["removal_blocked"])
        if parsed.format == "json":
            print(json.dumps(_upgrade_result_to_json(
                current_version, target_version, channel, source, parsed.dry_run,
                plan, result, needs_attention, changelog_delta,
                lock_written=lock_written), indent=2))
        else:
            _print_upgrade_report(current_version, target_version, channel,
                                  plan, result, dry_run=parsed.dry_run,
                                  changelog_delta=changelog_delta)
            if lock_blocked_by_collision:
                print(f"\n✗ toolkit.lock {not_written} — {blocked} unresolved "
                      f"file/directory collision(s); resolve them and every merge conflict "
                      f"(a re-run merges a file with markers again), then re-run `upgrade`",
                      file=sys.stderr)

    return 2 if needs_attention else 0
