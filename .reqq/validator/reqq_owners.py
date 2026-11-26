#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reqq_owners.py — ownership governance of the reqQuest Framework (REQQF-ADR-GOV-100).

Roles in requirements/00-context/roles.yaml own areas of requirements/. The level comes
from `ownership.mode` in .reqq/validator/config.yaml: off | catalog | generate | enforce;
without the key the state is `undetected`. Configuration, exclusions, YAML loading and
the front matter come from the validator modules `reqq_common` and `reqq_yaml`; the catalog is
checked by `reqq_check_schema`.

Usage:
  python3 .reqq/validator/reqq_owners.py --check   # offline rules of the level
  python3 .reqq/validator/reqq_owners.py generate  # write the reqq block to .github/CODEOWNERS
  python3 .reqq/validator/reqq_owners.py --verify-handles  # rule V6 online (enforce)

The validator entry point `reqq_validate.py` runs `--check` as its `owners` check (pre-commit,
CI) and `--verify-handles` as its `owners-host` check (CI only: `--check owners-host`), and
reports the findings as `owners.<rule>` records. `generate` exists only here.

Rules: roles (roles.schema.json), V1, V4, V5, V8, io (a requirement file that is not UTF-8
text, so its owner is unknown) from level catalog; V2, V3, V7 from
generate. Level enforce adds the online rule V6 (`--verify-handles`, CI only).
Exit codes: 0 OK, 2 rule violation (drift), 3 configuration error.
"""
import argparse
import functools
import os
import re
import sys
import urllib.parse
from itertools import combinations
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List, Mapping, NamedTuple, Optional, Tuple

sys.dont_write_bytecode = True  # importing the validator must not leave __pycache__ in adopter repos
import reqq_owners_github as G
import reqq_yaml as Y
import reqq_common as C
import reqq_check_schema as SC

ROLES_REL = "requirements/00-context/roles.yaml"
STAKEHOLDERS_REL = "requirements/00-context/stakeholders.md"
CODEOWNERS_REL = ".github/CODEOWNERS"
CONFIG_REL = ".reqq/validator/config.yaml"

MODES = ("off", "catalog", "generate", "enforce")
CODEOWNERS_MODES = ("generate", "enforce")
HOSTS = ("github", "gitlab")

# The `handle` format of roles.schema.json; `(?![\s\S])` rejects a trailing newline, `$` would not.
HANDLE_PATTERN = r"^@[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?(?:/[A-Za-z0-9._-]+)*(?![\s\S])"
# HANDLE_PATTERN with at most one "/": GitHub has @user and @org/team, no nested groups (D12).
GITHUB_HANDLE_PATTERN = r"^@[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?(?:/[A-Za-z0-9._-]+)?(?![\s\S])"
HANDLE_FORMS = {"github": "@user or @org/team", "gitlab": "@user or @group/subgroup/..."}


class ConfigError(Exception):
    """A configuration the script cannot run with; exit code 3."""


class Finding(NamedTuple):
    """One rule violation (or warning) reported by --check; `hint` replaces the rule's own,
    `line` is the line of `file` when the rule knows it."""
    rule: str
    file: str
    message: str
    severity: str = "error"
    hint: Optional[str] = None
    line: Optional[int] = None


# --- Level and host ------------------------------------------------------------------
def ownership_mode(cfg: Dict[str, Any]) -> str:
    """Return the ownership level from config.yaml, or `undetected` without the key."""
    if "ownership" not in cfg:
        return "undetected"
    ownership = cfg["ownership"]
    if not isinstance(ownership, dict):
        raise ConfigError("config.yaml: `ownership` must be a mapping with `mode`")
    mode = ownership.get("mode")
    if mode not in MODES:
        raise ConfigError(f"config.yaml: ownership.mode {mode!r} is not one of "
                          "off, catalog, generate, enforce")
    if mode == "off" and not (ownership.get("decided") and ownership.get("decided_by")):
        raise ConfigError("config.yaml: ownership.mode off needs `decided` and `decided_by` "
                          "— record when and by whom it was decided")
    return mode


def host_of(cfg: Dict[str, Any], mode: str) -> str:
    """Return `toolkit.host` (default github); levels that write CODEOWNERS support GitHub
    only (D9)."""
    host = (cfg.get("toolkit") or {}).get("host", "github")
    if host not in HOSTS:
        raise ConfigError(f"config.yaml: toolkit.host {host!r} is not github or gitlab")
    if mode in CODEOWNERS_MODES and host != "github":
        raise ConfigError(f"config.yaml: ownership.mode {mode} writes .github/CODEOWNERS "
                          "and supports toolkit.host github only")
    return host


# --- Role catalog: roles.schema.json, V4, V5 ------------------------------------------
def handles_of(role: Dict[str, Any]) -> List[str]:
    """The role's handles as a list (`handle` is one handle or a list)."""
    handle = role["handle"]
    return handle if isinstance(handle, list) else [handle]


