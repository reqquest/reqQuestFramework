# -*- coding: utf-8 -*-
"""The `check` subcommand."""
import argparse, json, sys
from pathlib import Path

import reqq_common as C  # noqa: E402
import reqq_toolkit_core as T  # noqa: E402
import reqq_toolkit_github as GH  # noqa: E402
import reqq_toolkit_align as AL  # noqa: E402


def cmd_check(args) -> int:
    """Check if toolkit is up to date and verify file integrity.

    Exit codes (REQQF-ADR-TOOLKIT-100, "Consequences"): 0 = clean, 2 = local drift, 3 = config error.
    A file declared in `local_overrides` that differs from the lock is listed, not drift (D3);
    a missing one is drift.
    An available update is NOT drift — it is reported as a warning and never fails, at any
    `update_check` level (reqquest/reqQuestFramework#4): a fact about the repository (local
    drift) gates the pipeline, an event outside the current commit (someone else published a
    release) never does — otherwise the same commit is green today and red tomorrow. `--ci`
    and a plain run agree on this for both conditions.

    `--format json` (reqquest/reqQuestFramework#6) is a pure facts query for the
    `requirements-toolkit-update.yml` workflow to act on — it ignores `--ci` and the
    `update_check` level entirely (deciding whether/how to act on an update is the caller's
    job, not this command's); exactly one JSON document on stdout, mirroring `adopt`/
    `upgrade --format json`:
      {"command": "check", "toolkit_version": "1.1.0", "latest_version": "1.2.0",
       "channel": "stable", "host": "github", "update_check": "notify",
       "has_update": true, "has_drift": false,
       "changelog_delta": "### v1.2.0\\n\\n...", "upgrade_command": "... upgrade --version 1.2.0"}
    `changelog_delta`/`upgrade_command` are `null` when there is no confirmed update.
    `has_update` is tri-state: `true`/`false` when the release lookup succeeded, `null` when
    it failed (network error, rate limit, ...) — "no update" and "couldn't tell" must stay
    distinguishable, since a caller that treats a failed lookup as "no update" would
    incorrectly close a still-open tracking issue. `latest_version` is also `null` whenever
    `has_update` is `null`. Errors use the same `{"error": {"code": ..., "message": ...}}`
    shape (codes: NOT_ADOPTED, LOCK_CORRUPT, LOCK_MISSING_VERSION).
    """
    ap = argparse.ArgumentParser(prog="reqq_validate.py check")
    ap.add_argument("--ci", action="store_true",
                    help="Run as the CI step: obey toolkit.update_check from config.yaml "
                         "and emit GitHub Actions ::warning:: annotations.")
    ap.add_argument("--channel", choices=["stable", "next"],
                    help="Override the channel from config.yaml / toolkit.lock.")
    ap.add_argument("--format", choices=["plain", "json"], default="plain",
                    help="Output format (default: plain).")
    parsed = ap.parse_args(args)
    as_json = parsed.format == "json"

    tk_cfg = C.load_config().get("toolkit") or {}
    update_check, deprecated_level = T._normalize_update_check(str(tk_cfg.get("update_check", "off")))
    host = str(tk_cfg.get("host", "github"))

    if deprecated_level:
        raw = tk_cfg.get("update_check", "off")
        msg = (f"toolkit.update_check: {raw!r} is deprecated, use {update_check!r} "
               f"(reqquest/reqQuestFramework#6)")
        if not as_json and parsed.ci:
            print(f"::warning::{msg}")
        else:
            print(f"⚠ {msg}", file=sys.stderr)

    # D5 / ADR "Consequences": no `toolkit:` key in config.yaml → no operation, exit 0.
    if not as_json:
        if parsed.ci and not tk_cfg:
            return 0
        if parsed.ci and update_check == "off":
            return 0

    try:
        lock = T.load_toolkit_lock(strict=True)
    except T.ToolkitError as e:
        if as_json:
            return T._emit_toolkit_error("json", e.code, str(e))
        C._die(3, str(e))
    if lock is None:
        if as_json:
            return T._emit_toolkit_error("json", "NOT_ADOPTED",
                                        "toolkit not adopted — no .reqq/toolkit.lock; run `adopt`")
        if parsed.ci:
            # A repo that has not adopted yet is not a CI failure — D5 levels only govern
            # how loudly we report, never whether the pipeline goes red on this.
            print("::warning::toolkit not adopted — no .reqq/toolkit.lock; run `adopt`")
            return 0
        print("✗ toolkit not adopted — run `reqq_validate.py adopt` first", file=sys.stderr)
        return 3

    current_version = lock.get("toolkit_version")
    if not current_version:
        if as_json:
            return T._emit_toolkit_error(
                "json", "LOCK_MISSING_VERSION",
                f"{T.TOOLKIT_LOCK.relative_to(C.ROOT)} has no 'toolkit_version' — re-run `adopt`")
        C._die(3, f"{T.TOOLKIT_LOCK.relative_to(C.ROOT)} has no 'toolkit_version' — re-run `adopt`")
    source = lock.get("source", T.DEFAULT_TOOLKIT_SOURCE)
    channel = parsed.channel or tk_cfg.get("update_channel") or lock.get("channel", "stable")
    if channel not in ("stable", "next"):
        print(f"⚠ unknown update channel {channel!r} — falling back to 'stable'", file=sys.stderr)
        channel = "stable"

    lookup_failed = False
    try:
        latest_tag = GH._latest_release_tag(source, channel)
        latest_version = T._normalize_version(latest_tag)
    except T.ToolkitError as e:
        print(f"⚠ cannot check for updates: {e}", file=sys.stderr)
        latest_version = None
        lookup_failed = True

    # Check local drift
    current_files = T._toolkit_boundary_files()
    lock_files = {Path(p): h for p, h in lock.get("files", {}).items()}
    # The boundary glob does not walk into a symlinked folder: a locked file there is present.
    # Only a path inside the repository counts; another one in a hand-edited lock stays removed.
    current_files += [C.ROOT / p for p in lock_files
                      if not p.is_absolute() and ".." not in p.parts
                      and AL._through_symlink(C.ROOT / p, C.ROOT) and (C.ROOT / p).is_file()
                      and C.ROOT / p not in current_files]
    current_set = {f.relative_to(C.ROOT) for f in current_files}
    lock_set = set(lock_files.keys())

    # A declared override differs from the canon on purpose: listed, not drift (ADR D3).
    overrides = set(lock.get("local_overrides", []))
    drifted, overridden = [], []
    for fpath in current_files:
        rel = fpath.relative_to(C.ROOT)
        expected_hash = lock_files.get(rel)
        if expected_hash and T._sha256_file(fpath) != expected_hash:
            (overridden if rel.as_posix() in overrides else drifted).append(rel.as_posix())

    added = current_set - lock_set
    removed = lock_set - current_set

    # `None` (as opposed to `False`) means the release lookup itself failed — "no update
    # found" and "couldn't determine" must stay distinguishable in --format json: a workflow
    # that treats a transient lookup failure as "no update" would wrongly close a still-open
    # tracking issue (reqquest/reqQuestFramework#6 review).
    has_update = None if lookup_failed else bool(latest_version and T._semver_lt(current_version, latest_version))
    has_drift = bool(drifted or added or removed)

    if as_json:
        changelog_delta = GH._changelog_delta(source, channel, current_version, latest_version) if has_update else None
        upgrade_command = (f"python3 .reqq/validator/reqq_validate.py upgrade "
                            f"--version {latest_version}") if has_update else None
        doc = {
            "command": "check",
            "toolkit_version": current_version,
            "latest_version": latest_version,
            "channel": channel,
            "host": host,
            "update_check": update_check,
            "has_update": has_update,
            "has_drift": has_drift,
            "changelog_delta": changelog_delta,
            "upgrade_command": upgrade_command,
        }
        print(json.dumps(doc, indent=2))
        return 2 if has_drift else 0

    print(f"toolkit v{current_version} (channel: {channel})")
    if latest_version:
        if has_update:
            print(f"  ⚠ update available: v{latest_version}")
        else:
            print(f"  ✓ up to date (latest: v{latest_version})")

    if overridden:
        print(f"  declared local overrides (not drift): {len(overridden)} file(s)")
        for it in overridden:
            print(f"    - {it}")
    if drifted or added or removed:
        print("  ⚠ local drift detected:")
        for label, items in (("modified", drifted),
                             ("added", sorted(p.as_posix() for p in added)),
                             ("removed", sorted(p.as_posix() for p in removed))):
            if items:
                print(f"    {label}: {len(items)} file(s)")
                for it in items:
                    print(f"      - {it}")

    if parsed.ci:
        # D5: every level (notify, pr) only annotates an available update — never fails CI
        # on it (#4). The mechanism that acts on an update (opening an issue/PR) is a
        # separate, dedicated workflow (requirements-toolkit-update.yml), not this
        # validation-job signal.
        if has_update:
            print(f"::warning::toolkit update available: v{current_version} → v{latest_version}")
        if has_drift:
            print(f"::warning::toolkit drift: {len(drifted)} modified, "
                  f"{len(added)} added, {len(removed)} removed")
        return 2 if has_drift else 0

    # Drift is the failure condition; an available update is informational. Same rule as
    # the `--ci` branch above.
    return 2 if has_drift else 0
