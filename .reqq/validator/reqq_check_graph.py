# -*- coding: utf-8 -*-
"""Requirement graph rules: dangling links, duplicate IDs, status and version of link targets."""
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import reqq_yaml as Y  # noqa: E402
import reqq_common as C  # noqa: E402


def load_graph_docs(files: List[Path]) -> Dict[Path, Dict[str, Any]]:
    """Front matter of each readable file, keyed by resolved path. Unreadable files, files with
    invalid front matter and files with a key written twice are left out; validate_doc()
    reports them. The schema and layout checks read the same docs, so they skip these files too."""
    docs: Dict[Path, Dict[str, Any]] = {}
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
            if not C.front_matter_duplicates(text):
                docs[f.resolve()] = C.load_yaml_front_matter(text)[0]
        except (OSError, UnicodeError, Y.YamlError):
            continue
    return docs


def _relations(fm: Dict[str, Any]) -> List[Tuple[str, str, Optional[str]]]:
    """(ptr, target ID, pinned version or None) of every reference in `traces_to`,
    `derives_from` (TC) and `conflict[].with`. Only lists and well-formed items are
    followed; the rest is left to _check_refs() and _check_conflict()."""
    refs: List[Tuple[str, str, Optional[str]]] = []
    for field in C._ref_fields(fm):
        if isinstance(fm.get(field), list):
            refs += [(f"{field}[{n}]", *C._split_ref(str(t))) for n, t in enumerate(fm[field])
                     if re.fullmatch(C.REF_PATTERN, str(t))]
    if isinstance(fm.get("conflict"), list):
        refs += [(f"conflict[{n}].with", e["with"], None) for n, e in enumerate(fm["conflict"])
                 if isinstance(e, dict) and re.fullmatch(C.ID_PATTERN, str(e.get("with", "")))]
    return refs


def _status_rule(source: str, target: str) -> Optional[str]:
    """Graph rule broken by a link from a `source`-status to a `target`-status document."""
    if source == "approved" and target in ("draft", "review"):
        return "graph.status-draft"
    if source != "deprecated" and target == "deprecated":
        return "graph.status-deprecated"
    return None


def _version_rule(rid: str, target: str, pinned: str, current: Any) -> Optional[Tuple[str, str, str]]:
    """(severity, rule, message) for `rid` pinned to `target@pinned` while `target` is at
    version `current` (reqqf#93); None while the versions are equal."""
    have, want = C._version_key(current), C._version_key(pinned)
    if have is None:
        return ("error", "graph.suspect-version",
                f"'{target}@{pinned}' cannot be compared: '{target}' has no valid `version`.")
    if want > have:
        return ("error", "graph.suspect-version",
                f"'{target}@{pinned}' does not exist: '{target}' is at version {current}.")
    if want < have:
        return ("warning", "graph.suspect",
                f"'{rid}' needs review: '{target}' changed from {pinned} to {current}.")
    return None


def check_graph(docs: Dict[Path, Dict[str, Any]], validated: Set[Path],
                id_prefix: Optional[str] = None) -> List[Dict[str, Any]]:
    """Graph integrity (reqqf#92): relations of the `validated` documents checked against
    the whole corpus `docs` (resolved path → front matter), including pinned source versions
    (reqqf#93). Only validated files get results. Only references in the repository's own
    form (`id_prefix`, reqqf#94) are followed; the rest point to another repository or are
    reported by _check_prefixes()."""
    index: Dict[str, List[Path]] = {}
    for path, fm in docs.items():
        if fm.get("id"):
            index.setdefault(str(fm["id"]), []).append(path)
    out: List[Dict[str, Any]] = []
    for path in sorted(validated & docs.keys()):
        fm = docs[path]
        rid = str(fm.get("id", ""))
        others = [C._file_ref(p) for p in index.get(rid, []) if p != path]
        if others:
            out.append(C._rec(path, "error", "graph.duplicate-id", "id",
                            f"ID '{rid}' is also used in: {', '.join(others)}.",
                            C.HINTS["graph.duplicate-id"]))
        source = str(fm.get("status", ""))
        for ptr, target, pinned in _relations(fm):
            if C._prefix(target) != id_prefix:
                continue
            if target not in index:
                out.append(C._rec(path, "error", "graph.dangling", ptr,
                                f"'{target}' does not match any requirement ID.",
                                C.HINTS["graph.dangling"]))
                continue
            for target_path in index[target]:
                status = str(docs[target_path].get("status", ""))
                rule = _status_rule(source, status)
                if rule:
                    out.append(C._rec(path, "warning", rule, ptr,
                                    f"'{source}' document points to '{target}' with status '{status}'.",
                                    C.HINTS[rule]))
                found = pinned and _version_rule(rid, target, pinned, docs[target_path].get("version"))
                if found:
                    severity, rule, message = found
                    out.append(C._rec(path, severity, rule, ptr, message, C.HINTS[rule]))
    return out


def run(ctx: C.RunContext) -> List[Dict[str, Any]]:
    """The `graph` check: results for the files of the run, against the whole corpus."""
    return check_graph(ctx.docs, {f.resolve() for f in ctx.files}, ctx.cfg.get("id_prefix"))
