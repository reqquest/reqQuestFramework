#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regression tests for toolkit versioning (ADR-TOOLKIT-001).

Tests cover: SemVer parsing/ordering, release-tag selection per channel, adopt determinism
and override validation, the per-file upgrade states of D6, conflict-marker labelling,
dry-run fidelity, and the min_toolkit_version guard of D7.

No external dependencies (no PyYAML, jsonschema, requests). Runs with:
  python3 tests/test_toolkit_versioning.py

Fixture: temporary directories with mocked .reqq state; no network calls.
"""
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_VALIDATOR_DIR = _ROOT / ".reqq" / "validator"
sys.path.insert(0, str(_VALIDATOR_DIR))

import io
import tarfile

import reqq_validate_stdlib as V
from reqq_validate_stdlib import (
    ToolkitError, _semver_tuple, _semver_lt, _normalize_version, _toolkit_boundary_files,
    _sha256_file, _compute_upgrade_plan, _apply_upgrade_plan, _latest_release_tag,
    _parse_sha256sums, _extract_tar_safely, _find_payload_root,
    cmd_adopt, cmd_upgrade, load_toolkit_lock,
)


# --- Fixtures ----------------------------------------------------------------

@contextlib.contextmanager
def temp_repo_root(root: Path):
    """Point the module's ROOT/TOOLKIT_LOCK globals at a throwaway tree."""
    saved_root, saved_lock = V.ROOT, V.TOOLKIT_LOCK
    V.ROOT = root
    V.TOOLKIT_LOCK = root / ".reqq" / "toolkit.lock"
    try:
        yield V.TOOLKIT_LOCK
    finally:
        V.ROOT, V.TOOLKIT_LOCK = saved_root, saved_lock


@contextlib.contextmanager
def stub_github(payload):
    """Replace the GitHub API call with a canned payload."""
    saved = V._github_api_get
    V._github_api_get = lambda endpoint: payload
    try:
        yield
    finally:
        V._github_api_get = saved


def _tri_fixture():
    """Create (base_dir, new_dir, working) under one temp root."""
    d = Path(tempfile.mkdtemp())
    base, new, work = d / "v1", d / "v2", d / "working"
    for p in (base, new, work):
        p.mkdir()
    return base, new, work


def _lock_for(base_dir: Path, names, overrides=None):
    return {
        "toolkit_version": "1.0.0",
        "files": {n: _sha256_file(base_dir / n) for n in names},
        "local_overrides": list(overrides or []),
    }


# --- SemVer ------------------------------------------------------------------

def test_semver_parsing():
    """Verify SemVer tuple parsing."""
    assert _semver_tuple("toolkit-v1.2.3") == (1, 2, 3, None)
    assert _semver_tuple("v1.0.0") == (1, 0, 0, None)
    assert _semver_tuple("1.10.5-rc.1") == (1, 10, 5, "rc.1")
    assert _semver_tuple("toolkit-v2.0.0-next.5") == (2, 0, 0, "next.5")


def test_normalize_version_strips_only_a_leading_v():
    """`lstrip("vV")` would eat leading characters from the version itself."""
    assert _normalize_version("toolkit-v1.2.3") == "1.2.3"
    assert _normalize_version("v1.2.3") == "1.2.3"
    assert _normalize_version("1.2.3") == "1.2.3"


def test_semver_comparison():
    """Verify SemVer less-than ordering."""
    assert _semver_lt("1.0.0", "1.0.1")
    assert _semver_lt("1.0.0", "1.1.0")
    assert _semver_lt("1.9.9", "2.0.0")
    assert not _semver_lt("1.0.0", "1.0.0")
    assert not _semver_lt("2.0.0", "1.9.9")

    # Prerelease vs release
    assert _semver_lt("1.0.0-rc.1", "1.0.0")
    assert _semver_lt("1.0.0-rc.1", "1.0.0-rc.2")
    assert not _semver_lt("1.0.0", "1.0.0-rc.1")


def test_semver_prerelease_identifiers_compare_numerically():
    """SemVer §11.4: rc.2 < rc.10. String comparison gets this backwards."""
    assert _semver_lt("1.0.0-rc.2", "1.0.0-rc.10")
    assert not _semver_lt("1.0.0-rc.10", "1.0.0-rc.2")
    # Numeric identifiers rank below alphanumeric ones
    assert _semver_lt("1.0.0-1", "1.0.0-alpha")
    # A longer identifier set wins when all preceding fields are equal
    assert _semver_lt("1.0.0-rc.1", "1.0.0-rc.1.1")


# --- Release tag selection ---------------------------------------------------

def test_latest_release_tag_ignores_foreign_tag_prefixes():
    """A `docs-v*` release must never be mistaken for the toolkit version (D1-decision)."""
    releases = [
        {"tag_name": "docs-v9.9.9", "prerelease": False},
        {"tag_name": "toolkit-v1.2.0", "prerelease": False},
        {"tag_name": "toolkit-v1.1.0", "prerelease": False},
    ]
    with stub_github(releases):
        assert _latest_release_tag("https://github.com/o/r", "stable") == "toolkit-v1.2.0"


def test_latest_release_tag_channel_semantics():
    """stable skips prereleases; next accepts them. Newest wins, not list order."""
    releases = [
        {"tag_name": "toolkit-v1.1.0", "prerelease": False},
        {"tag_name": "toolkit-v2.0.0-rc.1", "prerelease": True},
        {"tag_name": "toolkit-v1.2.0", "prerelease": False},
    ]
    with stub_github(releases):
        assert _latest_release_tag("https://github.com/o/r", "stable") == "toolkit-v1.2.0"
        assert _latest_release_tag("https://github.com/o/r", "next") == "toolkit-v2.0.0-rc.1"