def _catalog_error(message: str) -> Finding:
    return Finding("roles", ROLES_REL, message)


def _duplicate_keys(text: str) -> List[Finding]:
    """Keys written twice in any mapping of roles.yaml, in any spelling (plain, quoted,
    escaped, flow): the YAML loader keeps only the last one, silently, so a role, a whole
    `roles` block or a field would vanish."""
    return [_catalog_error(f"key {key!r} appears more than once" + (f" in {path!r}" if path else ""))
            for path, key in Y.duplicate_keys(text)]


def check_catalog(doc: Any, text: str) -> List[Finding]:
    """Check the parsed roles.yaml `doc` against roles.schema.json, and its `text` for repeated
    keys (rule `roles`). The format of a handle is V4 (`check_handles`), not the schema's."""
    return [_catalog_error(message) for message in SC.validate_catalog(doc)] + _duplicate_keys(text)


def check_handles(roles: Dict[str, Any], host: str) -> List[Finding]:
    """V4: every handle has the format of the host; min_approvals warns on GitHub (D12)."""
    pattern = GITHUB_HANDLE_PATTERN if host == "github" else HANDLE_PATTERN
    out = []
    for key, role in roles.items():
        out += [Finding("V4", ROLES_REL, f"{key}: handle {h!r} is not {HANDLE_FORMS[host]}")
                for h in handles_of(role) if not re.match(pattern, h)]
        if host == "github" and "min_approvals" in role:
            out.append(Finding("min_approvals", ROLES_REL,
                               f"{key}: min_approvals is ignored on GitHub", "warning"))
    return out


def _overlap(a: str, b: str) -> bool:
    return "*" in (a, b) or a == b or a.startswith(b + "/") or b.startswith(a + "/")


def check_responsible_for(roles: Dict[str, Any], requirements_dir: Path) -> List[Finding]:
    """V5: responsible_for names existing directories; two roles never share one.

    On GitHub the last matching CODEOWNERS rule wins, so of two roles claiming the same
    directory (or a parent and its subdirectory) one silently loses it (D5).
    """
    claims = [(p, key) for key, role in roles.items() for p in role["responsible_for"]]
    out = [Finding("V5", ROLES_REL, f"{key}: responsible_for {p!r} is not a directory "
                                    "in requirements/")
           for p, key in claims if p != "*" and not (requirements_dir / p).is_dir()]
    out += [Finding("V5", ROLES_REL, f"{k1} ({p1}) and {k2} ({p2}) claim the same directory")
            for (p1, k1), (p2, k2) in combinations(claims, 2) if k1 != k2 and _overlap(p1, p2)]
    return out


# --- Requirements side: V1, V8, V3 ---------------------------------------------------
STAKEHOLDER_ROLE_RE = re.compile(r"(?<![\w-])role-[a-z0-9-]+")


def check_owners(roles: Dict[str, Any], front_matters: Dict[str, Dict[str, Any]]) -> List[Finding]:
    """V1: `owner` of every requirement is a role key; a missing owner is the validator's."""
    return [Finding("V1", path, f"owner {fm['owner']!r} is not a role key in {ROLES_REL}")
            for path, fm in front_matters.items()
            if "owner" in fm and str(fm["owner"]) not in roles]


