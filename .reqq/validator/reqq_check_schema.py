# -*- coding: utf-8 -*-
"""JSON Schema checks: front matter against `requirement.schema.json` (warnings) and the role
catalog against `roles.schema.json`. Schemas are read from `.reqq/schema` under `C.ROOT`;
the `$ref`s of the requirement schema resolve to `types/*.schema.json`. A schema that is
missing, unreadable, not a valid draft-07 schema or with a reference that does not resolve
ends the run with exit 3, also when the run has no file to check."""
import json
import re
from pathlib import Path
from typing import Any, Dict, List

import reqq_common as C  # noqa: E402

MISSING = ("{} is not installed. Install the validator dependencies with: "
           "python3 -m pip install -r .reqq/validator/requirements.txt "
           "(on a system Python, in an active virtual environment)")
REQUIREMENT_SCHEMA = "requirement.schema.json"
ROLES_SCHEMA = "roles.schema.json"

try:
    from referencing import Registry, Resource
    from referencing.exceptions import Unresolvable
    from referencing.jsonschema import DRAFT7
except ImportError:
    C._die(3, MISSING.format("referencing"))
try:
    import jsonschema
except ImportError:
    C._die(3, MISSING.format("jsonschema"))


def _schema_dir() -> Path:
    return C.ROOT / ".reqq" / "schema"


def _read(path: Path) -> Any:
    """JSON of the schema file `path`; exit 3 when it cannot be read or is not a valid draft-07 schema."""
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        C._die(3, f"Cannot read the schema {C._file_ref(path)}: {e}")
    try:
        jsonschema.Draft7Validator.check_schema(schema)
    except jsonschema.SchemaError as e:
        C._die(3, f"The schema {C._file_ref(path)} is not a valid draft-07 JSON Schema: {e.message}")
    return schema


def _errors(validator: jsonschema.Draft7Validator, doc: Any, path: Path) -> List[jsonschema.ValidationError]:
    """The errors of `doc` against the schema read from `path`; exit 3 when the schema refers
    to something that is not there."""
    try:
        return list(validator.iter_errors(doc))
    except Unresolvable as e:
        C._die(3, f"The schema {C._file_ref(path)} has a reference that cannot be resolved: {e}")


def _check_refs(resolver, resource: Resource, path: Path) -> None:
    """Exit 3, naming the schema file `path`, when a `$ref` of `resource` or of a schema below
    it does not resolve. The walk is the validator's: `Resource.subresources` visits the schema
    positions of draft-07, so a `$ref` inside `examples` or `const` is data and a property named
    `$ref` holds a schema, and `in_subresource` makes a nested `$id` the base of what is in it."""
    resolver = resolver.in_subresource(resource)
    if isinstance(resource.contents, dict) and "$ref" in resource.contents:
        try:
            resolver.lookup(resource.contents["$ref"])
        except Unresolvable as e:
            C._die(3, f"The schema {C._file_ref(path)} has a reference that cannot be resolved: {e}")
    for sub in resource.subresources():
        _check_refs(resolver, sub, path)


def front_matter_validator() -> jsonschema.Draft7Validator:
    """Validator of requirement.schema.json. Its relative `$ref`s have no `$id` to resolve
    against, so each type schema is registered under its `types/<name>` path. Every `$ref` of
    the requirement schema and of each type schema is then looked up in that registry, against
    the schema it is in, so that a reference that does not resolve exits 3 here, whatever the
    files of the run are, and not when a document first reaches it."""
    folder = _schema_dir()
    paths = {f"types/{p.name}": p for p in sorted((folder / "types").glob("*.schema.json"))}
    types = {uri: Resource.from_contents(_read(p), default_specification=DRAFT7) for uri, p in paths.items()}
    registry = Registry().with_resources(types.items())
    path = folder / REQUIREMENT_SCHEMA
    schema = _read(path)
    root = Resource.from_contents(schema, default_specification=DRAFT7)
    _check_refs(registry.resolver_with_root(root), root, path)
    for uri, resource in types.items():
        _check_refs(registry.resolver(uri), resource, paths[uri])
    return jsonschema.Draft7Validator(schema, registry=registry)