def test_latest_release_tag_walks_past_a_full_page_of_foreign_releases():
    """/releases is paginated at 30 by default; a run of docs-v* releases must not hide the
    toolkit tag on a later page."""
    pages = {
        1: [{"tag_name": f"docs-v1.0.{i}", "prerelease": False}
            for i in range(V.GITHUB_RELEASES_PER_PAGE)],
        2: [{"tag_name": "toolkit-v1.3.0", "prerelease": False}],
    }
    seen = []

    def fake_get(endpoint):
        page = int(endpoint.split("page=")[-1])
        seen.append(page)
        return pages.get(page, [])

    saved = V._github_api_get
    V._github_api_get = fake_get
    try:
        assert _latest_release_tag("https://github.com/o/r", "stable") == "toolkit-v1.3.0"
    finally:
        V._github_api_get = saved
    assert seen == [1, 2], f"expected the walk to stop on the short page, visited {seen}"


def test_latest_release_tag_without_toolkit_releases_raises():
    """No toolkit release must be a clear error, not a bogus version."""
    with stub_github([{"tag_name": "docs-v1.0.0", "prerelease": False}]):
        try:
            _latest_release_tag("https://github.com/o/r", "stable")
        except ToolkitError:
            return
    raise AssertionError("expected ToolkitError when no toolkit-v* release exists")


# --- Adopt -------------------------------------------------------------------

def _make_adoptable_repo() -> Path:
    root = Path(tempfile.mkdtemp())
    (root / ".reqq" / "schema").mkdir(parents=True)
    (root / ".reqq" / "validator").mkdir(parents=True)
    (root / ".reqq" / "schema" / "requirement.schema.json").write_text('{"type":"object"}')
    (root / ".reqq" / "validator" / "reqq_validate_stdlib.py").write_text("# validator\n")
    (root / ".reqq" / "validator" / "config.yaml").write_text("require_full_traceability: true\n")
    return root


def test_adopt_is_deterministic_apart_from_installed_at():
    """Two consecutive adopt runs must produce an identical lock except `installed_at`."""
    root = _make_adoptable_repo()
    with temp_repo_root(root) as lock_path:
        assert cmd_adopt(["--version", "1.0.0"]) == 0
        first = json.loads(lock_path.read_text())
        assert cmd_adopt(["--version", "1.0.0"]) == 0
        second = json.loads(lock_path.read_text())

    assert first.pop("installed_at") and second.pop("installed_at")
    assert first == second, f"lock is not deterministic:\n{first}\nvs\n{second}"
    # config.yaml is explicitly outside the boundary (D1) and must not be hashed
    assert ".reqq/validator/config.yaml" not in first["files"]
    assert ".reqq/schema/requirement.schema.json" in first["files"]


def test_adopt_rejects_local_override_outside_the_boundary():
    """A typo'd override would silently do nothing until the first real upgrade."""
    root = _make_adoptable_repo()
    with temp_repo_root(root) as lock_path:
        cmd_adopt(["--version", "1.0.0",
                   "--local-override", ".reqq/validator/config.yaml",  # outside boundary
                   "--local-override", ".reqq/schema/requirement.schema.json"])
        lock = json.loads(lock_path.read_text())
    assert lock["local_overrides"] == [".reqq/schema/requirement.schema.json"]


def test_local_override_accepts_a_path_relative_to_the_working_directory():
    """`--local-override README.md` from requirements/ must mean requirements/README.md.

    Treating a relative path as ROOT-relative regardless of cwd rejects the override with a
    warning, and the file is then silently overwritten on the first real upgrade.
    """
    root = _make_adoptable_repo()
    (root / "requirements").mkdir()
    (root / "requirements" / "README.md").write_text("# Requirements\n")

    cwd = os.getcwd()
    try:
        os.chdir(root / "requirements")
        with temp_repo_root(root) as lock_path:
            cmd_adopt(["--version", "1.0.0", "--local-override", "README.md"])
            lock = json.loads(lock_path.read_text())
    finally:
        os.chdir(cwd)

    assert lock["local_overrides"] == ["requirements/README.md"], lock["local_overrides"]


def test_toolkit_lock_is_excluded_from_its_own_boundary():
    root = _make_adoptable_repo()
    with temp_repo_root(root) as lock_path:
        cmd_adopt(["--version", "1.0.0"])
        assert lock_path not in _toolkit_boundary_files()
        assert ".reqq/toolkit.lock" not in json.loads(lock_path.read_text())["files"]


# --- State 1: unchanged file replaced ----------------------------------------

def test_state1_unchanged_file_replaced():
    """State 1: file unchanged locally → replaced with new version."""
    base, new, work = _tri_fixture()
    (base / "test.txt").write_text("old")
    (work / "test.txt").write_text("old")
    (new / "test.txt").write_text("new")

    plan = _compute_upgrade_plan(_lock_for(base, ["test.txt"]), base, new, work)
    assert [a["action"] for a in plan] == ["REPLACE"]
    _apply_upgrade_plan(plan, work, dry_run=False)
    assert (work / "test.txt").read_text() == "new"


def test_state1_falls_back_to_content_when_lock_has_no_entry():
    """A boundary widened after adopt must not read as 'locally modified'."""
    base, new, work = _tri_fixture()
    (base / "test.txt").write_text("old")
    (work / "test.txt").write_text("old")
    (new / "test.txt").write_text("new")

    lock = {"toolkit_version": "1.0.0", "files": {}, "local_overrides": []}
    plan = _compute_upgrade_plan(lock, base, new, work)
    assert [a["action"] for a in plan] == ["REPLACE"]


