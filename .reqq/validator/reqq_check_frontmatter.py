# -*- coding: utf-8 -*-
"""Per-file front matter rules: required fields, ID, type, status, references, conflicts."""
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import reqq_yaml as Y  # noqa: E402
import reqq_common as C  # noqa: E402
import reqq_check_graph as GR  # noqa: E402


def _check_conflict(f: Path, fm: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Structure of `conflict[]` and its lifecycle gate (reqqf#97, mirrors the schema's if/then):
    every entry needs a non-empty `with`; a `resolution` must be from the enum; an
    `approved` requirement cannot carry an entry without `resolution`.
    """
    if "conflict" not in fm:
        return []
    entries = fm["conflict"]
    if not isinstance(entries, list):
        return [C._rec(f, "error", "schema", "conflict", "`conflict` must be a list of entries.",
                     C.HINTS["conflict"])]
    status = str(fm.get("status", ""))
    approved = status == "approved"
    out: List[Dict[str, Any]] = []
    for n, entry in enumerate(entries):
        ptr = f"conflict[{n}]"
        if not isinstance(entry, dict):
            out.append(C._rec(f, "error", "schema", ptr, "A `conflict` entry must be an object.",
                            C.HINTS["conflict"]))
            continue
        target = entry.get("with")
        if not (isinstance(target, str) and target):
            out.append(C._rec(f, "error", "schema", f"{ptr}.with",
                            "'with' is a required non-empty property", C.HINTS["conflict"]))
        elif not re.fullmatch(C.ID_PATTERN, target):
            out.append(C._rec(f, "error", "schema", f"{ptr}.with",
                            f"'{target}' does not match pattern '{C.ID_PATTERN}'", C.HINTS["conflict"]))
        if "resolution" not in entry:
            if approved:
                out.append(C._rec(f, "error", "schema", f"{ptr}.resolution",
                                f"Unresolved conflict with '{target}' blocks status '{status}'.",
                                C.HINTS["conflict_gate"]))
        elif not (isinstance(entry["resolution"], str) and entry["resolution"] in C.CONFLICT_RESOLUTIONS):
            out.append(C._rec(f, "error", "schema", f"{ptr}.resolution",
                            f"'{entry['resolution']}' is not valid. "
                            f"Allowed: {', '.join(sorted(C.CONFLICT_RESOLUTIONS))}", C.HINTS["conflict"]))
    return out


def _check_refs(f: Path, fm: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    `traces_to` and, for a TC, `derives_from`: a list of IDs, each optionally pinned to a
    version (`ID@major.minor`), unique by ID (mirrors requirement.schema.json and
    types/TC.schema.json). The schema limits `derives_from` to FR/NFR; another ID type is
    only a warning, so adopters that derive tests from ADRs keep a green CI. Empty values
    are left to the required-field checks.
    """
    out: List[Dict[str, Any]] = []
    for field in C._ref_fields(fm):
        value = fm.get(field)
        if not value:
            continue
        if not isinstance(value, list):
            out.append(C._rec(f, "error", "schema", field, f"`{field}` must be a list of IDs.",
                            C.HINTS[field]))
            continue
        items = [str(t) for t in value]
        for n, item in enumerate(items):
            if not re.fullmatch(C.REF_PATTERN, item):
                out.append(C._rec(f, "error", "schema", f"{field}[{n}]",
                                f"'{item}' does not match pattern '{C.REF_PATTERN}'", C.HINTS[field]))
            elif field == "derives_from" and not re.fullmatch(C.DERIVES_FROM_PATTERN, item):
                out.append(C._rec(f, "warning", "schema", f"{field}[{n}]",
                                f"'{item}' is not an FR/NFR; a TC should derive from requirements.",
                                C.HINTS[field]))
        ids = [C._split_ref(t)[0] for t in items]
        for rid in sorted({t for t in ids if ids.count(t) > 1}):
            out.append(C._rec(f, "error", "schema", field, f"'{rid}' is listed more than once.",
                            C.HINTS[field]))
    return out


def _check_prefixes(f: Path, fm: Dict[str, Any], id_prefix: Optional[str]) -> List[Dict[str, Any]]:
    """One ID form per repository (reqqf#94). With `id_prefix` the document's own ID carries
    exactly that prefix and every reference carries one; another prefix points to another
    repository. Without it, no ID or reference has a prefix."""
    out: List[Dict[str, Any]] = []
    rid = str(fm.get("id", ""))
    if re.fullmatch(C.ID_PATTERN, rid) and C._prefix(rid) != id_prefix:
        if id_prefix:
            out.append(C._rec(f, "error", "id-prefix", "id",
                            f"ID '{rid}' must start with the repository prefix '{id_prefix}-'.",
                            C.HINTS["id-prefix"]))
        else:
            out.append(C._rec(f, "error", "id-prefix", "id",
                            f"ID '{rid}' has a prefix, but config.yaml sets no `id_prefix`.",
                            C.HINTS["id-prefix.unset"]))
    for ptr, target, _ in GR._relations(fm):
        if id_prefix and not C._prefix(target):
            out.append(C._rec(f, "error", "id-prefix", ptr,
                            f"'{target}' has no repository prefix; `id_prefix: {id_prefix}` requires one.",
                            C.HINTS["id-prefix.ref"]))
        elif not id_prefix and C._prefix(target):
            out.append(C._rec(f, "error", "id-prefix", ptr,
                            f"'{target}' has a prefix, but config.yaml sets no `id_prefix`.",
                            C.HINTS["id-prefix.unset"]))
    return out


def _check_filename(f: Path, fm: Dict[str, Any], rid: str, short_title: bool) -> List[Dict[str, Any]]:
    """The file name is `<id>.md`, or `<id>-<short_title>.md` with `short_title: true` in
    config.yaml (reqqf#134). Without the flag the field is not checked."""
    expected = rid
    if short_title:
        st = fm.get("short_title")
        if not st:
            return [C._rec(f, "error", "schema", "short_title",
                         "'short_title' is required: config.yaml sets `short_title: true`",
                         C.HINTS["short_title"])]
        if not re.fullmatch(C.SHORT_TITLE_PATTERN, str(st)):
            return [C._rec(f, "error", "schema", "short_title",
                         f"'{st}' does not match pattern '{C.SHORT_TITLE_PATTERN}'",
                         C.HINTS["short_title"])]
        expected = f"{rid}-{st}"
    if f.stem != expected:
        return [C._rec(f, "error", "schema", "id",
                     f"File name '{f.name}' does not match '{expected}.md'", C.HINTS["filename"])]
    return []


def _check_duplicate_keys(f: Path, text: str) -> List[Dict[str, Any]]:
    """One error per key written twice in a mapping of the front matter: the loader keeps the
    last value, so the first would vanish silently, e.g. a `conflict` list or a `status`."""
    return [C._rec(f, "error", "frontmatter", f"{path}.{key}" if path else key,
                   f"key {key!r} appears more than once" + (f" in {path!r}" if path else ""),
                   C.HINTS["yaml.duplicate-key"])
            for path, key in C.front_matter_duplicates(text)]


def validate_doc(f: Path, require_full_traceability: bool,
                 id_prefix: Optional[str] = None, short_title: bool = False) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        text = f.read_text(encoding="utf-8")
    except Exception as e:
        out.append(C._rec(f, "error", "io", "$", f"Cannot read file: {e}", C.HINTS["io"]))
        return out

    try:
        fm, _ = C.load_yaml_front_matter(text)
    except Y.YamlError as e:
        out.append(C._rec(f, "error", "frontmatter", "$", f"Invalid YAML in the front matter: {e}",
                          C.HINTS["yaml"], e.line))
        return out
    if not fm:
        out.append(C._rec(f, "error", "frontmatter", "$", "Missing YAML front matter.", "Add `---` block."))
        return out
    out.extend(_check_duplicate_keys(f, text))

    # Required fields
    for field in C.REQUIRED_FIELDS:
        if field not in fm or fm[field] == "" or fm[field] is None:
            out.append(C._rec(f, "error", "schema", field,
                            f"'{field}' is a required property", C.HINTS[field]))

    # ID pattern + filename consistency
    rid = fm.get("id", "")
    if rid:
        if not re.fullmatch(C.ID_PATTERN, str(rid)):
            out.append(C._rec(f, "error", "schema", "id",
                            f"'{rid}' does not match pattern '{C.ID_PATTERN}'", C.HINTS["id"]))
        else:
            out.extend(_check_filename(f, fm, str(rid), short_title))
    if "legacy_id" in fm and not re.fullmatch(C.LEGACY_ID_PATTERN, str(fm["legacy_id"])):
        out.append(C._rec(f, "error", "schema", "legacy_id",
                        f"'{fm['legacy_id']}' does not match pattern '{C.LEGACY_ID_PATTERN}'",
                        C.HINTS["legacy_id"]))

    # Type enum
    rtype = fm.get("type", "")
    if rtype and str(rtype) not in C.TYPE_ENUM:
        out.append(C._rec(f, "error", "schema", "type",
                        f"'{rtype}' is not valid. Allowed: {', '.join(sorted(C.TYPE_ENUM))}",
                        C.HINTS["type"]))
    elif rtype and re.fullmatch(C.ID_PATTERN, str(fm.get("id", ""))):
        expected = C._id_segments(str(fm["id"]))[0]
        if expected != str(rtype):
            out.append(C._rec(f, "error", "schema", "type",
                            f"ID '{fm['id']}' does not match `type: {rtype}`: expected `type: {expected}`.",
                            C.HINTS["id-type"]))

    # Status enum
    status = fm.get("status", "")
    if status and str(status) not in C.STATUS_ENUM:
        out.append(C._rec(f, "error", "schema", "status",
                        f"'{status}' is not valid. Allowed: {', '.join(sorted(C.STATUS_ENUM))}",
                        C.HINTS["status"]))

    out.extend(_check_conflict(f, fm))
    out.extend(_check_refs(f, fm))
    out.extend(_check_prefixes(f, fm, id_prefix))

    # Type-specific required fields (mirrors .reqq/schema/types/*.schema.json)
    if rtype in ("FR", "NFR", "POL") and not fm.get("category"):
        out.append(C._rec(f, "error", "schema", "category",
                        f"'{rtype}' requires `category`.", C.HINTS["category"]))
    if rtype == "ADR" and not (fm.get("decisions") or []):
        out.append(C._rec(f, "error", "schema", "decisions",
                        "`ADR` requires a non-empty `decisions` list.", C.HINTS["decisions"]))
    if rtype == "TC" and not (fm.get("derives_from") or []):
        out.append(C._rec(f, "error", "schema", "derives_from",
                        "`TC` requires `derives_from`.", C.HINTS["derives_from"]))

    # Traceability (generic — traces_to, see section 4 of
    # https://github.com/reqquest/reqQuestFramework/blob/main/docs/framework/conventions.md)
    if require_full_traceability and rtype in ("FR", "NFR") and not (fm.get("traces_to") or []):
        out.append(C._rec(f, "error", "traceability", "traces_to",
                        f"`{rtype}` should have `traces_to` → BR/ADR.", C.HINTS["traces_to"]))

    return out


def run(ctx: C.RunContext) -> List[Dict[str, Any]]:
    """The `frontmatter` check: `validate_doc` on every file of the run."""
    return [r for f in ctx.files
            for r in validate_doc(f, ctx.cfg.get("require_full_traceability", True),
                                  ctx.cfg.get("id_prefix"), ctx.cfg.get("short_title", False))]
