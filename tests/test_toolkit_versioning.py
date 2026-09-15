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
    cmd_adopt, cmd_check, cmd_upgrade, load_toolkit_lock,
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


# --- Check: an available update must never fail CI (reqquest/reqQuestFramework#4) --------

def _make_checked_repo(update_check: str) -> Path:
    """An adopted repo, pinned at v1.0.0, configured with the given `update_check` level."""
    root = _make_adoptable_repo()
    (root / ".reqq" / "validator" / "config.yaml").write_text(
        "require_full_traceability: true\n"
        "toolkit:\n"
        "  update_channel: stable\n"
        f"  update_check: {update_check}\n")
    with temp_repo_root(root):
        assert cmd_adopt(["--version", "1.0.0"]) == 0
    return root


_NEWER_RELEASE = [{"tag_name": "toolkit-v1.1.0", "prerelease": False}]


def test_check_ci_update_available_never_fails_at_ci_notify():
    root = _make_checked_repo("ci-notify")
    with temp_repo_root(root), stub_github(_NEWER_RELEASE):
        assert cmd_check(["--ci"]) == 0


def test_check_ci_update_available_never_fails_at_ci_pr():
    """The regression this issue fixes: `ci-pr` used to signal exit 2 on an available
    update alone, which turned every unrelated push/PR red the day a release shipped."""
    root = _make_checked_repo("ci-pr")
    with temp_repo_root(root), stub_github(_NEWER_RELEASE):
        assert cmd_check(["--ci"]) == 0


def test_check_ci_manual_level_stays_a_no_op_even_with_drift():
    """`manual` means no CI operation at all — not even the drift check runs."""
    root = _make_checked_repo("manual")
    (root / ".reqq" / "schema" / "requirement.schema.json").write_text('{"type":"object","x":1}')
    with temp_repo_root(root):
        assert cmd_check(["--ci"]) == 0


def test_check_drift_fails_identically_with_and_without_ci():
    """Local drift is a fact about the repo — it must gate the pipeline in both modes,
    unlike an available update (reqquest/reqQuestFramework#4, proposal point 3)."""
    for update_check in ("ci-notify", "ci-pr"):
        root = _make_checked_repo(update_check)
        (root / ".reqq" / "schema" / "requirement.schema.json").write_text(
            '{"type":"object","x":1}')
        with temp_repo_root(root), stub_github(_NEWER_RELEASE):
            assert cmd_check([]) == 2, f"plain run did not fail on drift ({update_check})"
        with temp_repo_root(root), stub_github(_NEWER_RELEASE):
            assert cmd_check(["--ci"]) == 2, f"--ci did not fail on drift ({update_check})"


def test_check_ci_no_drift_no_update_is_clean():
    root = _make_checked_repo("ci-pr")
    with temp_repo_root(root), stub_github([{"tag_name": "toolkit-v1.0.0", "prerelease": False}]):
        assert cmd_check(["--ci"]) == 0


# --- Level rename (reqquest/reqQuestFramework#6): off | notify | pr -----------

def _capture_stderr(fn, *args, **kwargs):
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        rc = fn(*args, **kwargs)
    return rc, buf.getvalue()


def test_normalize_update_check_canonical_values_pass_through():
    for level in ("off", "notify", "pr"):
        assert V._normalize_update_check(level) == (level, False)


def test_normalize_update_check_deprecated_aliases_map_and_warn():
    assert V._normalize_update_check("manual") == ("off", True)
    assert V._normalize_update_check("ci-notify") == ("notify", True)
    assert V._normalize_update_check("ci-pr") == ("pr", True)


def test_normalize_update_check_unknown_value_falls_back_to_off_with_warning():
    """A typo must never silently escalate to a level that mutates GitHub."""
    assert V._normalize_update_check("cii-notify") == ("off", True)


def test_check_plain_warns_once_on_deprecated_level_and_behaves_like_its_alias():
    root = _make_checked_repo("ci-notify")
    with temp_repo_root(root), stub_github(_NEWER_RELEASE):
        rc, err = _capture_stderr(cmd_check, [])
    assert rc == 0
    assert err.count("deprecated") == 1
    assert "notify" in err and "ci-notify" in err


def test_check_ci_warns_once_on_deprecated_level_via_annotation():
    root = _make_checked_repo("manual")
    with temp_repo_root(root):
        rc, out = _capture_stdout(cmd_check, ["--ci"])
    assert rc == 0
    assert out.count("::warning::") == 1
    assert "deprecated" in out and "off" in out


def test_check_format_json_reports_update_available():
    root = _make_checked_repo("notify")
    with temp_repo_root(root), stub_github(_NEWER_RELEASE):
        rc, out = _capture_stdout(cmd_check, ["--format", "json"])
    assert rc == 0
    doc = json.loads(out)
    assert doc["command"] == "check"
    assert doc["toolkit_version"] == "1.0.0"
    assert doc["latest_version"] == "1.1.0"
    assert doc["has_update"] is True
    assert doc["has_drift"] is False
    assert doc["update_check"] == "notify"
    assert doc["host"] == "github"
    assert doc["upgrade_command"] == (
        "python3 .reqq/validator/reqq_validate_stdlib.py upgrade --version 1.1.0")
    assert doc["changelog_delta"] is not None


def test_check_format_json_no_update_has_null_changelog_and_command():
    root = _make_checked_repo("notify")
    with temp_repo_root(root), stub_github([{"tag_name": "toolkit-v1.0.0", "prerelease": False}]):
        rc, out = _capture_stdout(cmd_check, ["--format", "json"])
    assert rc == 0
    doc = json.loads(out)
    assert doc["has_update"] is False
    assert doc["changelog_delta"] is None
    assert doc["upgrade_command"] is None


def test_check_format_json_reports_drift():
    root = _make_checked_repo("pr")
    (root / ".reqq" / "schema" / "requirement.schema.json").write_text('{"type":"object","x":1}')
    with temp_repo_root(root), stub_github(_NEWER_RELEASE):
        rc, out = _capture_stdout(cmd_check, ["--format", "json"])
    assert rc == 2
    doc = json.loads(out)
    assert doc["has_drift"] is True


def test_check_format_json_ignores_off_level_and_ci_flag():
    """`--format json` is a facts query for the update workflow — deciding whether to act
    on the level is the caller's job, unlike the `--ci` short-circuit in plain mode."""
    root = _make_checked_repo("off")
    with temp_repo_root(root), stub_github(_NEWER_RELEASE):
        rc, out = _capture_stdout(cmd_check, ["--ci", "--format", "json"])
    assert rc == 0
    doc = json.loads(out)
    assert doc["has_update"] is True
    assert doc["update_check"] == "off"


def test_check_format_json_host_passthrough_and_default():
    root = _make_checked_repo("notify")
    with temp_repo_root(root), stub_github([{"tag_name": "toolkit-v1.0.0", "prerelease": False}]):
        rc, out = _capture_stdout(cmd_check, ["--format", "json"])
    assert json.loads(out)["host"] == "github"

    (root / ".reqq" / "validator" / "config.yaml").write_text(
        "require_full_traceability: true\n"
        "toolkit:\n"
        "  update_channel: stable\n"
        "  update_check: notify\n"
        "  host: gitlab\n")
    with temp_repo_root(root), stub_github([{"tag_name": "toolkit-v1.0.0", "prerelease": False}]):
        rc, out = _capture_stdout(cmd_check, ["--format", "json"])
    assert json.loads(out)["host"] == "gitlab"


@contextlib.contextmanager
def stub_github_raises():
    """Simulate a release-lookup failure (network error, rate limit, ...)."""
    saved = V._github_api_get
    def _raise(endpoint):
        raise V.ToolkitError("GitHub API 503: Service Unavailable", code="GITHUB_API_ERROR")
    V._github_api_get = _raise
    try:
        yield
    finally:
        V._github_api_get = saved


def test_check_format_json_lookup_failure_is_unknown_not_false():
    """A failed release lookup must surface as `null`, not `false` — a workflow that treats
    it as "no update" would incorrectly close a still-open tracking issue (#6 review)."""
    root = _make_checked_repo("notify")
    with temp_repo_root(root), stub_github_raises():
        rc, out = _capture_stdout(cmd_check, ["--format", "json"])
    assert rc == 0
    doc = json.loads(out)
    assert doc["has_update"] is None
    assert doc["latest_version"] is None
    assert doc["changelog_delta"] is None
    assert doc["upgrade_command"] is None


