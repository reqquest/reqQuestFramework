#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reqq_validate.py — reqQuest Framework validator entry point.

One run, one report: runs the checks of `CHECKS` (all but `owners-host` by default; `--check NAME`,
repeatable, runs only the named ones) and dispatches the toolkit subcommands `adopt`, `check` and
`upgrade`. Exit codes: 0 = OK, 2 = validation errors, 3 = configuration error."""
import argparse, json, os, sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.dont_write_bytecode = True  # no __pycache__ in adopter repos
import reqq_common as C  # noqa: E402
import reqq_config as CF  # noqa: E402
import reqq_check_graph as GR  # noqa: E402
import reqq_check_frontmatter as FM  # noqa: E402
import reqq_check_layout as LA  # noqa: E402
import reqq_check_links as LK  # noqa: E402
import reqq_check_openapi as OA  # noqa: E402
import reqq_check_schema as SC  # noqa: E402
import reqq_owners as OW  # noqa: E402
import reqq_toolkit_core as T  # noqa: E402
import reqq_toolkit_adopt as AD  # noqa: E402
import reqq_toolkit_check as CK  # noqa: E402
import reqq_toolkit_upgrade as UP  # noqa: E402


CHECKS = {  # name → run(ctx); the order of a run and of its report
    "frontmatter": FM.run,
    "schema": SC.run,
    "graph": GR.run,
    "layout": LA.run,
    "openapi": OA.run,
    "links": LK.run,
    "owners": OW.run,
    "owners-host": OW.run_host,  # asks the host: only on request
}
FILE_CHECKS = ("frontmatter", "schema", "graph", "layout", "openapi")  # the checks of the files given to a run
DEFAULT_CHECKS = tuple(name for name in CHECKS if name != "owners-host")


def enforce_min_toolkit_version() -> None:
    """REQQF-ADR-TOOLKIT-100 D7: fail with exit 3 when the adopted toolkit is older than the schema
    requires.

    The bound is an optional `min_toolkit_version` key at the root of
    `.reqq/schema/requirement.schema.json` (unknown keywords are ignored by JSON Schema
    validators, so this is inert for them). Absent key → no constraint. A repository that has
    not adopted yet gets a warning, not a failure — the bound only binds once a lock exists.
    """
    schema_path = C.ROOT / ".reqq" / "schema" / "requirement.schema.json"
    if not schema_path.exists():
        return
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return  # schema problems are already reported by the validation path
    required = schema.get("min_toolkit_version") if isinstance(schema, dict) else None
    if not required:
        return

    if not T.TOOLKIT_LOCK.exists():
        print(f"⚠ schema requires toolkit >= v{C.printable(required)} but this repo has no "
              f"{T.TOOLKIT_LOCK.relative_to(C.ROOT)} — run `adopt`", file=sys.stderr)
        return
    try:
        lock = json.loads(T.TOOLKIT_LOCK.read_text(encoding="utf-8"))
        current = lock.get("toolkit_version")
        if current and T._semver_lt(current, required):
            C._die(3, f"toolkit v{current} is older than the required v{required} "
                    f"— run `reqq_validate.py upgrade`")
    except (OSError, json.JSONDecodeError) as e:
        C._die(3, f"Failed to read {T.TOOLKIT_LOCK.relative_to(C.ROOT)}: {e}")
    except T.ToolkitError as e:
        C._die(3, str(e))


def print_results(results: List[Dict[str, Any]], scanned: int, excluded: List[str],
                  names: List[str]):
    """The text report; a run without a file check names its checks instead of counting files.
    In GitHub Actions an error or a warning is one `C.annotation` on its file, with the kind as
    title, the line when known and the hint in the message, so the pull request shows all of it.
    The ptr `$` (the whole file) is left out."""
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    n_err = sum(1 for r in results if r["severity"] == "error")
    n_warn = len(results) - n_err
    warn_part = f", warnings: {n_warn}" if n_warn else ""
    reads_files = bool(set(names) & set(FILE_CHECKS))
    scope = f"files scanned: {scanned}" if reads_files else f"checks: {', '.join(names)}"
    print(f"reqq validate — {scope}, errors: {n_err}{warn_part}")
    if excluded:
        print(f"excluded: {', '.join(map(C.printable, excluded))}")

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for r in results:
        grouped.setdefault(r["file"], []).append(r)

    for file, items in grouped.items():
        print(f"\n── {C.printable(file)}")
        for it in items:
            at = "" if it["ptr"] == "$" else f" @{it['ptr']}"
            if in_actions:
                level = "error" if it["severity"] == "error" else "warning"
                where = "" if it["ptr"] == "$" else f"@{it['ptr']}: "
                print(C.annotation(level, it["kind"], it["file"], where + it["message"],
                                   it.get("hint"), it.get("line")))
                continue
            sev = "✖ error" if it["severity"] == "error" else "⚠ warn"
            print(f"  {sev} [{C.printable(it['kind'])}]{C.printable(at)}: "
                  f"{C.printable(it['message'])}")
            if it.get("hint"):
                print(f"     ↳ hint: {C.printable(it['hint'])}")

    if n_err:
        warn_note = f", {n_warn} warning(s)" if n_warn else ""
        tail = f"scanned {scanned} file(s)" if reads_files else scope
        print(f"\nSummary: {n_err} error(s){warn_note} • {tail}")
    elif not reads_files:
        note = f" with {n_warn} warning(s)" if n_warn else ""
        print(f"\nChecks passed{note}: {', '.join(names)}. {'⚠' if n_warn else '✅'}")
    elif n_warn:
        print(f"\nValidated {scanned} file(s) with {n_warn} warning(s). ⚠")
    else:
        print(f"\nValidated {scanned} file(s). ✅")


def selected_checks(args: argparse.Namespace) -> List[str]:
    """Names of the checks to run, in CHECKS order. `--check` names exactly those (an unknown name
    is a configuration error); without it all but `owners-host` run, or only the file checks when
    the files are given explicitly."""
    for name in args.check or []:
        if name not in CHECKS:
            C._die(3, f"unknown check '{name}'; available: {', '.join(CHECKS)}")
    explicit_files = args.files and not (args.all or args.staged_only)
    wanted = args.check or (FILE_CHECKS if explicit_files else DEFAULT_CHECKS)
    return [name for name in CHECKS if name in wanted]


def select_files(args: argparse.Namespace, ex_globs: List[str]
                 ) -> Tuple[List[Path], List[str], List[Dict[str, Any]]]:
    """(files to validate, excluded files, a warning for each skipped file): the files given, the
    staged ones or all requirement files, less `exclude_globs` (config.yaml and .reqqignore)."""
    if args.files:
        files: List[Path] = [Path(p) for p in args.files]
    elif args.staged_only and not args.all:
        files = C.staged_md_files()
    else:
        files = C.all_md_files()

    excluded: List[str] = []
    keep: List[Path] = []
    for f in files:
        if C.is_excluded(f, ex_globs):
            try:
                excluded.append(f.relative_to(C.ROOT).as_posix())
            except ValueError:
                excluded.append(str(f))
        else:
            keep.append(f)
    # Before skipping: a staged file whose working copy is gone is unstaged, not deleted.
    if args.staged_only and not (args.all or args.files):
        C.stop_on_unstaged(keep)
    files, skipped = C.split_skipped(keep)
    return files, excluded, skipped


def file_scope(args: argparse.Namespace, ex_globs: List[str], names: List[str]
               ) -> Tuple[List[Path], List[str], List[Dict[str, Any]]]:
    """`select_files` for a run with a file check. Without one nothing is validated per file, but
    a named file that is missing or not Markdown is still warned about, whichever checks run
    (REQQF-FR-VALIDATION-100 story 5)."""
    if set(names) & set(FILE_CHECKS):
        return select_files(args, ex_globs)
    if args.files:
        return [], [], select_files(args, ex_globs)[2]
    return [], [], []


def load_docs(files: List[Path], ex_globs: List[str]) -> Dict[Path, Dict[str, Any]]:
    """Front matter of `files` and of the whole corpus: graph and layout compare against all of
    it, with results only for `files` (reqqf#92). Without files there is nothing to compare."""
    if not files:
        return {}
    corpus = [f for f in C.all_md_files() if not C.is_excluded(f, ex_globs)]
    return GR.load_graph_docs(corpus + files)


def run_checks(names: List[str], ctx: C.RunContext) -> List[Dict[str, Any]]:
    """The records of the named checks, in CHECKS order. A schema gap another front matter check
    reports is left out, so a field gets one report (REQQF-FR-VALIDATION-100 story 7); this needs
    the results of the whole run, which is why it is done here and not in `SC.run`."""
    found = {name: CHECKS[name](ctx) for name in names}
    if "schema" in found:
        others = [r for name in names if name in FILE_CHECKS and name != "schema" for r in found[name]]
        found["schema"] = SC.without_reported(found["schema"], others)
    return [r for records in found.values() for r in records]


def main() -> int:
    # Handle toolkit subcommands first
    if len(sys.argv) > 1 and sys.argv[1] in ("adopt", "check", "upgrade"):
        subcommand = sys.argv[1]
        sub_args = sys.argv[2:]
        try:
            if subcommand == "adopt":
                return AD.cmd_adopt(sub_args)
            elif subcommand == "check":
                return CK.cmd_check(sub_args)
            elif subcommand == "upgrade":
                return UP.cmd_upgrade(sub_args)
        except T.ToolkitError as e:
            C._die(3, str(e))
        return 3

    ap = argparse.ArgumentParser(description="Validate reqQuest Framework requirement files.")
    ap.add_argument("--staged-only", action="store_true",
                    help="Validate only staged files (used by pre-commit).")
    ap.add_argument("--all", action="store_true",
                    help="Validate all requirement files.")
    ap.add_argument("--format", choices=["plain", "json"], default="plain",
                    help="Output format.")
    ap.add_argument("--check", action="append", metavar="NAME",
                    help="Run only this check; repeatable. One of: " + ", ".join(CHECKS) + ". Default: "
                         "all but owners-host; with explicit files: " + ", ".join(FILE_CHECKS) + ".")
    ap.add_argument("files", nargs="*", help="Explicit Markdown file paths to validate.")
    args = ap.parse_args()
    names = selected_checks(args)

    enforce_min_toolkit_version()

    cfg = C.load_config()
    CF.check_language(cfg)
    CF.check_id_prefix(cfg)
    CF.check_short_title(cfg)
    CF.check_enforce_layout(cfg)
    CF.check_openapi(cfg)
    ex_globs: List[str] = cfg.get("exclude_globs", []) or []

    files, excluded, skipped = file_scope(args, ex_globs, names)
    results = skipped + run_checks(names, C.RunContext(cfg, files, load_docs(files, ex_globs)))

    errors = [r for r in results if r["severity"] == "error"]
    warnings = [r for r in results if r["severity"] != "error"]
    if args.format == "json":
        payload = {
            "ok":       not errors,
            "scanned":  len(files),
            "errors":   errors,
            "warnings": warnings,
            "excluded": excluded,
        }
        print(json.dumps(payload, indent=2))
    elif set(names) & set(FILE_CHECKS) and not files and not results:
        print("No requirement files to validate.")
    else:
        print_results(results, scanned=len(files), excluded=excluded, names=names)
        if "owners-host" in names:
            print(OW.host_scope(cfg))

    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