# --- State 2: local override, 3-way merge ------------------------------------

def test_state2_local_override_three_way_merge_clean():
    """State 2: local and upstream touch different regions → clean merge, no markers."""
    base, new, work = _tri_fixture()
    (base / "config.txt").write_text("line1\nline2\nline3\nline4\nline5\n")
    (work / "config.txt").write_text("line1_local\nline2\nline3\nline4\nline5\n")
    (new / "config.txt").write_text("line1\nline2\nline3\nline4\nline5_new\n")

    lock = _lock_for(base, ["config.txt"], overrides=["config.txt"])
    plan = _compute_upgrade_plan(lock, base, new, work)
    assert [a["action"] for a in plan] == ["MERGE"]

    result = _apply_upgrade_plan(plan, work, dry_run=False)
    merged = (work / "config.txt").read_text()
    assert "line1_local" in merged and "line5_new" in merged
    assert "<<<<<<<" not in merged, f"expected a clean merge, got:\n{merged}"
    assert result["conflicts"] == 0 and result["merged"] == 1


def test_state2_local_override_conflict():
    """State 2 with overlapping edits → conflict markers and a conflict count."""
    base, new, work = _tri_fixture()
    (base / "conflict.txt").write_text("common line\n")
    (work / "conflict.txt").write_text("common line - LOCAL\n")
    (new / "conflict.txt").write_text("common line - NEW\n")

    lock = _lock_for(base, ["conflict.txt"], overrides=["conflict.txt"])
    plan = _compute_upgrade_plan(lock, base, new, work)
    result = _apply_upgrade_plan(plan, work, dry_run=False)

    assert "<<<<<<<" in (work / "conflict.txt").read_text()
    assert result["conflicts"] == 1


def test_conflict_markers_label_local_and_upstream_correctly():
    """`git merge-file` maps -L onto (current, base, other) = (local, vA, vB).

    Swapping the labels signs the adopter's own change as the framework's version.
    """
    base, new, work = _tri_fixture()
    (base / "c.txt").write_text("common\n")
    (work / "c.txt").write_text("LOCAL EDIT\n")
    (new / "c.txt").write_text("UPSTREAM EDIT\n")

    lock = _lock_for(base, ["c.txt"], overrides=["c.txt"])
    _apply_upgrade_plan(_compute_upgrade_plan(lock, base, new, work), work, dry_run=False)
    merged = (work / "c.txt").read_text()

    lines = [l.rstrip("\n") for l in merged.splitlines()]
    assert lines[0] == "<<<<<<< local", f"local side mislabelled:\n{merged}"
    assert lines[1] == "LOCAL EDIT", f"local content is not under the local label:\n{merged}"
    assert "||||||| vA" in lines, f"base side mislabelled:\n{merged}"
    assert lines[lines.index("=======") + 1] == "UPSTREAM EDIT"
    assert lines[-1] == ">>>>>>> vB"


# --- State 3: overwritten without override -----------------------------------

def test_state3_overwritten_without_override():
    """State 3: changed locally but not declared → replaced, and reported as overwritten."""
    base, new, work = _tri_fixture()
    (base / "script.py").write_text("print('v1')")
    (work / "script.py").write_text("print('LOCAL CHANGE')")
    (new / "script.py").write_text("print('v2')")

    plan = _compute_upgrade_plan(_lock_for(base, ["script.py"]), base, new, work)
    result = _apply_upgrade_plan(plan, work, dry_run=False)

    assert (work / "script.py").read_text() == "print('v2')"
    assert result["overwritten_changes"] == 1


# --- State 4: added / collided / restored ------------------------------------

def test_state4_new_file_added():
    """State 4: file exists in v2 but not in v1 or working."""
    base, new, work = _tri_fixture()
    (new / "new_feature.md").write_text("# New Feature\nContent here.")

    lock = {"toolkit_version": "1.0.0", "files": {}, "local_overrides": []}
    plan = _compute_upgrade_plan(lock, base, new, work)
    result = _apply_upgrade_plan(plan, work, dry_run=False)

    assert (work / "new_feature.md").read_text() == "# New Feature\nContent here."
    assert result["added"] == 1


def test_state4_collision_keeps_local_and_reports():
    """A path new in vB that the adopter already occupies must not vanish silently.

    `local_overrides` could not have covered a path absent from vA, so the file is kept and
    the collision is reported rather than either side being clobbered.
    """
    base, new, work = _tri_fixture()
    (new / "newfile.txt").write_text("from v2")
    (work / "newfile.txt").write_text("adopter's own file")

    lock = {"toolkit_version": "1.0.0", "files": {}, "local_overrides": []}
    plan = _compute_upgrade_plan(lock, base, new, work)
    assert [a["action"] for a in plan] == ["ADD_COLLISION"], f"got {plan}"

    result = _apply_upgrade_plan(plan, work, dry_run=False)
    assert (work / "newfile.txt").read_text() == "adopter's own file"
    assert result["collisions"] == 1


def test_state4_collision_with_identical_content_is_a_no_op():
    base, new, work = _tri_fixture()
    (new / "same.txt").write_text("identical")
    (work / "same.txt").write_text("identical")

    lock = {"toolkit_version": "1.0.0", "files": {}, "local_overrides": []}
    assert _compute_upgrade_plan(lock, base, new, work) == []