def test_check_format_json_not_adopted_error():
    root = Path(tempfile.mkdtemp())
    with temp_repo_root(root):
        rc, out = _capture_stdout(cmd_check, ["--format", "json"])
    assert rc == 3
    doc = json.loads(out)
    assert doc == {"error": {"code": "NOT_ADOPTED", "message": doc["error"]["message"]}}


def test_check_format_json_corrupt_lock_error_code():
    """reqquest/reqQuestFramework#8 review: `check --format json` used to hit
    `load_toolkit_lock`'s non-strict `_die` before `--format json` ever got a chance to apply,
    so a corrupt lock exited 3 with empty stdout instead of the promised error document —
    same class of bug `upgrade --format json` was already fixed for (PR #49 review, see
    `test_upgrade_format_json_corrupt_lock_error_code`)."""
    root = Path(tempfile.mkdtemp())
    with temp_repo_root(root) as lock_path:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("{not valid json")
        rc, out = _capture_stdout(cmd_check, ["--format", "json"])
    assert rc == 3
    doc = json.loads(out)
    assert doc["error"]["code"] == "LOCK_CORRUPT"


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
    assert tk.get("update_check") in ("off", "notify", "pr", "manual", "ci-notify", "ci-pr"), tk
    assert tk.get("host") in ("github", "gitlab"), tk


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
            # Mirrors the real 404 path (_github_api_get) so tests exercise the same
            # code _fetch_release_by_tag normalizes into RELEASE_NOT_FOUND.
            raise ToolkitError(f"GitHub API 404: Not Found ({want})", code="GITHUB_API_NOT_FOUND")
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


# --- upgrade: missing-base (vA) fallback to full alignment (reqQuestFramework#7) --------

