# -*- coding: utf-8 -*-
"""Shared validator foundation: repository paths, config loading, file discovery, front matter, result records and the requirement ID vocabulary."""
import fnmatch, os, re, subprocess, sys, unicodedata
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Set, Tuple

import reqq_yaml as Y  # noqa: E402


# A pattern that equals one in `.reqq/schema` ends in `(?![\s\S])` as there: `$` also matches before a final newline.
# `[PREFIX-]TYPE-CATEGORY-NNN`; the repository prefix is governed by `id_prefix` (reqqf#94).
ID_PATTERN = r"^([A-Z]{2,6}-)?(BR|FR|NFR|ADR|TC|POL)-[A-Z0-9]{2,10}-[0-9]{3}(?![\s\S])"


LEGACY_ID_PATTERN = r"^(BR|FR|NFR|ADR|TC|POL)-[A-Z0-9]{2,10}-[0-9]{3}(?![\s\S])"  # `legacy_id`, no prefix


ID_PREFIX_PATTERN = r"^[A-Z]{2,6}$"  # `id_prefix` in config.yaml


# 1–4 English words in the file name `<id>-<short_title>.md`; required by `short_title: true` (reqqf#134).
SHORT_TITLE_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+){0,3}(?![\s\S])"


VERSION_PATTERN = r"^[0-9]+\.[0-9]+(?![\s\S])"  # requirement.schema.json `version`


# Relation items may pin the source version: `ID@major.minor` (reqqf#93).
REF_PATTERN = r"^([A-Z]{2,6}-)?(BR|FR|NFR|ADR|TC|POL)-[A-Z0-9]{2,10}-[0-9]{3}(@[0-9]+\.[0-9]+)?(?![\s\S])"  # traces_to


DERIVES_FROM_PATTERN = r"^([A-Z]{2,6}-)?(FR|NFR)-[A-Z0-9]{2,10}-[0-9]{3}(@[0-9]+\.[0-9]+)?(?![\s\S])"  # types/TC.schema.json


STATUS_ENUM = {"draft", "review", "approved", "deprecated"}


TYPE_ENUM   = {"BR", "FR", "NFR", "ADR", "TC", "POL"}


CONFLICT_RESOLUTIONS = {"accepted", "rejected", "superseded"}


