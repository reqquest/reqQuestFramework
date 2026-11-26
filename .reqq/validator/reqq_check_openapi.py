# -*- coding: utf-8 -*-
"""The `openapi` check: OpenAPI fragments embedded in requirements (REQQF-FR-MODEL-100 story 9,
REQQF-FR-VALIDATION-100 story 8).

A fragment is a fenced code block whose info string is `yaml openapi id=<ID>.<name>`. Each one
is checked on its own: valid YAML, root keys, its ID, and the official OpenAPI schema of the
version from `openapi.version` in config.yaml, read from `.reqq/schema/openapi` without network
access. `$ref`s are data here: resolving them across files is out of scope. The severity of every
result is `openapi.level`; `off` disables the check."""
import functools
import json
import re
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

import reqq_common as C  # noqa: E402
import reqq_config as CF  # noqa: E402
import reqq_yaml as Y  # noqa: E402
import reqq_check_schema  # noqa: E402,F401  exits 3 when jsonschema or referencing is missing
import jsonschema  # noqa: E402
from jsonschema.exceptions import best_match  # noqa: E402
from referencing import Registry, Resource  # noqa: E402

FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
ROOT_KEYS = ("paths", "components")
NAME_PATTERN = r"[a-z0-9]+(-[a-z0-9]+)*"
SCHEMAS = {  # version → (schema file, the `openapi` value of the wrapping document)
    "3.0": ("oas-3.0.json", "3.0.4"),
    "3.1": ("oas-3.1-base.json", "3.1.2"),
    "3.2": ("oas-3.2-base.json", "3.2.0"),
}


class Block(NamedTuple):
    """A fragment: the line of its opening fence, its ID (None without `id=`) and its text."""
    line: int
    fid: Optional[str]
    text: str


def _closes(line: str, fence: str) -> bool:
    """Whether `line` closes a block opened with `fence`."""
    return re.fullmatch(rf" {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}\s*", line) is not None


def blocks(text: str) -> List[Block]:
    """The fragments of a Markdown document: fenced blocks whose info string starts with
    `yaml openapi`. A block without a closing fence runs to the end of the document."""
    lines = text.splitlines()
    out: List[Block] = []
    i = 0
    while i < len(lines):
        m = FENCE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        end = i + 1
        while end < len(lines) and not _closes(lines[end], m.group(1)):
            end += 1
        words = m.group(2).split()
        if words[:2] == ["yaml", "openapi"]:
            ids = [w[3:] for w in words[2:] if w.startswith("id=")]
            out.append(Block(i + 1, ids[0] if ids else None, "\n".join(lines[i + 1:end])))
        i = end + 1
    return out


@functools.lru_cache(maxsize=None)
def _validator(version: str) -> Any:
    """The validator of the official OpenAPI schema of `version`; every schema of the folder is
    registered by its `$id`, so references resolve locally."""
    folder = C.ROOT / ".reqq" / "schema" / "openapi"
    schemas = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.json"))]
    registry = Registry().with_resources(
        (s["$id"], Resource.from_contents(s)) for s in schemas if "$id" in s)
    schema = json.loads((folder / SCHEMAS[version][0]).read_text(encoding="utf-8"))
    return jsonschema.validators.validator_for(schema)(schema, registry=registry)


def schema_error(fragment: Dict[str, Any], version: str) -> Optional[str]:
    """The most relevant violation of the OpenAPI schema by `fragment`, with its path, or None.
    The fragment is wrapped in the smallest document the schema accepts."""
    doc = {"openapi": SCHEMAS[version][1], "info": {"title": "fragment", "version": "0"},
           "paths": {}, **fragment}
    error = best_match(_validator(version).iter_errors(doc))
    if error is None:
        return None
    where = "/".join(str(part) for part in error.absolute_path) or "(root)"
    return f"{where}: {error.message}"


def _id_problem(fid: Optional[str], doc_id: str, seen: List[Optional[str]]) -> Optional[str]:
    """Why the fragment ID `fid` is wrong in the requirement `doc_id`, or None."""
    if fid is None:
        return f"the block has no `id={doc_id}.<name>`"
    if not re.fullmatch(re.escape(doc_id) + r"\." + NAME_PATTERN, fid):
        return f"fragment ID '{fid}' is not '{doc_id}.<name>' (lowercase letters, digits, hyphens)"
    if fid in seen:
        return f"fragment ID '{fid}' is used by another block of this file"
    return None


def _block_problems(block: Block, version: str) -> List[Tuple[str, str, int]]:
    """(kind, message, line of the file) of the YAML, root and schema rules for one block: the
    line of a YAML syntax error when the parser marks one, else the line of the fence."""
    try:
        fragment = Y.load_typed(block.text)
    except Y.YamlError as e:
        return [("openapi.yaml", f"not valid YAML: {e}, counted from the line after the fence",
                 block.line + e.line if e.line else block.line)]
    repeated = [f"{path}.{key}" if path else key for path, key in Y.duplicate_keys(block.text)]
    if repeated:
        return [("openapi.yaml", f"key written twice, the loader keeps the last: {', '.join(repeated)}",
                 block.line)]
    extra = sorted(set(fragment) - set(ROOT_KEYS))
    if extra:
        return [("openapi.root", f"root keys allowed: {', '.join(ROOT_KEYS)}; found: {', '.join(extra)}",
                 block.line)]
    problem = schema_error(fragment, version)
    return [("openapi.schema", f"OpenAPI {version}: {problem}", block.line)] if problem else []


def check_file(path: Path, doc_id: Optional[str], version: str, severity: str) -> List[Dict[str, Any]]:
    """The results for the fragments of one file. Without a valid `id` the ID rule is left to
    the front matter checks; a file that cannot be read is left to them as well."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []
    out: List[Dict[str, Any]] = []
    seen: List[Optional[str]] = []
    for block in blocks(text):
        ptr = f"line {block.line}"
        problems = _block_problems(block, version)
        id_problem = _id_problem(block.fid, doc_id, seen) if doc_id else None
        if id_problem:
            problems.insert(0, ("openapi.id", id_problem, block.line))
        seen.append(block.fid)
        out += [C._rec(path, severity, kind, ptr, message, C.HINTS[kind], line)
                for kind, message, line in problems]
    return out


def run(ctx: C.RunContext) -> List[Dict[str, Any]]:
    """The `openapi` check: results for the files of the run, unless `openapi.level` is off."""
    settings = CF.openapi_settings(ctx.cfg)
    if settings["level"] == "off":
        return []
    out: List[Dict[str, Any]] = []
    for f in ctx.files:
        doc_id = str(ctx.docs.get(f.resolve(), {}).get("id", ""))
        valid_id = doc_id if re.fullmatch(C.ID_PATTERN, doc_id) else None
        out += check_file(f, valid_id, settings["version"], settings["level"])
    return out