def test_upgrade_missing_base_release_falls_back_to_full_alignment():
    """The adopted (vA) tag was deleted entirely — no 3-way merge is possible. Falls back to
    a full alignment against vB instead of failing the whole upgrade."""
    schema = ".reqq/schema/requirement.schema.json"
    root = _adopted_repo({schema: '{"v":1}'})
    b_blob = _tar_gz({schema: '{"v":2}'})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob)]  # toolkit-v1.0.0 is absent
    blobs = {f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc = cmd_upgrade(["--channel", "stable"])
        lock = load_toolkit_lock()

    assert rc == 2, rc
    assert (root / schema).read_text() == '{"v":2}'
    assert lock["toolkit_version"] == "1.1.0"


def test_upgrade_missing_base_asset_falls_back_to_full_alignment():
    """The vA release still exists but its tarball asset was removed from it."""
    schema = ".reqq/schema/requirement.schema.json"
    root = _adopted_repo({schema: '{"v":1}'})
    rel_a = _release("toolkit-v1.0.0", ASSET_A, b"unused")
    rel_a["assets"] = []  # release exists, asset gone
    b_blob = _tar_gz({schema: '{"v":2}'})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob), rel_a]
    blobs = {f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc = cmd_upgrade(["--channel", "stable"])
        lock = load_toolkit_lock()

    assert rc == 2, rc
    assert (root / schema).read_text() == '{"v":2}'
    assert lock["toolkit_version"] == "1.1.0"


def test_upgrade_missing_base_checksum_falls_back_to_full_alignment():
    """The vA release exists and has the asset, but its body never got a SHA256SUMS entry —
    unverifiable, so treated the same as genuinely missing."""
    schema = ".reqq/schema/requirement.schema.json"
    root = _adopted_repo({schema: '{"v":1}'})
    a_blob = _tar_gz({schema: '{"v":1}'})
    rel_a = {
        "tag_name": "toolkit-v1.0.0", "prerelease": False, "body": "no sums here",
        "assets": [{"name": ASSET_A, "browser_download_url": f"https://cdn.example/toolkit-v1.0.0/{ASSET_A}"}],
    }
    b_blob = _tar_gz({schema: '{"v":2}'})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob), rel_a]
    blobs = {f"https://cdn.example/toolkit-v1.0.0/{ASSET_A}": a_blob,
             f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc = cmd_upgrade(["--channel", "stable"])

    assert rc == 2, rc
    assert (root / schema).read_text() == '{"v":2}'


def test_upgrade_missing_base_fallback_malformed_lock_files_field_is_not_a_crash():
    """Same guard as `adopt --align`'s, but for the missing-base full-alignment fallback — a
    `toolkit.lock` whose `files` field is not an object must not crash with AttributeError;
    it is treated as unknown history instead."""
    schema = ".reqq/schema/requirement.schema.json"
    root = _adopted_repo({schema: '{"v":1}'})
    with temp_repo_root(root):
        lock = load_toolkit_lock()
        lock["files"] = []  # malformed: should be an object of path -> hash
        V.write_toolkit_lock(lock)

    b_blob = _tar_gz({schema: '{"v":2}'})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob)]  # toolkit-v1.0.0 is absent
    blobs = {f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc, out = _capture_stdout(cmd_upgrade, ["--channel", "stable", "--format", "json"])

    assert rc == 2, rc
    doc = json.loads(out)
    assert doc["summary"]["local_only"] == 0
    assert (root / schema).read_text() == '{"v":2}'


def test_upgrade_base_checksum_mismatch_does_not_fall_back_exits_3():
    """A base whose bytes disagree with a PUBLISHED SHA256SUMS entry looks like tampering or
    a corrupt transfer, not a missing release — must fail loudly (reqQuestFramework#7), never
    silently fall back to overwriting the working tree."""
    schema = ".reqq/schema/requirement.schema.json"
    root = _adopted_repo({schema: '{"v":1}'})
    a_blob = _tar_gz({schema: '{"v":1}'})
    b_blob = _tar_gz({schema: '{"v":2}'})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob),
                _release("toolkit-v1.0.0", ASSET_A, a_blob)]
    # Serve tampered bytes for vA while its release body still lists the clean digest.
    blobs = {f"https://cdn.example/toolkit-v1.0.0/{ASSET_A}": a_blob + b"tampered",
             f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc = cmd_upgrade(["--channel", "stable"])

    assert rc == 3, rc
    assert (root / schema).read_text() == '{"v":1}', "must not touch the tree on a hard failure"


def test_upgrade_target_missing_never_falls_back_even_if_base_also_missing():
    """The fallback only ever applies to the BASE — a missing TARGET release always fails
    the whole command, since there is nothing to align *to* either."""
    root = _adopted_repo({".reqq/schema/requirement.schema.json": '{"v":1}'})
    releases = []  # neither toolkit-v1.0.0 nor toolkit-v1.1.0 exist

    with temp_repo_root(root), stub_release_channel(releases, {}):
        rc = cmd_upgrade(["--version", "1.1.0", "--channel", "stable"])
        lock = load_toolkit_lock()

    assert rc == 3, rc
    assert lock["toolkit_version"] == "1.0.0", "must not touch the lock on a hard failure"


def test_upgrade_missing_base_fallback_respects_local_overrides_as_keep():
    """A file declared in the existing lock's local_overrides survives the fallback
    untouched, same as `--keep` does for `adopt --align`."""
    # `.reqq/validator/config.yaml` would be a bad choice here — it's excluded from the
    # toolkit boundary entirely (toolkit-manifest.json), so it would be left alone regardless
    # of `local_overrides`, and the test would pass without ever exercising the keep-set path.
    # `.reqq/hooks/pre-commit` IS inside the boundary, so keeping it actually depends on the
    # fallback consulting `local_overrides`.
    schema = ".reqq/schema/requirement.schema.json"
    custom = ".reqq/hooks/pre-commit"
    root = _adopted_repo({schema: '{"v":1}', custom: "custom: true\n"}, overrides=[custom])
    b_blob = _tar_gz({schema: '{"v":2}', custom: "custom: false\n"})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob)]  # base absent
    blobs = {f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc = cmd_upgrade(["--channel", "stable"])

    assert rc == 2, rc
    assert (root / schema).read_text() == '{"v":2}', "non-override file is aligned to vB"
    assert (root / custom).read_text() == "custom: true\n", \
        "local_overrides path must be kept, not silently overwritten by the fallback"


def test_upgrade_missing_base_fallback_format_json():
    schema = ".reqq/schema/requirement.schema.json"
    root = _adopted_repo({schema: '{"v":1}'})
    b_blob = _tar_gz({schema: '{"v":2}'})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob)]
    blobs = {f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc, out = _capture_stdout(cmd_upgrade, ["--channel", "stable", "--format", "json"])

    doc = json.loads(out)
    assert rc == 2, rc
    assert doc["command"] == "upgrade"
    assert doc["mode"] == "full_alignment_fallback"
    assert doc["lock_written"] is True
    assert doc["from_version"] == "1.0.0"
    assert doc["to_version"] == "1.1.0"
    assert doc["needs_attention"] is True
    assert doc["changelog_delta"] is None
    assert "RELEASE_NOT_FOUND" in doc["fallback_reason"]
    actions = {f["path"]: f["action"] for f in doc["files"]}
    assert actions[schema] == "OVERWRITE"


def test_upgrade_missing_base_fallback_records_release_hash_for_kept_override():
    """PR #54 review: after the fallback KEEPs a local_overrides path, its lock baseline must
    be the RELEASE's hash of that path (same fix as `adopt --align`'s KEEP handling), not the
    kept local content's own hash. Otherwise the very next upgrade — even an ordinary
    non-fallback one — reads the override as "unchanged since lock" and silently REPLACEs it
    before local_overrides is ever consulted, discarding the customization one run later."""
    schema = ".reqq/schema/requirement.schema.json"
    custom = ".reqq/hooks/pre-commit"
    root = _adopted_repo({schema: '{"v":1}', custom: "custom: true\n"}, overrides=[custom])

    # Fallback 1.0.0 -> 1.1.0: base (toolkit-v1.0.0) is absent, so this goes through full
    # alignment. The override is kept, but the release's own copy of it differs from local.
    b_blob = _tar_gz({schema: '{"v":2}', custom: "custom: false\n"})
    releases_1 = [_release("toolkit-v1.1.0", ASSET_B, b_blob)]
    blobs_1 = {f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}
    with temp_repo_root(root), stub_release_channel(releases_1, blobs_1):
        rc1 = cmd_upgrade(["--channel", "stable"])
        lock1 = load_toolkit_lock()

    assert rc1 == 2, rc1
    assert (root / custom).read_text() == "custom: true\n", "the override must survive the fallback"
    import hashlib
    assert lock1["files"][custom] == f"sha256:{hashlib.sha256(b'custom: false\n').hexdigest()}", (
        "the lock baseline for a KEPT path must be the release's hash, not the kept local "
        "content's own hash")

    # A later, ORDINARY upgrade (base 1.1.0 is now available — no fallback) must still route
    # the override through a 3-way merge, not silently replace it.
    asset_c = "raac-toolkit-1.2.0.tar.gz"
    c_blob = _tar_gz({schema: '{"v":3}', custom: "custom: false\nupdated: true\n"})
    releases_2 = [_release("toolkit-v1.2.0", asset_c, c_blob),
                  _release("toolkit-v1.1.0", ASSET_B, b_blob)]
    blobs_2 = {f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob,
               f"https://cdn.example/toolkit-v1.2.0/{asset_c}": c_blob}
    with temp_repo_root(root), stub_release_channel(releases_2, blobs_2):
        rc2, out2 = _capture_stdout(cmd_upgrade, ["--channel", "stable", "--format", "json"])

    doc2 = json.loads(out2)
    actions2 = {f["path"]: f["action"] for f in doc2["files"]}
    assert actions2[custom] == "MERGE", (
        "a kept override must never be silently REPLACEd on the very next upgrade")


def test_upgrade_missing_base_fallback_collision_blocks_lock_write():
    """PR #54 review repro: a directory occupies a release boundary path during the
    missing-base fallback. Must report a COLLISION and leave the existing lock untouched —
    same protection `adopt --align` already has (reqQuestFramework#5) — rather than advancing
    toolkit_version to a release whose boundary isn't fully installed, which would make a
    re-run read the repo as already up to date and hide the problem forever."""
    schema = ".reqq/schema/requirement.schema.json"
    keep_file = ".reqq/schema/keep.json"
    root = _adopted_repo({keep_file: '{"v":"unrelated"}'})
    (root / schema).mkdir(parents=True)  # a directory occupies the release's file path

    b_blob = _tar_gz({schema: '{"v":2}', keep_file: '{"v":"unrelated"}'})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob)]  # base (1.0.0) absent
    blobs = {f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc, out = _capture_stdout(cmd_upgrade, ["--channel", "stable", "--format", "json"])
        lock_after = load_toolkit_lock()

    doc = json.loads(out)
    assert rc == 2, rc
    assert doc["mode"] == "full_alignment_fallback"
    assert doc["lock_written"] is False
    assert {"path": schema, "action": "COLLISION"} in doc["files"]
    assert doc["summary"]["collisions"] == 1
    assert lock_after["toolkit_version"] == "1.0.0", \
        "a collision must not be papered over by advancing the lock's toolkit_version"
    assert (root / schema).is_dir(), "the colliding path must be left exactly as it was"


def test_upgrade_missing_base_fallback_json_has_already_up_to_date():
    """reqquest/reqQuestFramework#8 review: the full_alignment_fallback document omitted
    `already_up_to_date`, so a caller reading it generically across both upgrade shapes (as
    `requirements-toolkit-update.yml` does via `jq -r '.already_up_to_date'`) got `null`
    instead of `false` — `null != 'false'` silently skipped the commit/push/PR steps, so the
    fallback's changes vanished with the runner."""
    schema = ".reqq/schema/requirement.schema.json"
    root = _adopted_repo({schema: '{"v":1}'})
    b_blob = _tar_gz({schema: '{"v":2}'})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob)]
    blobs = {f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc, out = _capture_stdout(cmd_upgrade, ["--channel", "stable", "--format", "json"])

    doc = json.loads(out)
    assert rc == 2, rc
    assert doc["mode"] == "full_alignment_fallback"
    assert doc["already_up_to_date"] is False


def test_upgrade_missing_base_fallback_lock_uses_release_boundary_not_kept_manifest():
    """reqquest/reqQuestFramework#8 review: when `toolkit-manifest.json` itself is a kept
    local_override, the fallback correctly copies files per the RELEASE's manifest (per
    `adopt --align`'s reqQuestFramework#5 fix, `align_globs = _toolkit_boundary_globs(new_root)`)
    but lock regeneration re-derived the boundary from ROOT's own (untouched, stale) manifest —
    a new file the release's manifest added would land on disk but never make it into the lock
    or drift detection. `_regenerate_lock_after_upgrade` must be handed the release's own
    boundary in this case, exactly like `adopt --align` already does."""
    manifest = "toolkit-manifest.json"
    old_manifest = json.dumps({"boundary": [manifest, "old.txt"]})
    root = _adopted_repo({manifest: old_manifest, "old.txt": "old\n"}, overrides=[manifest])

    new_manifest = json.dumps({"boundary": [manifest, "old.txt", "extra.txt"]})
    b_blob = _tar_gz({manifest: new_manifest, "old.txt": "old\n", "extra.txt": "new\n"})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob)]
    blobs = {f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc = cmd_upgrade(["--channel", "stable"])
        lock_after = load_toolkit_lock()

    assert rc == 2, rc
    assert (root / "extra.txt").read_text() == "new\n", "the release's new file must be applied"
    assert "extra.txt" in lock_after["files"], (
        "the lock must record every file the RELEASE's boundary ships, not just the ones "
        "the stale, kept local manifest already knew about")


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


# --- --format json (issue reqquest/reqQuestFramework#2) ----------------------

def _capture_stdout(fn, *args, **kwargs):
    """Run `fn`, returning (return_value, everything it printed to stdout).

    Deliberately not the pytest `capsys` fixture: this module doubles as a plain
    script (see module docstring) and its own `_main()` calls every `test_*`
    function with zero arguments, so fixtures are not an option here.
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(*args, **kwargs)
    return rc, buf.getvalue()


def test_adopt_format_json_emits_single_document():
    root = _make_adoptable_repo()
    with temp_repo_root(root):
        rc, out = _capture_stdout(cmd_adopt, ["--version", "1.0.0", "--format", "json"])
    assert rc == 0
    doc = json.loads(out)  # fails if anything else shares stdout with the document
    assert doc["command"] == "adopt"
    assert doc["version"] == "1.0.0"
    assert doc["channel"] == "stable"
    assert doc["lock_path"] == ".reqq/toolkit.lock"
    assert ".reqq/schema/requirement.schema.json" in doc["files"]
    assert ".reqq/validator/config.yaml" not in doc["files"]  # outside the boundary (D1)
    assert doc["local_overrides"] == []


def test_adopt_format_json_error_shape():
    """The empty-boundary failure (`test_adopt_refuses_to_write_an_empty_lock` in `plain`
    mode) must not `sys.exit` under `--format json` — it returns the error document."""
    root = Path(tempfile.mkdtemp())
    (root / "nested").mkdir()  # boundary globs match nothing at ROOT
    with temp_repo_root(root):
        rc, out = _capture_stdout(cmd_adopt, ["--version", "1.0.0", "--format", "json"])
    assert rc == 3
    doc = json.loads(out)
    assert doc == {"error": {"code": "EMPTY_BOUNDARY", "message": doc["error"]["message"]}}
    assert "nothing to adopt" in doc["error"]["message"]


def test_upgrade_format_json_state1_replace():
    root = _adopted_repo({".reqq/schema/requirement.schema.json": '{"v":1}'})
    a_blob = _tar_gz({".reqq/schema/requirement.schema.json": '{"v":1}'})
    b_blob = _tar_gz({".reqq/schema/requirement.schema.json": '{"v":2}'})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob),
                _release("toolkit-v1.0.0", ASSET_A, a_blob)]
    blobs = {f"https://cdn.example/toolkit-v1.0.0/{ASSET_A}": a_blob,
             f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc, out = _capture_stdout(cmd_upgrade, ["--channel", "stable", "--format", "json"])

    assert rc == 0
    doc = json.loads(out)
    assert doc["command"] == "upgrade"
    assert doc["dry_run"] is False
    assert doc["from_version"] == "1.0.0" and doc["to_version"] == "1.1.0"
    assert doc["major"] is False
    assert doc["already_up_to_date"] is False
    assert doc["needs_attention"] is False
    assert doc["files"] == [
        {"path": ".reqq/schema/requirement.schema.json", "action": "REPLACE"},
    ]
    assert doc["summary"]["replaced"] == 1
    assert isinstance(doc["changelog_delta"], str)


def test_upgrade_format_json_conflict_sets_needs_attention_and_per_file_flag():
    schema = ".reqq/schema/requirement.schema.json"
    root = _adopted_repo({schema: "COMMON\nBASE\n"}, overrides=[schema])
    (root / schema).write_text("COMMON\nLOCAL EDIT\n")
    a_blob = _tar_gz({schema: "COMMON\nBASE\n"})
    b_blob = _tar_gz({schema: "COMMON\nUPSTREAM EDIT\n"})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob),
                _release("toolkit-v1.0.0", ASSET_A, a_blob)]
    blobs = {f"https://cdn.example/toolkit-v1.0.0/{ASSET_A}": a_blob,
             f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc, out = _capture_stdout(cmd_upgrade, ["--channel", "stable", "--format", "json"])

    assert rc == 2
    doc = json.loads(out)
    assert doc["needs_attention"] is True
    assert doc["files"] == [{"path": schema, "action": "MERGE", "conflict": True}]
    assert doc["summary"]["conflicts"] == 1


def test_upgrade_format_json_dry_run_reports_conflict_without_touching_tree():
    """Conflicts must be visible under `--dry-run` too (issue's explicit requirement)."""
    schema = ".reqq/schema/requirement.schema.json"
    root = _adopted_repo({schema: "COMMON\nBASE\n"}, overrides=[schema])
    (root / schema).write_text("COMMON\nLOCAL EDIT\n")
    a_blob = _tar_gz({schema: "COMMON\nBASE\n"})
    b_blob = _tar_gz({schema: "COMMON\nUPSTREAM EDIT\n"})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob),
                _release("toolkit-v1.0.0", ASSET_A, a_blob)]
    blobs = {f"https://cdn.example/toolkit-v1.0.0/{ASSET_A}": a_blob,
             f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc, out = _capture_stdout(
            cmd_upgrade, ["--channel", "stable", "--dry-run", "--format", "json"])
        untouched = (root / schema).read_text()

    assert rc == 2
    doc = json.loads(out)
    assert doc["dry_run"] is True
    assert doc["files"] == [{"path": schema, "action": "MERGE", "conflict": True}]
    assert untouched == "COMMON\nLOCAL EDIT\n", "dry-run must not touch the working tree"


def test_upgrade_format_json_already_up_to_date():
    root = _adopted_repo({".reqq/schema/requirement.schema.json": '{"v":1}'}, version="1.1.0")
    b_blob = _tar_gz({".reqq/schema/requirement.schema.json": '{"v":1}'})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob)]

    with temp_repo_root(root), stub_release_channel(releases, {}):
        rc, out = _capture_stdout(cmd_upgrade, ["--channel", "stable", "--format", "json"])

    assert rc == 0
    doc = json.loads(out)
    assert doc["already_up_to_date"] is True
    assert doc["files"] == []
    assert doc["summary"]["replaced"] == 0
    assert doc["needs_attention"] is False