def _last_cell(row: str) -> str:
    """The last cell of a Markdown table row; `\\|` is a pipe inside a cell."""
    cells = re.split(r"(?<!\\)\|", row.strip())[1:]
    if cells and not cells[-1].strip():
        cells.pop()
    return cells[-1] if cells else ""


def check_stakeholders(roles: Dict[str, Any], text: Optional[str]) -> List[Finding]:
    """V8: the last column of the stakeholders.md tables names every role and no unknown one.

    The column is found by position, not by name, so the check does not depend on the
    language of the repository (FR-GOV-100 story 6, ADR D2).
    """
    if text is None:
        return [Finding("V8", STAKEHOLDERS_REL, "file missing; every role in roles.yaml must be "
                                                "assigned to a stakeholder")]
    named = {key for line in text.splitlines() if line.lstrip().startswith("|")
             for key in STAKEHOLDER_ROLE_RE.findall(_last_cell(line))}
    out = [Finding("V8", STAKEHOLDERS_REL, f"{key} is not assigned to any stakeholder")
           for key in roles if key not in named]
    out += [Finding("V8", STAKEHOLDERS_REL, f"{key} is not a role in {ROLES_REL}")
            for key in sorted(named) if key not in roles]
    return out


def _covered(directory: str, paths: List[str]) -> bool:
    return any(p == "*" or directory == p or directory.startswith(p + "/") for p in paths)


def check_orphans(roles: Dict[str, Any], requirement_paths: List[str]) -> List[Finding]:
    """V3: the directory of every requirement (relative to requirements/) has an owner."""
    paths = [p for role in roles.values() for p in role["responsible_for"]]
    dirs = dict.fromkeys(str(PurePosixPath(p).parent) for p in requirement_paths)
    return [Finding("V3", "requirements" if d == "." else f"requirements/{d}",
                    "no role in roles.yaml is responsible for this directory")
            for d in dirs if not _covered(d, paths)]


# --- CODEOWNERS block: render, merge, V2, V7 -------------------------------------------
BEGIN_MARKER = ("# reqq:begin - generated from requirements/00-context/roles.yaml "
                "by .reqq/validator/reqq_owners.py, do not edit")
END_MARKER = "# reqq:end"
# Governance input and machinery: editing any of them could switch the protection off (D5).
SELF_PROTECTED = ("/.reqq/**", "/.github/CODEOWNERS", "/.github/workflows/requirements-*.yml",
                  "/requirements/00-context/roles.yaml", "/.reqqignore")
_TOKEN_RE = re.compile(r"[\x21-\x7e]+")


def _rule_line(pattern: str, handles: List[str]) -> str:
    """One CODEOWNERS rule; a space or control character would split or forge a rule."""
    for token in (pattern, *handles):
        if not _TOKEN_RE.fullmatch(token):
            raise ValueError(f"refusing to write CODEOWNERS: {token!r} contains a space, "
                             "a control character or a non-ASCII character")
    return f"{pattern} {' '.join(handles)}"


def _area(path: str) -> str:
    return "/requirements/**" if path == "*" else f"/requirements/{path}/**"


def render_block(roles: Dict[str, Any]) -> str:
    """The generated block: one rule per responsible_for path, then self-protection
    owned by every handle of the catalog."""
    everyone = list(dict.fromkeys(h for role in roles.values() for h in handles_of(role)))
    lines = [BEGIN_MARKER, "# requirements: responsible_for in roles.yaml"]
    lines += [_rule_line(_area(p), handles_of(role))
              for role in roles.values() for p in role["responsible_for"]]
    lines.append("# governance self-protection")
    lines += [_rule_line(p, everyone) for p in SELF_PROTECTED]
    lines.append(END_MARKER)
    return "\n".join(lines) + "\n"