def test_locally_deleted_toolkit_file_is_restored():
    """Present in vA and vB, deleted by the adopter → restored, and flagged as such."""
    base, new, work = _tri_fixture()
    (base / "hook.sh").write_text("v1")
    (new / "hook.sh").write_text("v2")

    plan = _compute_upgrade_plan(_lock_for(base, ["hook.sh"]), base, new, work)
    assert [a["action"] for a in plan] == ["ADD"]
    result = _apply_upgrade_plan(plan, work, dry_run=False)

    assert (work / "hook.sh").read_text() == "v2"
    assert result["restored"] == 1


# --- State 5: removal --------------------------------------------------------

def test_state5_file_removed():
    """State 5: existed in v1, dropped in v2, untouched locally → removed."""
    base, new, work = _tri_fixture()
    (base / "deprecated.txt").write_text("old file")
    (work / "deprecated.txt").write_text("old file")

    plan = _compute_upgrade_plan(_lock_for(base, ["deprecated.txt"]), base, new, work)
    result = _apply_upgrade_plan(plan, work, dry_run=False)

    assert not (work / "deprecated.txt").exists()
    assert result["removed"] == 1


def test_state5_locally_modified_file_is_not_deleted():
    """Deleting a customised file is unrecoverable — keep it and report instead."""
    base, new, work = _tri_fixture()
    (base / "gone.txt").write_text("orig\n")
    (work / "gone.txt").write_text("HEAVILY CUSTOMISED\n")

    lock = _lock_for(base, ["gone.txt"], overrides=["gone.txt"])
    plan = _compute_upgrade_plan(lock, base, new, work)
    assert [a["action"] for a in plan] == ["REMOVE_KEPT"], f"got {plan}"

    result = _apply_upgrade_plan(plan, work, dry_run=False)
    assert (work / "gone.txt").read_text() == "HEAVILY CUSTOMISED\n"
    assert result["removal_blocked"] == 1


# --- State 6: toolkit.lock ---------------------------------------------------

def test_state6_lock_is_planned_for_regeneration_not_merged():
    """The lock must never be merged or replaced from the payload — it is regenerated."""
    base, new, work = _tri_fixture()
    for d, v in ((base, "1.0.0"), (work, "1.0.0"), (new, "2.0.0")):
        (d / ".reqq").mkdir(parents=True, exist_ok=True)
        (d / ".reqq" / "toolkit.lock").write_text(json.dumps({"toolkit_version": v}))

    plan = _compute_upgrade_plan(_lock_for(base, [".reqq/toolkit.lock"]), base, new, work)
    assert [a["action"] for a in plan] == ["REGENERATE"]

    _apply_upgrade_plan(plan, work, dry_run=False)
    kept = json.loads((work / ".reqq" / "toolkit.lock").read_text())
    assert kept["toolkit_version"] == "1.0.0"


def test_a_file_merely_named_toolkit_lock_is_upgraded_normally():
    """Only the boundary lock is regenerated. Matching on the bare filename would skip
    upgrade handling for any file called toolkit.lock anywhere in the tree."""
    base, new, work = _tri_fixture()
    for d in (base, new, work):
        (d / "requirements" / "00-context").mkdir(parents=True, exist_ok=True)
    stray = Path("requirements") / "00-context" / "toolkit.lock"
    (base / stray).write_text("v1")
    (work / stray).write_text("v1")
    (new / stray).write_text("v2")

    plan = _compute_upgrade_plan(_lock_for(base, [stray.as_posix()]), base, new, work)
    assert [a["action"] for a in plan] == ["REPLACE"], f"got {plan}"
    _apply_upgrade_plan(plan, work, dry_run=False)
    assert (work / stray).read_text() == "v2"


def test_lock_round_trips_deterministically():
    """write → load must be stable and byte-identical for equal input (D3: JSON, deterministic)."""
    root = Path(tempfile.mkdtemp())
    with temp_repo_root(root) as lock_path:
        data = {"toolkit_version": "1.4.0", "files": {"b": "sha256:2", "a": "sha256:1"},
                "local_overrides": ["x"], "channel": "stable"}
        V.write_toolkit_lock(data)
        first = lock_path.read_bytes()
        assert load_toolkit_lock() == data
        V.write_toolkit_lock(json.loads(first.decode()))
        assert lock_path.read_bytes() == first


# --- Dry run -----------------------------------------------------------------

def test_dry_run_reports_conflicts_and_touches_nothing():
    """Previewing conflicts is the whole point of --dry-run."""
    base, new, work = _tri_fixture()
    (base / "c.txt").write_text("common\n")
    (work / "c.txt").write_text("LOCAL\n")
    (new / "c.txt").write_text("UPSTREAM\n")
    (base / "plain.txt").write_text("a")
    (work / "plain.txt").write_text("a")
    (new / "plain.txt").write_text("b")

    lock = _lock_for(base, ["c.txt", "plain.txt"], overrides=["c.txt"])
    plan = _compute_upgrade_plan(lock, base, new, work)

    dry = _apply_upgrade_plan(plan, work, dry_run=True)
    assert dry["conflicts"] == 1, f"dry run must predict conflicts, got {dry}"
    assert (work / "c.txt").read_text() == "LOCAL\n", "dry run modified the working tree"
    assert (work / "plain.txt").read_text() == "a", "dry run modified the working tree"

    wet = _apply_upgrade_plan(plan, work, dry_run=False)
    assert wet["conflicts"] == dry["conflicts"]
    assert wet["replaced"] == dry["replaced"]


# --- min_toolkit_version (D7) ------------------------------------------------

def _write_schema(root: Path, min_version=None):
    (root / ".reqq" / "schema").mkdir(parents=True, exist_ok=True)
    doc = {"type": "object"}
    if min_version:
        doc["min_toolkit_version"] = min_version
    (root / ".reqq" / "schema" / "requirement.schema.json").write_text(json.dumps(doc))