def test_upgrade_format_json_not_adopted_error():
    root = Path(tempfile.mkdtemp())
    with temp_repo_root(root):
        rc, out = _capture_stdout(cmd_upgrade, ["--format", "json"])
    assert rc == 3
    doc = json.loads(out)
    assert doc == {"error": {"code": "NOT_ADOPTED", "message": doc["error"]["message"]}}


def test_upgrade_format_json_checksum_mismatch_error_code():
    root = _adopted_repo({".reqq/schema/requirement.schema.json": '{"v":1}'})
    a_blob = _tar_gz({".reqq/schema/requirement.schema.json": '{"v":1}'})
    b_blob = _tar_gz({".reqq/schema/requirement.schema.json": '{"v":2}'})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob),
                _release("toolkit-v1.0.0", ASSET_A, a_blob)]
    blobs = {f"https://cdn.example/toolkit-v1.0.0/{ASSET_A}": a_blob,
             f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob + b"tampered"}

    with temp_repo_root(root), stub_release_channel(releases, blobs):
        rc, out = _capture_stdout(cmd_upgrade, ["--channel", "stable", "--format", "json"])

    assert rc == 3
    doc = json.loads(out)
    assert doc["error"]["code"] == "CHECKSUM_MISMATCH"


def test_upgrade_format_json_invalid_version_error_code():
    """PR #49 review: an explicit `--version` that isn't valid SemVer used to slip past the
    release-determination try/except (`_normalize_version` only strips prefixes, it doesn't
    validate) and blow up in the `_semver_lt` comparison below it — reaching `main()`'s
    catch-all `_die` and exiting with plain text even under `--format json`."""
    root = _adopted_repo({".reqq/schema/requirement.schema.json": '{"v":1}'})
    with temp_repo_root(root):
        rc, out = _capture_stdout(
            cmd_upgrade, ["--version", "not-a-version", "--format", "json"])
    assert rc == 3
    doc = json.loads(out)
    assert doc["error"]["code"] == "INVALID_VERSION"


def test_upgrade_format_json_corrupt_lock_error_code():
    """PR #49 review: a malformed toolkit.lock used to hit `load_toolkit_lock`'s `_die` before
    `--format json` ever got a chance to apply."""
    root = Path(tempfile.mkdtemp())
    (root / ".reqq").mkdir(parents=True)
    with temp_repo_root(root) as lock_path:
        lock_path.write_text("{not valid json")
        rc, out = _capture_stdout(cmd_upgrade, ["--format", "json"])
    assert rc == 3
    doc = json.loads(out)
    assert doc["error"]["code"] == "LOCK_CORRUPT"


def test_upgrade_format_json_merge_failure_is_explicit_not_silent():
    """PR #49 review: when the `git merge-file` subprocess itself fails to run (not just
    conflicts), the plan entry used to stay a bare `{path, action}` with no `conflict` key —
    indistinguishable from a merge nobody looked at. It must carry an explicit `error`."""
    schema = ".reqq/schema/requirement.schema.json"
    root = _adopted_repo({schema: "COMMON\nBASE\n"}, overrides=[schema])
    (root / schema).write_text("COMMON\nLOCAL EDIT\n")
    a_blob = _tar_gz({schema: "COMMON\nBASE\n"})
    b_blob = _tar_gz({schema: "COMMON\nUPSTREAM EDIT\n"})
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob),
                _release("toolkit-v1.0.0", ASSET_A, a_blob)]
    blobs = {f"https://cdn.example/toolkit-v1.0.0/{ASSET_A}": a_blob,
             f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}

    saved_run = V.subprocess.run
    V.subprocess.run = lambda *a, **kw: (_ for _ in ()).throw(OSError("git not found"))
    try:
        with temp_repo_root(root), stub_release_channel(releases, blobs):
            rc, out = _capture_stdout(cmd_upgrade, ["--channel", "stable", "--format", "json"])
    finally:
        V.subprocess.run = saved_run

    assert rc == 2
    doc = json.loads(out)
    assert doc["needs_attention"] is True
    assert doc["summary"]["merge_failed"] == 1
    assert doc["summary"]["merged"] == 0
    assert doc["files"] == [{
        "path": schema, "action": "MERGE",
        "error": {"code": "MERGE_FAILED", "message": "git not found"},
    }]
    assert "conflict" not in doc["files"][0]


