# -*- coding: utf-8 -*-
"""Folder layout rules enabled by `enforce_layout`."""
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import reqq_common as C  # noqa: E402


_TYPE_DIRS = {"BR": "business", "FR": "functional", "NFR": "nonfunctional",
              "ADR": "adrs", "TC": "testcases", "POL": "policies"}


def _layout_entries(docs: Dict[Path, Dict[str, Any]]) -> Dict[Path, Tuple[Dict[str, Any], str, str]]:
    """path → (front matter, type, ID category) of documents under requirements/ whose ID is
    well-formed and whose `type` equals the type segment of the ID."""
    out: Dict[Path, Tuple[Dict[str, Any], str, str]] = {}
    for path, fm in docs.items():
        rid = str(fm.get("id", ""))
        if not re.fullmatch(C.ID_PATTERN, rid) or not C._file_ref(path).startswith("requirements/"):
            continue
        rtype, category = C._id_segments(rid)
        if str(fm.get("type", "")) == rtype:
            out[path] = (fm, rtype, category)
    return out


def _nfr_folder(path: Path) -> Optional[str]:
    """Quality folder of requirements/nonfunctional/<folder>/<file>; None for any other depth."""
    parts = C._file_ref(path).split("/")
    return parts[2] if len(parts) == 4 and parts[:2] == ["requirements", "nonfunctional"] else None


def _check_location(path: Path, fm: Dict[str, Any], rtype: str, category: str) -> List[Dict[str, Any]]:
    """Folder and `category` rules for one document (reqqf#102)."""
    out: List[Dict[str, Any]] = []
    declared = fm.get("category")
    expected_category = category
    if rtype == "NFR":
        folder = _nfr_folder(path)
        expected_category = folder or declared or "<category>"
        expected_dir = f"requirements/nonfunctional/{expected_category}"
        misplaced = folder is None
    else:
        expected_dir = f"requirements/{_TYPE_DIRS[rtype]}" + (f"/{category}" if rtype == "FR" else "")
        misplaced = C._file_ref(path) != f"{expected_dir}/{path.name}"
    if misplaced:
        out.append(C._rec(path, "error", "layout.path", "$",
                        f"File is in the wrong folder: expected {expected_dir}/{path.name}.",
                        C.HINTS["layout.path"]))
    if rtype in ("FR", "POL", "NFR") and declared and str(declared) != expected_category:
        out.append(C._rec(path, "error", "layout.category", "category",
                        f"`category: {declared}` does not match the ID or folder: "
                        f"expected `category: {expected_category}`.",
                        C.HINTS["layout.category"]))
    return out


def _nfr_code_conflicts(entries: Dict[Path, Tuple[Dict[str, Any], str, str]]) -> Dict[Path, str]:
    """path → message for each NFR whose quality folder has several ID codes or whose ID
    code is in several folders. Compares the whole corpus."""
    placed = {p: (C._id_segments(str(fm["id"]))[1], _nfr_folder(p))
              for p, (fm, rtype, _) in entries.items() if rtype == "NFR" and _nfr_folder(p)}
    codes: Dict[str, Set[str]] = {}
    folders: Dict[str, Set[str]] = {}
    for code, folder in placed.values():
        codes.setdefault(folder, set()).add(code)
        folders.setdefault(code, set()).add(folder)
    return {p: ("expected one code per folder and one folder per code: "
                f"folder '{folder}' has {', '.join(sorted(codes[folder]))}; "
                f"code '{code}' is in {', '.join(sorted(folders[code]))}")
            for p, (code, folder) in placed.items()
            if len(codes[folder]) > 1 or len(folders[code]) > 1}


def check_layout(docs: Dict[Path, Dict[str, Any]], validated: Set[Path]) -> List[Dict[str, Any]]:
    """Folder and `category` consistency with ID and `type` (reqqf#102), enabled by
    `enforce_layout`. Only `validated` documents get results; documents with a broken ID,
    a `type` that differs from the ID or a path outside requirements/ are left to other rules."""
    entries = _layout_entries(docs)
    conflicts = _nfr_code_conflicts(entries)
    out: List[Dict[str, Any]] = []
    for path in sorted(validated & entries.keys()):
        fm, rtype, category = entries[path]
        out.extend(_check_location(path, fm, rtype, category))
        if path in conflicts:
            out.append(C._rec(path, "error", "layout.nfr-code", "id", conflicts[path],
                            C.HINTS["layout.nfr-code"]))
    return out


def run(ctx: C.RunContext) -> List[Dict[str, Any]]:
    """The `layout` check: results for the files of the run, only with `enforce_layout`."""
    if not ctx.cfg.get("enforce_layout", False):
        return []
    return check_layout(ctx.docs, {f.resolve() for f in ctx.files})
