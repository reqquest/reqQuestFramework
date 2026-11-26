# -*- coding: utf-8 -*-
"""Full alignment with a release: plan, apply and report for `adopt --align` and the upgrade fallback."""
import shutil, sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import reqq_toolkit_core as T  # noqa: E402


def _blocked_by_non_directory_ancestor(path: Path, working_root: Path) -> bool:
    """True if some ancestor of `path` (below `working_root`) exists but is not a directory.

    `_toolkit_boundary_files()` walks through non-directory path components silently (a
    `glob()` just yields nothing there, no error), so a plain file sitting where the release
    needs a directory — e.g. a file at `.reqq/schema` when the release ships
    `.reqq/schema/requirement.schema.json` — reads as "absent locally" the same way a direct
    leaf collision does. Left undetected, `parent.mkdir(parents=True, exist_ok=True)` raises
    an uncaught `FileExistsError` when the plan is applied (reqQuestFramework#5 review).
    """
    cur = path.parent
    while cur != working_root and cur != cur.parent:
        if cur.exists() and not cur.is_dir():
            return True
        cur = cur.parent
    return False


def _through_symlink(path: Path, working_root: Path) -> bool:
    """Whether `path`, or a folder between it and `working_root`, is a symlink: writing the
    release file there would follow it, possibly out of the working tree."""
    cur = path
    while cur != working_root and cur != cur.parent:
        if cur.is_symlink():
            return True
        cur = cur.parent
    return False


def _release_hashes_beyond_glob(payload_root: Path, working_root: Path,
                                globs: Optional[Tuple[List[str], List[str]]] = None,
                                blocked: List[str] = ()) -> Dict[str, str]:
    """Release hashes, for the lock, of the payload's boundary files (`globs`: the boundary
    the lock follows; default the payload's own) that the boundary glob over `working_root`
    misses: one reached as a file through a symlink (the glob does not walk into a symlinked
    folder), and a `blocked` path whether or not a file is there."""
    rels = [p.relative_to(payload_root).as_posix()
            for p in T._toolkit_boundary_files(payload_root, payload_root, globs=globs)]
    return {rel: T._sha256_file(payload_root / rel) for rel in rels
            if rel in blocked or (_through_symlink(working_root / rel, working_root)
                                  and (working_root / rel).is_file())}


def _lock_ever_shipped(lock: Any) -> Optional[Set[str]]:
    """ROOT-relative paths an existing `toolkit.lock` records this toolkit as having
    hashed/managed in this repo — the `ever_shipped` history `_compute_align_plan()` needs
    to tell "matches the boundary glob" apart from "was actually ours" (reqQuestFramework#67).

    Returns None — "no usable history", handled by `_compute_align_plan()` the same as "no
    lock at all" — for a missing lock, a lock whose TOP-LEVEL document isn't even a JSON
    object, AND a lock whose `files` is not a JSON object (a hand-edited or otherwise
    malformed lock, e.g. `"files": []` or a lock that is itself a bare `[]`).
    `load_toolkit_lock(strict=True)` only validates that the file is well-formed JSON, not
    that its shape is the expected object — a `toolkit.lock` containing just `[]` parses
    fine and reaches here as a plain `list`, which has no `.get()` (PR #68 review). A caller
    that already guarantees `lock["files"]` is a dict (any lock this module itself wrote)
    still passes through fine; this only guards the pass-a-lock-you-loaded path against
    reading a differently-shaped value.
    """
    if not isinstance(lock, dict):
        return None
    files = lock.get("files")
    if not isinstance(files, dict):
        return None
    return set(files.keys())