def test_format_json_default_is_plain_text():
    """Acceptance: text output is unchanged, and stays the default, without the flag."""
    root = _make_adoptable_repo()
    with temp_repo_root(root):
        rc, out = _capture_stdout(cmd_adopt, ["--version", "1.0.0"])
    assert rc == 0
    assert out.startswith("✓ adopted toolkit v1.0.0")
    try:
        json.loads(out)
        raise AssertionError("plain-mode output must not parse as JSON")
    except json.JSONDecodeError:
        pass


# --- Config resolution outside the adopter repo (reqQuestFramework#3) --------

def test_resolve_config_path_prefers_script_location_when_inside_root():
    """The normal in-repo install: config.yaml sits beside the script itself."""
    assert V._resolve_config_path() == V._CONFIG_NEXT_TO_SCRIPT


def test_config_falls_back_to_root_relative_path_when_script_is_outside_root():
    """Running the validator from a copy that lives outside the adopter repo (an
    orchestrator using the target release's script against a different working tree) must
    still read that repo's config.yaml — the copy's own directory ships no config.yaml,
    only config.example.yaml."""
    root = Path(tempfile.mkdtemp())
    cfg_dir = root / ".reqq" / "validator"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.yaml").write_text(
        "require_full_traceability: false\ntoolkit:\n  update_channel: next\n")
    with temp_repo_root(root):
        cfg = V.load_config()
    assert cfg["require_full_traceability"] is False
    assert cfg["toolkit"]["update_channel"] == "next"


def test_config_missing_at_root_relative_fallback_is_not_an_error():
    root = Path(tempfile.mkdtemp())
    with temp_repo_root(root):
        cfg = V.load_config()
    assert cfg["require_full_traceability"] is True  # documented default


def test_find_repo_root_falls_back_to_cwd_not_script_location():
    """A payload copy, invoked in a bare adopter tree, must use that tree as ROOT."""
    script_copy_dir = Path(tempfile.mkdtemp()) / "payload" / ".reqq" / "validator"
    script_copy_dir.mkdir(parents=True)
    shutil.copy(_VALIDATOR_DIR / "reqq_validate_stdlib.py",
                script_copy_dir / "reqq_validate_stdlib.py")

    adopter_tree = Path(tempfile.mkdtemp())  # deliberately no .git anywhere above it
    proc = subprocess.run(
        [sys.executable, "-c",
         f"import sys; sys.path.insert(0, {str(script_copy_dir)!r}); "
         "import reqq_validate_stdlib as m; print(m.ROOT)"],
        cwd=adopter_tree, capture_output=True, text=True)

    assert proc.returncode == 0, proc.stderr
    assert Path(proc.stdout.strip()).resolve() == adopter_tree.resolve()


# --- upgrade: offline payload mode (reqQuestFramework#3) ---------------------

def _payload_dir(files: dict) -> Path:
    """An already-extracted `raac-toolkit-<version>/` directory, no wrapper needed."""
    dest = Path(tempfile.mkdtemp())
    for rel, text in files.items():
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return dest


def test_upgrade_offline_requires_version():
    root = _adopted_repo({".reqq/schema/requirement.schema.json": '{"v":1}'})
    with temp_repo_root(root):
        rc = cmd_upgrade(["--base-payload", str(_payload_dir({})),
                          "--target-payload", str(_payload_dir({}))])
    assert rc == 3


def test_upgrade_offline_requires_both_payload_dirs_together():
    root = _adopted_repo({".reqq/schema/requirement.schema.json": '{"v":1}'})
    with temp_repo_root(root):
        rc = cmd_upgrade(["--base-payload", str(_payload_dir({})), "--version", "1.1.0"])
    assert rc == 3


def test_upgrade_offline_bad_args_error_code_under_format_json():
    root = _adopted_repo({".reqq/schema/requirement.schema.json": '{"v":1}'})
    with temp_repo_root(root):
        rc, out = _capture_stdout(cmd_upgrade,
            ["--base-payload", str(_payload_dir({})), "--format", "json"])
    assert rc == 3
    assert json.loads(out)["error"]["code"] == "INVALID_ARGS"


def test_upgrade_offline_nonexistent_target_payload_is_rejected_not_treated_as_removal():
    """P1 regression (PR #50 review): `_find_payload_root` does not check existence, so a
    mistyped --target-payload used to resolve right back to itself. Fed into
    `_compute_upgrade_plan`, that read as "the release removed every file" — every
    unchanged local file got REMOVEd, the adopter's tree was emptied, and toolkit.lock
    still advanced to the requested version with exit 0. A bad path must be rejected
    before any plan is computed, leaving the tree and lock untouched."""
    files_a = {".reqq/schema/requirement.schema.json": '{"type":"object","v":1}'}
    root = _adopted_repo(files_a)
    base_dir = _payload_dir(files_a)
    missing_target = Path(tempfile.mkdtemp()) / "does-not-exist"

    with temp_repo_root(root):
        rc, out = _capture_stdout(cmd_upgrade,
            ["--base-payload", str(base_dir), "--target-payload", str(missing_target),
             "--version", "1.1.0", "--format", "json"])
        lock = load_toolkit_lock()

    assert rc == 3
    assert json.loads(out)["error"]["code"] == "PAYLOAD_INVALID"
    assert (root / ".reqq/schema/requirement.schema.json").read_text() == \
        '{"type":"object","v":1}', "the adopter's file must not be deleted"
    assert lock["toolkit_version"] == "1.0.0", "the lock must not advance"


def test_upgrade_offline_empty_payload_dir_is_rejected():
    """An existing but empty directory (e.g. an extraction that silently produced nothing)
    must be rejected the same way as a missing one — it has no `.reqq/`."""
    files_a = {".reqq/schema/requirement.schema.json": '{"v":1}'}
    root = _adopted_repo(files_a)
    base_dir = _payload_dir(files_a)
    empty_target = Path(tempfile.mkdtemp())  # exists, but empty — no .reqq/

    with temp_repo_root(root):
        rc = cmd_upgrade(["--base-payload", str(base_dir), "--target-payload", str(empty_target),
                          "--version", "1.1.0"])

    assert rc == 3
    assert (root / ".reqq/schema/requirement.schema.json").read_text() == '{"v":1}'


def test_upgrade_offline_payload_pointing_at_a_plain_file_is_rejected():
    files_a = {".reqq/schema/requirement.schema.json": '{"v":1}'}
    root = _adopted_repo(files_a)
    base_dir = _payload_dir(files_a)
    not_a_dir = Path(tempfile.mkdtemp()) / "payload.tar.gz"
    not_a_dir.write_bytes(b"not actually extracted")

    with temp_repo_root(root):
        rc = cmd_upgrade(["--base-payload", str(base_dir), "--target-payload", str(not_a_dir),
                          "--version", "1.1.0"])

    assert rc == 3
    assert (root / ".reqq/schema/requirement.schema.json").read_text() == '{"v":1}'


def test_upgrade_offline_makes_no_network_calls_and_matches_online_plan():
    """Acceptance: `upgrade --base-payload … --target-payload … --version X` succeeds with
    networking disabled and produces the same plan/result as the equivalent online run."""
    files_a = {".reqq/schema/requirement.schema.json": '{"type":"object","v":1}'}
    files_b = {".reqq/schema/requirement.schema.json": '{"type":"object","v":2}'}

    # Online baseline.
    root_online = _adopted_repo(files_a)
    a_blob, b_blob = _tar_gz(files_a), _tar_gz(files_b)
    releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob),
                _release("toolkit-v1.0.0", ASSET_A, a_blob)]
    blobs = {f"https://cdn.example/toolkit-v1.0.0/{ASSET_A}": a_blob,
             f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}
    with temp_repo_root(root_online), stub_release_channel(releases, blobs):
        rc_online = cmd_upgrade(["--channel", "stable"])
        lock_online = load_toolkit_lock()
    assert rc_online == 0

    # Offline: same content, pre-extracted, network calls forbidden.
    root_offline = _adopted_repo(files_a)
    base_dir = _payload_dir(files_a)
    target_dir = _payload_dir(files_b)

    def _forbidden(*_a, **_k):
        raise AssertionError("offline upgrade must not touch the network")

    saved_api, saved_dl = V._github_api_get, V._http_get_bytes
    V._github_api_get, V._http_get_bytes = _forbidden, _forbidden
    try:
        with temp_repo_root(root_offline):
            rc_offline = cmd_upgrade(["--base-payload", str(base_dir),
                                      "--target-payload", str(target_dir),
                                      "--version", "1.1.0"])
            lock_offline = load_toolkit_lock()
    finally:
        V._github_api_get, V._http_get_bytes = saved_api, saved_dl

    assert rc_offline == 0
    assert (root_offline / ".reqq/schema/requirement.schema.json").read_text() == \
        (root_online / ".reqq/schema/requirement.schema.json").read_text()
    assert lock_offline["toolkit_version"] == lock_online["toolkit_version"] == "1.1.0"
    assert lock_offline["files"] == lock_online["files"]