HINTS = {
    "io":         "Check that the file is readable and saved as UTF-8 text.",
    "yaml":       "Fix the YAML syntax of the front matter; line numbers count from the line after "
                  "the opening `---`. Quote a value that contains `: `, e.g. `title: \"a: b\"`.",
    "yaml.duplicate-key": "Keep one of the repeated keys and remove the other: the loader would use "
                          "only the last value, silently.",
    "missing_file": "Check the path. A file deleted in this change needs no validation.",
    "not_markdown": "Pass requirement files only: Markdown with the `.md` extension.",
    "layout.path": "Move the file with `git mv` to the expected folder, or remove `enforce_layout` from config.yaml.",
    "layout.category": "Set `category` to the expected value.",
    "layout.nfr-code": "Use one ID code per quality folder and one folder per code; "
                       "keep a changed ID in `legacy_id`.",
    "id-type":    "Make the type segment of `id` and the field `type` the same.",
    "id":         "Use `[PREFIX-]TYPE-CATEGORY-NNN`: TYPE is BR, FR, NFR, ADR, TC or POL, "
                  "and TYPE equals the field `type`; CATEGORY is 2–10 characters A–Z or 0–9, "
                  "NNN is 3 digits; PREFIX (2–6 letters A–Z) is required when config.yaml sets "
                  "`id_prefix`, otherwise omitted. E.g. FR-BOOKING-001, REQA-NFR-PERF-003.",
    "legacy_id":  "Use `TYPE-CATEGORY-NNN`: TYPE is BR, FR, NFR, ADR, TC or POL, "
                  "CATEGORY is 2–10 characters A–Z or 0–9, NNN is 3 digits. "
                  "`legacy_id` is the last previous ID, without a prefix. E.g. FR-BOOKING-001.",
    "id-prefix":  "Rename the file and `id` to the repository prefix and keep the old ID in `legacy_id`. "
                  "Leftover toolkit examples can be removed.",
    "id-prefix.ref": "Prefix the reference: with the repository prefix for its own requirements, "
                     "with another repository's prefix for that repository's requirements.",
    "id-prefix.unset": "Set `id_prefix` in .reqq/validator/config.yaml, or drop the prefix.",
    "short_title": "Set `short_title` to 1–4 English words in lowercase letters and digits, "
                   "joined by hyphens, e.g. `traceability`.",
    "filename":   "Rename the file to `<id>.md`, or to `<id>-<short_title>.md` when config.yaml "
                  "sets `short_title: true`.",
    "title":      "Add a short `title` that names the requirement.",
    "type":       "Allowed types: BR, FR, NFR, ADR, TC, POL.",
    "status":     "Allowed statuses: draft, review, approved, deprecated (lowercase).",
    "owner":      "Owner is a role or person accountable for this artifact.",
    "last_updated": 'Use ISO date "YYYY-MM-DD".',
    "traces_to":  "FR/NFR should have `traces_to: [BR-*, ...]` pointing at the requirement(s) they realize.",
    "derives_from": "TC must derive from at least one FR/NFR via `derives_from`.",
    "category":   "FR/POL: the ID's category segment (e.g. `BOOKING`); NFR: the full quality attribute (e.g. `performance`).",
    "decisions":  'List the decisions taken: `decisions: ["..."]`, one sentence each.',
    "conflict":   "Each `conflict` entry: `with: <ID>`, optional `resolution: accepted | rejected | superseded`.",
    "conflict_gate": "Set `resolution` (accepted | rejected | superseded) or keep the status at draft/review.",
    "schema.contract": "Make the field match .reqq/schema/requirement.schema.json, as the message says. "
                       "A warning does not fail the run.",
    "openapi.yaml": "Fix the YAML of the block; its lines count from the line after the opening fence.",
    "openapi.root": "Keep only `paths` and `components` at the root of the fragment; the rest of the "
                    "OpenAPI document belongs to the shared parts of the contract.",
    "openapi.id": "Write the fence as ```yaml openapi id=<id>.<name>, with the requirement's `id` and a "
                  "name of lowercase letters, digits and hyphens, unique in the file.",
    "openapi.schema": "Fix the fragment at the path the message names, against the OpenAPI version set by "
                      "`openapi.version` in .reqq/validator/config.yaml.",
    "graph.dangling": "Fix the ID or restore the target. Files excluded by .reqqignore/exclude_globs are not targets.",
    "graph.duplicate-id": "Give each requirement its own ID; rename one of the files and its `id`.",
    "graph.status-draft": "Approve the target first, or keep this document at draft/review.",
    "graph.status-deprecated": "Point to the successor, or deprecate this document too.",
    "graph.suspect": "Review this document against the source, then pin the source's current version.",
    "graph.suspect-version": 'Pin a version the source has reached, give the source `version: "major.minor"`, '
                             "or drop the `@version`.",
}


FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


REQUIRED_FIELDS = ["id", "title", "type", "status", "owner", "last_updated"]


def _find_repo_root() -> Path:
    """Locate the git repository root; fall back to the current working directory.

    reqQuestFramework#3's offline payload mode (`upgrade --base-payload/--target-payload`)
    runs this exact script from a *copy* living inside the target release payload, against
    a separate adopter working tree passed in as `cwd` — possibly with no `.git` there
    (e.g. an orchestrator strips `.git` before handing the tree to an isolated sandbox, so
    the sandbox never receives repo credentials, remote config or hooks). `git rev-parse
    --show-toplevel` then fails as expected, and cwd — not this script's own location
    inside the payload copy — is the adopter tree TOOLKIT_LOCK etc. must resolve against.
    A wrong fallback here silently returns NOT_ADOPTED for a repo that has, in fact,
    adopted the toolkit."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        return Path(out)
    except Exception:
        return Path.cwd()


ROOT           = _find_repo_root()


_CONFIG_NEXT_TO_SCRIPT = Path(__file__).resolve().parent / "config.yaml"


CONFIG_REL     = ".reqq/validator/config.yaml"  # ROOT-relative fallback (adopter config)


REQQIGNORE     = ROOT / ".reqqignore"


def _resolve_config_path() -> Path:
    """Locate the adopter's config.yaml.

    Next to the script when the script lives inside ROOT (the normal in-repo install,
    where config.yaml sits beside reqq_validate.py). Otherwise — running `upgrade`
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


