# -*- coding: utf-8 -*-
"""Upgrade plan and its application: per-file states and the three-way merge."""
import shutil, subprocess, sys, tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import reqq_toolkit_core as T  # noqa: E402
import reqq_toolkit_align as AL  # noqa: E402


def _is_unchanged(work_file: Path, base_file: Path, expected_hash: Optional[str]) -> bool:
    """Is the working copy still the pristine vA file?

    Prefers the hash recorded in toolkit.lock. When the lock has no entry (boundary widened
    since adopt, or a hand-edited lock) it falls back to comparing against the vA payload,
    rather than assuming the file was modified.
    """
    if expected_hash:
        return T._sha256_file(work_file) == expected_hash
    if base_file.exists():
        return T._same_content(work_file, base_file)
    return False


def _compute_upgrade_plan(lock: Dict[str, Any], base_dir: Path, new_dir: Path, working_root: Path) -> List[Dict[str, Any]]:
    """
    Compute upgrade plan per REQQF-ADR-TOOLKIT-100 D6 (states 1–6 per file).

    Returns list of FileAction dicts: {path, action, base, local, new}
    - REPLACE: unchanged locally → replace with the new version
    - MERGE: changed locally AND in local_overrides → 3-way merge
    - REPLACE_WITH_WARNING: changed locally but NOT in overrides → replace and warn
    - ADD: present in vB, absent locally → add (`restored` marks a file the adopter deleted)
    - ADD_COLLISION: new in vB but the adopter already has that path → keep local, warn;
      the caller records vB's hash and declares it in `local_overrides` (REQQF#79)
    - KEEP_SEED: a seed file of vA that vB moves into the boundary, edited locally → keep
      local; the caller records vB's hash and declares it in `local_overrides` (REQQF#77)
    - REMOVE: dropped in vB and untouched locally → delete
    - REMOVE_KEPT: dropped in vB but modified locally, or reached through a symlink → keep, warn
    - PATH_BLOCKED: shipped by vB where the adopter has a directory, below a local file or
      through a symlink → leave untouched (checked before anything reads or writes the path);
      when vB changed it (`release_changed`), report a collision and the caller keeps the lock
    - KEEP: the adopter's file reached through a symlink — in `local_overrides`, a former seed
      or on a path new in vB → leave untouched, report as a collision when vB changed it
      (`release_changed`); the caller records vB's hash and the path as an override, as for
      ADD_COLLISION
    - REGENERATE: toolkit.lock (handled separately)
    """
    plan: List[Dict[str, Any]] = []
    lock_files = {Path(p): h for p, h in lock.get("files", {}).items()}
    local_overrides = set(Path(p) for p in lock.get("local_overrides", []))
    # Seed files ship in the payload for a fresh install, but belong to the adopter from
    # then on (REQQF#77) — never add, replace or remove them. vA may predate the `seed` key,
    # so vB's declaration counts too. A seed of vA that vB moves INTO the boundary becomes
    # toolkit-managed, but the adopter's edits must survive that hand-over: see KEEP_SEED.
    seed_old = T._toolkit_seed_globs(base_dir)
    seed_new = T._toolkit_seed_globs(new_dir)
    new_boundary: Optional[set] = None

    # Collect all paths: union of v1 and v2. Files only in working_root are irrelevant
    # (no state condition requires them). Checking existence via in_work is sufficient.
    all_paths = set()
    for fpath in base_dir.rglob("*"):
        if fpath.is_file():
            try:
                all_paths.add(fpath.relative_to(base_dir))
            except ValueError:
                pass
    for fpath in new_dir.rglob("*"):
        if fpath.is_file():
            try:
                all_paths.add(fpath.relative_to(new_dir))
            except ValueError:
                pass

    for rel_path in sorted(all_paths):
        if rel_path.as_posix() == T.TOOLKIT_LOCK_REL:
            plan.append({"path": str(rel_path), "action": "REGENERATE"})
            continue
        rel = rel_path.as_posix()
        if T._matches_any(rel, seed_new):
            continue
        was_seed = T._matches_any(rel, seed_old)
        if was_seed:
            if new_boundary is None:
                new_boundary = {p.relative_to(new_dir).as_posix()
                                for p in T._toolkit_boundary_files(new_dir)}
            if rel not in new_boundary:
                continue  # still the adopter's, vB just stopped shipping a template
        # Only paths the toolkit manages reach this check; a seed stays the adopter's, whatever
        # occupies it.
        work_path = working_root / rel_path
        if (AL._through_symlink(work_path, working_root)
                or (work_path.exists() and not work_path.is_file())
                or AL._blocked_by_non_directory_ancestor(work_path, working_root)):
            # A plain file here can only be reached through a symlink: one already at the
            # release needs nothing; the adopter's own one — declared, a former seed, or on a
            # path new in vB (as KEEP_SEED and ADD_COLLISION) — is kept; one the release
            # dropped is kept and reported.
            new_file, base_file = new_dir / rel_path, base_dir / rel_path
            if new_file.is_file():
                if not (work_path.is_file() and T._same_content(work_path, new_file)):
                    kept = work_path.is_file() and (
                        rel_path in local_overrides or was_seed or not base_file.is_file())
                    plan.append({"path": str(rel_path),
                                 "action": "KEEP" if kept else "PATH_BLOCKED",
                                 "new": str(new_file),
                                 "release_changed": not (base_file.is_file()
                                                         and T._same_content(base_file, new_file)),
                                 "new_override": kept and rel_path not in local_overrides})
            elif work_path.is_file():
                plan.append({"path": str(rel_path), "action": "REMOVE_KEPT"})
            continue
        if was_seed:
            new_file, work_file = new_dir / rel_path, working_root / rel_path
            if not work_file.exists():
                plan.append({"path": str(rel_path), "action": "ADD", "new": str(new_file),
                             "restored": False})
            elif not T._same_content(work_file, new_file):
                # Recording the local hash as canonical (what the lock regeneration would do
                # on its own) would make the next upgrade read the file as untouched and
                # silently REPLACE it — the adopter's edits would last exactly one upgrade.
                plan.append({"path": str(rel_path), "action": "KEEP_SEED", "new": str(new_file)})
            continue

        base_file = base_dir / rel_path
        new_file = new_dir / rel_path
        work_file = working_root / rel_path

        in_base = base_file.exists()
        in_new = new_file.exists()
        in_work = work_file.exists()

        # --- State 5: vB dropped the file
        if not in_new:
            if not in_work:
                continue  # already absent locally; nothing to do
            if _is_unchanged(work_file, base_file, lock_files.get(rel_path)):
                plan.append({"path": str(rel_path), "action": "REMOVE"})
            else:
                # Deleting a file the adopter customised is unrecoverable — keep it and
                # surface it instead (D6 state 5 requires the removal to be reported anyway).
                plan.append({"path": str(rel_path), "action": "REMOVE_KEPT"})
            continue

        # --- State 4: file present in vB, absent locally (new upstream, or deleted by adopter)
        if not in_work:
            plan.append({"path": str(rel_path), "action": "ADD", "new": str(new_file),
                         "restored": in_base})
            continue

        # --- vB introduces a path the adopter already occupies
        if not in_base:
            if T._same_content(work_file, new_file):
                continue  # identical; nothing to reconcile
            # `local_overrides` could not have covered a path that did not exist in vA, so the
            # "you were warned" logic of state 3 does not apply — never clobber. Report instead.
            plan.append({"path": str(rel_path), "action": "ADD_COLLISION", "new": str(new_file)})
            continue

        # --- States 1–3: file present in vA, vB and locally
        if T._same_content(work_file, new_file):
            continue  # already at vB, e.g. a retry after a blocked lock; nothing to reconcile
        if _is_unchanged(work_file, base_file, lock_files.get(rel_path)):
            # State 1: untouched locally → replace
            plan.append({"path": str(rel_path), "action": "REPLACE", "new": str(new_file)})
        elif rel_path in local_overrides:
            # State 2: changed locally and declared → 3-way merge
            plan.append({"path": str(rel_path), "action": "MERGE",
                         "base": str(base_file), "local": str(work_file), "new": str(new_file)})
        else:
            # State 3: changed locally, not declared → replace and warn
            plan.append({"path": str(rel_path), "action": "REPLACE_WITH_WARNING", "new": str(new_file)})

    return plan