def test_min_toolkit_version_absent_is_not_a_constraint():
    root = Path(tempfile.mkdtemp())
    _write_schema(root)
    with temp_repo_root(root):
        V.enforce_min_toolkit_version()  # must not raise or exit


def test_min_toolkit_version_blocks_an_older_toolkit():
    root = Path(tempfile.mkdtemp())
    _write_schema(root, "1.5.0")
    with temp_repo_root(root) as lock_path:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(json.dumps({"toolkit_version": "1.4.0"}))
        try:
            V.enforce_min_toolkit_version()
        except SystemExit as e:
            assert e.code == 3, f"expected exit 3 (config error), got {e.code}"
            return
    raise AssertionError("expected SystemExit(3) for a toolkit below min_toolkit_version")


def test_min_toolkit_version_accepts_a_newer_toolkit():
    root = Path(tempfile.mkdtemp())
    _write_schema(root, "1.5.0")
    with temp_repo_root(root) as lock_path:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(json.dumps({"toolkit_version": "1.6.0"}))
        V.enforce_min_toolkit_version()  # must not raise or exit


# --- Shipped config ----------------------------------------------------------

def test_shipped_config_toolkit_block_parses_to_valid_values():
    """The stdlib YAML parser keeps inline `#` as part of the value.

    `update_channel: stable  # stable | next` silently yields "stable  # stable | next",
    which then never matches the channel comparison. Guard the config we ship.
    """
    tk = V.load_config().get("toolkit")
    assert tk, "config.yaml must carry a toolkit: block (ADR-TOOLKIT-001 D5)"
    assert tk.get("update_channel") in ("stable", "next"), tk
    assert tk.get("update_check") in ("manual", "ci-notify", "ci-pr"), tk


def test_toolkit_lock_is_declared_in_reqqignore():
    """D3: the lock is excluded explicitly, not by relying on one validator's scan scope."""
    patterns = (_ROOT / ".reqqignore").read_text(encoding="utf-8").splitlines()
    assert ".reqq/toolkit.lock" in [p.strip() for p in patterns]
    assert ".reqq/toolkit.lock" in V.load_config().get("exclude_globs", [])


# --- Full integration --------------------------------------------------------

def test_all_states_in_sequence():
    """One realistic upgrade exercising every state at once."""
    base, new, work = _tri_fixture()

    # State 1: unchanged
    (base / "default.conf").write_text("[default]\nkey=value\n")
    (work / "default.conf").write_text("[default]\nkey=value\n")
    (new / "default.conf").write_text("[default]\nkey=value_v2\n")

    # State 2: declared override, non-overlapping edits → clean merge
    (base / "custom.conf").write_text("# Base\nsetting1=A\nsetting2=B\nsetting3=C\nsetting4=D\n")
    (work / "custom.conf").write_text("# Base\nsetting1=A_LOCAL\nsetting2=B\nsetting3=C\nsetting4=D\n")
    (new / "custom.conf").write_text("# Base\nsetting1=A\nsetting2=B\nsetting3=C\nsetting4=D_NEW\n")

    # State 3: undeclared local change → overwritten with a warning
    (base / "schema.json").write_text('{"type": "object"}')
    (work / "schema.json").write_text('{"type": "object", "custom": true}')
    (new / "schema.json").write_text('{"type": "object", "version": 2}')

    # State 4: new upstream file
    (new / "workflow.yml").write_text("name: CI\n")

    # State 4 collision: new upstream file the adopter already has
    (new / "notes.md").write_text("upstream notes\n")
    (work / "notes.md").write_text("my notes\n")

    # State 5: dropped upstream, untouched locally
    (base / "deprecated.txt").write_text("old")
    (work / "deprecated.txt").write_text("old")

    # State 5 blocked: dropped upstream, customised locally
    (base / "tuned.cfg").write_text("stock\n")
    (work / "tuned.cfg").write_text("tuned by hand\n")

    lock = _lock_for(base, ["default.conf", "custom.conf", "schema.json",
                            "deprecated.txt", "tuned.cfg"],
                     overrides=["custom.conf", "tuned.cfg"])

    plan = _compute_upgrade_plan(lock, base, new, work)
    result = _apply_upgrade_plan(plan, work, dry_run=False)

    assert (work / "default.conf").read_text() == "[default]\nkey=value_v2\n"

    merged = (work / "custom.conf").read_text()
    assert "A_LOCAL" in merged and "D_NEW" in merged
    assert "<<<<<<<" not in merged, f"expected a clean merge, got:\n{merged}"

    assert (work / "schema.json").read_text() == '{"type": "object", "version": 2}'
    assert (work / "workflow.yml").exists()
    assert (work / "notes.md").read_text() == "my notes\n"
    assert not (work / "deprecated.txt").exists()
    assert (work / "tuned.cfg").read_text() == "tuned by hand\n"

    assert result["replaced"] == 1
    assert result["merged"] == 1 and result["conflicts"] == 0
    assert result["overwritten_changes"] == 1
    assert result["added"] == 1
    assert result["collisions"] == 1
    assert result["removed"] == 1
    assert result["removal_blocked"] == 1


# --- upgrade: download + verify + unpack -----------------------------------

