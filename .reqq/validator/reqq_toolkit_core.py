# -*- coding: utf-8 -*-
"""
reqq_toolkit_core.py — toolkit versioning of the reqQuest Framework validator: lock, manifest and
the CLI contract of the subcommands of `reqq_validate.py` (the validator entry point, which
dispatches them to the `reqq_toolkit_*.py` modules; this docstring is where their contract lives).
The validator runs only with the libraries pinned in `requirements.txt` beside it installed.

Subcommands (toolkit versioning, per REQQF-ADR-TOOLKIT-100):
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
so a later `upgrade` 3-way-merges it instead of clobbering it. A local file that an EXISTING
`toolkit.lock` already recorded this toolkit as managing, but that the target release no
longer ships, is reported on stderr as LOCAL_ONLY, never deleted — a path that merely matches
the release's boundary glob without ever having been in a lock this toolkit wrote is not
LOCAL_ONLY at all and is not reported (reqQuestFramework#67); likewise, a release-shipped
path occupied locally by something other than a plain
file — a directory at that exact path, or a plain file blocking one of its ancestor
directories — is reported as a COLLISION and never touched: `_toolkit_boundary_files()`
silently skips through both cases, so applying them regardless would either let
`shutil.copy2()` nest the release file in the wrong place or crash `parent.mkdir()` with an
uncaught `FileExistsError`. A path reached through a symlink is a COLLISION too, unless it is
a `--keep` file: that one is KEEP, never written through. **Any COLLISION aborts before the
lock is written at all** —
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
    "from_version": "1.1.0", "to_version": "1.2.0", "channel": "stable",
    "source": "https://github.com/reqquest/reqQuestFramework", "major": false,
    "already_up_to_date": false,
    "files": [
      {"path": ".reqq/validator/reqq_validate.py", "action": "REPLACE"},
      {"path": ".reqq/schema/types/FR.schema.json", "action": "MERGE", "conflict": true},
      {"path": ".reqq/hooks/pre-commit", "action": "ADD", "restored": false}
    ],
    "summary": {"replaced": 1, "merged": 1, "conflicts": 1, "merge_failed": 0,
                "overwritten_changes": 0, "added": 1, "restored": 0,
                "collisions": 0, "removed": 0, "removal_blocked": 0, "seed_kept": 0},
    "needs_attention": true,
    "changelog_delta": "### v1.2.0\n\n...",
    "lock_written": true
  }
`files[].action` is one of the D6 states (REPLACE, MERGE, REPLACE_WITH_WARNING, ADD,
ADD_COLLISION — an adopter's file kept on a path new in the release and declared in
local_overrides, REQQF#79 — REMOVE, REMOVE_KEPT, KEEP_SEED — a former seed file kept with
the adopter's edits and declared in local_overrides, REQQF#77 — and REGENERATE for
toolkit.lock itself), or one of two states for a path upgrade never writes through:
PATH_BLOCKED — a path the release ships that a local directory or a file above it occupies,
or that runs through a symlink and differs from the release, left untouched; and KEEP — the
adopter's file reached through a symlink (in local_overrides, a former seed or on a path new
in the release), kept as it is, with the release's hash in the lock and the path in
local_overrides. Both carry `release_changed`; only when it is true do they count toward
`summary.collisions`, and a PATH_BLOCKED path then holds the lock back (`lock_written:
false`), so a re-run installs it once the path is cleared. Normal mode reports
`lock_written: false` under `--dry-run` too. The missing-base fallback below reports
the first as COLLISION and the second as KEEP, as `adopt --align --keep` does;
`conflict` is
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
    "already_up_to_date": false,
    "lock_written": true,
    "from_version": "1.1.0", "to_version": "1.4.0", "channel": "stable",
    "source": "https://github.com/reqquest/reqQuestFramework", "major": false,
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
nothing to fall back from. `already_up_to_date` is always `false` here — the fallback only
runs once the normal already-up-to-date check above has already passed, so a caller reading
this field generically across both the normal-upgrade and fallback shapes (as
`requirements-toolkit-update.yml` does) never sees it missing (reqQuestFramework#8 review).
`changelog_delta` is always `null` here (the delta needs a real
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
COLLISION path was reported. Above, `.reqq/schema/legacy.json` is LOCAL_ONLY only because an
EXISTING `toolkit.lock` (a prior v1.1.0 adoption, say) already recorded this toolkit as
managing that path — align reads any lock already on disk before computing the plan. A path
that merely matches the release boundary's glob pattern, without ever having been recorded in
a lock this toolkit wrote, is not LOCAL_ONLY at all and produces no entry — matching the
pattern by name/location alone (e.g. an adopter's own `requirements/<CUSTOM>/README.md`) does
not make it the toolkit's file (reqQuestFramework#67).

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
import fnmatch, hashlib, json, re, sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import reqq_common as C  # noqa: E402


# The toolkit boundary (REQQF-ADR-TOOLKIT-100 D1) is owned by `toolkit-manifest.json` in the
# framework root, which ships inside every release tarball. This list is the fallback for
# a tree without the manifest — a validator copied on its own, or a repo adopted before
# the manifest shipped. It MUST stay byte-for-byte equal to the manifest's `boundary`;
# `tests/test_toolkit_versioning.py` fails the build if the two drift.
TOOLKIT_MANIFEST_REL = "toolkit-manifest.json"


_FALLBACK_TOOLKIT_BOUNDARY_GLOBS = [
    "toolkit-manifest.json",
    "LICENSES/Apache-2.0.txt",
    "LICENSES/NOTICE-reqQuest-Framework.txt",
    ".reqqignore",
    ".reqq/schema/**/*",
    ".reqq/validator/*.py",
    ".reqq/validator/config.example.yaml",
    ".reqq/validator/requirements.txt",
    ".reqq/hooks/**/*",
    ".github/workflows/requirements-*.yml",
    "requirements/README.md",
    "requirements/AGENTS.md",
    "requirements/CLAUDE.md",
    "requirements/adrs/README.md",
    "requirements/00-context/glossary.md",
]


DEFAULT_TOOLKIT_SOURCE = "https://github.com/reqquest/reqQuestFramework"


# Toolkit releases are tagged `toolkit-vX.Y.Z`; docs releases use `docs-v*` (ADR D1-decision).
TOOLKIT_TAG_PREFIX = "toolkit-"


TOOLKIT_LOCK_REL = ".reqq/toolkit.lock"  # the one path that is regenerated, never merged


# REQQF-ADR-TOOLKIT-100 D4: every `toolkit-vX.Y.Z` tag ships this asset on its GitHub Release,
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


TOOLKIT_LOCK   = C.ROOT / TOOLKIT_LOCK_REL


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

    Read from `toolkit-manifest.json` at `manifest_root` (default: ROOT) per REQQF-ADR-TOOLKIT-100
    D1, when present; otherwise fall back to the built-in list. A malformed manifest is an
    error, not a silent fallback — a wrong boundary corrupts every lock written from it.

    `align` (reqQuestFramework#5) passes an extracted release payload directory here so the
    RELEASE's own manifest decides what belongs to that version, instead of the adopter's
    (which may be stale, hand-written, or absent for a pre-versioning repo).
    """
    manifest = (manifest_root if manifest_root is not None else C.ROOT) / TOOLKIT_MANIFEST_REL
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