def _markers(lines: List[str]) -> Optional[Tuple[int, int]]:
    """Indexes of the begin and end markers, None without a block; ValueError when unbalanced."""
    begins = [i for i, line in enumerate(lines) if line.rstrip("\r\n").startswith("# reqq:begin")]
    ends = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == END_MARKER]
    if not begins and not ends:
        return None
    if len(begins) != 1 or len(ends) != 1 or ends[0] < begins[0]:
        raise ValueError(f"{CODEOWNERS_REL}: unbalanced '# reqq:begin' / '# reqq:end' markers "
                         "— fix them by hand")
    return begins[0], ends[0]


def _split(text: str) -> Tuple[List[str], List[str]]:
    """(lines outside the block, lines of the block); ValueError on unbalanced markers."""
    lines = text.splitlines(keepends=True)
    markers = _markers(lines)
    if markers is None:
        return lines, []
    begin, end = markers
    return lines[:begin] + lines[end + 1:], lines[begin:end + 1]


def block_line_range(text: str) -> Optional[Tuple[int, int]]:
    """Line numbers (from 1, inclusive) of the block markers, counted by "\\n" as GitHub
    does; None without a block."""
    markers = _markers(text.split("\n"))
    return None if markers is None else (markers[0] + 1, markers[1] + 1)


def merge_codeowners(existing: str, block: str) -> str:
    """Existing CODEOWNERS with the block removed and appended at the end (D5, D7).

    Lines outside the markers stay byte for byte, except trailing blank lines.
    """
    outside, _ = _split(existing)
    while outside and not outside[-1].strip():
        outside.pop()
    if not outside:
        return block
    if not outside[-1].endswith("\n"):
        outside[-1] += "\n"
    return "".join(outside) + "\n" + block


def check_codeowners(existing: Optional[str], block: str) -> List[Finding]:
    """V2: CODEOWNERS ends with the freshly generated block; V7: self-protection complete.

    Line endings are compared normalized: a CRLF checkout is not drift.
    """
    if existing is None:
        return [Finding("V2", CODEOWNERS_REL, "file missing; run `reqq_owners.py generate`")]
    text = existing.replace("\r\n", "\n")
    _, current = _split(text)
    out = []
    if merge_codeowners(text, block) != text:
        out.append(Finding("V2", CODEOWNERS_REL, "the reqq block is missing, differs from "
                                                 "roles.yaml or is not at the end of the file"))
    if current:
        present = {line.rstrip("\n") for line in current}
        missing = [line.split(" ")[0] for line in block.splitlines()
                   if line.split(" ")[0] in SELF_PROTECTED and line not in present]
        if missing:
            out.append(Finding("V7", CODEOWNERS_REL, "self-protection incomplete, missing: "
                                                     + ", ".join(missing)))
    return out


# --- Host: V6 (online, CI only) --------------------------------------------------------
class CiContext(NamedTuple):
    """Where --verify-handles looks: the API, the repository, the target branch, the commit."""
    api_url: str
    token: str
    repo: str
    branch: str
    ref: str


def ci_context(env: Mapping[str, str]) -> CiContext:
    """The context from GitHub Actions variables; the branch is the PR base or the pushed one."""
    branch = env.get("GITHUB_BASE_REF") or env.get("GITHUB_REF_NAME")
    missing = [k for k in ("GITHUB_TOKEN", "GITHUB_REPOSITORY", "GITHUB_SHA") if not env.get(k)]
    missing += [] if branch else ["GITHUB_BASE_REF or GITHUB_REF_NAME"]
    if missing:
        raise ConfigError("the host check (--check owners-host, --verify-handles) runs in "
                          f"GitHub Actions; missing: {', '.join(missing)}")
    return CiContext(env.get("GITHUB_API_URL") or "https://api.github.com", env["GITHUB_TOKEN"],
                     env["GITHUB_REPOSITORY"], branch, env["GITHUB_SHA"])


