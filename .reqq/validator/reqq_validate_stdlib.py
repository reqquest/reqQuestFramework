#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reqq_validate_stdlib.py — stdlib-only reqQuest Framework front-matter validator.

Generic starter-kit validator for the BR/FR/NFR/ADR/TC/POL convention
described in docs/conventions.md. No third-party dependencies (no PyYAML,
jsonschema, or rich required) — copy this file into a new repository and it
works as-is.

Subcommands (toolkit versioning, per ADR-TOOLKIT-001):
  adopt [--version X.Y.Z] [--source URL] [--channel stable|next] [--installed-by NAME]
        [--local-override PATH ...] [--format plain|json]
        [--align [--keep PATH ...] [--payload DIR] [--dry-run]]
  check [--ci] [--channel stable|next] [--format plain|json]
  upgrade [--version X.Y.Z] [--channel stable|next] [--dry-run] [--format plain|json]
          [--base-payload DIR --target-payload DIR]

The adopter's config.yaml is resolved next to this script when the script lives inside the
repository (the normal in-repo install); otherwise (running a copy of the script from
outside the adopter repo, e.g. an extracted release payload) it falls back to
ROOT/.reqq/validator/config.yaml, so `check`/`upgrade` still honour the adopter's
toolkit.update_channel / update_check.

`upgrade --base-payload DIR --target-payload DIR --version X.Y.Z` runs offline: it merges
two already-extracted `raac-toolkit-<version>/` payloads without any network access.
Checksum verification of those payloads is the caller's responsibility.