def printable(value: Any) -> str:
    """`value` as output text: every control or line-separator character (`\\n`, `\\r`,
    `\\x85`, `\\u2028`, ...) in its visible backslash form, other text unchanged.

    Text from a pull request must not start a line in CI output: a runner takes a line
    starting with `::` for a workflow command."""
    return "".join(ch.encode("unicode_escape").decode("ascii")
                   if unicodedata.category(ch) in ("Cc", "Zl", "Zp") else ch for ch in str(value))


def _command_data(text: str) -> str:
    """`text` encoded as the message of a GitHub Actions workflow command."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _command_property(value: Any) -> str:
    """`value` encoded as a property of a workflow command: a `,` or `:` cannot end it."""
    return _command_data(printable(value)).replace(":", "%3A").replace(",", "%2C")


def annotation(level: str, title: str, file: str, message: str,
               hint: Optional[str] = None, line: Optional[int] = None) -> str:
    """One GitHub Actions workflow command (`::error` or `::warning`) on `file` at `line`, when
    known, with the hint as the second line of the message. Text from a pull request passes
    through `printable` before the encoding, so it can neither end the command nor add a property."""
    props = [f"file={_command_property(file)}"]
    props += [f"line={line}"] if line is not None else []
    props.append(f"title={_command_property(title)}")
    body = printable(message) + (f"\nHint: {printable(hint)}" if hint else "")
    return f"::{level} {','.join(props)}::{_command_data(body)}"


def _die(code: int, msg: str):
    print(f"✖ {printable(msg)}", file=sys.stderr)
    sys.exit(code)


STRING_LIST_KEYS = ("exclude_globs", "link_check_paths")  # config.yaml keys holding globs or folders


def _check_string_lists(cfg: Dict[str, Any]) -> None:
    """Exit 3 when a key of STRING_LIST_KEYS is not a list of non-empty strings."""
    for key in STRING_LIST_KEYS:
        value = cfg.get(key, [])
        if not (isinstance(value, list) and all(isinstance(item, str) and item for item in value)):
            _die(3, f"config.yaml: `{key}` must be a list of non-empty strings, e.g. `{key}: []`")


def load_config() -> Dict[str, Any]:
    cfg: Dict[str, Any] = {"require_full_traceability": True, "exclude_globs": []}
    config_path = _resolve_config_path()
    if config_path.exists():
        try:
            parsed = Y.load(config_path.read_text(encoding="utf-8"))
            for k, v in parsed.items():
                if v is not None:
                    cfg[k] = v
        except Exception as e:
            _die(3, f"Failed to read config.yaml: {e}")
        _check_string_lists(cfg)
    # .reqqignore (repo root): gitignore-style, one glob per line, '#' comments.
    # Portable across validator implementations — see section 6 of
    # https://github.com/reqquest/reqQuestFramework/blob/main/docs/framework/conventions.md
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
    """Staged requirement files: added, copied, modified or renamed (under the new path)."""
    cmd = ["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"]
    try:
        out = _nul_separated(subprocess.check_output(cmd, cwd=ROOT))
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        _die(3, f"git diff failed: {e}")
        return []
    return [ROOT / p for p in out if p.endswith(".md") and "requirements/" in p.replace("\\", "/")]


def stop_on_unstaged(files: List[Path]) -> None:
    """Stop (exit 3) when a file to validate has unstaged changes: the checks read the working
    tree, which is then not the content being committed, so they could pass or block the
    wrong version."""
    partial = unstaged_paths(files)
    if partial:
        _die(3, "staged requirement files with unstaged changes: " + ", ".join(partial)
             + " — stage them or stash the rest (git stash --keep-index) before committing")


def unstaged_paths(files: List[Path]) -> List[str]:
    """ROOT-relative paths of `files` whose working copy differs from the index. The paths are
    matched here, not passed to git, so a large import cannot overflow the command line."""
    if not files:
        return []
    rels = [f.relative_to(ROOT).as_posix() for f in files]
    try:
        out = subprocess.check_output(["git", "diff", "--name-only", "-z"], cwd=ROOT)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        _die(3, f"git diff failed: {e}")
        return []
    changed = set(_nul_separated(out))
    return [r for r in rels if r in changed]


def _nul_separated(out: bytes) -> List[str]:
    """Paths from git's `-z` output: unquoted, so a non-ASCII name stays as it is; decoded as
    `Path` does, so a name that is not UTF-8 does not fail."""
    return [os.fsdecode(p) for p in out.split(b"\0") if p]


def all_md_files() -> List[Path]:
    return list((ROOT / "requirements").rglob("*.md"))


def load_yaml_front_matter(text: str) -> Tuple[Dict[str, Any], int]:
    """Front matter of `text` and the number of lines up to its closing `---`; `({}, 0)` without one.

    Raises Y.YamlError when the front matter is not valid YAML; its `line` counts in `text`."""
    m = FM_RE.search(text)
    if not m:
        return {}, 0
    try:
        fm = Y.load(m.group(1))
    except Y.YamlError as e:
        if e.line:
            e.line += text[:m.start(1)].count("\n")
        raise
    line_offset = text[:m.end()].count("\n")
    return fm, line_offset


def front_matter_duplicates(text: str) -> List[Tuple[str, str]]:
    """(path, key) of every key written twice in one mapping of the front matter of `text`;
    none without front matter. `load_yaml_front_matter` hides them, the last one wins.

    Raises Y.YamlError when the front matter is not valid YAML."""
    m = FM_RE.search(text)
    return Y.duplicate_keys(m.group(1)) if m else []


def _file_ref(f: Path) -> str:
    """Path as reported in results: relative to ROOT when inside it."""
    try:
        return f.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return f.as_posix()


def _rec(f: Path, severity: str, kind: str, ptr: str, message: str, hint: str,
         line: Optional[int] = None) -> Dict[str, Any]:
    """One validation result; every result carries a fix hint (REQQF-FR-VALIDATION-100) and the
    line of the file only when the rule knows it."""
    rec = {
        "file":     _file_ref(f),
        "severity": severity,   # error | warning
        "kind":     kind,       # schema | schema.contract | frontmatter | traceability | io | graph.<rule> | layout.<rule> | openapi.<rule> | links.broken | owners.<rule>
        "ptr":      ptr,        # JSON pointer-ish path
        "message":  message,
        "hint":     hint,
    }
    if line is not None:
        rec["line"] = line
    return rec


class RunContext(NamedTuple):
    """What the checks of one run read: the config, the `files` results are reported for, and the
    front matter (`docs`, resolved path → front matter) of the whole corpus and those files. A
    module's `run(ctx)` returns result records."""
    cfg: Dict[str, Any]
    files: List[Path]
    docs: Dict[Path, Dict[str, Any]]