def check_host(verdict: str, branch: str) -> List[Finding]:
    """V6: the branch requires review from code owners; unproven is a warning (D10, D11)."""
    if verdict == G.NOT_ENFORCED:
        return [Finding("V6-host", CONFIG_REL, f"ownership.mode enforce is declared, but branch "
                        f"{branch} does not require review from code owners — enable it in branch "
                        "protection or a ruleset, or set ownership.mode to generate")]
    if verdict == G.UNKNOWN:
        return [Finding("V6-host", CONFIG_REL, f"could not confirm that branch {branch} requires "
                        "review from code owners: branch protection is unreadable for this token "
                        "or the API did not answer", "warning", V6_HOST_UNKNOWN_HINT)]
    return []


def check_owner_errors(errors: G.Response, lines: Tuple[int, int], ref: str,
                       sees_repo: bool) -> List[Finding]:
    """V6: the host reports no owner of the reqq block at commit `ref`; lines outside it are the
    adopter's. One error per problem lists its lines: a bad handle of a role also stands in every
    self-protection line. A 404 is the commit when the token `sees_repo`, otherwise the token."""
    if errors.status == 404:
        return [_not_found(ref) if sees_repo else _no_repo_access()]
    if not (errors.status == 200 and isinstance(errors.body, dict)):
        return [Finding("V6", CODEOWNERS_REL, f"could not read CODEOWNERS errors "
                                              f"(HTTP {errors.status})", "warning",
                        V6_UNANSWERED_HINT)]
    first, last = lines
    grouped: Dict[Tuple[str, str], List[int]] = {}
    for e in errors.body["errors"]:
        if e.get("path") == CODEOWNERS_REL and first <= e["line"] <= last:
            grouped.setdefault((e["kind"], e.get("suggestion") or e["message"]), []).append(e["line"])
    return [Finding("V6", CODEOWNERS_REL, f"{_lines(numbers)} ({kind}): {text}", line=numbers[0])
            for (kind, text), numbers in grouped.items()]


def _not_found(ref: str) -> Finding:
    return Finding("V6", CODEOWNERS_REL, f"the host has no CODEOWNERS at commit {ref}, although "
                   "the checked-out copy has the reqq block", "warning", V6_MISSING_AT_COMMIT_HINT)


def _no_repo_access() -> Finding:
    return Finding("V6", CODEOWNERS_REL, "the token has no access to this repository (HTTP 404)",
                   "warning", V6_NO_REPO_ACCESS_HINT)


def _lines(numbers: List[int]) -> str:
    return ("line " if len(numbers) == 1 else "lines ") + ", ".join(map(str, numbers))


def run_verify(ctx: CiContext, codeowners: Optional[str],
               get: Callable[[str], G.Response]) -> List[Finding]:
    """V6 on GitHub: the host probe of the branch, then CODEOWNERS errors at the commit."""
    lines = block_line_range(codeowners) if codeowners else None
    if lines is None:
        return [Finding("V2", CODEOWNERS_REL, f"no reqq block in {CODEOWNERS_REL} to verify; "
                                              "run generate")]
    name = urllib.parse.quote(ctx.branch, safe="/")
    branch_path = f"repos/{ctx.repo}/branches/{name}"
    rules = get(f"repos/{ctx.repo}/rules/branches/{name}?per_page=100")
    verdict = G.probe_verdict(rules, get(f"{branch_path}/protection"), get(branch_path))
    errors = get(f"repos/{ctx.repo}/codeowners/errors?ref={ctx.ref}")
    return check_host(verdict, ctx.branch) + check_owner_errors(errors, lines, ctx.ref,
                                                                G.sees_repository(rules))


