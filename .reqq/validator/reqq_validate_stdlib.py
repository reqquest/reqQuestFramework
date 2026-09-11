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
        [--local-override PATH ...]
  check [--ci] [--channel stable|next]
  upgrade [--version X.Y.Z] [--channel stable|next] [--dry-run]

Exit codes:
  0 = OK (no errors); toolkit: operation succeeded, no local drift. An available update is
      reported as a warning and does NOT fail, so the `ci-notify` level of D5 never fails CI.
      `upgrade`: clean upgrade, or already on the newest release.
  2 = Validation errors found; toolkit: local drift against toolkit.lock (or, under
      `check --ci` with update_check=ci-pr, an available update). `upgrade`: applied but
      needs a human — merge conflicts, clobbered undeclared edits, collisions, blocked
      removals.
  3 = Configuration error; toolkit: missing/corrupt .lock, failed to fetch release,
      adopted toolkit older than the schema's min_toolkit_version. `upgrade`: not adopted,
      release/asset missing, or checksum mismatch.
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
CONFIG         = Path(__file__).resolve().parent / "config.yaml"
REQQIGNORE     = ROOT / ".reqqignore"
TOOLKIT_LOCK   = ROOT / TOOLKIT_LOCK_REL

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
    if CONFIG.exists():
        try:
            parsed = _parse_simple_yaml(CONFIG.read_text(encoding="utf-8")) or {}
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
    pass

