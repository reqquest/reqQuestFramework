#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regression test for the K1 trap documented in ADR-GOV-001.

Two claims are pinned here:

  1. A map-form roles.yaml parses IDENTICALLY (same tree, same leaf values)
     through PyYAML and through the starter-kit stdlib parser
     `_parse_simple_yaml`, and validates against roles.schema.json under
     BOTH parses.

  2. A list-form roles.yaml is a silent-data-loss trap: `_parse_simple_yaml`
     drops the nested fields of a `- key: value` list entry without raising.
     The schema then rejects the shape under both parsers — the failure is
     loud only because the map form is mandated.

Runs with plain `python3 tests/test_roles_parsing.py`
(asserts + non-zero exit on failure) and is also pytest-discoverable.

Requires PyYAML and jsonschema. These are dev-only: this file lives in the
framework's own `tests/` — deliberately OUTSIDE `.reqq/` — so it is never
copied into an adopter repo (only `requirements/`, `.reqq/` and `.reqqignore`
are). The shipped validator stays strictly stdlib-only; this test exists
precisely to prove the stdlib parser agrees with the real one on the shape
we ship.
"""
import json
import sys
from pathlib import Path

import yaml  # PyYAML — the reference parser
from jsonschema import Draft7Validator

_ROOT = Path(__file__).resolve().parents[1]
_VALIDATOR_DIR = _ROOT / ".reqq" / "validator"
_SCHEMA_DIR = _ROOT / ".reqq" / "schema"
sys.path.insert(0, str(_VALIDATOR_DIR))

from reqq_validate_stdlib import _parse_simple_yaml  # noqa: E402

SCHEMA = json.loads((_SCHEMA_DIR / "roles.schema.json").read_text(encoding="utf-8"))
EXAMPLES = [
    _SCHEMA_DIR / "examples" / "roles.flat.example.yaml",
    _SCHEMA_DIR / "examples" / "roles.by-role.example.yaml",
]

# List form — the trap. Kept inline so the failure mode is visible in the test.
LIST_FORM_YAML = (
    "roles:\n"
    "  - id: role-product-owner\n"
    "    title: Product Owner\n"
    '    handle: "@po"\n'
    '    responsible_for: ["business"]\n'
)


def _normalize(node):
    """
    Canonical, parser-agnostic view of a parsed tree.

    `_parse_simple_yaml` returns every scalar as a string (it only special-cases
    true/false), so 'identical' means: same containers, same keys, same list
    order, and leaf scalars equal AS STRINGS. That is the property that matters
    for roles.yaml — role ids, handles and paths must survive the parse, not be
    silently dropped.
    """
    if isinstance(node, dict):
        return {k: _normalize(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_normalize(v) for v in node]
    if isinstance(node, bool):
        return str(node).lower()
    return str(node)


def _schema_errors(doc):
    return sorted(Draft7Validator(SCHEMA).iter_errors(doc), key=lambda e: e.path)


# --- Claim 1: map form parses identically and validates under both parsers ---

def test_map_form_parses_identically_and_validates():
    for path in EXAMPLES:
        text = path.read_text(encoding="utf-8")
        ref = yaml.safe_load(text)
        std = _parse_simple_yaml(text)

        assert _normalize(std) == _normalize(ref), (
            f"{path.name}: stdlib parser diverged from PyYAML\n"
            f"  PyYAML : {_normalize(ref)}\n"
            f"  stdlib : {_normalize(std)}"
        )

        # Both parses must satisfy the schema. min_approvals is the one field
        # where the parsers differ by TYPE (int vs '2') — the schema's
        # anyOf(integer, string) is what keeps both green.
        assert not _schema_errors(ref), f"{path.name}: PyYAML parse fails schema"
        assert not _schema_errors(std), f"{path.name}: stdlib parse fails schema"

        # Sanity: the nested fields actually made it through.
        for rid, role in std["roles"].items():
            assert role.get("title"), f"{path.name}:{rid} lost 'title'"
            assert role.get("handle"), f"{path.name}:{rid} lost 'handle'"
            assert role.get("responsible_for"), f"{path.name}:{rid} lost 'responsible_for'"


# --- Claim 2: list form is a silent-data-loss trap ---

def test_list_form_is_a_silent_data_loss_trap():
    ref = yaml.safe_load(LIST_FORM_YAML)
    std = _parse_simple_yaml(LIST_FORM_YAML)

    # PyYAML keeps the data: roles is a list of full mappings.
    assert isinstance(ref["roles"], list)
    assert ref["roles"][0]["title"] == "Product Owner"
    assert ref["roles"][0]["handle"] == "@po"

    # The stdlib parser silently collapses each entry to its first line —
    # title / handle / responsible_for are gone, with no error raised.
    assert std["roles"] == ["id: role-product-owner"], (
        f"expected silent collapse to a single string, got: {std['roles']!r}"
    )

    # The schema rejects the shape under BOTH parsers (roles must be an object).
    # This is the whole point of mandating the map form: without the schema and
    # the mandate, the stdlib path above loses data with zero signal.
    assert _schema_errors(ref), "list form unexpectedly passed schema (PyYAML)"
    assert _schema_errors(std), "list form unexpectedly passed schema (stdlib)"


def _main() -> int:
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}\n     {e}")
    if failed:
        print(f"\n{failed} test(s) failed")
        return 1
    print("\nall roles-parsing regression tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