def test_upgrade_offline_dry_run_touches_nothing():
    files_a = {".reqq/schema/requirement.schema.json": '{"v":1}'}
    files_b = {".reqq/schema/requirement.schema.json": '{"v":2}'}
    root = _adopted_repo(files_a)
    base_dir = _payload_dir(files_a)
    target_dir = _payload_dir(files_b)

    with temp_repo_root(root):
        rc = cmd_upgrade(["--base-payload", str(base_dir), "--target-payload", str(target_dir),
                          "--version", "1.1.0", "--dry-run"])
        lock = load_toolkit_lock()

    assert rc == 0
    assert (root / ".reqq/schema/requirement.schema.json").read_text() == '{"v":1}'
    assert lock["toolkit_version"] == "1.0.0"


def test_upgrade_offline_format_json_omits_changelog_delta():
    files_a = {".reqq/schema/requirement.schema.json": '{"v":1}'}
    files_b = {".reqq/schema/requirement.schema.json": '{"v":2}'}
    root = _adopted_repo(files_a)
    base_dir = _payload_dir(files_a)
    target_dir = _payload_dir(files_b)

    with temp_repo_root(root):
        rc, out = _capture_stdout(cmd_upgrade,
            ["--base-payload", str(base_dir), "--target-payload", str(target_dir),
             "--version", "1.1.0", "--format", "json"])

    assert rc == 0
    doc = json.loads(out)
    assert doc["changelog_delta"] is None


# --- adopt --align (reqQuestFramework#5) --------------------------------------

def _bare_repo(files: dict) -> Path:
    """A pre-versioning working tree: files on disk, no toolkit.lock."""
    root = Path(tempfile.mkdtemp())
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return root


def test_align_requires_align_flag():
    """--keep/--payload/--dry-run without --align must be rejected, not silently ignored."""
    root = _bare_repo({".reqq/schema/requirement.schema.json": '{"v":"local"}'})
    with temp_repo_root(root):
        rc, out = _capture_stdout(cmd_adopt,
            ["--version", "1.0.0", "--keep", ".reqq/schema/requirement.schema.json",
             "--format", "json"])
    assert rc == 3
    assert json.loads(out)["error"]["code"] == "INVALID_ARGS"


def test_align_overwrites_differing_adds_missing_keeps_declared():
    """Acceptance: a pre-versioning repo ends up byte-identical to the release boundary
    except for --keep paths, with a valid toolkit.lock."""
    root = _bare_repo({
        ".reqq/schema/requirement.schema.json": '{"v":"local-plain"}',
        ".reqq/schema/keep.json": '{"v":"local-keep"}',
    })
    payload = _payload_dir({
        ".reqq/schema/requirement.schema.json": '{"v":"release-plain"}',
        ".reqq/schema/keep.json": '{"v":"release-keep"}',
        ".reqq/hooks/pre-commit": "#!/bin/sh\necho hi\n",
    })

    with temp_repo_root(root) as lock_path:
        rc = cmd_adopt(["--version", "1.0.0", "--align", "--payload", str(payload),
                        "--keep", ".reqq/schema/keep.json"])
        lock = json.loads(lock_path.read_text())

    assert rc == 0
    assert (root / ".reqq/schema/requirement.schema.json").read_text() == '{"v":"release-plain"}'
    assert (root / ".reqq/schema/keep.json").read_text() == '{"v":"local-keep"}', \
        "kept path must not be overwritten"
    assert (root / ".reqq/hooks/pre-commit").read_text() == "#!/bin/sh\necho hi\n"

    assert lock["toolkit_version"] == "1.0.0"
    assert lock["local_overrides"] == [".reqq/schema/keep.json"]
    # The lock records the RELEASE's hash for a kept path, not the kept local content's own
    # hash — otherwise the kept content would read as "unchanged" on the very next upgrade
    # and be replaced before local_overrides is ever consulted (PR #52 review; see
    # test_align_kept_path_three_way_merges_on_an_immediate_later_upgrade).
    assert lock["files"][".reqq/schema/keep.json"] == \
        _sha256_file(payload / ".reqq/schema/keep.json")
    assert lock["files"][".reqq/schema/keep.json"] != \
        _sha256_file(root / ".reqq/schema/keep.json")
    assert lock["files"][".reqq/schema/requirement.schema.json"] == \
        _sha256_file(root / ".reqq/schema/requirement.schema.json")


def test_align_identical_file_is_left_alone():
    files = {".reqq/schema/requirement.schema.json": '{"v":"same"}'}
    root = _bare_repo(files)
    payload = _payload_dir(files)

    with temp_repo_root(root):
        rc, out = _capture_stdout(cmd_adopt,
            ["--version", "1.0.0", "--align", "--payload", str(payload), "--format", "json"])

    assert rc == 0
    doc = json.loads(out)
    assert doc["align"]["files"] == [], "an identical file must produce no align entry"
    assert doc["align"]["summary"] == {"added": 0, "overwritten": 0, "kept": 0,
                                        "local_only": 0, "collisions": 0}


def test_align_local_only_file_is_reported_never_deleted():
    """Acceptance: a file this toolkit previously managed (per an existing toolkit.lock) but
    that the target release no longer ships is reported LOCAL_ONLY, never deleted."""
    root = _adopted_repo({
        ".reqq/schema/requirement.schema.json": '{"v":"local"}',
        ".reqq/schema/legacy.json": '{"v":"legacy, dropped upstream"}',
    })
    payload = _payload_dir({".reqq/schema/requirement.schema.json": '{"v":"release"}'})

    with temp_repo_root(root):
        rc, out = _capture_stdout(cmd_adopt,
            ["--version", "1.1.0", "--align", "--payload", str(payload), "--format", "json"])

    assert rc == 2, "a local-only file must be reported via a non-zero exit"
    doc = json.loads(out)
    assert {"path": ".reqq/schema/legacy.json", "action": "LOCAL_ONLY"} in doc["align"]["files"]
    assert doc["align"]["needs_attention"] is True
    assert (root / ".reqq/schema/legacy.json").read_text() == '{"v":"legacy, dropped upstream"}', \
        "a local-only file must never be deleted"


def test_align_glob_match_never_recorded_in_a_lock_is_not_local_only():
    """reqQuestFramework#14 regression: a file that merely matches the release boundary's
    glob pattern (by name/location), but that no lock ever recorded this toolkit as having
    shipped in this repo, is NOT LOCAL_ONLY — it is not the toolkit's file at all and must
    not be reported. Modelled on the real case: `requirements/**/README.md` catching an
    adopter's own README in a category the toolkit itself never had."""
    root = _bare_repo({
        ".reqq/schema/requirement.schema.json": '{"v":"local"}',
        "requirements/functional/CUSTOM/README.md": "# Our own category, never shipped by the toolkit\n",
    })
    payload = _payload_dir({
        ".reqq/schema/requirement.schema.json": '{"v":"release"}',
        "requirements/README.md": "# toolkit README\n",
    })
    boundary_manifest = {
        "boundary": [".reqq/schema/*.json", "requirements/README.md",
                     "requirements/**/README.md"],
    }
    (payload / "toolkit-manifest.json").write_text(json.dumps(boundary_manifest))

    with temp_repo_root(root):
        rc, out = _capture_stdout(cmd_adopt,
            ["--version", "1.0.0", "--align", "--payload", str(payload), "--format", "json"])

    assert rc == 0, "a file never recorded in any lock must not trigger needs_attention"
    doc = json.loads(out)
    paths = {f["path"] for f in doc["align"]["files"]}
    assert "requirements/functional/CUSTOM/README.md" not in paths, \
        "a glob match with no lock history must produce no align entry at all"
    assert doc["align"]["summary"]["local_only"] == 0
    assert doc["align"]["needs_attention"] is False
    assert (root / "requirements/functional/CUSTOM/README.md").read_text() == \
        "# Our own category, never shipped by the toolkit\n", \
        "an adopter's own file must never be touched"