def _tar_gz(files: dict) -> bytes:
    """Build an in-memory .tar.gz from {relpath: text}."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(name=rel)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _release(tag: str, asset_name: str, blob: bytes, *, prerelease=False, body_extra=""):
    """A GitHub release dict whose body carries the SHA256SUMS line for `asset_name`."""
    import hashlib as _h
    digest = _h.sha256(blob).hexdigest()
    return {
        "tag_name": tag,
        "prerelease": prerelease,
        "body": f"## {tag}\n{body_extra}\n\n```\n{digest}  {asset_name}\n```\n",
        "assets": [{"name": asset_name,
                    "browser_download_url": f"https://cdn.example/{tag}/{asset_name}"}],
    }


@contextlib.contextmanager
def stub_release_channel(releases: list, blobs: dict):
    """Route _github_api_get by endpoint and serve asset bytes from `blobs` (keyed by URL)."""
    saved_api, saved_dl = V._github_api_get, V._http_get_bytes

    def fake_api(endpoint: str):
        if "/releases/tags/" in endpoint:
            want = endpoint.rsplit("/", 1)[-1]
            for r in releases:
                if r["tag_name"] == want:
                    return r
            raise ToolkitError(f"GitHub API 404: Not Found ({want})")
        if "/releases?" in endpoint or endpoint.endswith("/releases"):
            page = int(endpoint.split("page=")[-1]) if "page=" in endpoint else 1
            return releases if page == 1 else []
        raise AssertionError(f"unexpected endpoint {endpoint}")

    V._github_api_get = fake_api
    V._http_get_bytes = lambda url: blobs[url]
    try:
        yield
    finally:
        V._github_api_get, V._http_get_bytes = saved_api, saved_dl


def _adopted_repo(files: dict, version="1.0.0", overrides=None) -> Path:
    """A working tree carrying `files` (relpath: text) plus a matching toolkit.lock."""
    root = Path(tempfile.mkdtemp())
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    with temp_repo_root(root):
        lock = {
            "toolkit_version": version,
            "source": "https://github.com/o/r",
            "channel": "stable",
            "installed_by": "manual",
            "files": {rel: _sha256_file(root / rel) for rel in files},
            "local_overrides": list(overrides or []),
        }
        (root / ".reqq").mkdir(parents=True, exist_ok=True)
        V.write_toolkit_lock(lock)
    return root


def test_parse_sha256sums_reads_lines_out_of_prose_and_fences():
    body = ("Release notes.\n\n```\n"
            + "a" * 64 + "  raac-toolkit-1.1.0.tar.gz\n"
            + "b" * 64 + " *other.txt\n```\nthanks!\n")
    sums = _parse_sha256sums(body)
    assert sums["raac-toolkit-1.1.0.tar.gz"] == "a" * 64
    assert sums["other.txt"] == "b" * 64


def test_extract_tar_safely_rejects_path_traversal():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = b"pwned"
        info = tarfile.TarInfo(name="../escape.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    dest = Path(tempfile.mkdtemp()) / "unpack"
    try:
        _extract_tar_safely(buf.getvalue(), dest)
    except ToolkitError:
        assert not (dest.parent / "escape.txt").exists()
        return
    raise AssertionError("expected ToolkitError for a member escaping the destination")


def test_find_payload_root_descends_a_single_wrapper_dir():
    d = Path(tempfile.mkdtemp())
    (d / "reqQuestFramework-1.0.0" / ".reqq").mkdir(parents=True)
    assert _find_payload_root(d) == d / "reqQuestFramework-1.0.0"


ASSET_A = "raac-toolkit-1.0.0.tar.gz"
ASSET_B = "raac-toolkit-1.1.0.tar.gz"


def test_upgrade_state1_replaces_and_regenerates_lock():
    """Clean upgrade: an untouched boundary file is replaced and the lock is rewritten."""
    root = _adopted_repo({
        ".reqq/schema/requirement.schema.json": '{"type":"object","v":1}',
        ".reqq/validator/reqq_validate_stdlib.py": "# validator v1\n",
    })
    a_blob = _tar_gz({
        ".reqq/schema/requirement.schema.json": '{"type":"object","v":1}',
        ".reqq/validator/reqq_validate_stdlib.py": "# validator v1\n",
    })
    b_blob = _tar_gz({
        ".reqq/schema/requirement.schema.json": '{"type":"object","v":2}',
        ".reqq/validator/reqq_validate_stdlib.py": "# validator v2\n",
    })
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob),
                _release("toolkit-v1.0.0", ASSET_A, a_blob)]
    blobs = {f"https://cdn.example/toolkit-v1.0.0/{ASSET_A}": a_blob,
             f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc = cmd_upgrade(["--channel", "stable"])
        lock = load_toolkit_lock()

    assert rc == 0, rc
    assert (root / ".reqq/schema/requirement.schema.json").read_text() == '{"type":"object","v":2}'
    assert lock["toolkit_version"] == "1.1.0"
    assert lock["files"][".reqq/schema/requirement.schema.json"] == \
        _sha256_file(root / ".reqq/schema/requirement.schema.json")


def test_upgrade_dry_run_touches_nothing_and_keeps_lock():
    root = _adopted_repo({
        ".reqq/schema/requirement.schema.json": '{"type":"object","v":1}',
    })
    a_blob = _tar_gz({".reqq/schema/requirement.schema.json": '{"type":"object","v":1}'})
    b_blob = _tar_gz({".reqq/schema/requirement.schema.json": '{"type":"object","v":2}'})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob),
                _release("toolkit-v1.0.0", ASSET_A, a_blob)]
    blobs = {f"https://cdn.example/toolkit-v1.0.0/{ASSET_A}": a_blob,
             f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc = cmd_upgrade(["--channel", "stable", "--dry-run"])
        lock = load_toolkit_lock()

    assert rc == 0
    assert (root / ".reqq/schema/requirement.schema.json").read_text() == '{"type":"object","v":1}'
    assert lock["toolkit_version"] == "1.0.0", "dry-run must not regenerate the lock"


def test_upgrade_conflict_exits_2():
    """A declared override with overlapping edits leaves conflict markers → exit 2."""
    schema = ".reqq/schema/requirement.schema.json"
    root = _adopted_repo({schema: "COMMON\nBASE\n"}, overrides=[schema])
    (root / schema).write_text("COMMON\nLOCAL EDIT\n")  # local drift after adoption
    a_blob = _tar_gz({".reqq/schema/requirement.schema.json": "COMMON\nBASE\n"})
    b_blob = _tar_gz({".reqq/schema/requirement.schema.json": "COMMON\nUPSTREAM EDIT\n"})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob),
                _release("toolkit-v1.0.0", ASSET_A, a_blob)]
    blobs = {f"https://cdn.example/toolkit-v1.0.0/{ASSET_A}": a_blob,
             f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc = cmd_upgrade(["--channel", "stable"])

    assert rc == 2, rc
    assert "<<<<<<<" in (root / ".reqq/schema/requirement.schema.json").read_text()


def test_upgrade_without_lock_exits_3():
    root = Path(tempfile.mkdtemp())
    with temp_repo_root(root):
        assert cmd_upgrade([]) == 3


def test_upgrade_checksum_mismatch_exits_3_and_leaves_tree_untouched():
    root = _adopted_repo({".reqq/schema/requirement.schema.json": '{"v":1}'})
    a_blob = _tar_gz({".reqq/schema/requirement.schema.json": '{"v":1}'})
    b_blob = _tar_gz({".reqq/schema/requirement.schema.json": '{"v":2}'})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob),
                _release("toolkit-v1.0.0", ASSET_A, a_blob)]
    # Serve a corrupted payload for vB while the release body still lists the clean digest.
    blobs = {f"https://cdn.example/toolkit-v1.0.0/{ASSET_A}": a_blob,
             f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob + b"tampered"}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc = cmd_upgrade(["--channel", "stable"])

    assert rc == 3, rc
    assert (root / ".reqq/schema/requirement.schema.json").read_text() == '{"v":1}'


def test_upgrade_when_already_newest_is_a_noop_exit_0():
    root = _adopted_repo({".reqq/schema/requirement.schema.json": '{"v":1}'}, version="1.1.0")
    b_blob = _tar_gz({".reqq/schema/requirement.schema.json": '{"v":1}'})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob)]

    with temp_repo_root(root), stub_release_channel(releases, {}):
        rc = cmd_upgrade(["--channel", "stable"])
        lock = load_toolkit_lock()

    assert rc == 0
    assert lock["toolkit_version"] == "1.1.0"


def test_upgrade_missing_asset_exits_3():
    root = _adopted_repo({".reqq/schema/requirement.schema.json": '{"v":1}'})
    a_blob = _tar_gz({".reqq/schema/requirement.schema.json": '{"v":1}'})
    rel_b = _release("toolkit-v1.1.0", ASSET_B, b"x")
    rel_b["assets"] = []  # release exists but the tarball was never attached
    releases = [rel_b, _release("toolkit-v1.0.0", ASSET_A, a_blob)]
    blobs = {f"https://cdn.example/toolkit-v1.0.0/{ASSET_A}": a_blob}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        assert cmd_upgrade(["--channel", "stable"]) == 3


# --- Adopter install: the tarball must stand on its own ------------------------

def _pack(dest: Path, version: str = "9.9.9") -> Path:
    """Build the release asset from the current tree; return the tarball path."""
    out = dest / "dist"
    proc = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "pack-toolkit.py"),
         "--version", version, "--out", str(out), "--repo-root", str(_ROOT)],
        capture_output=True, text=True)
    assert proc.returncode == 0, f"pack-toolkit.py failed:\n{proc.stdout}\n{proc.stderr}"
    return out / f"raac-toolkit-{version}.tar.gz"


def _install_as_adopter(dest: Path, version: str = "9.9.9") -> Path:
    """Unpack the release asset the way `tar xzf ... --strip-components=1` does — into the
    root of a fresh repo — and return that root."""
    tarball = _pack(dest, version)
    unpacked = dest / "unpacked"
    _extract_tar_safely(tarball.read_bytes(), unpacked)
    payload = _find_payload_root(unpacked)
    repo = dest / "adopter"
    shutil.copytree(payload, repo)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
    return repo


def test_fresh_extract_passes_the_validation_it_ships_with():
    """The first command an adopter runs is `--all`, from the CI workflow in the same
    tarball. Everything that takes to exit 0 has to be inside the boundary — notably
    `.reqqignore`, without which the shipped README / 00-context templates fail."""
    repo = _install_as_adopter(Path(tempfile.mkdtemp()))
    proc = subprocess.run(
        [sys.executable, ".reqq/validator/reqq_validate_stdlib.py", "--all"],
        cwd=repo, capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"a fresh extract fails its own validation (exit {proc.returncode}):\n"
        f"{proc.stdout}\n{proc.stderr}")


def test_fresh_extract_adopts_into_a_non_empty_lock():
    repo = _install_as_adopter(Path(tempfile.mkdtemp()))
    proc = subprocess.run(
        [sys.executable, ".reqq/validator/reqq_validate_stdlib.py", "adopt", "--version", "9.9.9"],
        cwd=repo, capture_output=True, text=True)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    lock = json.loads((repo / ".reqq" / "toolkit.lock").read_text(encoding="utf-8"))
    assert lock["files"], "adopt wrote an empty `files` map"
    assert ".reqqignore" in lock["files"], sorted(lock["files"])


def test_shipped_ci_template_runs_only_on_paths_it_ships():
    """The template executes in the adopter's repo, where nothing outside the boundary
    exists. `tests/` and `scripts/` are framework-only — a step touching them makes the
    adopter's very first CI run red."""
    dest = Path(tempfile.mkdtemp())
    tarball = _pack(dest)
    with tarfile.open(tarball, mode="r:gz") as tar:
        shipped = {m.name.split("/", 1)[1] for m in tar.getmembers()
                   if m.isfile() and "/" in m.name}
    templates = sorted(n for n in shipped if n.startswith(".github/workflows/"))
    assert templates, "the boundary ships no CI workflow template"
    for name in templates:
        body = (_ROOT / name).read_text(encoding="utf-8")
        for foreign in ("tests/", "scripts/"):
            assert foreign not in body, (
                f"{name} is shipped to adopters but references {foreign!r}, "
                f"which is not in the toolkit boundary")