def _compute_align_plan(payload_root: Path, working_root: Path, keep: set,
                         globs: Optional[Tuple[List[str], List[str]]] = None,
                         ever_shipped: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    """Compute an `adopt --align` plan (reqQuestFramework#5).

    Unlike `_compute_upgrade_plan` there is no vA — a pre-versioning or unanchored repo has
    no captured "before" state to diff against, only the release payload and whatever is
    on disk now. The release payload's own `toolkit-manifest.json` decides the boundary for
    both sides (`_toolkit_boundary_files(root, payload_root)`), so a stale or absent local
    manifest never causes the wrong file set to be compared.

    `ever_shipped`, when given, is the set of ROOT-relative paths recorded in an existing
    `toolkit.lock`'s `files` — i.e. paths some past release of this toolkit actually
    hashed/managed in this repo (reqQuestFramework#67). A path matching the boundary glob
    locally but ABSENT from `ever_shipped` (including when `ever_shipped` is None — no prior
    lock at all, e.g. a genuinely pre-versioning repo) is not this toolkit's business: the
    glob only says the filename/location happens to look like something the toolkit could
    ship, not that it ever did — a `README.md` an adopter wrote for their own requirements
    category, say. Such a path produces no plan entry at all. Only a path the lock says was
    once managed, but that this release no longer ships, is a real LOCAL_ONLY: something the
    toolkit used to own and dropped, which the adopter may still be relying on.

    Returns a list of {path, action[, new]} dicts, one per path that needs attention:
      ADD        - shipped by the release, absent locally
      OVERWRITE  - shipped by the release, differs locally, not in `keep`
      KEEP       - shipped by the release, differs locally, in `keep` — local file untouched,
                   also when reached through a symlink.
                   Carries `new` (the release's copy) too: the caller records ITS hash, not
                   the kept local content's, as this path's lock baseline — otherwise the
                   very next `upgrade` would see the kept content as "unchanged since lock"
                   and REPLACE it before ever consulting local_overrides (reqQuestFramework#5
                   review).
      LOCAL_ONLY - previously recorded in `ever_shipped` (a past release of this toolkit
                   managed it in this repo) but the current release no longer ships it;
                   reported only, never deleted. A path that merely matches the boundary
                   glob without ever having been in the lock is NOT LOCAL_ONLY — see
                   `ever_shipped` above — and produces no entry.
      COLLISION  - shipped by the release; the local path exists but is not a plain file (a
                   directory, most commonly), OR an ancestor directory the release needs is
                   itself occupied by a plain file — `_toolkit_boundary_files()` silently
                   skips both cases, so they would otherwise be indistinguishable from
                   "absent locally" (ADD) and either make `shutil.copy2()` nest the release
                   file inside the wrong place or crash `parent.mkdir()` with an uncaught
                   `FileExistsError` when the plan is applied (reqQuestFramework#5 review).
                   So is a path reached through a symlink, unless it is a kept file or
                   already has the release content.
                   Reported only, untouched.
    A path identical in both places produces no entry.
    """
    release_files = {p.relative_to(payload_root).as_posix(): p
                      for p in T._toolkit_boundary_files(payload_root, payload_root, globs=globs)}
    local_files = {p.relative_to(working_root).as_posix(): p
                   for p in T._toolkit_boundary_files(working_root, payload_root, globs=globs)}

    plan: List[Dict[str, Any]] = []
    for rel in sorted(set(release_files) | set(local_files)):
        release_file = release_files.get(rel)
        local_file = local_files.get(rel)

        # Never written through a symlink: a file already at the release needs nothing, and
        # a kept one is the adopter's. Read the path itself: `**` skips symlinked folders.
        target = working_root / rel
        if release_file is not None and _through_symlink(target, working_root):
            if target.is_file() and T._same_content(target, release_file):
                continue
            if rel in keep and target.is_file():
                plan.append({"path": rel, "action": "KEEP", "new": str(release_file)})
            else:
                plan.append({"path": rel, "action": "COLLISION"})
            continue
        if release_file is None:
            if ever_shipped is not None and rel in ever_shipped:
                plan.append({"path": rel, "action": "LOCAL_ONLY"})
            # else: matches the boundary glob but no lock ever recorded this toolkit as
            # managing it here — not ours, skip silently (reqQuestFramework#67).
        elif local_file is None:
            target = working_root / rel
            if target.exists() or _blocked_by_non_directory_ancestor(target, working_root):
                plan.append({"path": rel, "action": "COLLISION"})
            else:
                plan.append({"path": rel, "action": "ADD", "new": str(release_file)})
        elif not T._same_content(local_file, release_file):
            if rel in keep:
                plan.append({"path": rel, "action": "KEEP", "new": str(release_file)})
            else:
                plan.append({"path": rel, "action": "OVERWRITE", "new": str(release_file)})
    return plan


_ALIGN_ACTION_LABELS = [
    ("ADD",        "added"),
    ("OVERWRITE",  "overwritten with the release version"),
    ("KEEP",       "kept as-is (recorded as local_overrides)"),
    ("LOCAL_ONLY", "previously managed by this toolkit but not shipped by this release — "
                   "kept, not deleted"),
    ("COLLISION",  "shipped by the release but occupied locally by something other than a "
                   "plain file, or reached through a symlink — left untouched, reconcile by hand"),
]


def _apply_align_plan(plan: List[Dict[str, Any]], working_root: Path,
                      dry_run: bool = False) -> Dict[str, int]:
    """Apply an align plan. With dry_run=True nothing under `working_root` is touched."""
    result = {"added": 0, "overwritten": 0, "kept": 0, "local_only": 0, "collisions": 0}
    local_only_files: List[str] = []
    collision_files: List[str] = []

    for action in plan:
        kind = action["action"]
        if kind in ("ADD", "OVERWRITE"):
            result["added" if kind == "ADD" else "overwritten"] += 1
            if not dry_run:
                work_file = working_root / Path(action["path"])
                work_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(Path(action["new"]), work_file)
        elif kind == "KEEP":
            result["kept"] += 1
        elif kind == "LOCAL_ONLY":
            result["local_only"] += 1
            local_only_files.append(action["path"])
        elif kind == "COLLISION":
            result["collisions"] += 1
            collision_files.append(action["path"])

    if local_only_files:
        print(f"⚠ previously managed by this toolkit but not shipped by this release "
              f"(kept, not deleted): {', '.join(sorted(local_only_files))}", file=sys.stderr)
    if collision_files:
        print(f"⚠ shipped by this release but occupied locally by something other than a "
              f"plain file — left untouched, reconcile by hand: "
              f"{', '.join(sorted(collision_files))}", file=sys.stderr)
    return result


def _print_align_report(version: str, plan: List[Dict[str, Any]], result: Dict[str, int],
                        dry_run: bool) -> None:
    verb = "Would align" if dry_run else "Aligned"
    print(f"\n{verb} to toolkit v{version}\n")
    by_action: Dict[str, List[str]] = {}
    for a in plan:
        by_action.setdefault(a["action"], []).append(a["path"])
    for action, label in _ALIGN_ACTION_LABELS:
        paths = by_action.get(action)
        if not paths:
            continue
        print(f"{label}: {len(paths)}")
        for p in sorted(paths):
            print(f"  - {p}")
    if result["local_only"]:
        print(f"\n⚠ {result['local_only']} file(s) previously managed by this toolkit but "
              f"not shipped by this release — reconcile by hand")
    if result["collisions"]:
        print(f"\n⚠ {result['collisions']} path(s) shipped by this release are occupied "
              f"locally by something other than a plain file — reconcile by hand")


def _align_plan_to_json(plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{"path": a["path"], "action": a["action"]} for a in plan]