def test_align_malformed_lock_files_field_is_treated_as_no_history_not_a_crash():
    """A hand-edited toolkit.lock whose `files` is not an object (e.g. a list) must not crash
    `adopt --align` with AttributeError from a bare `.keys()` call — it is treated the same
    as no prior lock at all: unknown history, not a fatal error."""
    root = _bare_repo({".reqq/schema/requirement.schema.json": '{"v":"local"}'})
    with temp_repo_root(root):
        V.write_toolkit_lock({
            "toolkit_version": "1.0.0",
            "files": [],  # malformed: should be an object of path -> hash
            "local_overrides": [],
        })
        payload = _payload_dir({".reqq/schema/requirement.schema.json": '{"v":"release"}'})
        rc, out = _capture_stdout(cmd_adopt,
            ["--version", "1.1.0", "--align", "--payload", str(payload), "--format", "json"])

    assert rc == 0, "a malformed files field must not crash align nor report a false LOCAL_ONLY"
    doc = json.loads(out)
    assert doc["align"]["summary"]["local_only"] == 0


def test_align_lock_document_itself_not_an_object_is_treated_as_no_history_not_a_crash():
    """`load_toolkit_lock(strict=True)` only validates that the file is well-formed JSON, not
    that its top-level document is even an object — a `toolkit.lock` containing just `[]`
    parses fine and would otherwise crash `_lock_ever_shipped()`'s `lock.get(...)` with
    AttributeError (a list has no `.get()`). Must be treated as unknown history instead,
    same as a missing lock."""
    root = _bare_repo({".reqq/schema/requirement.schema.json": '{"v":"local"}'})
    with temp_repo_root(root) as lock_path:
        lock_path.write_text("[]\n")
        payload = _payload_dir({".reqq/schema/requirement.schema.json": '{"v":"release"}'})
        rc, out = _capture_stdout(cmd_adopt,
            ["--version", "1.1.0", "--align", "--payload", str(payload), "--format", "json"])

    assert rc == 0, "a non-object lock document must not crash align nor report a false LOCAL_ONLY"
    doc = json.loads(out)
    assert doc["align"]["summary"]["local_only"] == 0


def test_align_keep_path_outside_release_boundary_is_ignored_with_a_warning():
    root = _bare_repo({".reqq/schema/requirement.schema.json": '{"v":"local"}'})
    payload = _payload_dir({".reqq/schema/requirement.schema.json": '{"v":"release"}'})

    with temp_repo_root(root) as lock_path:
        rc = cmd_adopt(["--version", "1.0.0", "--align", "--payload", str(payload),
                        "--keep", "not/in/the/boundary.txt"])
        lock = json.loads(lock_path.read_text())

    assert rc == 0
    assert lock["local_overrides"] == []
    assert (root / ".reqq/schema/requirement.schema.json").read_text() == '{"v":"release"}'


def test_align_dry_run_reports_without_touching_tree_or_writing_lock():
    """Acceptance: --dry-run --format json lists the differing files without touching the
    working tree."""
    root = _bare_repo({".reqq/schema/requirement.schema.json": '{"v":"local"}'})
    payload = _payload_dir({
        ".reqq/schema/requirement.schema.json": '{"v":"release"}',
        ".reqq/hooks/pre-commit": "#!/bin/sh\n",
    })

    with temp_repo_root(root) as lock_path:
        rc, out = _capture_stdout(cmd_adopt,
            ["--version", "1.0.0", "--align", "--payload", str(payload), "--dry-run",
             "--format", "json"])
        lock_written = lock_path.exists()

    assert rc == 0
    assert not lock_written, "--dry-run must not write toolkit.lock"
    assert (root / ".reqq/schema/requirement.schema.json").read_text() == '{"v":"local"}', \
        "--dry-run must not touch the working tree"
    assert not (root / ".reqq/hooks/pre-commit").exists()

    doc = json.loads(out)
    assert doc["dry_run"] is True
    assert doc["mode"] == "align"
    assert "lock_path" not in doc and "files" not in doc, \
        "a dry run must not report lock fields — nothing was written"
    actions = {f["path"]: f["action"] for f in doc["align"]["files"]}
    assert actions[".reqq/schema/requirement.schema.json"] == "OVERWRITE"
    assert actions[".reqq/hooks/pre-commit"] == "ADD"


def test_align_offline_payload_makes_no_network_calls():
    root = _bare_repo({".reqq/schema/requirement.schema.json": '{"v":"local"}'})
    payload = _payload_dir({".reqq/schema/requirement.schema.json": '{"v":"release"}'})

    def _forbidden(*_a, **_k):
        raise AssertionError("--align --payload must not touch the network")

    saved_api, saved_dl = V._github_api_get, V._http_get_bytes
    V._github_api_get, V._http_get_bytes = _forbidden, _forbidden
    try:
        with temp_repo_root(root):
            rc = cmd_adopt(["--version", "1.0.0", "--align", "--payload", str(payload)])
    finally:
        V._github_api_get, V._http_get_bytes = saved_api, saved_dl

    assert rc == 0
    assert (root / ".reqq/schema/requirement.schema.json").read_text() == '{"v":"release"}'


def test_align_downloads_and_verifies_the_payload_when_no_offline_path_is_given():
    """Without --payload, align must go through the same download + SHA256SUMS verification
    as upgrade, not trust an unverified source."""
    root = _bare_repo({".reqq/schema/requirement.schema.json": '{"v":"local"}'})
    blob = _tar_gz({".reqq/schema/requirement.schema.json": '{"v":"release"}'})
    releases = [_release("toolkit-v1.0.0", ASSET_A, blob)]
    blobs = {f"https://cdn.example/toolkit-v1.0.0/{ASSET_A}": blob}

    with temp_repo_root(root) as lock_path, stub_release_channel(releases, blobs):
        rc = cmd_adopt(["--version", "1.0.0", "--align"])
        lock = json.loads(lock_path.read_text())

    assert rc == 0
    assert (root / ".reqq/schema/requirement.schema.json").read_text() == '{"v":"release"}'
    assert lock["toolkit_version"] == "1.0.0"


def test_align_kept_path_three_way_merges_on_an_immediate_later_upgrade():
    """Acceptance: --keep paths are preserved and listed in local_overrides; a later upgrade
    merges them (state 2) — even with NO further local edit between align and upgrade.

    P1 regression (PR #52 review): `adopt` used to record the KEPT LOCAL content's own hash
    as this path's lock baseline. Since nothing touches the file again before the next
    upgrade, its hash still matched that baseline, so `_is_unchanged()` read it as untouched
    and picked REPLACE before ever consulting local_overrides — silently discarding the
    customization the very first time `upgrade` ran. The fix records the RELEASE's hash as
    the baseline instead, so the kept (diverging) local content always reads as "changed"
    and routes into MERGE.
    """
    root = _bare_repo({".reqq/schema/requirement.schema.json": '{"v":"local"}'})
    payload = _payload_dir({
        ".reqq/schema/requirement.schema.json": '{"v":"release-1.0"}',
    })

    with temp_repo_root(root):
        assert cmd_adopt(["--version", "1.0.0", "--align", "--payload", str(payload),
                          "--keep", ".reqq/schema/requirement.schema.json"]) == 0
        assert (root / ".reqq/schema/requirement.schema.json").read_text() == '{"v":"local"}'

        a_blob = _tar_gz({".reqq/schema/requirement.schema.json": '{"v":"release-1.0"}'})
        b_blob = _tar_gz({".reqq/schema/requirement.schema.json": '{"v":"release-1.1"}'})
        releases = [_release("toolkit-v1.1.0", ASSET_B, b_blob),
                    _release("toolkit-v1.0.0", ASSET_A, a_blob)]
        blobs = {f"https://cdn.example/toolkit-v1.0.0/{ASSET_A}": a_blob,
                 f"https://cdn.example/toolkit-v1.1.0/{ASSET_B}": b_blob}
        with stub_release_channel(releases, blobs):
            rc, out = _capture_stdout(cmd_upgrade, ["--channel", "stable", "--format", "json"])

    doc = json.loads(out)
    files_by_path = {f["path"]: f for f in doc["files"]}
    assert files_by_path[".reqq/schema/requirement.schema.json"]["action"] == "MERGE", (
        "a kept file must never be silently REPLACEd on the very next upgrade")