# --- toolkit-manifest.json (D1) --------------------------------------------------

def test_manifest_boundary_matches_validator_fallback():
    """The built-in fallback list must mirror the shipped manifest byte-for-byte —
    a drift means adopters without the manifest hash a different set than the tarball."""
    manifest = json.loads((_ROOT / V.TOOLKIT_MANIFEST_REL).read_text(encoding="utf-8"))
    assert manifest["boundary"] == V._FALLBACK_TOOLKIT_BOUNDARY_GLOBS, (
        "toolkit-manifest.json `boundary` and _FALLBACK_TOOLKIT_BOUNDARY_GLOBS have drifted")
    # The manifest tracks itself, so an upgrade that widens the boundary reaches the adopter.
    assert "toolkit-manifest.json" in manifest["boundary"]


def test_manifest_drives_boundary_and_honours_exclude():
    root = Path(tempfile.mkdtemp())
    (root / ".reqq" / "schema").mkdir(parents=True)
    (root / ".reqq" / "schema" / "requirement.schema.json").write_text("{}")
    (root / ".reqq" / "schema" / "keep.json").write_text("{}")
    (root / ".reqq" / "schema" / "skip.json").write_text("{}")
    (root / "toolkit-manifest.json").write_text(json.dumps({
        "boundary": ["toolkit-manifest.json", ".reqq/schema/*.json"],
        "exclude": [".reqq/schema/skip.json"],
    }))
    with temp_repo_root(root):
        include, exclude = V._toolkit_boundary_globs()
        assert include == ["toolkit-manifest.json", ".reqq/schema/*.json"]
        assert exclude == [".reqq/schema/skip.json"]
        rels = {p.relative_to(root).as_posix() for p in _toolkit_boundary_files()}
    assert ".reqq/schema/keep.json" in rels
    assert ".reqq/schema/requirement.schema.json" in rels
    assert ".reqq/schema/skip.json" not in rels, "exclude glob was not applied"
    assert "toolkit-manifest.json" in rels