def _merge_three_way(base: Path, local: Path, new: Path, out: Path) -> Tuple[bool, Optional[str]]:
    """3-way merge vA(base) + local + vB(new) into `out`.

    Returns (conflicted, error). `out` always ends up holding the merged text; on error it
    holds the unchanged local content.

    Label order matters: `git merge-file` maps -L onto (current, base, other) = (local, vA, vB).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        base_tmp = Path(tmpdir) / "base"
        local_tmp = Path(tmpdir) / "local"
        new_tmp = Path(tmpdir) / "new"
        shutil.copy2(base, base_tmp)
        shutil.copy2(local, local_tmp)
        shutil.copy2(new, new_tmp)
        try:
            run = subprocess.run(
                ["git", "merge-file", "--diff3",
                 "-L", "local", "-L", "vA", "-L", "vB",
                 str(local_tmp), str(base_tmp), str(new_tmp)],
                check=False,          # 1..127 is the number of conflicts, not a failure
                capture_output=True,  # keep git's diagnostics off the user's stderr
            )
            # A negative status (255 in the shell), e.g. for a binary file, is a failure: git
            # left `local_tmp` untouched, without markers, which would read as a clean merge.
            # So is a kill by a signal, which `subprocess` reports as a negative returncode.
            error = None if 0 <= run.returncode <= 127 else (
                run.stderr.decode(errors="replace").strip()
                or f"git merge-file exited {run.returncode}")
        except (OSError, subprocess.SubprocessError) as e:
            error = str(e)
        if error:
            # In the non-dry-run case `out` IS `local` (the caller merges in place), so the
            # content is already "unchanged" and copying onto itself raises SameFileError.
            # Dry-run passes a distinct temp path here, which does need the copy.
            if out.resolve() != local.resolve():
                shutil.copy2(local, out)
            return False, error
        merged = local_tmp.read_bytes()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(merged)
        return b"<<<<<<<" in merged, None


def _empty_upgrade_result() -> Dict[str, int]:
    """Zero-valued upgrade counters — shared by `_apply_upgrade_plan` and the
    already-up-to-date `--format json` payload (which never runs a plan)."""
    return {"replaced": 0, "merged": 0, "conflicts": 0, "merge_failed": 0,
            "overwritten_changes": 0, "added": 0, "restored": 0,
            "collisions": 0, "removed": 0, "removal_blocked": 0, "seed_kept": 0}


def _apply_upgrade_plan(plan: List[Dict[str, Any]], working_root: Path, dry_run: bool = False) -> Dict[str, Any]:
    """
    Apply an upgrade plan and report what happened.

    Counters: replaced, merged, conflicts, merge_failed, overwritten_changes, added, restored,
    collisions, removed, removal_blocked, seed_kept.

    With dry_run=True nothing under `working_root` is touched, but merges are still performed
    into a temporary file so that conflicts are reported — previewing conflicts is the whole
    point of a dry run.

    Mutates `action["conflict"]` (bool) on every MERGE entry in `plan` in place — the
    `--format json` file list surfaces it per-file instead of only as an aggregate count.
    """
    result = _empty_upgrade_result()
    conflicts_files: List[str] = []
    overwritten_files: List[str] = []
    collision_files: List[str] = []
    blocked_paths: List[str] = []
    blocked_unchanged: List[str] = []
    kept_overrides: List[str] = []
    new_kept: List[str] = []
    blocked_removals: List[str] = []
    failed_merges: List[str] = []
    seed_kept: List[str] = []

    for action in plan:
        path = Path(action["path"])
        work_file = working_root / path
        kind = action["action"]
        if kind == "KEEP" and action["new_override"]:
            new_kept.append(str(path))

        if kind == "REGENERATE":
            continue  # handled by the caller once the payload is in place

        elif kind == "KEEP_SEED":
            result["seed_kept"] += 1
            seed_kept.append(str(path))

        elif kind in ("REPLACE", "REPLACE_WITH_WARNING", "ADD"):
            if kind == "REPLACE":
                result["replaced"] += 1
            elif kind == "REPLACE_WITH_WARNING":
                result["overwritten_changes"] += 1
                overwritten_files.append(str(path))
            else:
                result["added"] += 1
                if action.get("restored"):
                    result["restored"] += 1
            if not dry_run:
                work_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(Path(action["new"]), work_file)

        elif kind == "REMOVE":
            result["removed"] += 1
            if not dry_run and work_file.exists():
                work_file.unlink()

        elif kind == "REMOVE_KEPT":
            result["removal_blocked"] += 1
            blocked_removals.append(str(path))

        elif kind == "ADD_COLLISION":
            result["collisions"] += 1
            collision_files.append(str(path))

        elif kind == "PATH_BLOCKED" and action["release_changed"]:
            result["collisions"] += 1
            blocked_paths.append(str(path))

        elif kind == "PATH_BLOCKED":
            blocked_unchanged.append(str(path))

        elif kind == "KEEP" and action["release_changed"]:
            result["collisions"] += 1
            kept_overrides.append(str(path))

        elif kind == "MERGE":
            with tempfile.TemporaryDirectory() as outdir:
                target = work_file if not dry_run else Path(outdir) / "merged"
                conflicted, err = _merge_three_way(
                    Path(action["base"]), Path(action["local"]), Path(action["new"]), target)
            if err:
                result["merge_failed"] += 1
                failed_merges.append(f"{path} ({err})")
                # The merge never ran, so `conflict` (which asks "did the merge leave
                # markers?") is not just unknown but inapplicable — represent the
                # failure explicitly instead of a bare `{path, action}` a JSON consumer
                # would otherwise mistake for "clean".
                action["error"] = {"code": "MERGE_FAILED", "message": err}
                continue
            result["merged"] += 1
            action["conflict"] = conflicted
            if conflicted:
                result["conflicts"] += 1
                conflicts_files.append(str(path))

    prefix = "would " if dry_run else ""
    if conflicts_files:
        print(f"⚠ {prefix}leave merge conflicts in: {', '.join(conflicts_files)}", file=sys.stderr)
    if overwritten_files:
        print(f"⚠ {prefix}overwrite local changes (not in local_overrides): "
              f"{', '.join(overwritten_files)}", file=sys.stderr)
    if collision_files:
        print(f"⚠ new in this release but already present locally — kept your version as a "
              f"local_overrides entry (the next upgrade 3-way merges it), reconcile by hand: "
              f"{', '.join(collision_files)}", file=sys.stderr)
    if blocked_paths:
        print(f"⚠ shipped by this release but occupied locally by a directory, below a file or "
              f"through a symlink — "
              f"left untouched, reconcile by hand: {', '.join(blocked_paths)}", file=sys.stderr)
    if blocked_unchanged:
        print(f"⚠ not installed — occupied locally by a directory, below a file or through a "
              f"symlink; this release did not change it, so the lock moves on and `check` "
              f"reports it: {', '.join(blocked_unchanged)}", file=sys.stderr)
    if kept_overrides:
        print(f"⚠ your file reached through a symlink — never written through it, kept your "
              f"version; apply this release's changes by hand: "
              f"{', '.join(kept_overrides)}", file=sys.stderr)
    if new_kept:
        print(f"⚠ your file reached through a symlink — {'would be ' if dry_run else ''}kept and "
              f"added to local_overrides: {', '.join(new_kept)}", file=sys.stderr)
    if blocked_removals:
        print(f"⚠ dropped upstream but modified locally — kept, delete by hand if intended: "
              f"{', '.join(blocked_removals)}", file=sys.stderr)
    if failed_merges:
        print(f"⚠ merge failed, local content kept: {', '.join(failed_merges)}", file=sys.stderr)
    if seed_kept:
        print(f"ℹ your seed file is now managed by the toolkit — kept your version and "
              f"{prefix}declare it in local_overrides (the next upgrade 3-way merges it): "
              f"{', '.join(seed_kept)}", file=sys.stderr)

    return result
