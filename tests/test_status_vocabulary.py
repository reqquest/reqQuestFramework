#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regression tests for the requirement `status` vocabulary (reqQuestFramework#16).

`approved` is canonical; `accepted` is a deprecated alias that still validates but produces a
warning and does NOT change the exit code; anything else outside the enum is an error.

No external dependencies. Runs with:
  python3 tests/test_status_vocabulary.py
"""
import contextlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_VALIDATOR = _ROOT / ".reqq" / "validator" / "reqq_validate_stdlib.py"
sys.path.insert(0, str(_VALIDATOR.parent))

import reqq_validate_stdlib as V


def _doc(status: str) -> str:
    return (
        "---\n"
        "id: FR-TST-001\n"
        "title: Status vocabulary fixture requirement\n"
        "type: FR\n"
        f"status: {status}\n"
        "owner: tester\n"
        "last_updated: \"2026-09-20\"\n"
        "category: TST\n"
        "traces_to: [BR-TST-001]\n"
        "---\n\n# FR-TST-001\n"
    )


@contextlib.contextmanager
def repo_with(status: str):
    """A throwaway (non-git) repo holding one requirement; ROOT falls back to cwd."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        f = root / "requirements" / "functional" / "FR-TST-001.md"
        f.parent.mkdir(parents=True)
        f.write_text(_doc(status), encoding="utf-8")
        saved = V.ROOT
        V.ROOT = root
        try:
            yield root, f
        finally:
            V.ROOT = saved


def _records(status: str):
    with repo_with(status) as (_root, f):
        return V.validate_doc(f, require_full_traceability=False)


def _cli(status: str, *extra: str):
    with repo_with(status) as (root, _f):
        p = subprocess.run([sys.executable, str(_VALIDATOR), "--all", *extra],
                           cwd=root, capture_output=True, text=True)
        return p.returncode, p.stdout


def test_approved_is_valid_and_silent():
    assert _records("approved") == [], _records("approved")


def test_other_canonical_values_still_valid():
    for status in ("draft", "review", "deprecated"):
        assert _records(status) == [], (status, _records(status))


def test_accepted_alias_warns_and_names_the_canonical_value():
    recs = _records("accepted")
    assert len(recs) == 1, recs
    r = recs[0]
    assert r["severity"] == "warning" and r["ptr"] == "status", r
    assert "approved" in r["message"] and "approved" in r["hint"], r


def test_unknown_status_is_an_error_listing_approved_not_accepted():
    recs = _records("implemented")
    assert len(recs) == 1 and recs[0]["severity"] == "error", recs
    assert "approved" in recs[0]["message"] and "accepted" not in recs[0]["message"], recs[0]


def test_alias_does_not_change_exit_code_plain():
    code, out = _cli("accepted")
    assert code == 0, (code, out)
    assert "errors: 0, warnings: 1" in out and "deprecated alias" in out, out


def test_alias_does_not_change_ok_in_json():
    code, out = _cli("accepted", "--format", "json")
    payload = json.loads(out)
    assert code == 0 and payload["ok"] is True, payload
    assert payload["errors"] == [] and len(payload["warnings"]) == 1, payload


def test_error_still_fails_the_run():
    code, out = _cli("implemented", "--format", "json")
    payload = json.loads(out)
    assert code == 2 and payload["ok"] is False and len(payload["errors"]) == 1, (code, payload)


def test_clean_run_output_is_unchanged_when_there_are_no_warnings():
    code, out = _cli("approved")
    assert code == 0 and "errors: 0\n" in out and "warnings" not in out, out


def test_schema_enum_matches_validator_vocabulary():
    schema = json.loads((_ROOT / ".reqq" / "schema" / "requirement.schema.json").read_text(encoding="utf-8"))
    enum = set(schema["properties"]["status"]["enum"])
    assert enum == V.STATUS_ENUM | set(V.STATUS_ALIASES), (enum, V.STATUS_ENUM, V.STATUS_ALIASES)
    assert V.STATUS_ENUM == {"draft", "review", "approved", "deprecated"}
    assert V.STATUS_ALIASES == {"accepted": "approved"}


def test_conflict_resolution_enum_is_untouched():
    schema = json.loads((_ROOT / ".reqq" / "schema" / "requirement.schema.json").read_text(encoding="utf-8"))
    res = schema["properties"]["conflict"]["items"]["properties"]["resolution"]["enum"]
    assert res == ["accepted", "rejected", "superseded"], res


def main() -> int:
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except Exception as exc:  # noqa: BLE001 - report every failing test
                failed += 1
                print(f"FAIL {name}: {exc!r}")
    print(f"\n{'FAILED' if failed else 'passed'}: {failed} failing")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