def _field(ptr: str) -> str:
    """First segment of a result's `ptr`: `conflict/0`, `conflict[0].with` and `conflict` are all `conflict`."""
    return re.split(r"[/\[.]", ptr, maxsplit=1)[0]


def _ptr(error: jsonschema.ValidationError) -> str:
    """Path of the field `error` is about, joined by `/`; `$` for the document itself. A missing
    property has no path of its own, so its name, which the message starts with, is added."""
    path = [str(part) for part in error.absolute_path]
    if error.validator == "required":
        path += [name for name in error.validator_value if error.message.startswith(repr(name))]
    return "/".join(path) or "$"


def schema_warnings(validator: jsonschema.Draft7Validator, f: Path, fm: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One `schema.contract` warning per gap between the front matter `fm` of `f` and
    requirement.schema.json, which `validator` was built from (REQQF-FR-VALIDATION-100 story 7)."""
    out: List[Dict[str, Any]] = []
    for error in _errors(validator, fm, _schema_dir() / REQUIREMENT_SCHEMA):
        ptr = _ptr(error)
        out.append(C._rec(f, "warning", "schema.contract", ptr, error.message,
                          C.HINTS.get(_field(ptr), C.HINTS["schema.contract"])))
    return out


def run(ctx: C.RunContext) -> List[Dict[str, Any]]:
    """The `schema` check: the gaps of the readable front matter of every file of the run. The
    schemas are read once, before the files, so a broken one ends the run with exit 3 even when
    there is no file to check. The entry point leaves out the gaps another selected check
    reports (`without_reported`)."""
    validator = front_matter_validator()
    return [w for f in ctx.files if (fm := ctx.docs.get(f.resolve())) for w in schema_warnings(validator, f, fm)]


def _violation(ptr: str) -> str:
    """What `ptr` is about: its field. `id` and `type` are one violation, as the ID names the
    type and the type schemas pin the ID to it (reported on `type` by the hard rule, on `id` by the schema)."""
    field = _field(ptr)
    return "id" if field == "type" else field


def without_reported(warnings: List[Dict[str, Any]], results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """`warnings` without those for a violation the same file already has a result for in
    `results`, an error or a warning of any rule (REQQF-FR-VALIDATION-100 story 7)."""
    reported = {(r["file"], _violation(r["ptr"])) for r in results}
    return [w for w in warnings if (w["file"], _violation(w["ptr"])) not in reported]


def _where(path) -> str:
    """Location in a document as `['roles']['role-x']`; keys come from the file, so they are
    shown with `repr`, which keeps a control character visible. `$` is the document itself."""
    return "".join(f"[{part!r}]" for part in path) or "$"


def validate_catalog(doc: Any) -> List[str]:
    """One message per gap between the role catalog `doc` and roles.schema.json, except the
    format of a handle: it depends on the host and is rule V4 of reqq_owners.py. A handle of the
    wrong shape (not a string, an empty or repeating list) is still a gap. Every `$ref` of the
    schema is looked up first (`_check_refs`), so one that does not resolve exits 3 even in a
    branch no catalog reaches."""
    path = _schema_dir() / ROLES_SCHEMA
    schema = _read(path)
    handle = schema.get("definitions", {}).get("handle") if isinstance(schema, dict) else None
    if not isinstance(handle, dict):
        C._die(3, f"The schema {C._file_ref(path)} has no `definitions.handle`, "
                  "which the shape of a handle is read from")
    handle.pop("pattern", None)
    root = Resource.from_contents(schema, default_specification=DRAFT7)
    _check_refs(Registry().resolver_with_root(root), root, path)
    return [f"{_where(error.absolute_path)}: {error.message}"
            for error in _errors(jsonschema.Draft7Validator(schema), doc, path)]