def split_skipped(files: List[Path]) -> Tuple[List[Path], List[Dict[str, Any]]]:
    """Split `files` into those to validate and one warning per skipped file: a path that
    is not a Markdown file or does not exist is not validated (REQQF-FR-VALIDATION-100)."""
    keep: List[Path] = []
    skipped: List[Dict[str, Any]] = []
    for f in files:
        if f.suffix.lower() != ".md":
            skipped.append(_rec(f, "warning", "io", "$", "Skipped: not a Markdown (.md) file.",
                                HINTS["not_markdown"]))
        elif not f.is_file():
            skipped.append(_rec(f, "warning", "io", "$", "Skipped: file does not exist.",
                                HINTS["missing_file"]))
        else:
            keep.append(f)
    return keep, skipped


def _ref_fields(fm: Dict[str, Any]) -> List[str]:
    """Fields holding requirement IDs: `traces_to`, plus `derives_from` for a TC (the only type
    the schema defines it for; elsewhere it is adopter metadata)."""
    return ["traces_to"] + (["derives_from"] if fm.get("type") == "TC" else [])


def _split_ref(item: str) -> Tuple[str, Optional[str]]:
    """(ID, pinned version or None) of a relation item `ID` or `ID@major.minor`."""
    rid, _, version = item.partition("@")
    return rid, version or None


def _prefix(rid: str) -> Optional[str]:
    """Repository prefix of a well-formed ID or reference; None if it has none (reqqf#94)."""
    parts = rid.split("-")
    return parts[0] if len(parts) == 4 else None


def _id_segments(rid: str) -> Tuple[str, str]:
    """(type, category) segments of a well-formed ID, with or without a prefix (reqqf#102)."""
    parts = rid.split("-")
    return parts[-3], parts[-2]


def _version_key(version: Any) -> Optional[Tuple[int, int]]:
    """(major, minor) of a `major.minor` version, for numeric comparison; None if malformed."""
    if not re.fullmatch(VERSION_PATTERN, str(version)):
        return None
    major, minor = str(version).split(".")
    return int(major), int(minor)