# --- CLI -------------------------------------------------------------------------------
HINTS = {
    "roles": "Shape roles.yaml as in .reqq/schema/roles.schema.json: roles -> role-<name> -> "
             "title, handle, responsible_for.",
    "V1": "Set `owner` to a role key from requirements/00-context/roles.yaml, e.g. role-architect.",
    "V2": "Run `python3 .reqq/validator/reqq_owners.py generate` and commit .github/CODEOWNERS; "
          "never edit the reqq block by hand.",
    "V3": "Add the directory, or a parent of it, to `responsible_for` of one role in roles.yaml.",
    "V4": "Use @user or @org/team on GitHub, @user or @group/subgroup/... on GitLab.",
    "V5": "Point responsible_for at existing directories under requirements/ and give each "
          "directory to one role only.",
    "V7": "Run `python3 .reqq/validator/reqq_owners.py generate`; the block always carries the "
          "self-protection rules.",
    "V8": "Put each role key from roles.yaml in the last column of the stakeholders.md table, "
          "and only keys from roles.yaml.",
    "min_approvals": "GitHub counts approvals per branch rule, not per path; keep min_approvals "
                     "only for GitLab.",
    "V6": "Give every handle write access to the repository; a team must also be visible.",
    "V6-host": "Require review from Code Owners on the branch (branch protection or a ruleset), "
               "or set ownership.mode to generate.",
    "io": "Save the requirement file as UTF-8 text; its `owner` is read from the front matter.",
    "undetected": "Set `ownership.mode` in .reqq/validator/config.yaml to off, catalog, generate or "
                  "enforce; off also needs `decided` and `decided_by`.",
}
OWNERS_TOKEN = ("OWNERS_VERIFY_TOKEN needs Administration: read and Contents: read on this "
                "repository")
V6_UNANSWERED_HINT = (f"The host did not answer as expected: {OWNERS_TOKEN}; check the token and "
                      "run again.")
V6_MISSING_AT_COMMIT_HINT = ("Check that commit GITHUB_SHA is on the host and that the checkout "
                             "fetches it (actions/checkout without `ref`).")
V6_NO_REPO_ACCESS_HINT = ("Issue OWNERS_VERIFY_TOKEN for this repository with Contents: read "
                          "(Administration: read only for classic branch protection).")
V6_HOST_UNKNOWN_HINT = ("Require review from Code Owners in a ruleset, which the default token "
                        "reads, or, for classic branch protection, store a fine-grained token with "
                        "Administration: read and Contents: read as the OWNERS_VERIFY_TOKEN secret.")
UNDETECTED = ("ownership undetected: config.yaml has no `ownership` key, so no decision is "
              "recorded. Set ownership.mode to off, catalog, generate or enforce "
              "(see conventions.md, section \"Ownership governance\").")
OTHER_CODEOWNERS = ("CODEOWNERS", "docs/CODEOWNERS")


def hint_of(finding: Finding) -> str:
    """The fix hint of a finding: its own, or the one of its rule."""
    return finding.hint or HINTS[finding.rule]