`adopt --align [--version X.Y.Z]` (reqQuestFramework#5) is for a repo that cannot run a
normal `upgrade` yet: a hand-copied or pre-versioning toolkit copy, a hand-written
`toolkit.lock` with no `files` hashes, or a lock pinned to a release that no longer exists.
It brings the working tree in line with the target release's own boundary (its
`toolkit-manifest.json`, not the adopter's, decides what belongs to that version) before
writing the lock exactly like a normal adopt: every file the release ships is added if
absent locally and overwritten if it differs, unless its path is listed in `--keep` — a
kept file is left untouched and recorded in `local_overrides`, same as `--local-override`,
so a later `upgrade` 3-way-merges it instead of clobbering it. A local file that matches the
release's boundary patterns but that release does not ship is reported on stderr, never
deleted; likewise, a release-shipped path occupied locally by something other than a plain
file — a directory at that exact path, or a plain file blocking one of its ancestor
directories — is reported as a COLLISION and never touched: `_toolkit_boundary_files()`
silently skips through both cases, so applying them regardless would either let
`shutil.copy2()` nest the release file in the wrong place or crash `parent.mkdir()` with an
uncaught `FileExistsError`. **Any COLLISION aborts before the lock is written at all** —
any previous lock is left completely untouched, so `check` keeps reporting the real,
unresolved state instead of a falsely "clean" new version (reqQuestFramework#5 review).
`--payload DIR` points at an already-extracted `raac-toolkit-<version>/` directory for
offline use, exactly like `upgrade`'s offline mode — no network calls, checksum
verification is the caller's responsibility, and `--version` is required (there is no
release API to detect it from). `--dry-run` reports what would change (files
added/overwritten/kept/reported) without touching the working tree or writing the lock.
`--keep`/`--payload`/`--dry-run` require `--align` (`INVALID_ARGS` otherwise). Exit 2 means
at least one local-only file was reported, or the run aborted on a collision (needs a human
to reconcile either way); 0 means the align and the lock write (unless `--dry-run`) both
went through clean.

The lock records a kept path's hash from the RELEASE's copy, not the kept local content's
own hash (reqQuestFramework#5 review) — so `check`/`check --ci` correctly report that path
as drifted immediately after `align`, exactly as they would for any other file whose
content differs from what `toolkit.lock` expects. This is intentional, not a defect: it is
the same "declared but currently diverging" signal `local_overrides` already carries for a
normal `adopt --local-override`, and it is what lets `upgrade` recognise the path needs a
3-way merge (state 2) on the very next run instead of silently replacing it.

Exit codes:
  0 = OK (no errors); toolkit: operation succeeded, no local drift. An available update is
      always reported as a warning and never fails `check`, at any `update_check` level
      (reqquest/reqQuestFramework#4) — publishing a release must never turn an adopter's
      unrelated push/PR red. `upgrade`: clean upgrade, or already on the newest release.
  2 = Validation errors found; toolkit: local drift against toolkit.lock — identical
      condition with and without `--ci`. `upgrade`: applied but needs a human — merge
      conflicts, clobbered undeclared edits, collisions, blocked removals, OR the adopted
      (BASE/vA) release was genuinely missing and a full-alignment fallback ran instead of a
      3-way merge (reqQuestFramework#7) — always exit 2, never a silent success. `adopt
      --align`: a local-only file was reported (lock still written), or a COLLISION aborted
      the run before the lock was written at all — either way, needs a human.
  3 = Configuration error; toolkit: missing/corrupt .lock, failed to fetch release,
      adopted toolkit older than the schema's min_toolkit_version. `upgrade`: not adopted,
      TARGET (vB) release/asset missing or checksum-mismatched, or bad arguments — a missing
      or unverifiable BASE (vA) release does not land here, it falls back to full alignment
      (exit 2) instead (reqQuestFramework#7).

`adopt --format json` and `upgrade --format json` (default remains `plain`, unchanged
text on stdout): emit exactly one JSON document on stdout, nothing else — text/warnings
that would normally print still go to stderr. An error (exit 3) is instead
  {"error": {"code": "NOT_ADOPTED", "message": "..."}}
with a stable `code` (NOT_ADOPTED, LOCK_CORRUPT, LOCK_MISSING_VERSION, RELEASE_NOT_FOUND,
ASSET_MISSING, CHECKSUM_MISSING, CHECKSUM_MISMATCH, DOWNLOAD_FAILED, DOWNLOAD_TIMEOUT,
GITHUB_API_ERROR, GITHUB_API_NOT_FOUND, GITHUB_API_TIMEOUT, GITHUB_API_MALFORMED, NETWORK_ERROR,
INVALID_SOURCE_URL, INVALID_VERSION, MANIFEST_INVALID, BOUNDARY_GLOB_INVALID,
EMPTY_BOUNDARY, TAR_CORRUPT, TAR_UNSAFE_MEMBER, INVALID_ARGS (bad --base-payload/
--target-payload/--version combination), PAYLOAD_INVALID (--base-payload/--target-payload
does not resolve to an existing, extracted toolkit payload), or the fallback TOOLKIT_ERROR) — never
text-parse `message`. This covers every failure reachable from `adopt`/`upgrade`,
including an invalid `--version` and a corrupt `toolkit.lock` — both raise before a plan
can be computed, so they surface as this document too, not as `plain` text on stderr.

`upgrade --format json` success document:
  {
    "command": "upgrade", "dry_run": false,
    "from_version": "1.1.0", "to_version": "1.2.0", "channel": "stable", "major": false,
    "already_up_to_date": false,
    "files": [
      {"path": ".reqq/validator/reqq_validate_stdlib.py", "action": "REPLACE"},
      {"path": ".reqq/schema/types/FR.schema.json", "action": "MERGE", "conflict": true},
      {"path": ".reqq/hooks/pre-commit", "action": "ADD", "restored": false}
    ],
    "summary": {"replaced": 1, "merged": 1, "conflicts": 1, "merge_failed": 0,
                "overwritten_changes": 0, "added": 1, "restored": 0,
                "collisions": 0, "removed": 0, "removal_blocked": 0},
    "needs_attention": true,
    "changelog_delta": "### v1.2.0\n\n..."
  }
`files[].action` is one of the D6 states (REPLACE, MERGE, REPLACE_WITH_WARNING, ADD,
ADD_COLLISION, REMOVE, REMOVE_KEPT, REGENERATE for toolkit.lock itself); `conflict` is
present (true/false) only on a MERGE entry whose 3-way merge actually ran, and is known
under `--dry-run` too, since the merge still runs into a temporary file there; `restored`
is present only on ADD entries. A MERGE that could not run at all (e.g. `git` missing or
erroring) carries `error: {"code": "MERGE_FAILED", "message": "..."}` instead of
`conflict` — the two are mutually exclusive on the same entry, and this file's outcome
also counts toward `summary.merge_failed` and `needs_attention`.
`already_up_to_date: true` means nothing else in the document is meaningful (`files` is
empty, `summary` is all zero) — the adopted version was already >= the target.

**Missing-base fallback** (reqQuestFramework#7): when the adopted (BASE/vA) release or its
asset is genuinely gone, or its release body never got a SHA256SUMS entry, `upgrade` cannot
3-way-merge — there is nothing to diff against. It falls back to the same full-alignment
plan `adopt --align` uses, against the TARGET (vB) release, with the lock's existing
`local_overrides` as the `--keep` set. The document shape switches to the `align` shape
instead of the normal upgrade shape, tagged `"mode": "full_alignment_fallback"` and always
`"needs_attention": true`:
  {
    "command": "upgrade", "mode": "full_alignment_fallback", "dry_run": false,
    "lock_written": true,
    "from_version": "1.1.0", "to_version": "1.4.0", "channel": "stable",
    "fallback_reason": "RELEASE_NOT_FOUND: No release found for tag 'toolkit-v1.1.0' in ...",
    "files": [
      {"path": ".reqq/hooks/pre-commit", "action": "ADD"},
      {"path": ".reqq/schema/types/FR.schema.json", "action": "OVERWRITE"},
      {"path": "requirements/README.md", "action": "KEEP"}
    ],
    "summary": {"added": 1, "overwritten": 1, "kept": 1, "local_only": 0, "collisions": 0},
    "needs_attention": true,
    "changelog_delta": null
  }
A KEEP entry's lock baseline is the RELEASE's hash of that path, not the kept local content's
own hash — same reasoning as `adopt --align`'s KEEP (module docstring above): otherwise the
very next `upgrade` would read it as unchanged and REPLACE it before ever consulting
`local_overrides`. `lock_written: false` means a COLLISION was reported (`summary.collisions >
0`) — same protection as `adopt --align`: the target boundary is not fully realized on disk,
so the existing `toolkit.lock` is left completely untouched rather than falsely advancing to a
version that isn't fully installed; re-run `upgrade` after resolving the collision by hand.
`dry_run: true` never writes the lock either, regardless of collisions.
This never happens for the TARGET release — a missing/unverifiable vB fails the whole
command (exit 3, `RELEASE_NOT_FOUND`/`ASSET_MISSING`/etc.) before any plan is computed, since
there is no release to align *to* either. It also never happens in offline mode
(`--base-payload`/`--target-payload`) — the caller hands in a base directly, so there is
nothing to fall back from. `changelog_delta` is always `null` here (the delta needs a real
`from_version` release to start counting from). A BASE that fails checksum verification
against a release body that DOES publish SHA256SUMS (`CHECKSUM_MISMATCH`) is not "missing" —
that looks like tampering or a corrupt transfer, and still fails hard with exit 3 instead of
falling back.

`adopt --format json` success document:
  {
    "command": "adopt", "version": "1.1.0", "source": "https://github.com/...",
    "channel": "stable", "installed_by": "manual", "installed_at": "2026-09-11T16:30:00Z",
    "lock_path": ".reqq/toolkit.lock",
    "files": [".reqq/schema/...", "..."], "local_overrides": []
  }

`adopt --align --format json` adds an `"align"` block (and `"mode": "align"`) describing the
file-level align plan on top of the shape above:
  {
    "command": "adopt", "mode": "align", "version": "1.2.0", "source": "...",
    "channel": "stable", "installed_by": "manual", "installed_at": "...",
    "lock_path": ".reqq/toolkit.lock", "files": [...], "local_overrides": ["requirements/README.md"],
    "align": {
      "dry_run": false,
      "files": [
        {"path": ".reqq/hooks/pre-commit", "action": "ADD"},
        {"path": ".reqq/schema/types/FR.schema.json", "action": "OVERWRITE"},
        {"path": "requirements/README.md", "action": "KEEP"},
        {"path": ".reqq/schema/legacy.json", "action": "LOCAL_ONLY"}
      ],
      "summary": {"added": 1, "overwritten": 1, "kept": 1, "local_only": 1, "collisions": 0},
      "needs_attention": true
    }
  }
`align.files[].action` is one of ADD, OVERWRITE, KEEP, LOCAL_ONLY, COLLISION (the release
ships this path, but a directory sits at it, or a plain file blocks one of its ancestor
directories — the path is left exactly as it was) — a path identical in the release and
locally produces no entry. `needs_attention` is true when at least one LOCAL_ONLY or
COLLISION path was reported.

**A COLLISION aborts before the lock is written.** Its document has `"lock_written": false`
and, like `--dry-run`, only the top-level `command`/`mode`/`dry_run`/`version`/`source`/
`channel`/`align` keys — no `files`/`local_overrides`/`lock_path`/`installed_at`, and any
lock that already existed is left byte-for-byte untouched:
  {
    "command": "adopt", "mode": "align", "dry_run": false, "lock_written": false,
    "version": "1.2.0", "source": "...", "channel": "stable",
    "align": {
      "files": [{"path": ".reqq/schema/requirement.schema.json", "action": "COLLISION"}],
      "summary": {"added": 0, "overwritten": 0, "kept": 0, "local_only": 0, "collisions": 1},
      "needs_attention": true
    }
  }
Under `--align --dry-run` nothing is written either (regardless of collisions): the document
has `"dry_run": true` and the same reduced top-level shape — no `files`/`local_overrides`/
`lock_path`/`installed_at`, since no lock was written.
"""
import argparse, fnmatch, hashlib, io, json, os, re, shutil, socket, subprocess, sys, tarfile, tempfile
import urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --- Constants ---------------------------------------------------------------
ID_PATTERN = r"^(BR|FR|NFR|ADR|TC|POL)-[A-Z0-9]{2,10}-[0-9]{3}$"
STATUS_ENUM = {"draft", "review", "accepted", "deprecated"}
TYPE_ENUM   = {"BR", "FR", "NFR", "ADR", "TC", "POL"}

HINTS = {
    "id":         f"ID must match `{ID_PATTERN}` e.g. FR-DEMO-001, NFR-PERF-003.",
    "type":       "Allowed types: BR, FR, NFR, ADR, TC, POL.",
    "status":     "Allowed statuses: draft, review, accepted, deprecated (lowercase).",
    "owner":      "Owner is a role or person accountable for this artifact.",
    "last_updated": 'Use ISO date "YYYY-MM-DD".',
    "traces_to":  "FR/NFR should have `traces_to: [BR-*, ...]` pointing at the requirement(s) they realize.",
    "derives_from": "TC must derive from at least one FR/NFR via `derives_from`.",
}

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

REQUIRED_FIELDS = ["id", "title", "type", "status", "owner", "last_updated"]

# --- Toolkit versioning constants (ADR-TOOLKIT-001) --------------------------------
# The toolkit boundary (ADR-TOOLKIT-001 D1) is owned by `toolkit-manifest.json` in the
# framework root, which ships inside every release tarball. This list is the fallback for
# a tree without the manifest — a validator copied on its own, or a repo adopted before
# the manifest shipped. It MUST stay byte-for-byte equal to the manifest's `boundary`;
# `tests/test_toolkit_versioning.py` fails the build if the two drift.
TOOLKIT_MANIFEST_REL = "toolkit-manifest.json"
_FALLBACK_TOOLKIT_BOUNDARY_GLOBS = [
    "toolkit-manifest.json",
    ".reqqignore",
    ".reqq/schema/**/*",
    ".reqq/validator/*.py",
    ".reqq/validator/config.example.yaml",
    ".reqq/hooks/**/*",
    ".github/workflows/requirements-*.yml",
    "requirements/README.md",
    "requirements/**/README.md",
    "requirements/00-context/**/*",
]
DEFAULT_TOOLKIT_SOURCE = "https://github.com/reqquest/reqQuestFramework"
# Toolkit releases are tagged `toolkit-vX.Y.Z`; docs releases use `docs-v*` (ADR D1-decision).
TOOLKIT_TAG_PREFIX = "toolkit-"
TOOLKIT_LOCK_REL = ".reqq/toolkit.lock"  # the one path that is regenerated, never merged
# ADR-TOOLKIT-001 D4: every `toolkit-vX.Y.Z` tag ships this asset on its GitHub Release,
# with a `SHA256SUMS` block in the release body. `{version}` is the bare SemVer (no `v`).
TOOLKIT_ASSET_TEMPLATE = "raac-toolkit-{version}.tar.gz"

# `toolkit.update_check` levels (reqquest/reqQuestFramework#6): canonical names describe
# what the level now does — off | notify | pr. The original names stay accepted so an
# existing config.yaml keeps working, mapped through this table with a one-time
# deprecation warning; an unrecognised value (typo) falls back to `off` rather than
# silently escalating to a level that mutates GitHub.
_UPDATE_CHECK_ALIASES = {"manual": "off", "ci-notify": "notify", "ci-pr": "pr"}
_UPDATE_CHECK_LEVELS = ("off", "notify", "pr")


def _normalize_update_check(raw: str) -> Tuple[str, bool]:
    """Map a `toolkit.update_check` value to its canonical name.

    Returns (canonical, is_deprecated_alias). An unknown value normalizes to `off` — still
    flagged as "deprecated" so the caller warns about it the same way as a recognised alias.
    """
    if raw in _UPDATE_CHECK_LEVELS:
        return raw, False
    if raw in _UPDATE_CHECK_ALIASES:
        return _UPDATE_CHECK_ALIASES[raw], True
    return "off", True

# --- Paths -------------------------------------------------------------------
def _find_repo_root() -> Path:
    """Locate the git repository root; fall back to two levels up from this file."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        return Path(out)
    except Exception:
        return Path(__file__).resolve().parents[2]


ROOT           = _find_repo_root()
_CONFIG_NEXT_TO_SCRIPT = Path(__file__).resolve().parent / "config.yaml"
CONFIG_REL     = ".reqq/validator/config.yaml"  # ROOT-relative fallback (adopter config)
REQQIGNORE     = ROOT / ".reqqignore"
TOOLKIT_LOCK   = ROOT / TOOLKIT_LOCK_REL


def _resolve_config_path() -> Path:
    """Locate the adopter's config.yaml.

    Next to the script when the script lives inside ROOT (the normal in-repo install,
    where config.yaml sits beside reqq_validate_stdlib.py). Otherwise — running `upgrade`
    from a copy of the script that lives outside the adopter repo (reqQuestFramework#3,
    e.g. an orchestrator invoking a release payload's script against a different working
    tree) — the script's own directory ships no config.yaml, only config.example.yaml, so
    fall back to ROOT/.reqq/validator/config.yaml.
    """
    try:
        _CONFIG_NEXT_TO_SCRIPT.resolve().relative_to(ROOT.resolve())
        return _CONFIG_NEXT_TO_SCRIPT
    except (ValueError, OSError):
        return ROOT / CONFIG_REL

# --- Minimal stdlib YAML parser ----------------------------------------------
def _parse_yaml_block(lines: List[str], start: int, min_indent: int) -> Tuple[Dict[str, Any], int]:
    """
    Internal recursive helper. Parses lines[start:] as a YAML mapping whose
    keys are indented at exactly `min_indent` spaces. Returns (dict, next_i).
    """
    result: Dict[str, Any] = {}
    i = start
    while i < len(lines):
        raw = lines[i]
        content = raw.strip()
        if not content or content.startswith("#"):
            i += 1
            continue
        cur_indent = len(raw) - len(raw.lstrip())
        if cur_indent < min_indent:
            break  # dedented → return to parent caller
        if cur_indent > min_indent:
            i += 1  # already consumed as child; skip
            continue
        if ":" not in content:
            i += 1
            continue
        key, _, val = content.partition(":")
        key = key.strip()
        val = val.strip()
        if not val or val in ("|", ">"):
            # Empty value — look ahead to decide list vs nested mapping
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i].strip().startswith("#")):
                i += 1
            if i >= len(lines):
                result[key] = None
                continue
            child_indent = len(lines[i]) - len(lines[i].lstrip())
            if child_indent <= min_indent:
                result[key] = None
                continue
            if lines[i].strip().startswith("- "):
                items: List[Any] = []
                while i < len(lines):
                    inner_raw = lines[i]
                    inner_content = inner_raw.strip()
                    if not inner_content or inner_content.startswith("#"):
                        i += 1
                        continue
                    inner_indent = len(inner_raw) - len(inner_raw.lstrip())
                    if inner_indent < child_indent:
                        break
                    if inner_indent == child_indent and inner_content.startswith("- "):
                        items.append(inner_content[2:].strip().strip('"').strip("'"))
                        i += 1
                    else:
                        i += 1  # skip sub-items inside complex list entries
                result[key] = items
            else:
                sub, i = _parse_yaml_block(lines, i, child_indent)
                result[key] = sub
        elif val.startswith("[") and val.endswith("]"):
            inner = val[1:-1]
            result[key] = [v.strip().strip('"').strip("'") for v in inner.split(",") if v.strip()]
            i += 1
        else:
            v = val.strip('"').strip("'")
            if v.lower() == "true":
                result[key] = True
            elif v.lower() == "false":
                result[key] = False
            else:
                result[key] = v
            i += 1
    return result, i


def _parse_simple_yaml(text: str) -> Dict[str, Any]:
    """
    Minimal YAML parser for the simple structures used in config.yaml and
    requirement front-matter: scalar key: value, block/inline lists, nested
    mappings. Does NOT support anchors, merge keys, or multi-line scalars.
    """
    result, _ = _parse_yaml_block(text.splitlines(), 0, 0)
    return result

# --- IO helpers --------------------------------------------------------------
def _die(code: int, msg: str):
    print(f"✖ {msg}", file=sys.stderr)
    sys.exit(code)

# --- Config ------------------------------------------------------------------
def load_config() -> Dict[str, Any]:
    cfg: Dict[str, Any] = {"require_full_traceability": True, "exclude_globs": []}
    config_path = _resolve_config_path()
    if config_path.exists():
        try:
            parsed = _parse_simple_yaml(config_path.read_text(encoding="utf-8")) or {}
            for k, v in parsed.items():
                if v is not None:
                    cfg[k] = v
        except Exception as e:
            _die(3, f"Failed to read config.yaml: {e}")
    # .reqqignore (repo root): gitignore-style, one glob per line, '#' comments.
    # Portable across validator implementations — see docs/conventions.md, section 6.
    if REQQIGNORE.exists():
        try:
            for ln in REQQIGNORE.read_text(encoding="utf-8").splitlines():
                s = ln.strip()
                if s and not s.startswith("#"):
                    cfg.setdefault("exclude_globs", [])
                    cfg["exclude_globs"].append(s)
        except Exception as e:
            _die(3, f"Failed to read .reqqignore: {e}")
    return cfg

# --- FS / Git ----------------------------------------------------------------
def is_excluded(path: Path, patterns: List[str]) -> bool:
    p = path.as_posix()
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        rel = p
    return any(
        fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(rel, pat)
        for pat in (patterns or [])
    )

def staged_md_files() -> List[Path]:
    cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"]
    try:
        out = subprocess.check_output(cmd, cwd=ROOT).decode().splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        _die(3, f"git diff failed: {e}")
        return []
    return [ROOT / p for p in out if p.endswith(".md") and "requirements/" in p.replace("\\", "/")]

def all_md_files() -> List[Path]:
    return list((ROOT / "requirements").rglob("*.md"))

# --- YAML front matter -------------------------------------------------------
def load_yaml_front_matter(text: str) -> Tuple[Dict[str, Any], int]:
    m = FM_RE.search(text)
    if not m:
        return {}, 0
    fm = _parse_simple_yaml(m.group(1)) or {}
    line_offset = text[:m.end()].count("\n")
    return fm, line_offset

# --- Validation --------------------------------------------------------------
def _rec(f: Path, severity: str, kind: str, ptr: str, message: str, hint: Optional[str] = None) -> Dict[str, Any]:
    try:
        file_ref = f.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        file_ref = f.as_posix()
    return {
        "file":     file_ref,
        "severity": severity,   # error | warning
        "kind":     kind,       # schema | frontmatter | traceability | io
        "ptr":      ptr,        # JSON pointer-ish path
        "message":  message,
        "hint":     hint,
    }

def validate_doc(f: Path, require_full_traceability: bool) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        text = f.read_text(encoding="utf-8")
    except Exception as e:
        out.append(_rec(f, "error", "io", "$", f"Cannot read file: {e}"))
        return out

    fm, _ = load_yaml_front_matter(text)
    if not fm:
        out.append(_rec(f, "error", "frontmatter", "$", "Missing YAML front matter.", "Add `---` block."))
        return out

    # Required fields
    for field in REQUIRED_FIELDS:
        if field not in fm or fm[field] == "" or fm[field] is None:
            out.append(_rec(f, "error", "schema", field,
                            f"'{field}' is a required property", HINTS.get(field)))

    # ID pattern + filename consistency
    rid = fm.get("id", "")
    if rid:
        if not re.match(ID_PATTERN, str(rid)):
            out.append(_rec(f, "error", "schema", "id",
                            f"'{rid}' does not match pattern '{ID_PATTERN}'", HINTS["id"]))
        elif f.stem != str(rid):
            out.append(_rec(f, "error", "schema", "id",
                            f"ID '{rid}' does not match filename '{f.name}'",
                            "Rename the file or update the ID to match."))

    # Type enum
    rtype = fm.get("type", "")
    if rtype and str(rtype) not in TYPE_ENUM:
        out.append(_rec(f, "error", "schema", "type",
                        f"'{rtype}' is not valid. Allowed: {', '.join(sorted(TYPE_ENUM))}",
                        HINTS["type"]))

    # Status enum
    status = fm.get("status", "")
    if status and str(status) not in STATUS_ENUM:
        out.append(_rec(f, "error", "schema", "status",
                        f"'{status}' is not valid. Allowed: {', '.join(sorted(STATUS_ENUM))}",
                        HINTS["status"]))

    # Type-specific required fields (mirrors .reqq/schema/types/*.schema.json)
    if rtype in ("FR", "NFR", "POL") and not fm.get("category"):
        out.append(_rec(f, "error", "schema", "category",
                        f"'{rtype}' requires `category`.", None))
    if rtype == "ADR" and not (fm.get("decisions") or []):
        out.append(_rec(f, "error", "schema", "decisions",
                        "`ADR` requires a non-empty `decisions` list.", None))
    if rtype == "TC" and not (fm.get("derives_from") or []):
        out.append(_rec(f, "error", "schema", "derives_from",
                        "`TC` requires `derives_from`.", HINTS["derives_from"]))

    # Traceability (generic — traces_to, see docs/conventions.md section 4)
    if require_full_traceability and rtype in ("FR", "NFR") and not (fm.get("traces_to") or []):
        out.append(_rec(f, "error", "traceability", "traces_to",
                        f"`{rtype}` should have `traces_to` → BR/ADR.", HINTS["traces_to"]))

    return out

# --- Toolkit versioning (ADR-TOOLKIT-001) ------------------------------------
class ToolkitError(Exception):
    """Raised for toolkit-versioning failures (adopt/check/upgrade).

    `code` is a stable, machine-readable identifier surfaced by `--format json` error
    output; sites that don't set one fall back to `"TOOLKIT_ERROR"` when reported.
    """
    def __init__(self, message: str, code: str = "TOOLKIT_ERROR"):
        super().__init__(message)
        self.code = code

def _sha256_file(path: Path) -> str:
    """Compute SHA256 hash of a file, returning format 'sha256:hexdigest'."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"

def _toolkit_boundary_globs(manifest_root: Optional[Path] = None) -> Tuple[List[str], List[str]]:
    """Return (include, exclude) glob lists for the toolkit boundary.

    Read from `toolkit-manifest.json` at `manifest_root` (default: ROOT) per ADR-TOOLKIT-001
    D1, when present; otherwise fall back to the built-in list. A malformed manifest is an
    error, not a silent fallback — a wrong boundary corrupts every lock written from it.

    `align` (reqQuestFramework#5) passes an extracted release payload directory here so the
    RELEASE's own manifest decides what belongs to that version, instead of the adopter's
    (which may be stale, hand-written, or absent for a pre-versioning repo).
    """
    manifest = (manifest_root if manifest_root is not None else ROOT) / TOOLKIT_MANIFEST_REL
    if manifest.is_file():
        try:
            doc = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ToolkitError(f"Failed to read {TOOLKIT_MANIFEST_REL}: {e}", code="MANIFEST_INVALID")
        include = doc.get("boundary")
        if not isinstance(include, list) or not all(isinstance(x, str) for x in include):
            raise ToolkitError(
                f"{TOOLKIT_MANIFEST_REL}: `boundary` must be a list of glob strings",
                code="MANIFEST_INVALID")
        if not include:
            # An empty boundary hashes nothing, so every lock written from it reads as
            # "no toolkit files" — drift detection silently turns off. Same class of failure
            # as a manifest that fails to parse, so it gets the same treatment.
            raise ToolkitError(
                f"{TOOLKIT_MANIFEST_REL}: `boundary` must not be empty", code="MANIFEST_INVALID")
        exclude = doc.get("exclude") or []
        if not isinstance(exclude, list) or not all(isinstance(x, str) for x in exclude):
            raise ToolkitError(
                f"{TOOLKIT_MANIFEST_REL}: `exclude` must be a list of glob strings",
                code="MANIFEST_INVALID")
        return include, exclude
    return list(_FALLBACK_TOOLKIT_BOUNDARY_GLOBS), []


def _toolkit_boundary_files(glob_root: Optional[Path] = None,
                             manifest_root: Optional[Path] = None,
                             globs: Optional[Tuple[List[str], List[str]]] = None) -> List[Path]:
    """Expand the toolkit boundary to actual file paths under `glob_root` (default: ROOT).

    `manifest_root` (default: `glob_root`) says which `toolkit-manifest.json` decides the
    boundary patterns; `align` passes a release payload directory for one, the other, or
    both, so a release's own manifest can be expanded against ROOT (what does the adopter
    already have) as well as against the payload itself (what does the release ship).

    `globs`, when given, is used verbatim instead of re-deriving (include, exclude) from
    `manifest_root` — for a caller that already read the manifest once and needs to reuse
    those patterns after the directory it lived in (e.g. a downloaded release payload) is
    gone.

    Returns sorted list of existing files (excluding toolkit.lock itself when glob_root is
    ROOT — a payload never contains it, so the check is a no-op there).
    """
    base = glob_root if glob_root is not None else ROOT
    include, exclude = globs if globs is not None else \
        _toolkit_boundary_globs(manifest_root if manifest_root is not None else base)
    files: set = set()
    for glob_pat in include:
        try:
            for p in base.glob(glob_pat):
                if p.is_file() and p != TOOLKIT_LOCK:
                    files.add(p)
        except (OSError, ValueError) as e:
            # A silently dropped pattern yields an incomplete lock, which later reads as
            # "files removed" — surface it instead of hiding it.
            raise ToolkitError(f"Failed to expand toolkit boundary pattern {glob_pat!r}: {e}",
                                code="BOUNDARY_GLOB_INVALID")
    if exclude:
        kept = set()
        for p in files:
            rel = p.relative_to(base).as_posix()
            if any(rel == pat or fnmatch.fnmatch(rel, pat) for pat in exclude):
                continue
            kept.add(p)
        files = kept
    return sorted(files)

def _relativize_to_root(raw: str) -> str:
    """Normalise a user-supplied path to a ROOT-relative POSIX string.

    Relative paths resolve against the working directory, so `--local-override README.md`
    from `requirements/` means the same file as `--local-override requirements/README.md`
    from the repo root. Anything that lands outside ROOT is returned as given, so the caller
    can reject it by name.
    """
    try:
        return Path(raw).resolve().relative_to(ROOT.resolve()).as_posix()
    except (ValueError, OSError):
        return Path(raw).as_posix()

def load_toolkit_lock(strict: bool = False) -> Optional[Dict[str, Any]]:
    """Load .reqq/toolkit.lock. Returns None if not present.

    `strict=True` raises `ToolkitError(code="LOCK_CORRUPT")` on a malformed lock instead of
    calling `_die` — for callers (`upgrade`) that must route the failure through
    `--format json` rather than exiting the process directly.
    """
    if not TOOLKIT_LOCK.exists():
        return None
    try:
        return json.loads(TOOLKIT_LOCK.read_text(encoding="utf-8"))
    except Exception as e:
        message = f"Failed to read {TOOLKIT_LOCK.relative_to(ROOT)}: {e}"
        if strict:
            raise ToolkitError(message, code="LOCK_CORRUPT")
        _die(3, message)
        return None

def write_toolkit_lock(data: Dict[str, Any]) -> None:
    """Write .reqq/toolkit.lock with deterministic JSON formatting."""
    TOOLKIT_LOCK.parent.mkdir(parents=True, exist_ok=True)
    TOOLKIT_LOCK.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def _parse_github_repo(source_url: str) -> Tuple[str, str]:
    """Parse https://github.com/<owner>/<repo> into (owner, repo)."""
    url = source_url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.split("/")
    if len(parts) >= 2 and parts[-1] and parts[-2]:
        return parts[-2], parts[-1]
    raise ToolkitError(f"Invalid GitHub URL: {source_url}", code="INVALID_SOURCE_URL")

GITHUB_API_TIMEOUT = 10  # seconds; `ci-notify` runs on every push — never hang a runner
GITHUB_DOWNLOAD_TIMEOUT = 30  # asset payloads only carry the toolkit boundary (a few KB), but
                              # allow for a slow redirect to the CDN
GITHUB_RELEASES_PER_PAGE = 100   # API maximum
GITHUB_RELEASES_MAX_PAGES = 5    # 500 releases is plenty; keeps the CI step bounded

def _github_api_get(endpoint: str) -> Any:
    """Fetch JSON from GitHub API. Supports optional GITHUB_TOKEN from env.

    Returns whatever the endpoint yields — a dict for /releases/latest, a list for /releases.
    """
    url = f"https://api.github.com{endpoint}"
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=GITHUB_API_TIMEOUT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Distinct from the catch-all below (reqQuestFramework#7): a 404 is the one HTTP
            # status that unambiguously means "this resource does not exist", as opposed to
            # auth/rate-limit/server trouble (401/403/5xx) that also lands here as
            # GITHUB_API_ERROR. `_fetch_release_by_tag` relies on this to tell "the release
            # was genuinely deleted" apart from "GitHub is unreachable right now" — only the
            # former is safe to treat as a missing merge base and fall back from.
            raise ToolkitError(f"GitHub API 404: {e.reason} ({endpoint})", code="GITHUB_API_NOT_FOUND")
        raise ToolkitError(f"GitHub API {e.code}: {e.reason}", code="GITHUB_API_ERROR")
    except (socket.timeout, TimeoutError):
        raise ToolkitError(f"GitHub API timed out after {GITHUB_API_TIMEOUT}s", code="GITHUB_API_TIMEOUT")
    except urllib.error.URLError as e:
        raise ToolkitError(f"Network error: {e.reason}", code="NETWORK_ERROR")
    except json.JSONDecodeError as e:
        raise ToolkitError(f"Malformed GitHub API response: {e}", code="GITHUB_API_MALFORMED")

def _iter_releases(owner: str, repo: str):
    """Yield releases newest-first across pages.

    /releases is paginated at 30 by default. With two tag prefixes in play
    (ADR-TOOLKIT-001 D1-decision) a run of `docs-v*` releases can push every `toolkit-v*`
    tag off the first page, which would read as "no toolkit release exists". Walks up to
    GITHUB_RELEASES_MAX_PAGES so `ci-notify` stays bounded — it runs on every push.
    """
    for page in range(1, GITHUB_RELEASES_MAX_PAGES + 1):
        batch = _github_api_get(
            f"/repos/{owner}/{repo}/releases"
            f"?per_page={GITHUB_RELEASES_PER_PAGE}&page={page}")
        if not isinstance(batch, list):
            raise ToolkitError("Invalid GitHub API response: expected a list of releases",
                                code="GITHUB_API_MALFORMED")
        for rel in batch:
            yield rel
        if len(batch) < GITHUB_RELEASES_PER_PAGE:
            return

def _latest_release_tag(source: str, channel: str) -> str:
    """Get the newest toolkit release tag on `channel`.

    Deliberately does NOT use /releases/latest: that endpoint ignores tag prefixes, so a
    `docs-v*` release (ADR-TOOLKIT-001 D1-decision) would be returned as the toolkit version.
    Both channels list /releases and keep only `toolkit-v*` tags.

    channel='stable' → newest non-prerelease; channel='next' → newest of any kind.
    """
    owner, repo = _parse_github_repo(source)

    candidates: List[str] = []
    for rel in _iter_releases(owner, repo):
        tag = (rel or {}).get("tag_name")
        if not tag or not tag.startswith(TOOLKIT_TAG_PREFIX):
            continue
        if channel == "stable" and rel.get("prerelease"):
            continue
        try:
            _semver_tuple(tag)  # skip tags that are not parseable SemVer
        except ToolkitError:
            continue
        candidates.append(tag)

    if not candidates:
        raise ToolkitError(
            f"No {TOOLKIT_TAG_PREFIX}* release found on channel '{channel}' in {owner}/{repo}",
            code="RELEASE_NOT_FOUND")

    newest = candidates[0]
    for tag in candidates[1:]:
        if _semver_lt(newest, tag):
            newest = tag
    return newest

def _normalize_version(tag: str) -> str:
    """Strip the `toolkit-` tag prefix and a leading `v` → bare SemVer string.

    Only a leading `v` is removed (not `str.lstrip("vV")`, which would also eat characters
    from a version that legitimately starts with them).
    """
    v = tag[len(TOOLKIT_TAG_PREFIX):] if tag.startswith(TOOLKIT_TAG_PREFIX) else tag
    if v[:1] in ("v", "V"):
        v = v[1:]
    return v

def _prerelease_key(pre: str) -> List[Tuple[int, int, str]]:
    """SemVer 2.0.0 §11.4 precedence key for a prerelease string.

    Dot-separated identifiers; numeric ones compare numerically and rank below alphanumeric
    ones. Plain string comparison gets `rc.10` < `rc.2` wrong.
    """
    key: List[Tuple[int, int, str]] = []
    for ident in pre.split("."):
        if ident.isdigit():
            key.append((0, int(ident), ""))
        else:
            key.append((1, 0, ident))
    return key

def _semver_tuple(tag: str) -> Tuple[int, int, int, Optional[str]]:
    """Parse toolkit-vX.Y.Z or vX.Y.Z[-rc.N] → (major, minor, patch, prerelease|None)."""
    normalized = _normalize_version(tag)
    parts = normalized.split("-", 1)
    version = parts[0]
    prerelease = parts[1] if len(parts) > 1 else None
    try:
        major, minor, patch = map(int, version.split(".", 2))
        return (major, minor, patch, prerelease)
    except (ValueError, IndexError):
        raise ToolkitError(f"Invalid SemVer tag: {tag}", code="INVALID_VERSION")

def _semver_lt(a: str, b: str) -> bool:
    """Check if SemVer a < b."""
    a_tuple = _semver_tuple(a)
    b_tuple = _semver_tuple(b)
    # Compare (major, minor, patch) first; if equal, prerelease wins (pre < release)
    a_version = a_tuple[:3]
    b_version = b_tuple[:3]
    if a_version != b_version:
        return a_version < b_version
    # Same release version; has prerelease loses (1.0.0-rc < 1.0.0)
    a_pre = a_tuple[3]
    b_pre = b_tuple[3]
    if a_pre is None and b_pre is None:
        return False
    if a_pre is None:
        return False  # a is release, b is pre; a >= b
    if b_pre is None:
        return True  # a is pre, b is release; a < b
    return _prerelease_key(a_pre) < _prerelease_key(b_pre)

def cmd_adopt(args) -> int:
    """Generate toolkit.lock from current state. Saves adopted toolkit version.

    `--align` (reqQuestFramework#5) brings a pre-versioning or unanchored repo in line with
    the target release first: every file the release boundary covers is added if absent and
    overwritten if it differs, except `--keep` paths (kept as-is and recorded as
    local_overrides, same as `--local-override`); a local file the release boundary matches
    but does not ship is reported, never deleted. The lock is then written exactly like a
    normal adopt of that version.
    """
    ap = argparse.ArgumentParser(prog="reqq_validate_stdlib.py adopt")
    ap.add_argument("--version", help="Explicit toolkit version (e.g., 1.0.0). If omitted, fetches latest from source.")
    ap.add_argument("--source", default=DEFAULT_TOOLKIT_SOURCE, help="GitHub repo URL (default: reqQuestFramework)")
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
            return _emit_toolkit_error("json", code, message)
        _die(3, message)
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
            tag = _latest_release_tag(parsed.source, parsed.channel)
            version = _normalize_version(tag)
        except ToolkitError as e:
            return _fail(e.code, f"Failed to detect latest version: {e}")

    keep_set: set = set()
    # Hashes of the RELEASE's copy of each kept path, captured while the payload still
    # exists (a downloaded payload lives in a TemporaryDirectory cleaned up before the lock
    # is written). Recorded in the lock instead of the kept local content's own hash — see
    # `_compute_align_plan`'s KEEP docstring for why using the local hash would let the very
    # next upgrade silently clobber the customization (reqQuestFramework#5 review).
    keep_release_hashes: Dict[str, str] = {}
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
                    payload_root = _validate_offline_payload_dir(parsed.payload, "--payload")
                else:
                    tag = f"{TOOLKIT_TAG_PREFIX}v{version}"
                    payload_root = _download_toolkit_payload(parsed.source, tag, Path(td) / "release")
            except ToolkitError as e:
                return _fail(e.code, str(e))

            try:
                align_boundary_globs = _toolkit_boundary_globs(payload_root)
                release_files = {p.relative_to(payload_root).as_posix()
                                  for p in _toolkit_boundary_files(payload_root, globs=align_boundary_globs)}
            except ToolkitError as e:
                return _fail(e.code, str(e))
            if not release_files:
                return _fail("EMPTY_BOUNDARY",
                             f"Release v{version}'s boundary matched no files — nothing to align to.")

            for raw in (parsed.keep or []):
                rel = _relativize_to_root(raw)
                if rel not in release_files:
                    print(f"⚠ --keep {raw!r} is not part of the v{version} release boundary "
                          f"— ignored", file=sys.stderr)
                    continue
                keep_set.add(rel)

            align_plan = _compute_align_plan(payload_root, ROOT, keep_set, globs=align_boundary_globs)
            align_result = _apply_align_plan(align_plan, ROOT, dry_run=parsed.dry_run)
            keep_release_hashes = {a["path"]: _sha256_file(Path(a["new"]))
                                    for a in align_plan if a["action"] == "KEEP"}

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
                        "files": _align_plan_to_json(align_plan),
                        "summary": align_result,
                        "needs_attention": needs_attention,
                    },
                }, indent=2))
            else:
                _print_align_report(version, align_plan, align_result, dry_run=True)
            return 2 if needs_attention else 0

        if parsed.format != "json":
            _print_align_report(version, align_plan, align_result, dry_run=False)

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
                        "files": _align_plan_to_json(align_plan),
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
        boundary_files = _toolkit_boundary_files(globs=align_boundary_globs) if parsed.align \
            else _toolkit_boundary_files()
    except ToolkitError as e:
        return _fail(e.code, str(e))
    if not boundary_files:
        # The usual cause is a tarball unpacked without --strip-components=1, leaving the
        # toolkit one directory below ROOT. Writing `"files": {}` here would report success
        # and leave `check` with nothing to compare against, forever.
        return _fail("EMPTY_BOUNDARY",
                     f"Toolkit boundary matched no files under {ROOT} — nothing to adopt. "
                     f"Check that the toolkit was extracted into the repository root "
                     f"(tar xzf raac-toolkit-*.tar.gz --strip-components=1).")

    files_dict: Dict[str, str] = {}
    for fpath in boundary_files:
        rel = fpath.relative_to(ROOT).as_posix()
        files_dict[rel] = keep_release_hashes.get(rel, _sha256_file(fpath))

    local_overrides = []
    for raw in (parsed.local_override or []):
        rel = _relativize_to_root(raw)
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

    write_toolkit_lock(lock_data)
    rel_path = TOOLKIT_LOCK.relative_to(ROOT)
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
                "files": _align_plan_to_json(align_plan),
                "summary": align_result,
                # Collisions never reach here — a collision returns above, before the lock
                # is written at all.
                "needs_attention": bool(align_result["local_only"]),
            }
        print(json.dumps(doc, indent=2))
    else:
        print(f"✓ adopted toolkit v{version} to {rel_path}")
    return 2 if (parsed.align and align_result["local_only"]) else 0

def cmd_check(args) -> int:
    """Check if toolkit is up to date and verify file integrity.

    Exit codes (ADR-TOOLKIT-001, "Konsekwencje"): 0 = clean, 2 = local drift, 3 = config error.
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
    shape (codes: NOT_ADOPTED, LOCK_MISSING_VERSION).
    """
    ap = argparse.ArgumentParser(prog="reqq_validate_stdlib.py check")
    ap.add_argument("--ci", action="store_true",
                    help="Run as the CI step: obey toolkit.update_check from config.yaml "
                         "and emit GitHub Actions ::warning:: annotations.")
    ap.add_argument("--channel", choices=["stable", "next"],
                    help="Override the channel from config.yaml / toolkit.lock.")
    ap.add_argument("--format", choices=["plain", "json"], default="plain",
                    help="Output format (default: plain).")
    parsed = ap.parse_args(args)
    as_json = parsed.format == "json"

    tk_cfg = load_config().get("toolkit") or {}
    update_check, deprecated_level = _normalize_update_check(str(tk_cfg.get("update_check", "off")))
    host = str(tk_cfg.get("host", "github"))

    if deprecated_level:
        raw = tk_cfg.get("update_check", "off")
        msg = (f"toolkit.update_check: {raw!r} is deprecated, use {update_check!r} "
               f"(reqquest/reqQuestFramework#6)")
        if not as_json and parsed.ci:
            print(f"::warning::{msg}")
        else:
            print(f"⚠ {msg}", file=sys.stderr)

    # D5 / ADR "Konsekwencje": no `toolkit:` key in config.yaml → no operation, exit 0.
    if not as_json:
        if parsed.ci and not tk_cfg:
            return 0
        if parsed.ci and update_check == "off":
            return 0

    lock = load_toolkit_lock()
    if lock is None:
        if as_json:
            return _emit_toolkit_error("json", "NOT_ADOPTED",
                                        "toolkit not adopted — no .reqq/toolkit.lock; run `adopt`")
        if parsed.ci:
            # A repo that has not adopted yet is not a CI failure — D5 levels only govern
            # how loudly we report, never whether the pipeline goes red on this.
            print("::warning::toolkit not adopted — no .reqq/toolkit.lock; run `adopt`")
            return 0
        print("✗ toolkit not adopted — run `reqq_validate_stdlib.py adopt` first", file=sys.stderr)
        return 3

    current_version = lock.get("toolkit_version")
    if not current_version:
        if as_json:
            return _emit_toolkit_error(
                "json", "LOCK_MISSING_VERSION",
                f"{TOOLKIT_LOCK.relative_to(ROOT)} has no 'toolkit_version' — re-run `adopt`")
        _die(3, f"{TOOLKIT_LOCK.relative_to(ROOT)} has no 'toolkit_version' — re-run `adopt`")
    source = lock.get("source", DEFAULT_TOOLKIT_SOURCE)
    channel = parsed.channel or tk_cfg.get("update_channel") or lock.get("channel", "stable")
    if channel not in ("stable", "next"):
        print(f"⚠ unknown update channel {channel!r} — falling back to 'stable'", file=sys.stderr)
        channel = "stable"

    lookup_failed = False
    try:
        latest_tag = _latest_release_tag(source, channel)
        latest_version = _normalize_version(latest_tag)
    except ToolkitError as e:
        print(f"⚠ cannot check for updates: {e}", file=sys.stderr)
        latest_version = None
        lookup_failed = True

    # Check local drift
    current_files = _toolkit_boundary_files()
    lock_files = {Path(p): h for p, h in lock.get("files", {}).items()}
    current_set = {f.relative_to(ROOT) for f in current_files}
    lock_set = set(lock_files.keys())

    drifted = []
    for fpath in current_files:
        rel = fpath.relative_to(ROOT)
        expected_hash = lock_files.get(rel)
        if expected_hash and _sha256_file(fpath) != expected_hash:
            drifted.append(rel.as_posix())

    added = current_set - lock_set
    removed = lock_set - current_set

    # `None` (as opposed to `False`) means the release lookup itself failed — "no update
    # found" and "couldn't determine" must stay distinguishable in --format json: a workflow
    # that treats a transient lookup failure as "no update" would wrongly close a still-open
    # tracking issue (reqquest/reqQuestFramework#6 review).
    has_update = None if lookup_failed else bool(latest_version and _semver_lt(current_version, latest_version))
    has_drift = bool(drifted or added or removed)

    if as_json:
        changelog_delta = _changelog_delta(source, channel, current_version, latest_version) if has_update else None
        upgrade_command = (f"python3 .reqq/validator/reqq_validate_stdlib.py upgrade "
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

def _same_content(a: Path, b: Path) -> bool:
    """True when two existing files hash identically."""
    return _sha256_file(a) == _sha256_file(b)

def _is_unchanged(work_file: Path, base_file: Path, expected_hash: Optional[str]) -> bool:
    """Is the working copy still the pristine vA file?

    Prefers the hash recorded in toolkit.lock. When the lock has no entry (boundary widened
    since adopt, or a hand-edited lock) it falls back to comparing against the vA payload,
    rather than assuming the file was modified.
    """
    if expected_hash:
        return _sha256_file(work_file) == expected_hash
    if base_file.exists():
        return _same_content(work_file, base_file)
    return False

def _compute_upgrade_plan(lock: Dict[str, Any], base_dir: Path, new_dir: Path, working_root: Path) -> List[Dict[str, Any]]:
    """
    Compute upgrade plan per ADR-TOOLKIT-001 D6 (states 1–6 per file).

    Returns list of FileAction dicts: {path, action, base, local, new}
    - REPLACE: unchanged locally → replace with the new version
    - MERGE: changed locally AND in local_overrides → 3-way merge
    - REPLACE_WITH_WARNING: changed locally but NOT in overrides → replace and warn
    - ADD: present in vB, absent locally → add (`restored` marks a file the adopter deleted)
    - ADD_COLLISION: new in vB but the adopter already has that path → keep local, warn
    - REMOVE: dropped in vB and untouched locally → delete
    - REMOVE_KEPT: dropped in vB but modified locally → keep, warn
    - REGENERATE: toolkit.lock (handled separately)
    """
    plan: List[Dict[str, Any]] = []
    lock_files = {Path(p): h for p, h in lock.get("files", {}).items()}
    local_overrides = set(Path(p) for p in lock.get("local_overrides", []))

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
        if rel_path.as_posix() == TOOLKIT_LOCK_REL:
            plan.append({"path": str(rel_path), "action": "REGENERATE"})
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
            if _same_content(work_file, new_file):
                continue  # identical; nothing to reconcile
            # `local_overrides` could not have covered a path that did not exist in vA, so the
            # "you were warned" logic of state 3 does not apply — never clobber. Report instead.
            plan.append({"path": str(rel_path), "action": "ADD_COLLISION", "new": str(new_file)})
            continue

        # --- States 1–3: file present in vA, vB and locally
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
            subprocess.run(
                ["git", "merge-file", "--diff3",
                 "-L", "local", "-L", "vA", "-L", "vB",
                 str(local_tmp), str(base_tmp), str(new_tmp)],
                check=False,          # non-zero simply means "conflicts", not failure
                capture_output=True,  # keep git's diagnostics off the user's stderr
            )
        except (OSError, subprocess.SubprocessError) as e:
            # In the non-dry-run case `out` IS `local` (the caller merges in place), so the
            # content is already "unchanged" and copying onto itself raises SameFileError.
            # Dry-run passes a distinct temp path here, which does need the copy.
            if out.resolve() != local.resolve():
                shutil.copy2(local, out)
            return False, str(e)
        merged = local_tmp.read_bytes()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(merged)
        return b"<<<<<<<" in merged, None


def _empty_upgrade_result() -> Dict[str, int]:
    """Zero-valued upgrade counters — shared by `_apply_upgrade_plan` and the
    already-up-to-date `--format json` payload (which never runs a plan)."""
    return {"replaced": 0, "merged": 0, "conflicts": 0, "merge_failed": 0,
            "overwritten_changes": 0, "added": 0, "restored": 0,
            "collisions": 0, "removed": 0, "removal_blocked": 0}


def _apply_upgrade_plan(plan: List[Dict[str, Any]], working_root: Path, dry_run: bool = False) -> Dict[str, Any]:
    """
    Apply an upgrade plan and report what happened.

    Counters: replaced, merged, conflicts, merge_failed, overwritten_changes, added, restored,
    collisions, removed, removal_blocked.

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
    blocked_removals: List[str] = []
    failed_merges: List[str] = []

    for action in plan:
        path = Path(action["path"])
        work_file = working_root / path
        kind = action["action"]

        if kind == "REGENERATE":
            continue  # handled by the caller once the payload is in place

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
        print(f"⚠ new in this release but already present locally — kept your version, "
              f"reconcile by hand: {', '.join(collision_files)}", file=sys.stderr)
    if blocked_removals:
        print(f"⚠ dropped upstream but modified locally — kept, delete by hand if intended: "
              f"{', '.join(blocked_removals)}", file=sys.stderr)
    if failed_merges:
        print(f"⚠ merge failed, local content kept: {', '.join(failed_merges)}", file=sys.stderr)

    return result


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


def _compute_align_plan(payload_root: Path, working_root: Path, keep: set,
                         globs: Optional[Tuple[List[str], List[str]]] = None) -> List[Dict[str, Any]]:
    """Compute an `adopt --align` plan (reqQuestFramework#5).

    Unlike `_compute_upgrade_plan` there is no vA — a pre-versioning or unanchored repo has
    no captured "before" state to diff against, only the release payload and whatever is
    on disk now. The release payload's own `toolkit-manifest.json` decides the boundary for
    both sides (`_toolkit_boundary_files(root, payload_root)`), so a stale or absent local
    manifest never causes the wrong file set to be compared.

    Returns a list of {path, action[, new]} dicts, one per path that needs attention:
      ADD        - shipped by the release, absent locally
      OVERWRITE  - shipped by the release, differs locally, not in `keep`
      KEEP       - shipped by the release, differs locally, in `keep` — local file untouched.
                   Carries `new` (the release's copy) too: the caller records ITS hash, not
                   the kept local content's, as this path's lock baseline — otherwise the
                   very next `upgrade` would see the kept content as "unchanged since lock"
                   and REPLACE it before ever consulting local_overrides (reqQuestFramework#5
                   review).
      LOCAL_ONLY - matches the release boundary locally but the release does not ship it;
                   reported only, never deleted
      COLLISION  - shipped by the release; the local path exists but is not a plain file (a
                   directory, most commonly), OR an ancestor directory the release needs is
                   itself occupied by a plain file — `_toolkit_boundary_files()` silently
                   skips both cases, so they would otherwise be indistinguishable from
                   "absent locally" (ADD) and either make `shutil.copy2()` nest the release
                   file inside the wrong place or crash `parent.mkdir()` with an uncaught
                   `FileExistsError` when the plan is applied (reqQuestFramework#5 review).
                   Reported only, untouched.
    A path identical in both places produces no entry.
    """
    release_files = {p.relative_to(payload_root).as_posix(): p
                      for p in _toolkit_boundary_files(payload_root, payload_root, globs=globs)}
    local_files = {p.relative_to(working_root).as_posix(): p
                   for p in _toolkit_boundary_files(working_root, payload_root, globs=globs)}

    plan: List[Dict[str, Any]] = []
    for rel in sorted(set(release_files) | set(local_files)):
        release_file = release_files.get(rel)
        local_file = local_files.get(rel)

        if release_file is None:
            plan.append({"path": rel, "action": "LOCAL_ONLY"})
        elif local_file is None:
            target = working_root / rel
            if target.exists() or _blocked_by_non_directory_ancestor(target, working_root):
                plan.append({"path": rel, "action": "COLLISION"})
            else:
                plan.append({"path": rel, "action": "ADD", "new": str(release_file)})
        elif not _same_content(local_file, release_file):
            if rel in keep:
                plan.append({"path": rel, "action": "KEEP", "new": str(release_file)})
            else:
                plan.append({"path": rel, "action": "OVERWRITE", "new": str(release_file)})
    return plan


_ALIGN_ACTION_LABELS = [
    ("ADD",        "added"),
    ("OVERWRITE",  "overwritten with the release version"),
    ("KEEP",       "kept as-is (recorded as local_overrides)"),
    ("LOCAL_ONLY", "present locally but not shipped by this release — kept, not deleted"),
    ("COLLISION",  "shipped by the release but occupied locally by something other than a "
                   "plain file — left untouched, reconcile by hand"),
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
        print(f"⚠ present locally but not shipped by this release (kept, not deleted): "
              f"{', '.join(sorted(local_only_files))}", file=sys.stderr)
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
        print(f"\n⚠ {result['local_only']} file(s) present locally but not shipped by this "
              f"release — reconcile by hand")
    if result["collisions"]:
        print(f"\n⚠ {result['collisions']} path(s) shipped by this release are occupied "
              f"locally by something other than a plain file — reconcile by hand")


def _align_plan_to_json(plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{"path": a["path"], "action": a["action"]} for a in plan]


def _http_get_bytes(url: str) -> bytes:
    """GET raw bytes from an arbitrary URL — used to download a release asset.

    Separate from `_github_api_get`: asset downloads come from a different host (the
    release CDN, after a redirect) and are not JSON. `GITHUB_TOKEN` is forwarded for
    private repos.
    """
    headers = {"Accept": "application/octet-stream"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=GITHUB_DOWNLOAD_TIMEOUT) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise ToolkitError(f"Download failed — HTTP {e.code} {e.reason}: {url}", code="DOWNLOAD_FAILED")
    except (socket.timeout, TimeoutError):
        raise ToolkitError(f"Download timed out after {GITHUB_DOWNLOAD_TIMEOUT}s: {url}",
                                code="DOWNLOAD_TIMEOUT")
    except urllib.error.URLError as e:
        raise ToolkitError(f"Network error downloading {url}: {e.reason}", code="NETWORK_ERROR")


def _fetch_release_by_tag(source: str, tag: str) -> Dict[str, Any]:
    """GET /repos/<owner>/<repo>/releases/tags/<tag> → the release object.

    A 404 from the API (`GITHUB_API_NOT_FOUND`) is normalized to `RELEASE_NOT_FOUND` here,
    same as a malformed-but-200 response — both mean "no release for this tag", the case
    `cmd_upgrade`'s missing-base fallback (reqQuestFramework#7) treats as genuinely missing.
    Any other API failure (auth, rate limit, 5xx, timeout, network) propagates unchanged and
    is NOT treated as "missing".
    """
    owner, repo = _parse_github_repo(source)
    try:
        rel = _github_api_get(f"/repos/{owner}/{repo}/releases/tags/{tag}")
    except ToolkitError as e:
        if e.code == "GITHUB_API_NOT_FOUND":
            raise ToolkitError(f"No release found for tag {tag!r} in {owner}/{repo}",
                                code="RELEASE_NOT_FOUND")
        raise
    if not isinstance(rel, dict) or not rel.get("tag_name"):
        raise ToolkitError(f"No release found for tag {tag!r} in {owner}/{repo}", code="RELEASE_NOT_FOUND")
    return rel


_SHA256SUMS_RE = re.compile(r"^([0-9a-fA-F]{64})\s+[*]?(\S.*)$")

def _parse_sha256sums(text: str) -> Dict[str, str]:
    """Parse a coreutils-style `SHA256SUMS` block → {basename: lowercase hexdigest}.

    Per ADR-TOOLKIT-001 D4 / D7-decision the sums live in the GitHub Release body
    (no separate signature for now). Non-matching lines are ignored so the block may
    be wrapped in prose or a ``` fence.
    """
    sums: Dict[str, str] = {}
    for line in text.splitlines():
        m = _SHA256SUMS_RE.match(line.strip())
        if m:
            sums[os.path.basename(m.group(2).strip())] = m.group(1).lower()
    return sums


def _extract_tar_safely(blob: bytes, dest: Path) -> None:
    """Unpack a .tar.gz held in memory into `dest`, rejecting path traversal.

    No member may resolve outside `dest`; only regular files and directories are
    written — symlinks, hardlinks and devices are skipped (the toolkit boundary is
    plain files, D1).
    """
    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
            safe_members = []
            for member in tar.getmembers():
                if not (member.isfile() or member.isdir()):
                    continue
                target = (dest / member.name).resolve()
                if target != dest_resolved and dest_resolved not in target.parents:
                    raise ToolkitError(
                        f"Refusing tar member that escapes the destination: {member.name!r}",
                        code="TAR_UNSAFE_MEMBER")
                safe_members.append(member)
            try:
                tar.extractall(dest, members=safe_members, filter="data")
            except TypeError:  # Python < 3.12 has no `filter=`
                tar.extractall(dest, members=safe_members)
    except tarfile.TarError as e:
        raise ToolkitError(f"Corrupt toolkit tarball: {e}", code="TAR_CORRUPT")


def _find_payload_root(unpacked: Path) -> Path:
    """The tarball may or may not wrap its contents in a single top-level directory.

    Descend through lone sub-directories until `.reqq/` appears, so the plan sees the
    same layout as the working tree regardless of how #32 packs the asset.
    """
    cur = unpacked
    for _ in range(4):
        if (cur / ".reqq").exists():
            return cur
        if not cur.is_dir():
            break
        children = list(cur.iterdir())
        if len(children) == 1 and children[0].is_dir():
            cur = children[0]
            continue
        break
    return unpacked


def _validate_offline_payload_dir(raw: str, flag: str) -> Path:
    """Validate a `--base-payload`/`--target-payload` directory before it is trusted as a
    release payload, and return its resolved payload root.

    `_find_payload_root` does not check existence — a missing, empty, or mistyped directory
    resolves right back to itself with no error. Fed straight into `_compute_upgrade_plan`,
    that reads as "the target release removed every boundary file": every unchanged local
    file gets a REMOVE action, the adopter's tree gets emptied, and `toolkit.lock` still
    advances to the requested version with exit 0 — a silent data-loss path from a plain
    typo (reqQuestFramework#3 review). Requiring `.reqq/` under the resolved root — the same
    marker `_find_payload_root` itself searches for — catches a missing directory, an empty
    one, a path to a plain file, and a directory that just isn't a toolkit payload.
    """
    p = Path(raw)
    if not p.is_dir():
        raise ToolkitError(f"{flag} {raw!r} is not an existing directory", code="PAYLOAD_INVALID")
    root = _find_payload_root(p)
    if not (root / ".reqq").is_dir():
        raise ToolkitError(
            f"{flag} {raw!r} does not look like an extracted toolkit payload "
            f"(no .reqq/ found under {root})", code="PAYLOAD_INVALID")
    return root


def _download_toolkit_payload(source: str, tag: str, dest: Path) -> Path:
    """Download, checksum-verify and unpack the `raac-toolkit-*.tar.gz` for `tag`.

    Verification is mandatory: the SHA256 of the asset must match its entry in the
    release body's `SHA256SUMS` block. A missing or mismatched sum aborts the upgrade
    rather than merging from an unverifiable payload. Returns the payload root.
    """
    version = _normalize_version(tag)
    asset_name = TOOLKIT_ASSET_TEMPLATE.format(version=version)
    rel = _fetch_release_by_tag(source, tag)

    asset_url = None
    for asset in rel.get("assets") or []:
        if asset.get("name") == asset_name:
            asset_url = asset.get("browser_download_url")
            break
    if not asset_url:
        present = [a.get("name") for a in rel.get("assets") or []]
        raise ToolkitError(f"Release {tag} has no asset named {asset_name!r} (assets: {present})",
                            code="ASSET_MISSING")

    expected = _parse_sha256sums(rel.get("body") or "").get(asset_name)
    if not expected:
        raise ToolkitError(
            f"Release {tag} body has no SHA256SUMS entry for {asset_name} — "
            f"refusing to upgrade from an unverifiable payload", code="CHECKSUM_MISSING")

    blob = _http_get_bytes(asset_url)
    actual = hashlib.sha256(blob).hexdigest()
    if actual != expected:
        raise ToolkitError(
            f"Checksum mismatch for {asset_name}: expected {expected}, got {actual}",
            code="CHECKSUM_MISMATCH")

    _extract_tar_safely(blob, dest)
    return _find_payload_root(dest)


def _changelog_delta(source: str, channel: str, from_version: str, to_version: str) -> str:
    """Concatenate release notes for every toolkit release in the range (from, to].

    Best effort: any API problem yields a short pointer instead of failing the upgrade —
    the delta is documentation for the PR body (D6), not a gate.
    """
    try:
        owner, repo = _parse_github_repo(source)
        picked: List[Tuple[str, str]] = []
        for rel in _iter_releases(owner, repo):
            tag = (rel or {}).get("tag_name") or ""
            if not tag.startswith(TOOLKIT_TAG_PREFIX):
                continue
            if channel == "stable" and rel.get("prerelease"):
                continue
            try:
                v = _normalize_version(tag)
                _semver_tuple(v)  # skip tags that are not parseable SemVer
            except ToolkitError:
                continue
            if _semver_lt(from_version, v) and not _semver_lt(to_version, v):
                picked.append((v, (rel.get("body") or "").strip()))
        if not picked:
            return f"(no release notes found for v{from_version}..v{to_version})"
        picked.sort(key=lambda t: _semver_tuple(t[0]))
        return "\n\n".join(f"### v{v}\n\n{body or '(no notes)'}" for v, body in picked)
    except ToolkitError as e:
        return f"(changelog delta unavailable: {e})"


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
    ("ADD_COLLISION",        "State 4 — collision, local file kept"),
    ("REMOVE",               "State 5 — removed"),
    ("REMOVE_KEPT",          "State 5 — removal blocked, local file kept"),
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
    unavailable) — mutually exclusive with `conflict` on the same entry."""
    files = []
    for a in plan:
        entry = {"path": a["path"], "action": a["action"]}
        if "conflict" in a:
            entry["conflict"] = a["conflict"]
        if "restored" in a:
            entry["restored"] = a["restored"]
        if "error" in a:
            entry["error"] = a["error"]
        files.append(entry)
    return files


def _upgrade_result_to_json(from_v: str, to_v: str, channel: str, dry_run: bool,
                            plan: List[Dict[str, Any]], result: Dict[str, Any],
                            needs_attention: bool, changelog_delta: Optional[str],
                            already_up_to_date: bool = False) -> Dict[str, Any]:
    """Build the `upgrade --format json` success document (see module docstring)."""
    return {
        "command": "upgrade",
        "dry_run": dry_run,
        "from_version": from_v,
        "to_version": to_v,
        "channel": channel,
        "major": _semver_tuple(to_v)[0] != _semver_tuple(from_v)[0],
        "already_up_to_date": already_up_to_date,
        "files": _upgrade_plan_files_for_json(plan),
        "summary": result,
        "needs_attention": needs_attention,
        "changelog_delta": changelog_delta,
    }


def _emit_toolkit_error(fmt: str, code: str, message: str, exit_code: int = 3) -> int:
    """Report an `adopt`/`upgrade` failure and return its exit code (never raises/exits).

    `fmt == "json"` prints the single-document error shape to stdout; otherwise mirrors
    `_die`'s wording on stderr without the process-exit — callers that must preserve the
    legacy `sys.exit` behaviour in `plain` mode call `_die` directly instead.
    """
    if fmt == "json":
        print(json.dumps({"error": {"code": code, "message": message}}, indent=2))
    else:
        print(f"✗ {message}", file=sys.stderr)
    return exit_code


def _regenerate_lock_after_upgrade(old_lock: Dict[str, Any], version: str,
                                   channel: str, source: str,
                                   override_hashes: Optional[Dict[str, str]] = None) -> None:
    """D6 state 6: rewrite `toolkit.lock` from the upgraded working tree.

    New `toolkit_version` / `installed_at` / recomputed hashes; `local_overrides` and
    `installed_by` carry over — the adopter's intent survives an upgrade. An override
    that no longer names a boundary file (upstream dropped it) is quietly discarded.

    `override_hashes` (reqQuestFramework#7 review): hashes to record instead of hashing the
    working tree, for paths the missing-base fallback KEPT untouched. Recording the kept
    local content's OWN hash would make it read as "unchanged since lock" on the very next
    upgrade and get silently REPLACEd before `local_overrides` is ever consulted — the same
    class of bug `adopt --align`'s KEEP handling already guards against.
    """
    files_dict = {p.relative_to(ROOT).as_posix(): _sha256_file(p)
                  for p in _toolkit_boundary_files()}
    for rel, digest in (override_hashes or {}).items():
        if rel in files_dict:
            files_dict[rel] = digest
    kept_overrides = sorted(o for o in old_lock.get("local_overrides", []) if o in files_dict)
    write_toolkit_lock({
        "toolkit_version": version,
        "source": source,
        "channel": channel,
        "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "installed_by": old_lock.get("installed_by", "manual"),
        "files": files_dict,
        "local_overrides": kept_overrides,
    })


def cmd_upgrade(args) -> int:
    """Upgrade the adopted toolkit to a newer release via 3-way merge (ADR-TOOLKIT-001 D6).

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
    ap = argparse.ArgumentParser(prog="reqq_validate_stdlib.py upgrade")
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
        return _emit_toolkit_error(parsed.format, "INVALID_ARGS",
            "--base-payload and --target-payload must be given together")
    offline = bool(parsed.base_payload and parsed.target_payload)
    if offline and not parsed.version:
        return _emit_toolkit_error(parsed.format, "INVALID_ARGS",
            "--version is required with --base-payload/--target-payload "
            "(offline mode has no release API to detect it from)")

    if offline:
        try:
            offline_base_root = _validate_offline_payload_dir(parsed.base_payload, "--base-payload")
            offline_target_root = _validate_offline_payload_dir(parsed.target_payload, "--target-payload")
        except ToolkitError as e:
            return _emit_toolkit_error(parsed.format, e.code, str(e))

    try:
        lock = load_toolkit_lock(strict=True)
    except ToolkitError as e:
        return _emit_toolkit_error(parsed.format, e.code, str(e))
    if lock is None:
        return _emit_toolkit_error(parsed.format, "NOT_ADOPTED",
            "toolkit not adopted — run `reqq_validate_stdlib.py adopt` first")
    current_version = lock.get("toolkit_version")
    if not current_version:
        return _emit_toolkit_error(parsed.format, "LOCK_MISSING_VERSION",
            f"{TOOLKIT_LOCK.relative_to(ROOT)} has no 'toolkit_version' — re-run `adopt`")

    source = lock.get("source", DEFAULT_TOOLKIT_SOURCE)
    tk_cfg = load_config().get("toolkit") or {}
    channel = parsed.channel or tk_cfg.get("update_channel") or lock.get("channel", "stable")
    if channel not in ("stable", "next"):
        print(f"⚠ unknown update channel {channel!r} — falling back to 'stable'", file=sys.stderr)
        channel = "stable"

    try:
        if parsed.version:
            target_version = _normalize_version(parsed.version)
        else:
            target_version = _normalize_version(_latest_release_tag(source, channel))
    except ToolkitError as e:
        return _emit_toolkit_error(parsed.format, e.code,
                                   f"cannot determine the target release: {e}")

    try:
        already_up_to_date = not _semver_lt(current_version, target_version)
    except ToolkitError as e:
        # An explicit --version that isn't valid SemVer (or a hand-edited lock's
        # toolkit_version) reaches here — _normalize_version above does not itself
        # validate, it only strips known prefixes.
        return _emit_toolkit_error(parsed.format, e.code, str(e))

    if already_up_to_date:
        if parsed.format == "json":
            print(json.dumps(_upgrade_result_to_json(
                current_version, target_version, channel, parsed.dry_run,
                [], _empty_upgrade_result(), False, None,
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
                target_tag = f"{TOOLKIT_TAG_PREFIX}v{target_version}"
                new_root = _download_toolkit_payload(source, target_tag, Path(td) / "vB")
        except ToolkitError as e:
            return _emit_toolkit_error(parsed.format, e.code, str(e))

        base_root: Optional[Path] = None
        if offline:
            base_root = offline_base_root
        else:
            current_tag = f"{TOOLKIT_TAG_PREFIX}v{_normalize_version(current_version)}"
            try:
                base_root = _download_toolkit_payload(source, current_tag, Path(td) / "vA")
            except ToolkitError as e:
                if e.code not in _BASE_MISSING_CODES:
                    return _emit_toolkit_error(parsed.format, e.code, str(e))
                # reqQuestFramework#7: the merge base is genuinely gone — its release/tag or
                # asset was deleted, or the release body never got a SHA256SUMS entry. A
                # 3-way merge has nothing trustworthy to diff against, and guessing which
                # local files "changed since vA" without vA would risk a silently wrong
                # merge. Fall back to the same full-alignment machinery `adopt --align` uses
                # for a repo with no captured baseline at all, and say so loudly.
                fallback_reason = f"{e.code}: {e}"

        keep_release_hashes: Dict[str, str] = {}
        try:
            if fallback_reason is not None:
                keep_set = set(lock.get("local_overrides", []))
                align_globs = _toolkit_boundary_globs(new_root)
                plan = _compute_align_plan(new_root, ROOT, keep_set, globs=align_globs)
                result = _apply_align_plan(plan, ROOT, dry_run=parsed.dry_run)
                # Same fix as `adopt --align`'s KEEP handling (reqQuestFramework#5 review):
                # record the RELEASE's hash for a kept path, not the (untouched-by-definition)
                # local content's own hash — otherwise the very next upgrade reads it as
                # "unchanged since lock" and REPLACEs it before local_overrides is ever
                # consulted, silently discarding the customization one run later.
                keep_release_hashes = {a["path"]: _sha256_file(Path(a["new"]))
                                        for a in plan if a["action"] == "KEEP"}
            else:
                plan = _compute_upgrade_plan(lock, base_root, new_root, ROOT)
                result = _apply_upgrade_plan(plan, ROOT, dry_run=parsed.dry_run)
        except ToolkitError as e:
            return _emit_toolkit_error(parsed.format, e.code, str(e))

        # A collision during the fallback means the working tree cannot actually be brought in
        # line with the target release yet — same reasoning `adopt --align` already applies
        # (reqQuestFramework#5 review): writing the lock regardless would advance
        # toolkit_version to a release whose boundary is not fully realized on disk, and the
        # very next run would read the repo as already up to date, permanently hiding the
        # unresolved collision instead of letting a re-run pick it up once resolved by hand.
        lock_blocked_by_collision = fallback_reason is not None and bool(result.get("collisions"))
        lock_written = not parsed.dry_run and not lock_blocked_by_collision
        if lock_written:
            _regenerate_lock_after_upgrade(lock, target_version, channel, source,
                                           override_hashes=keep_release_hashes)

    changelog_delta = None if (offline or fallback_reason is not None) else \
        _changelog_delta(source, channel, current_version, target_version)

    if fallback_reason is not None:
        # The fallback itself is always worth a human's attention, regardless of whether the
        # alignment also hit its own local_only/collision cases.
        needs_attention = True
        if parsed.format == "json":
            print(json.dumps({
                "command": "upgrade",
                "mode": "full_alignment_fallback",
                "dry_run": parsed.dry_run,
                "lock_written": lock_written,
                "from_version": current_version,
                "to_version": target_version,
                "channel": channel,
                "fallback_reason": fallback_reason,
                "files": _align_plan_to_json(plan),
                "summary": result,
                "needs_attention": True,
                "changelog_delta": changelog_delta,
            }, indent=2))
        else:
            print(f"\n⚠ merge base v{current_version} unavailable ({fallback_reason}) — "
                  f"falling back to FULL ALIGNMENT against v{target_version} instead of a "
                  f"3-way merge; review overwritten files by hand", file=sys.stderr)
            _print_align_report(target_version, plan, result, dry_run=parsed.dry_run)
            if lock_blocked_by_collision:
                print(f"\n✗ toolkit.lock NOT written — {result['collisions']} unresolved "
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
                current_version, target_version, channel, parsed.dry_run,
                plan, result, needs_attention, changelog_delta), indent=2))
        else:
            _print_upgrade_report(current_version, target_version, channel,
                                  plan, result, dry_run=parsed.dry_run,
                                  changelog_delta=changelog_delta)

    return 2 if needs_attention else 0

def enforce_min_toolkit_version() -> None:
    """ADR-TOOLKIT-001 D7: fail with exit 3 when the adopted toolkit is older than the schema
    requires.

    The bound is an optional `min_toolkit_version` key at the root of
    `.reqq/schema/requirement.schema.json` (unknown keywords are ignored by JSON Schema
    validators, so this is inert for them). Absent key → no constraint. A repository that has
    not adopted yet gets a warning, not a failure — the bound only binds once a lock exists.
    """
    schema_path = ROOT / ".reqq" / "schema" / "requirement.schema.json"
    if not schema_path.exists():
        return
    try:
        required = json.loads(schema_path.read_text(encoding="utf-8")).get("min_toolkit_version")
    except (OSError, json.JSONDecodeError):
        return  # schema problems are already reported by the validation path
    if not required:
        return

    if not TOOLKIT_LOCK.exists():
        print(f"⚠ schema requires toolkit >= v{required} but this repo has no "
              f"{TOOLKIT_LOCK.relative_to(ROOT)} — run `adopt`", file=sys.stderr)
        return
    try:
        lock = json.loads(TOOLKIT_LOCK.read_text(encoding="utf-8"))
        current = lock.get("toolkit_version")
        if current and _semver_lt(current, required):
            _die(3, f"toolkit v{current} is older than the required v{required} "
                    f"— run `reqq_validate_stdlib.py upgrade`")
    except (OSError, json.JSONDecodeError) as e:
        _die(3, f"Failed to read {TOOLKIT_LOCK.relative_to(ROOT)}: {e}")
    except ToolkitError as e:
        _die(3, str(e))

# --- Output ------------------------------------------------------------------
def print_results(results: List[Dict[str, Any]], scanned: int, excluded: List[str]):
    print(f"reqq validate — files scanned: {scanned}, errors: {len(results)}")
    if excluded:
        print(f"excluded: {', '.join(excluded)}")

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for r in results:
        grouped.setdefault(r["file"], []).append(r)

    for file, items in grouped.items():
        print(f"\n── {file}")
        for it in items:
            sev = "✖ error" if it["severity"] == "error" else "⚠ warn"
            print(f"  {sev} [{it['kind']}] @{it['ptr']}: {it['message']}")
            if it.get("hint"):
                print(f"     ↳ hint: {it['hint']}")

    if results:
        print(f"\nSummary: {len(results)} error(s) • scanned {scanned} file(s)")
    else:
        print(f"\nValidated {scanned} file(s). ✅")

# --- Main --------------------------------------------------------------------
def main() -> int:
    # Handle toolkit subcommands first
    if len(sys.argv) > 1 and sys.argv[1] in ("adopt", "check", "upgrade"):
        subcommand = sys.argv[1]
        sub_args = sys.argv[2:]
        try:
            if subcommand == "adopt":
                return cmd_adopt(sub_args)
            elif subcommand == "check":
                return cmd_check(sub_args)
            elif subcommand == "upgrade":
                return cmd_upgrade(sub_args)
        except ToolkitError as e:
            _die(3, str(e))
        return 3

    ap = argparse.ArgumentParser(description="Validate reqQuest Framework requirement files (stdlib-only).")
    ap.add_argument("--staged-only", action="store_true",
                    help="Validate only staged files (used by pre-commit).")
    ap.add_argument("--all", action="store_true",
                    help="Validate all requirement files.")
    ap.add_argument("--format", choices=["plain", "json"], default="plain",
                    help="Output format.")
    ap.add_argument("files", nargs="*", help="Explicit Markdown file paths to validate.")
    args = ap.parse_args()

    enforce_min_toolkit_version()

    cfg = load_config()
    ex_globs: List[str] = cfg.get("exclude_globs", []) or []

    # Choose files
    if args.files:
        files: List[Path] = [Path(p) for p in args.files if p.lower().endswith(".md")]
    elif args.staged_only:
        files = staged_md_files()
    else:
        files = all_md_files()

    if getattr(args, "all", False) and not args.files:
        files = all_md_files()

    # Apply exclude_globs (config.yaml + .reqqignore)
    excluded: List[str] = []
    if ex_globs:
        keep: List[Path] = []
        for f in files:
            if is_excluded(f, ex_globs):
                try:
                    excluded.append(f.relative_to(ROOT).as_posix())
                except ValueError:
                    excluded.append(str(f))
            else:
                keep.append(f)
        files = keep

    if not files:
        print("No requirement files to validate.")
        return 0

    # Validate
    results: List[Dict[str, Any]] = []
    for f in files:
        if not f.exists():
            continue
        results.extend(validate_doc(f, cfg.get("require_full_traceability", True)))

    # Output
    if args.format == "json":
        payload = {
            "ok":       not bool(results),
            "scanned":  len(files),
            "errors":   results,
            "excluded": excluded,
        }
        print(json.dumps(payload, indent=2))
    else:
        print_results(results, scanned=len(files), excluded=excluded)

    return 0 if not results else 2


if __name__ == "__main__":
    sys.exit(main())
