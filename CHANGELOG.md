# Changelog

All notable changes to the **reqQuest Framework toolkit** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0/).

Toolkit releases are tagged `toolkit-vX.Y.Z`. The tarball boundary is defined by
[`toolkit-manifest.json`](https://github.com/reqquest/reqQuestFramework/blob/main/toolkit-manifest.json).
The upgrade notes of a release, such as the migration steps of a MAJOR version, are part of its section.

## [toolkit-v2.0.0]

The first release of the 2.x line: a new validator, new checks, ownership governance and a
rewritten methodology. It is a MAJOR release without backward compatibility; read
"Migration from 1.3.0" before you upgrade.

### What 2.0.0 brings since 1.3.0

- **One validator entry point**, `.reqq/validator/reqq_validate.py`, split into `reqq_*.py`
  modules. It runs every check with one report and one exit code, in the pre-commit hook and
  in CI; `--check NAME` runs only the named checks.
- **Front matter checked against the JSON Schemas** in `.reqq/schema/`, YAML read strictly, and
  a fix hint with every error. In GitHub Actions the findings appear as annotations on the file
  and line.
- **New checks**: Markdown link integrity (`links`), integrity of the requirements graph
  (`graph`), the life cycle of the `conflict` field, documents due for review when a source
  they link with `ID@major.minor` bumps its version, and OpenAPI fragments embedded in
  requirements (`openapi`).
- **Optional conventions** in `config.yaml`: the language of requirements (`language`), a
  repository prefix in IDs (`id_prefix`), a short title in file names (`short_title`) and a
  checked folder layout (`enforce_layout`).
- **Ownership governance**: a role catalog (`requirements/00-context/roles.yaml`), a generated
  `CODEOWNERS` block and the levels `off`, `catalog`, `generate` and `enforce`, checked by
  `reqq_owners.py` and the `owners` and `owners-host` checks.
- **Toolkit management**: installation from the release asset with `adopt`; starting
  templates (example requirements, context files, `AGENTS.project.md`) are adopter-owned
  `seed` files that `upgrade` never touches; `upgrade` keeps local content on a collision or a
  merge, never writes through a symlink, and leaves `.reqq/toolkit.lock` unchanged when a release
  file cannot be installed because a local directory, a file above its path or a symlink is in
  the way, so the next run retries it; the adopter's own file behind a symlink is kept instead
  and does not hold the lock back. `check` lists a changed file declared in
  `local_overrides` instead of reporting it as drift. The scheduled
  `requirements-toolkit-update.yml` fails when the validator returns no result, instead of
  ending green without a check, and opens the PR of a later MAJOR upgrade with the `breaking`
  label and a migration section (the upgrade to 2.0.0 itself runs your current workflow).
- **Starter kit**: example requirements in a fictional domain (meeting room booking),
  instructions for AI agents in `requirements/` (`AGENTS.md`, `CLAUDE.md`,
  `AGENTS.project.md`), and the Apache-2.0 licence and NOTICE in `LICENSES/`.
- **Methodology** rewritten in English and moved to `docs/framework/`, with
  `docs/starter-kit.md` as the installation guide.

### Migration from 1.3.0

The full guide, with every breaking change, is in
[`.reqq/README.md`, section "Moving to the release with `reqq_validate.py`"](https://github.com/reqquest/reqQuestFramework/blob/main/.reqq/README.md#moving-to-the-release-with-reqq_validatepy).
In short:

1. **Save local changes to `reqq_validate_stdlib.py` first.** The upgrade does not carry local
   edits over. When `.reqq/toolkit.lock` holds the hash of your edited file, the upgrade removes
   it without a warning. When the lock holds the release hash, the upgrade exits with code 2,
   keeps the file and warns that it was dropped upstream but modified locally; delete it by
   hand. Move the changes to the new `reqq_*.py` modules afterwards.
2. **Upgrade with the 1.3.0 script**, the one your repository has, or let
   `requirements-toolkit-update.yml` open the upgrade PR. The upgrade rewrites
   `.github/workflows/requirements-*.yml`, which the default `GITHUB_TOKEN` cannot push, so the
   workflow then needs the optional secret `TOOLKIT_UPDATE_TOKEN` (a fine-grained PAT or GitHub
   App installation token with contents, pull-requests and workflows write):

   ```bash
   python3 .reqq/validator/reqq_validate_stdlib.py upgrade --version 2.0.0
   ```

3. **Review what the upgrade added or replaced.** The 1.3.0 script does not know adopter-owned
   files: it adds the example requirements (`requirements/**/REQQF-*.md`) and the starting
   templates, and replaces a locally changed `objectives-and-scope.md` or `stakeholders.md`
   with a warning. Delete the examples you do not want and restore your own context files
   before you commit. From 2.0.0 on, `upgrade` leaves these files alone.
4. **Install Python >= 3.10 and the validator libraries** (PyYAML, jsonschema, referencing),
   in a virtual environment; without them the validator exits with code 3:

   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   python3 -m pip install -r .reqq/validator/requirements.txt
   ```

5. **Call the new entry point.** Replace every call of `reqq_validate_stdlib.py` (scripts, CI)
   with `reqq_validate.py`; there is no shim under the old name. One call runs the validation,
   the link check and the ownership check.
6. **Take the new workflows.** The `requirements-*.yml` workflows are replaced: they install the
   libraries and call `reqq_validate.py`. A workflow you kept as a local override must be taken
   in full; renaming the call is not enough.
7. **Update links to the methodology.** In the public repository it moved from `docs/` to
   `docs/framework/`, and the old pages `docs/<page>.md` are gone. Files shipped in a 1.3.0
   package link to those old pages with relative `docs/<page>.md` paths, so their links stay
   broken until you upgrade; the 2.0.0 files link to the new pages with absolute URLs. Point
   your own links to `docs/framework/<page>.md` too.
8. **Validate and fix the findings**: `python3 .reqq/validator/reqq_validate.py --all`. Among
   other things, `status: accepted` is now an error (use `approved`).
9. **Commit requirement files whole.** The pre-commit hook validates the files as they are on
   disk, so it now stops with code 3 when a staged requirement file also has unstaged changes.
   Stage the whole file, or set the rest aside with `git stash --keep-index` before you commit.

Later upgrades use the new entry point:
`python3 .reqq/validator/reqq_validate.py upgrade --version X.Y.Z`.

## [toolkit-v1.3.0]() (2026-09-20)

### Added

* feat(toolkit): reqqf#16 — &quot;approved&quot; as canonical requirement status, &quot;accepted&quot; as deprecated alias (#17) - mkarwasz-reqquest-dev