class _Parser(argparse.ArgumentParser):
    """Argument errors are configuration errors (3), not drift (argparse's 2)."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"✖ {message}", file=sys.stderr)
        sys.exit(3)


def _parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    ap = _Parser(description="Ownership governance of the reqQuest Framework.")
    ap.add_argument("command", nargs="?", choices=["generate"],
                    help="write the reqq block to .github/CODEOWNERS")
    ap.add_argument("--check", action="store_true",
                    help="run the offline rules of the configured level")
    ap.add_argument("--verify-handles", action="store_true",
                    help="rule V6 at level enforce: ask the host (GitHub Actions only)")
    args = ap.parse_args(argv)
    if [args.command == "generate", args.check, args.verify_handles].count(True) != 1:
        ap.error("use exactly one of: --check, --verify-handles, generate")
    return args


def _read(rel: str) -> Optional[str]:
    """File content with line endings kept, or None when the file does not exist."""
    path = C.ROOT / rel
    if not path.is_file():
        return None
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _load_catalog(mode: str) -> Tuple[Any, str]:
    text = _read(ROLES_REL)
    if text is None:
        raise ConfigError(f"{ROLES_REL} not found; ownership.mode {mode} needs the role catalog")
    try:
        return Y.load(text), text
    except Y.YamlError as e:
        raise ConfigError(f"{ROLES_REL}: {e}") from e


def _front_matter(path: Path) -> Optional[Dict[str, Any]]:
    """Front matter of a requirement file; an invalid one counts as empty, the validator reports
    it. None when the file cannot be read as UTF-8 text."""
    try:
        return C.load_yaml_front_matter(path.read_text(encoding="utf-8"))[0]
    except (OSError, UnicodeError):
        return None
    except Y.YamlError:
        return {}


def _requirement_files(cfg: Dict[str, Any]) -> List[Path]:
    """Requirement files after the validator's exclusions (config.yaml and .reqqignore); a path
    that is not a file, e.g. a folder named `x.md`, is none."""
    globs = cfg.get("exclude_globs", []) or []
    return [f for f in C.all_md_files() if f.is_file() and not C.is_excluded(f, globs)]


def _role_rules(roles: Dict[str, Any], host: str) -> List[Finding]:
    return check_handles(roles, host) + check_responsible_for(roles, C.ROOT / "requirements")


def run_check(cfg: Dict[str, Any], mode: str, host: str) -> List[Finding]:
    """All offline rules of `mode`; rules that need the roles run on a valid catalog only."""
    doc, text = _load_catalog(mode)
    out = check_catalog(doc, text)
    if out:
        return out
    roles = doc["roles"]
    files = _requirement_files(cfg)
    read = {f.relative_to(C.ROOT).as_posix(): _front_matter(f) for f in files}
    front_matters = {path: fm for path, fm in read.items() if fm is not None}
    out = _role_rules(roles, host) + check_owners(roles, front_matters)
    out += [Finding("io", path, "cannot be read as UTF-8 text, so its owner is not checked")
            for path, fm in read.items() if fm is None]
    out += check_stakeholders(roles, _read(STAKEHOLDERS_REL))
    if mode in CODEOWNERS_MODES:
        requirements = C.ROOT / "requirements"
        out += check_orphans(roles, [f.relative_to(requirements).as_posix() for f in files])
        out += check_codeowners(_read(CODEOWNERS_REL), render_block(roles))
    return out


def _refuse_other_codeowners() -> None:
    """GitHub reads .github/CODEOWNERS first; creating it would disable a file elsewhere."""
    if (C.ROOT / CODEOWNERS_REL).is_file():
        return
    for rel in OTHER_CODEOWNERS:
        if (C.ROOT / rel).is_file():
            raise ConfigError(f"{rel} exists and GitHub reads {CODEOWNERS_REL} first; move {rel} "
                              f"to {CODEOWNERS_REL}, then run generate again")


def run_generate(mode: str, host: str) -> int:
    """Write the block at the end of .github/CODEOWNERS; nothing below level generate."""
    if mode not in CODEOWNERS_MODES:
        print(f"ownership: {mode} — the CODEOWNERS block starts at mode generate; nothing written.")
        return 0
    doc, text = _load_catalog(mode)
    findings = check_catalog(doc, text) or _role_rules(doc["roles"], host)
    if any(f.severity == "error" for f in findings):
        _report(mode, findings)
        print(f"{CODEOWNERS_REL} not written.")
        return 2
    _refuse_other_codeowners()
    existing = _read(CODEOWNERS_REL)
    merged = merge_codeowners(existing or "", render_block(doc["roles"]))
    if merged == existing:
        print(f"{CODEOWNERS_REL} is up to date.")
        return 0
    path = C.ROOT / CODEOWNERS_REL
    path.parent.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(merged)
    print(f"wrote {CODEOWNERS_REL}")
    return 0


def _verify_handles() -> List[Finding]:
    """Findings of V6 at level enforce, asked from the host of the CI context."""
    ctx = ci_context(os.environ)
    return run_verify(ctx, _read(CODEOWNERS_REL),
                      functools.partial(G.api_get, ctx.api_url, ctx.token))


def _report(mode: str, findings: List[Finding]) -> None:
    """Print the findings; in GitHub Actions each is a `C.annotation` with its hint, a warning
    never silent (D10)."""
    errors = [f for f in findings if f.severity == "error"]
    warnings = len(findings) - len(errors)
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    print(f"reqq owners — mode: {mode}, errors: {len(errors)}, warnings: {warnings}")
    for f in findings:
        if in_actions:
            print(C.annotation(f.severity, f"owners.{f.rule}", f.file, f.message, hint_of(f), f.line))
            continue
        text = f"[{f.rule}] {C.printable(f.file)}: {C.printable(f.message)}"
        print(f"  {'✖' if f.severity == 'error' else '⚠'} {text}")
        print(f"     ↳ hint: {hint_of(f)}")
    if not errors:
        note = f" with {warnings} warning(s)" if warnings else ""
        print(f"Ownership check passed{note} (mode: {mode}).")


def _records(findings: List[Finding]) -> List[Dict[str, Any]]:
    """The findings as validator records of kind `owners.<rule>`, each with the hint of its rule."""
    return [C._rec(C.ROOT / f.file, f.severity, f"owners.{f.rule}", "$", f.message, hint_of(f),
                   f.line) for f in findings]


def run(ctx: C.RunContext) -> List[Dict[str, Any]]:
    """The `owners` check: the offline rules of the configured level as records. Level off adds
    nothing, `undetected` one warning; a configuration error ends the run with exit 3."""
    try:
        mode = ownership_mode(ctx.cfg)
        if mode == "off":
            return []
        if mode == "undetected":
            return [C._rec(C.ROOT / CONFIG_REL, "warning", "owners.undetected", "$", UNDETECTED,
                           HINTS["undetected"])]
        return _records(run_check(ctx.cfg, mode, host_of(ctx.cfg, mode)))
    except (ConfigError, ValueError) as e:
        C._die(3, str(e))


def run_host(ctx: C.RunContext) -> List[Dict[str, Any]]:
    """The `owners-host` check: rule V6 as records. It asks the host, so it runs only when
    requested, and only at level enforce; elsewhere it adds nothing."""
    try:
        mode = ownership_mode(ctx.cfg)
        if mode != "enforce":
            return []
        host_of(ctx.cfg, mode)
        return _records(_verify_handles())
    except (ConfigError, ValueError) as e:
        C._die(3, str(e))


def host_scope(cfg: Dict[str, Any]) -> str:
    """What the `owners-host` check covered: the branch and commit of rule V6, nothing below level
    enforce or without the reqq block (`run_verify` then asks nothing). Called after `run_host`,
    which has already refused a bad configuration."""
    mode = ownership_mode(cfg)
    if mode != "enforce":
        return f"ownership: {mode} — V6 starts at mode enforce; nothing checked."
    if block_line_range(_read(CODEOWNERS_REL) or "") is None:
        return f"owners-host: rule V6 not run: no reqq block in {CODEOWNERS_REL} (mode: enforce)"
    ctx = ci_context(os.environ)
    return (f"owners-host: rule V6 checked branch {C.printable(ctx.branch)} at commit "
            f"{C.printable(ctx.ref)} (mode: enforce)")


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    cfg = C.load_config()
    try:
        mode = ownership_mode(cfg)
        if args.verify_handles and mode != "enforce":
            print(host_scope(cfg))
            return 0
        if mode == "undetected":
            in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
            print(C.annotation("warning", "owners.undetected", CONFIG_REL, UNDETECTED,
                               HINTS["undetected"]) if in_actions else f"⚠ {UNDETECTED}")
            return 0
        if mode == "off":
            own = cfg["ownership"]
            print(f"ownership: off (decided {C.printable(own['decided'])} by "
                  f"{C.printable(own['decided_by'])}) — no rules run.")
            return 0
        host = host_of(cfg, mode)
        if args.command == "generate":
            return run_generate(mode, host)
        findings = _verify_handles() if args.verify_handles else run_check(cfg, mode, host)
    except (ConfigError, ValueError) as e:
        print(f"✖ {C.printable(e)}", file=sys.stderr)
        return 3
    _report(mode, findings)
    return 2 if any(f.severity == "error" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