def _toolkit_seed_globs(manifest_root: Optional[Path] = None) -> List[str]:
    """Return the manifest's `seed` globs (REQQF#77): files the release asset ships for a
    fresh install only — a starting template the adopter then owns, such as the project
    glossary. They are outside the boundary, so `adopt`/`check` never hash them, and
    `_compute_upgrade_plan` skips them, so `upgrade` never adds, replaces or removes them.

    No manifest (the fallback boundary) means no seed files. Malformed `seed` is an error
    for the same reason a malformed `boundary` is.
    """
    manifest = (manifest_root if manifest_root is not None else C.ROOT) / TOOLKIT_MANIFEST_REL
    if not manifest.is_file():
        return []
    try:
        doc = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ToolkitError(f"Failed to read {TOOLKIT_MANIFEST_REL}: {e}", code="MANIFEST_INVALID")
    if not isinstance(doc, dict):
        raise ToolkitError(f"{TOOLKIT_MANIFEST_REL}: must be a JSON object", code="MANIFEST_INVALID")
    seed = doc.get("seed") or []
    if not isinstance(seed, list) or not all(isinstance(x, str) for x in seed):
        raise ToolkitError(
            f"{TOOLKIT_MANIFEST_REL}: `seed` must be a list of glob strings",
            code="MANIFEST_INVALID")
    return seed


def _matches_any(rel: str, globs) -> bool:
    return any(rel == pat or fnmatch.fnmatch(rel, pat) for pat in globs)


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
    base = glob_root if glob_root is not None else C.ROOT
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
        return Path(raw).resolve().relative_to(C.ROOT.resolve()).as_posix()
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
        message = f"Failed to read {TOOLKIT_LOCK.relative_to(C.ROOT)}: {e}"
        if strict:
            raise ToolkitError(message, code="LOCK_CORRUPT")
        C._die(3, message)
        return None


def write_toolkit_lock(data: Dict[str, Any]) -> None:
    """Write .reqq/toolkit.lock with deterministic JSON formatting."""
    TOOLKIT_LOCK.parent.mkdir(parents=True, exist_ok=True)
    TOOLKIT_LOCK.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def _semver_key(tag: str) -> Tuple[int, int, int, int, List[Tuple[int, int, str]]]:
    """SemVer precedence key of toolkit-vX.Y.Z or vX.Y.Z[-rc.N]: a prerelease sorts below its
    release, and prereleases compare by `_prerelease_key`."""
    major, minor, patch, pre = _semver_tuple(tag)
    return (major, minor, patch, 0, _prerelease_key(pre)) if pre else (major, minor, patch, 1, [])


def _semver_lt(a: str, b: str) -> bool:
    """Check if SemVer a < b."""
    return _semver_key(a) < _semver_key(b)


def _same_content(a: Path, b: Path) -> bool:
    """True when two existing files hash identically."""
    return _sha256_file(a) == _sha256_file(b)


_SHA256SUMS_RE = re.compile(r"^([0-9a-fA-F]{64})\s+[*]?(\S.*)$")


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