def test_malformed_manifest_is_an_error_not_a_silent_fallback():
    root = Path(tempfile.mkdtemp())
    (root / "toolkit-manifest.json").write_text('{"boundary": "not-a-list"}')
    with temp_repo_root(root):
        try:
            V._toolkit_boundary_globs()
        except ToolkitError:
            return
    raise AssertionError("a manifest with a non-list `boundary` must raise ToolkitError")


def test_manifest_ships_the_ignore_file_the_validator_needs():
    """`.reqqignore` carries the exclusions for the templates the boundary itself ships."""
    manifest = json.loads((_ROOT / V.TOOLKIT_MANIFEST_REL).read_text(encoding="utf-8"))
    assert ".reqqignore" in manifest["boundary"]
    assert ".reqq/validator/config.yaml" in manifest["exclude"], (
        "local config must stay out of the tarball (D1)")
    assert ".reqq/validator/config.example.yaml" in manifest["boundary"], (
        "config.yaml is excluded, so the template that replaces it has to ship")


def test_empty_manifest_boundary_is_an_error():
    """A boundary matching nothing hashes nothing — drift detection silently turns off."""
    root = Path(tempfile.mkdtemp())
    (root / "toolkit-manifest.json").write_text('{"boundary": []}')
    with temp_repo_root(root):
        try:
            V._toolkit_boundary_globs()
        except ToolkitError:
            return
    raise AssertionError("an empty `boundary` must raise ToolkitError")


def test_adopt_refuses_to_write_an_empty_lock():
    """Extracting the tarball without --strip-components=1 leaves the toolkit one level
    below ROOT. Recording `"files": {}` there reports success and leaves `check` with
    nothing to compare against, forever."""
    root = Path(tempfile.mkdtemp())
    (root / "nested").mkdir()   # boundary globs match nothing at ROOT
    with temp_repo_root(root):
        # `cmd_adopt` reports this through `_die`, which calls `sys.exit` — so the exit code
        # arrives as a raised SystemExit, not as a return value. The `return 3` that follows
        # each `_die` in the validator is unreachable; assert on the exception, not the
        # return. (`cmd_upgrade` does return its codes, hence the different shape there.)
        try:
            cmd_adopt(["--version", "1.0.0"])
        except SystemExit as e:
            assert e.code == 3, f"expected exit 3, got {e.code}"
            assert not (root / ".reqq" / "toolkit.lock").exists(), "an empty lock was written"
            return
    raise AssertionError("adopt on an empty boundary must exit 3, not write an empty lock")


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
            except Exception as e:
                failed += 1
                print(f"ERROR {name}\n     {type(e).__name__}: {e}")
    if failed:
        print(f"\n{failed} test(s) failed")
        return 1
    print("\nall toolkit versioning tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