def _sha256_file(path: Path) -> str:
    """Compute SHA256 hash of a file, returning format 'sha256:hexdigest'."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"

def _toolkit_boundary_globs() -> Tuple[List[str], List[str]]:
    """Return (include, exclude) glob lists for the toolkit boundary.

    Read from `toolkit-manifest.json` at ROOT (ADR-TOOLKIT-001 D1) when present; otherwise
    fall back to the built-in list. A malformed manifest is an error, not a silent fallback —
    a wrong boundary corrupts every lock written from it.
    """
    manifest = ROOT / TOOLKIT_MANIFEST_REL
    if manifest.is_file():
        try:
            doc = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ToolkitError(f"Failed to read {TOOLKIT_MANIFEST_REL}: {e}")
        include = doc.get("boundary")
        if not isinstance(include, list) or not all(isinstance(x, str) for x in include):
            raise ToolkitError(
                f"{TOOLKIT_MANIFEST_REL}: `boundary` must be a list of glob strings")
        if not include:
            # An empty boundary hashes nothing, so every lock written from it reads as
            # "no toolkit files" — drift detection silently turns off. Same class of failure
            # as a manifest that fails to parse, so it gets the same treatment.
            raise ToolkitError(
                f"{TOOLKIT_MANIFEST_REL}: `boundary` must not be empty")
        exclude = doc.get("exclude") or []
        if not isinstance(exclude, list) or not all(isinstance(x, str) for x in exclude):
            raise ToolkitError(
                f"{TOOLKIT_MANIFEST_REL}: `exclude` must be a list of glob strings")
        return include, exclude
    return list(_FALLBACK_TOOLKIT_BOUNDARY_GLOBS), []


def _toolkit_boundary_files() -> List[Path]:
    """Expand the toolkit boundary to actual file paths under ROOT.
    Returns sorted list of existing files (excluding toolkit.lock itself).
    """
    include, exclude = _toolkit_boundary_globs()
    files: set = set()
    for glob_pat in include:
        try:
            for p in ROOT.glob(glob_pat):
                if p.is_file() and p != TOOLKIT_LOCK:
                    files.add(p)
        except (OSError, ValueError) as e:
            # A silently dropped pattern yields an incomplete lock, which later reads as
            # "files removed" — surface it instead of hiding it.
            raise ToolkitError(f"Failed to expand toolkit boundary pattern {glob_pat!r}: {e}")
    if exclude:
        kept = set()
        for p in files:
            rel = p.relative_to(ROOT).as_posix()
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

def load_toolkit_lock() -> Optional[Dict[str, Any]]:
    """Load .reqq/toolkit.lock. Returns None if not present."""
    if not TOOLKIT_LOCK.exists():
        return None
    try:
        return json.loads(TOOLKIT_LOCK.read_text(encoding="utf-8"))
    except Exception as e:
        _die(3, f"Failed to read {TOOLKIT_LOCK.relative_to(ROOT)}: {e}")
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
    raise ToolkitError(f"Invalid GitHub URL: {source_url}")

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
        raise ToolkitError(f"GitHub API {e.code}: {e.reason}")
    except (socket.timeout, TimeoutError):
        raise ToolkitError(f"GitHub API timed out after {GITHUB_API_TIMEOUT}s")
    except urllib.error.URLError as e:
        raise ToolkitError(f"Network error: {e.reason}")
    except json.JSONDecodeError as e:
        raise ToolkitError(f"Malformed GitHub API response: {e}")

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
            raise ToolkitError("Invalid GitHub API response: expected a list of releases")
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
            f"No {TOOLKIT_TAG_PREFIX}* release found on channel '{channel}' in {owner}/{repo}")

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
        raise ToolkitError(f"Invalid SemVer tag: {tag}")

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
    """Generate toolkit.lock from current state. Saves adopted toolkit version."""
    ap = argparse.ArgumentParser(prog="reqq_validate_stdlib.py adopt")
    ap.add_argument("--version", help="Explicit toolkit version (e.g., 1.0.0). If omitted, fetches latest from source.")
    ap.add_argument("--source", default=DEFAULT_TOOLKIT_SOURCE, help="GitHub repo URL (default: reqQuestFramework)")
    ap.add_argument("--channel", choices=["stable", "next"], default="stable")
    ap.add_argument("--installed-by", default="manual", help="Who ran adopt (default: manual)")
    ap.add_argument("--local-override", nargs="*", default=[], help="Paths to mark as local overrides (relative to the working directory)")
    parsed = ap.parse_args(args)

    version = parsed.version
    if not version:
        try:
            tag = _latest_release_tag(parsed.source, parsed.channel)
            version = _normalize_version(tag)
        except ToolkitError as e:
            _die(3, f"Failed to detect latest version: {e}")
            return 3

    try:
        boundary_files = _toolkit_boundary_files()
    except ToolkitError as e:
        _die(3, str(e))
        return 3
    if not boundary_files:
        # The usual cause is a tarball unpacked without --strip-components=1, leaving the
        # toolkit one directory below ROOT. Writing `"files": {}` here would report success
        # and leave `check` with nothing to compare against, forever.
        _die(3, f"Toolkit boundary matched no files under {ROOT} — nothing to adopt. "
                f"Check that the toolkit was extracted into the repository root "
                f"(tar xzf raac-toolkit-*.tar.gz --strip-components=1).")
        return 3

    files_dict: Dict[str, str] = {}
    for fpath in boundary_files:
        rel = fpath.relative_to(ROOT).as_posix()
        files_dict[rel] = _sha256_file(fpath)

    local_overrides = []
    for raw in (parsed.local_override or []):
        rel = _relativize_to_root(raw)
        if rel not in files_dict:
            print(f"⚠ --local-override {raw!r} is not inside the toolkit boundary — ignored "
                  f"(it would be silently overwritten on upgrade)", file=sys.stderr)
            continue
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
    print(f"✓ adopted toolkit v{version} to {rel_path}")
    return 0

def cmd_check(args) -> int:
    """Check if toolkit is up to date and verify file integrity.

    Exit codes (ADR-TOOLKIT-001, "Konsekwencje"): 0 = clean, 2 = local drift, 3 = config error.
    An available update is NOT drift — it is reported as a warning and does not fail, so that
    the `ci-notify` level of D5 ("nigdy fail") can call this directly.
    """
    ap = argparse.ArgumentParser(prog="reqq_validate_stdlib.py check")
    ap.add_argument("--ci", action="store_true",
                    help="Run as the CI step: obey toolkit.update_check from config.yaml "
                         "and emit GitHub Actions ::warning:: annotations.")
    ap.add_argument("--channel", choices=["stable", "next"],
                    help="Override the channel from config.yaml / toolkit.lock.")
    parsed = ap.parse_args(args)

    tk_cfg = load_config().get("toolkit") or {}
    update_check = str(tk_cfg.get("update_check", "manual"))

    # D5 / ADR "Konsekwencje": no `toolkit:` key in config.yaml → no operation, exit 0.
    if parsed.ci and not tk_cfg:
        return 0
    if parsed.ci and update_check == "manual":
        return 0

    lock = load_toolkit_lock()
    if lock is None:
        if parsed.ci:
            # A repo that has not adopted yet is not a CI failure — D5 levels only govern
            # how loudly we report, never whether the pipeline goes red on this.
            print("::warning::toolkit not adopted — no .reqq/toolkit.lock; run `adopt`")
            return 0
        print("✗ toolkit not adopted — run `reqq_validate_stdlib.py adopt` first", file=sys.stderr)
        return 3

    current_version = lock.get("toolkit_version")
    if not current_version:
        _die(3, f"{TOOLKIT_LOCK.relative_to(ROOT)} has no 'toolkit_version' — re-run `adopt`")
    source = lock.get("source", DEFAULT_TOOLKIT_SOURCE)
    channel = parsed.channel or tk_cfg.get("update_channel") or lock.get("channel", "stable")
    if channel not in ("stable", "next"):
        print(f"⚠ unknown update channel {channel!r} — falling back to 'stable'", file=sys.stderr)
        channel = "stable"

    try:
        latest_tag = _latest_release_tag(source, channel)
        latest_version = _normalize_version(latest_tag)
    except ToolkitError as e:
        print(f"⚠ cannot check for updates: {e}", file=sys.stderr)
        latest_version = None

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

    print(f"toolkit v{current_version} (channel: {channel})")
    if latest_version:
        if _semver_lt(current_version, latest_version):
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

    has_update = bool(latest_version and _semver_lt(current_version, latest_version))
    has_drift = bool(drifted or added or removed)

    if parsed.ci:
        # D5: `ci-notify` annotates and never fails; `ci-pr` signals with 2 so the
        # scheduled workflow knows to open an upgrade PR.
        if has_update:
            print(f"::warning::toolkit update available: v{current_version} → v{latest_version}")
        if has_drift:
            print(f"::warning::toolkit drift: {len(drifted)} modified, "
                  f"{len(added)} added, {len(removed)} removed")
        return 2 if (update_check == "ci-pr" and has_update) else 0

    # Drift is the failure condition; an available update is informational.
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
            shutil.copy2(local, out)
            return False, str(e)
        merged = local_tmp.read_bytes()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(merged)
        return b"<<<<<<<" in merged, None


def _apply_upgrade_plan(plan: List[Dict[str, Any]], working_root: Path, dry_run: bool = False) -> Dict[str, Any]:
    """
    Apply an upgrade plan and report what happened.

    Counters: replaced, merged, conflicts, merge_failed, overwritten_changes, added, restored,
    collisions, removed, removal_blocked.

    With dry_run=True nothing under `working_root` is touched, but merges are still performed
    into a temporary file so that conflicts are reported — previewing conflicts is the whole
    point of a dry run.
    """
    result = {"replaced": 0, "merged": 0, "conflicts": 0, "merge_failed": 0,
              "overwritten_changes": 0, "added": 0, "restored": 0,
              "collisions": 0, "removed": 0, "removal_blocked": 0}
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
                continue
            result["merged"] += 1
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
        raise ToolkitError(f"Download failed — HTTP {e.code} {e.reason}: {url}")
    except (socket.timeout, TimeoutError):
        raise ToolkitError(f"Download timed out after {GITHUB_DOWNLOAD_TIMEOUT}s: {url}")
    except urllib.error.URLError as e:
        raise ToolkitError(f"Network error downloading {url}: {e.reason}")


def _fetch_release_by_tag(source: str, tag: str) -> Dict[str, Any]:
    """GET /repos/<owner>/<repo>/releases/tags/<tag> → the release object."""
    owner, repo = _parse_github_repo(source)
    rel = _github_api_get(f"/repos/{owner}/{repo}/releases/tags/{tag}")
    if not isinstance(rel, dict) or not rel.get("tag_name"):
        raise ToolkitError(f"No release found for tag {tag!r} in {owner}/{repo}")
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
                        f"Refusing tar member that escapes the destination: {member.name!r}")
                safe_members.append(member)
            try:
                tar.extractall(dest, members=safe_members, filter="data")
            except TypeError:  # Python < 3.12 has no `filter=`
                tar.extractall(dest, members=safe_members)
    except tarfile.TarError as e:
        raise ToolkitError(f"Corrupt toolkit tarball: {e}")


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
        raise ToolkitError(f"Release {tag} has no asset named {asset_name!r} (assets: {present})")

    expected = _parse_sha256sums(rel.get("body") or "").get(asset_name)
    if not expected:
        raise ToolkitError(
            f"Release {tag} body has no SHA256SUMS entry for {asset_name} — "
            f"refusing to upgrade from an unverifiable payload")

    blob = _http_get_bytes(asset_url)
    actual = hashlib.sha256(blob).hexdigest()
    if actual != expected:
        raise ToolkitError(
            f"Checksum mismatch for {asset_name}: expected {expected}, got {actual}")

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

def _print_upgrade_report(from_v: str, to_v: str, channel: str, source: str,
                          plan: List[Dict[str, Any]], result: Dict[str, Any],
                          dry_run: bool) -> None:
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
    print(_changelog_delta(source, channel, from_v, to_v))


def _regenerate_lock_after_upgrade(old_lock: Dict[str, Any], version: str,
                                   channel: str, source: str) -> None:
    """D6 state 6: rewrite `toolkit.lock` from the upgraded working tree.

    New `toolkit_version` / `installed_at` / recomputed hashes; `local_overrides` and
    `installed_by` carry over — the adopter's intent survives an upgrade. An override
    that no longer names a boundary file (upstream dropped it) is quietly discarded.
    """
    files_dict = {p.relative_to(ROOT).as_posix(): _sha256_file(p)
                  for p in _toolkit_boundary_files()}
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

    Exit: 0 = clean upgrade / already newest, 2 = applied but needs a human, 3 = not
    adopted / release or asset missing / checksum mismatch.
    """
    ap = argparse.ArgumentParser(prog="reqq_validate_stdlib.py upgrade")
    ap.add_argument("--version", help="Target toolkit version (default: latest on channel)")
    ap.add_argument("--channel", choices=["stable", "next"],
                    help="Override the channel from config.yaml / toolkit.lock.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute and report the plan without touching the working tree.")
    parsed = ap.parse_args(args)

    lock = load_toolkit_lock()
    if lock is None:
        print("✗ toolkit not adopted — run `reqq_validate_stdlib.py adopt` first", file=sys.stderr)
        return 3
    current_version = lock.get("toolkit_version")
    if not current_version:
        print(f"✗ {TOOLKIT_LOCK.relative_to(ROOT)} has no 'toolkit_version' — re-run `adopt`",
              file=sys.stderr)
        return 3

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
        print(f"✗ cannot determine the target release: {e}", file=sys.stderr)
        return 3

    if not _semver_lt(current_version, target_version):
        print(f"✓ already on toolkit v{current_version} "
              f"(target v{target_version} is not newer) — nothing to upgrade")
        return 0

    current_tag = f"{TOOLKIT_TAG_PREFIX}v{_normalize_version(current_version)}"
    target_tag = f"{TOOLKIT_TAG_PREFIX}v{target_version}"

    with tempfile.TemporaryDirectory() as td:
        try:
            base_root = _download_toolkit_payload(source, current_tag, Path(td) / "vA")
            new_root = _download_toolkit_payload(source, target_tag, Path(td) / "vB")
        except ToolkitError as e:
            print(f"✗ {e}", file=sys.stderr)
            return 3

        plan = _compute_upgrade_plan(lock, base_root, new_root, ROOT)
        result = _apply_upgrade_plan(plan, ROOT, dry_run=parsed.dry_run)

        if not parsed.dry_run:
            _regenerate_lock_after_upgrade(lock, target_version, channel, source)

    _print_upgrade_report(current_version, target_version, channel, source,
                          plan, result, dry_run=parsed.dry_run)

    needs_attention = bool(result["conflicts"] or result["merge_failed"]
                           or result["overwritten_changes"] or result["collisions"]
                           or result["removal_blocked"])
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