def test_align_offline_requires_version():
    """P2 regression (PR #52 review): --align --payload without --version used to fall
    through to the normal (network) latest-version lookup, mislabeling the supplied payload
    with whatever the release API currently reports as latest — violating the offline
    contract `upgrade --base-payload/--target-payload` already enforces."""
    root = _bare_repo({".reqq/schema/requirement.schema.json": '{"v":"local"}'})
    payload = _payload_dir({".reqq/schema/requirement.schema.json": '{"v":"release"}'})

    def _forbidden(*_a, **_k):
        raise AssertionError("--align --payload without --version must fail before any "
                              "network call, not silently query for the latest version")

    saved_api = V._github_api_get
    V._github_api_get = _forbidden
    try:
        with temp_repo_root(root):
            rc, out = _capture_stdout(cmd_adopt,
                ["--align", "--payload", str(payload), "--format", "json"])
    finally:
        V._github_api_get = saved_api

    assert rc == 3
    assert json.loads(out)["error"]["code"] == "INVALID_ARGS"
    assert not V.TOOLKIT_LOCK.exists()


def test_align_keeping_the_manifest_does_not_drop_new_release_files_from_the_lock():
    """P2 regression (PR #52 review): if --keep preserves an older toolkit-manifest.json,
    lock generation used to re-derive the boundary from THAT (now-stale) local manifest,
    silently omitting files the release just introduced — even though align had already
    copied them onto disk. The lock must be generated from the release's boundary."""
    old_manifest = json.dumps({"boundary": [".reqq/schema/*.json", "toolkit-manifest.json"]})
    new_manifest = json.dumps({
        "boundary": [".reqq/schema/*.json", "toolkit-manifest.json", "extra.txt"],
    })
    root = _bare_repo({
        "toolkit-manifest.json": old_manifest,
        ".reqq/schema/requirement.schema.json": '{"v":"local"}',
    })
    payload = _payload_dir({
        "toolkit-manifest.json": new_manifest,
        ".reqq/schema/requirement.schema.json": '{"v":"release"}',
        "extra.txt": "new in this release\n",
    })

    with temp_repo_root(root) as lock_path:
        rc = cmd_adopt(["--version", "1.0.0", "--align", "--payload", str(payload),
                        "--keep", "toolkit-manifest.json"])
        lock = json.loads(lock_path.read_text())

    assert rc == 0
    assert (root / "toolkit-manifest.json").read_text() == old_manifest, \
        "the kept manifest itself must stay untouched"
    assert (root / "extra.txt").read_text() == "new in this release\n", \
        "align must still copy a file the release boundary introduced"
    assert "extra.txt" in lock["files"], \
        "a file align copied must not be silently missing from the lock"
    assert lock["local_overrides"] == ["toolkit-manifest.json"]


def test_align_directory_collision_is_reported_not_silently_nested():
    """P2 regression (PR #52 follow-up review): a local DIRECTORY occupying a release file's
    path is excluded by `_toolkit_boundary_files()` (`is_file()` only), so it used to read as
    "absent locally" — the plan picked ADD, and `shutil.copy2(src, a_directory)` silently
    copied the release file INSIDE that directory instead of occupying the intended path,
    leaving the required path still a directory and exiting 0. Must instead be reported as a
    COLLISION, left untouched, with a non-zero exit and no lock written."""
    root = _bare_repo({".reqq/schema/keep.json": '{"v":"unrelated"}'})
    (root / ".reqq/schema/requirement.schema.json").mkdir(parents=True)
    payload = _payload_dir({
        ".reqq/schema/requirement.schema.json": '{"v":"release"}',
        ".reqq/schema/keep.json": '{"v":"unrelated"}',
    })

    with temp_repo_root(root) as lock_path:
        rc, out = _capture_stdout(cmd_adopt,
            ["--version", "1.0.0", "--align", "--payload", str(payload), "--format", "json"])
        lock_written = lock_path.exists()

    assert rc == 2, "a directory/file collision must be reported via a non-zero exit"
    doc = json.loads(out)
    assert {"path": ".reqq/schema/requirement.schema.json", "action": "COLLISION"} \
        in doc["align"]["files"]
    assert doc["align"]["summary"]["collisions"] == 1
    assert doc["align"]["needs_attention"] is True
    assert doc["lock_written"] is False
    assert "files" not in doc and "lock_path" not in doc, \
        "no top-level adopt fields must be reported — the lock was not actually written"
    assert (root / ".reqq/schema/requirement.schema.json").is_dir(), \
        "the colliding path must be left exactly as it was, not nested into"
    assert not list((root / ".reqq/schema/requirement.schema.json").iterdir()), \
        "the release file must not be silently copied inside the local directory"
    assert not lock_written, \
        "a collision must not be papered over by writing a lock anyway"


def test_align_collision_preserves_the_previous_lock_and_check_still_reports_it():
    """P2 regression (PR #52 follow-up review): the earlier fix wrote a lock even when a
    collision was reported — omitting the colliding path (since it isn't a plain file) but
    otherwise looking clean, so an immediate `check` returned 0 despite the required schema
    still being a directory. A collision must instead leave any existing lock untouched, so
    `check` keeps reporting the real (pre-align) state."""
    files_a = {".reqq/schema/requirement.schema.json": '{"v":"1.0-local"}'}
    root = _adopted_repo(files_a, version="1.0.0")
    (root / ".reqq/schema/requirement.schema.json").unlink()
    (root / ".reqq/schema/requirement.schema.json").mkdir()
    payload = _payload_dir({".reqq/schema/requirement.schema.json": '{"v":"1.1-release"}'})

    with temp_repo_root(root) as lock_path:
        pre_lock = json.loads(lock_path.read_text())
        rc = cmd_adopt(["--version", "1.1.0", "--align", "--payload", str(payload)])
        post_lock = json.loads(lock_path.read_text())
        with stub_github([{"tag_name": "toolkit-v1.1.0", "prerelease": False}]):
            check_rc = cmd_check([])

    assert rc == 2
    assert post_lock == pre_lock, "the previous lock must be left completely untouched"
    assert check_rc == 2, \
        "check must keep reporting the unresolved state, not a falsely clean v1.1.0"


def test_align_file_blocking_a_parent_directory_is_reported_not_a_crash():
    """P2 regression (PR #52 follow-up review): a plain FILE occupying a path the release
    needs as a directory (e.g. a file at .reqq/schema when the release ships
    .reqq/schema/requirement.schema.json) reads as "absent locally" the same way a leaf
    collision does, since `_toolkit_boundary_files()` silently skips through it. Applying
    the resulting ADD action used to crash with an uncaught FileExistsError from
    parent.mkdir(parents=True, exist_ok=True). Must be reported as COLLISION instead."""
    root = _bare_repo({})
    (root / ".reqq").mkdir(parents=True)
    (root / ".reqq/schema").write_text("a plain file where the release needs a directory")
    payload = _payload_dir({".reqq/schema/requirement.schema.json": '{"v":"release"}'})

    with temp_repo_root(root) as lock_path:
        rc, out = _capture_stdout(cmd_adopt,
            ["--version", "1.0.0", "--align", "--payload", str(payload), "--format", "json"])
        lock_written = lock_path.exists()

    assert rc == 2, "a blocked-ancestor collision must be reported, not raise"
    doc = json.loads(out)
    assert {"path": ".reqq/schema/requirement.schema.json", "action": "COLLISION"} \
        in doc["align"]["files"]
    assert not lock_written
    assert (root / ".reqq/schema").read_text() == \
        "a plain file where the release needs a directory", \
        "the blocking file must be left untouched"


def test_align_kept_path_reads_as_drift_immediately_after_align():
    """Documents the intentional behavior noted in the PR #52 follow-up review: because the
    lock records the RELEASE's hash (not the kept local content's) for a --keep path, `check`
    immediately reports it as drift. This is the same "declared but diverging" signal
    `local_overrides` already carries for a plain `adopt --local-override`, and it is exactly
    what lets `upgrade` pick MERGE instead of REPLACE on the very next run."""
    root = _bare_repo({".reqq/schema/requirement.schema.json": '{"v":"local"}'})
    payload = _payload_dir({".reqq/schema/requirement.schema.json": '{"v":"release"}'})

    with temp_repo_root(root):
        assert cmd_adopt(["--version", "1.0.0", "--align", "--payload", str(payload),
                          "--keep", ".reqq/schema/requirement.schema.json"]) == 0
        with stub_github([{"tag_name": "toolkit-v1.0.0", "prerelease": False}]):
            rc = cmd_check([])

    assert rc == 2, "a kept override must read as drift right after align, by design"


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
