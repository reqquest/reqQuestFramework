# .reqq — reqQuest Framework validator (starter kit)

A generic requirements validator for the `BR/FR/NFR/ADR/TC/POL` convention described in [`../docs/framework/conventions.md`](../docs/framework/conventions.md), with a single entry point `validator/reqq_validate.py`. It needs Python >= 3.10 and the libraries from `validator/requirements.txt` (PyYAML, jsonschema, referencing); without the libraries it exits with code `3`. The `requirements.txt` file pins the direct dependencies, and pip resolves the transitive ones.

**Installation:** download the asset `raac-toolkit-X.Y.Z.tar.gz` from the release [`toolkit-vX.Y.Z`](https://github.com/reqquest/reqQuestFramework/releases) and unpack it **in the repo's root directory**:

```bash
# The tarball content lies in the raac-toolkit-X.Y.Z/ directory — --strip-components=1 removes
# that wrapper, so the files land in the repo's root directory, not in a subdirectory.
tar xzf raac-toolkit-X.Y.Z.tar.gz --strip-components=1

# The validator configuration is local (not part of the package, `upgrade` does not touch it):
cp .reqq/validator/config.example.yaml .reqq/validator/config.yaml

# Install the validator libraries (Python >= 3.10; direct dependencies pinned
# in requirements.txt, pip resolves the transitive ones) in a virtual environment:
# the system Python refuses `pip install` (PEP 668). Add `.venv/` to .gitignore.
python3 -m venv .venv
source .venv/bin/activate   # the hook uses python3 from PATH: the environment must be active when committing
python3 -m pip install -r .reqq/validator/requirements.txt

# Record the adopted toolkit version:
python3 .reqq/validator/reqq_validate.py adopt --version X.Y.Z
```

The package boundary — a closed list of paths — is defined by [`../toolkit-manifest.json`](../toolkit-manifest.json).

## Structure

```
.reqq/
  schema/
    requirement.schema.json    # base front matter schema (common fields + references to types/*)
    types/
      BR.schema.json
      FR.schema.json            # requires `category`
      NFR.schema.json           # requires `category`
      ADR.schema.json           # requires `decisions`
      TC.schema.json             # requires `derives_from`
      POL.schema.json           # requires `category`
    roles.schema.json            # role catalog requirements/00-context/roles.yaml
    openapi/                     # official OpenAPI 3.0, 3.1 and 3.2 schemas (OAI) for the `openapi` check
  validator/
    reqq_validate.py            # the single entry point: checks, adopt/check/upgrade, one report and exit code (CI and hook)
    reqq_yaml.py                # YAML loading (PyYAML BaseLoader; OpenAPI fragments with types)
    reqq_common.py              # paths, configuration, front matter, ID patterns, TYPE_ENUM
    reqq_config.py              # configuration rules (language, ID prefix, enforce_layout, openapi)
    reqq_check_frontmatter.py   # single-file rules (validate_doc)
    reqq_check_schema.py        # front matter against schema/*.json (schema.contract warnings); role catalog
    reqq_check_graph.py         # requirements graph rules
    reqq_check_layout.py        # folder layout rule (enforce_layout)
    reqq_check_openapi.py       # OpenAPI fragments in `yaml openapi` blocks (`openapi` check)
    reqq_toolkit_*.py           # adopt, check and upgrade commands (core, github, align, merge, adopt, check, upgrade)
    reqq_check_links.py         # Markdown link integrity check (`links` check; also runs standalone)
    reqq_owners.py              # ownership governance (`owners`, `owners-host` checks); standalone: --check, generate (CODEOWNERS), --verify-handles
    reqq_owners_github.py       # GitHub API client for rule V6
    requirements.txt            # pinned validator libraries: PyYAML, jsonschema, referencing
    config.example.yaml         # configuration template — copy it to config.yaml
    config.yaml                 # local configuration (outside the toolkit boundary, not in the package)
  hooks/
    pre-commit                  # runs `reqq_validate.py --staged-only`
```

Front matter is checked against `schema/*.json` (`reqq_check_schema.py`). A schema violation that no other rule reports is a `schema.contract` warning; the hard rules (`validate_doc` in `reqq_check_frontmatter.py`) stay errors. Changing the requirements for a given type needs an update of the schema and the rules.

OpenAPI fragments in ` ```yaml openapi id=<ID>.<name> ` blocks are checked by the `openapi` check (`reqq_check_openapi.py`): YAML, root keys (`paths`, `components`), the identifier and the OpenAPI schema of the version from `openapi.version` in `config.yaml` (`3.0`, `3.1`, `3.2`; default `3.2`). The reporting level is set by `openapi.level`: `off`, `warning` (default) or `error`. Convention: [conventions.md, section 9](../docs/framework/conventions.md#9-openapi-fragments-in-requirements).

## Usage

```bash
# Install the hook (once per repository clone):
git config core.hooksPath .reqq/hooks

# Full validation:
python3 .reqq/validator/reqq_validate.py --all

# Validation of staged files only (the pre-commit hook does the same); a staged requirement
# file with unstaged changes stops it with code 3 (stage it or git stash --keep-index):
python3 .reqq/validator/reqq_validate.py --staged-only

# JSON output (for CI integration):
python3 .reqq/validator/reqq_validate.py --all --format json

# Only the given checks (the `--check` option, repeatable):
python3 .reqq/validator/reqq_validate.py --check links --check owners
```

With `--all` or `--staged-only` the checks `frontmatter`, `schema`, `graph`, `layout`, `openapi`, `links` and `owners` run by default, in this order; `owners-host` (rule V6, which queries the host) only with `--check owners-host`. For explicitly given files the file checks run: `frontmatter`, `schema`, `graph`, `layout` and `openapi`. An unknown name in `--check` is a configuration error.

Exit code: `0` = OK, `2` = validation errors, `3` = configuration error.

Beyond checking each file, the validator checks the requirements graph: `traces_to`, `derives_from` (in TC) and `conflict[].with` must point to existing `id`s, unless they have another repository's prefix (`id_prefix`, below). The rule code goes into the `kind` field: `graph.dangling`, `graph.duplicate-id` and `graph.suspect-version` are errors, and `graph.status-draft`, `graph.status-deprecated` and `graph.suspect` are warnings. A link `ID@major.minor` points to the version of the source the document was last consistent with; when the source has a higher `version`, the document is due for review (`graph.suspect`). The graph is built from the whole `requirements/` also with `--staged-only`. Rules: [`../docs/framework/conventions.md`](../docs/framework/conventions.md), section 6. The graph follows only valid `id`s. The shape of the fields is checked by schema validation: `traces_to` and, in TC, `derives_from` must be a list of unique `id`s, each with an optional `@major.minor` suffix. The schema limits `derives_from` to FR/NFR, but the validator reports another `id` type only as a warning, so as not to block the CI of repositories that derive tests from ADRs.

## Link integrity — `reqq_check_links.py`

```bash
# Dead relative links to .md files (the validator's `links` check does the same, so the hook and CI do too):
python3 .reqq/validator/reqq_check_links.py
```

Every relative link `[...](<path>.md)` must point to an existing file. The anchor (`#...`) is cut off and not checked. Absolute links (`http(s)://`), `mailto:` and links in inline code and code blocks are skipped. The `.md` files in the folders from `link_check_paths` in `config.yaml` are scanned — by default only `requirements`.

Exit code: `0` = OK, `2` = dead links or files that cannot be read.

## Toolkit versioning

Managing the toolkit version in an adopting repository:

```bash
# Initialisation — record the current toolkit state as v1.0.0
python3 .reqq/validator/reqq_validate.py adopt --version 1.0.0

# Check — is a newer version available, have the files drifted
python3 .reqq/validator/reqq_validate.py check

# The same as a CI step — respects `toolkit.update_check` from config.yaml
python3 .reqq/validator/reqq_validate.py check --ci
```

### `adopt`

Creates `.reqq/toolkit.lock` — a manifest of the version and checksums of the toolkit boundary files.
Two consecutive runs give an identical file except for the `installed_at` field.

`--local-override PATH ...` marks files that on upgrade are to go through a 3-way merge
instead of a hard replacement. Relative paths are resolved against the working directory, so
`--local-override README.md` from `requirements/` means the same as `--local-override
requirements/README.md` from the repo's root directory. A path outside the toolkit boundary is
rejected with a warning — a silently accepted override would be overwritten anyway on the first
upgrade.

### `check`

Compares the local state with `toolkit.lock` and with the latest `toolkit-v*` release in the
`stable` / `next` channel. Exit codes:

| Code | Meaning |
|---|---|
| `0` | no drift (an available newer version is reported as a warning, it is **not** an error) |
| `2` | local drift relative to `toolkit.lock` |
| `3` | missing or corrupted `toolkit.lock`, error fetching the release list |

`--ci` enables the CI step mode driven by the `toolkit:` key from `config.yaml`:

| `update_check` | Behaviour |
|---|---|
| no `toolkit:` key / `manual` | no operation, exit `0` |
| `ci-notify` | `::warning::` annotations, an available update **never** fails |
| `ci-pr` | as above — an available update also **never** fails; the level reserves room for a future, separate mechanism that reacts to the result (e.g. opening a PR), it does not change the exit code today |

A file declared in `local_overrides` that differs from `toolkit.lock` is a declared change,
not drift: `check` lists it as overridden and ends with code `0` for it. A missing declared
file is still drift. In a folder reached through a symlink, `check` reads only the files in
`toolkit.lock`: a new file there is not reported as added.

Local drift relative to `toolkit.lock` **always** ends with code `2` — identically with `--ci` and without `--ci`. An available newer version is an event outside the current commit (someone else published a release), so it never gates the pipeline — otherwise the same commit would be green today and red tomorrow only because the framework published something. For this reason the `check --ci` step itself does **not** sit in the validation workflow run on `push`/`pull_request` (`requirements-validate.yml`) — it has its own, separate workflow (`requirements-toolkit-check.yml`) triggered only by `schedule` and `workflow_dispatch`.

### `upgrade`

Downloads the `raac-toolkit-*.tar.gz` assets for the version currently recorded in `toolkit.lock` and
for the target version, verifies each against the `SHA256SUMS` block in the release body, and then
performs a per-file 3-way merge. The reference point is the first release —
[`toolkit-v1.0.0`](https://github.com/reqquest/reqQuestFramework/releases/tag/toolkit-v1.0.0).
Without `toolkit.lock` it exits with code `3` (run `adopt` first); a mismatching checksum also
aborts the upgrade instead of merging from an unverified package.

Per-file states the engine distinguishes on `vA → vB`:

| Condition | Action |
|---|---|
| unchanged locally | replaced with the version from `vB` |
| changed and listed in `local_overrides` | 3-way merge, conflicts as `<<<<<<< local` / `\|\|\|\|\|\|\| vA` / `>>>>>>> vB` markers |
| changed, outside `local_overrides` | replaced + warning |
| new in `vB` | added (or restored, if the adopter deleted it) |
| new in `vB`, but the adopter already has this file | local version kept + collision reported; the file goes into `local_overrides`, so the next upgrade merges it |
| removed in `vB`, unchanged locally | removed |
| removed in `vB`, changed locally | kept + reported for a manual decision |
| already equal to `vB` | nothing to do |

A path occupied by a directory, lying below a local file or leading through a symlink is never
written. A file there that already equals `vB` needs nothing. Your own one (declared in `local_overrides`, a starting file `vB` moves into the boundary, or on a path new in `vB`) is kept with the hash from `vB`, goes into `local_overrides` and is
reported as a collision when `vB` changed it. Any other release file there is reported as a blocked path, and
when `vB` changed it, `toolkit.lock` is then not written: clear the path, resolve the merge conflicts and re-run `upgrade`.

`--dry-run` performs the merge into a temporary file, so it reports the real number of conflicts
without touching the working tree.

`--base-payload DIR --target-payload DIR` performs the merge offline on two already unpacked
`raac-toolkit-<version>/` directories instead of downloading them — for an orchestrator that has already
downloaded both packages and verified their checksums itself and wants the merge to run without network
access or credentials. `--version` still has to be given explicitly (there is no release API from which it
could be detected); verifying the package checksums in this mode is the caller's responsibility.
The CHANGELOG delta in the report is then skipped, because fetching it also needs the network.

Running the validator from a copy outside the adopter's repository — exactly what the above assumes —
is supported, as long as all `reqq_*.py` files lie together and the libraries from `requirements.txt` are installed: `config.yaml` is resolved next to the script when the script lies inside the
repository (the usual in-repo installation), and otherwise falls back to
`ROOT/.reqq/validator/config.yaml`, so `upgrade`/`check` still respect the adopter's
`toolkit.update_channel` / `update_check` even when called as
`python3 /path/to/another/copy/reqq_validate.py upgrade` with `cwd` inside the adopter's
repository.

### Immutability of `toolkit-v*` releases

`upgrade` treats the version recorded in `toolkit.lock` (vA) as a durable, immutable reference
point for the 3-way merge — the only way for the merge to know what is the "base" and what is
the adopter's local change. This gives a hard rule for the framework:

- `toolkit-v*` releases and their assets (`raac-toolkit-<version>.tar.gz`) are **never deleted
  or re-tagged**.
- A missing public asset is restored by re-running the publication, which copies the internal
  asset of the same version: an identical asset already in place is left alone, a **different**
  one makes the publication **fail** instead of silently overwriting it.
- A packaging change that **would change the bytes** never replaces the asset of an existing
  tag — it ships as a new release (version bump).
- Deprecating a release is an entry in the release notes, not deleting the asset.

**When the base is unavailable anyway** (release/tag deleted, asset deleted, or the release body
never got a `SHA256SUMS` block) — `upgrade` does not guess which files "changed
since an unknown vA". Instead it switches to **full alignment** with the target
version (the same engine as `adopt --align`), with `local_overrides` from the existing lock as the
`--keep` set, and **always** exits with code `2` — the report (`plain` on stderr/stdout or
`"mode": "full_alignment_fallback"` in `--format json`) clearly says that the fallback
mode was used, never silently. Without vA the alignment cannot tell whether the release changed a
file: a path it cannot write (a directory, a file above it or a symlink) holds back the lock until
you clear it or declare the file in `local_overrides`. A mismatch between the base asset's checksum **and the published**
`SHA256SUMS` (`CHECKSUM_MISMATCH`) is something other than "missing" — it looks like tampering or a
corrupted transfer and always exits with code `3`, never with the fallback alignment. Fallback
alignment never applies to the **target** version (vB) — its absence always aborts the whole
upgrade with code `3`, because there is nothing to align to.

### `min_toolkit_version`

An optional key in the root of `.reqq/schema/requirement.schema.json`. When it is set,
validation exits with code `3` if `toolkit.lock.toolkit_version` is older. No
key = no constraint; a repository without `toolkit.lock` gets a warning, not an error.

The `.reqq/toolkit.lock` file is listed in `.reqqignore` and `exclude_globs`. This validator
would not touch it anyway (it scans only `requirements/**/*.md`), but the contract applies to
several copies of the validator, so the exclusion is declared, not assumed.

## Moving to the release with `reqq_validate.py`

The release with the single entry point `reqq_validate.py` is a MAJOR release without backward compatibility. The upgrade is still performed by the **old** script (`reqq_validate_stdlib.py upgrade`): it removes `reqq_validate_stdlib.py` and adds `reqq_validate.py`, the `reqq_*.py` modules and `requirements.txt`.

**Before the upgrade, copy every local change in `reqq_validate_stdlib.py` to a separate file.** The old `upgrade` compares the hash of the local file with the hash in `toolkit.lock`; it does not depend on whether and how the change was declared:

- The lock holds the hash of the local file: `upgrade` treats the file as unchanged and removes it **without a warning** — code `0`, action `REMOVE`, the `local_overrides` entry disappears. This is the case after every `adopt` without `--align` recorded after editing the file, with `--local-override` and without.
- The lock holds the release hash (`adopt` recorded before the edit, or `adopt --align --keep <file>`): `upgrade` exits with code `2`, leaves the file and warns `dropped upstream but modified locally — kept, delete by hand if intended` (action `REMOVE_KEPT`). Next: move the change to the new `reqq_*.py` modules or drop it, remove the old file (`git rm`; removing it alone gives `check` with code `2`, drift `removed`) and rewrite the lock: `reqq_validate.py adopt --align --version X.Y.Z --keep <remaining local overrides>`. Without `--keep`, `adopt --align` clears `local_overrides` and overwrites the remaining locally changed boundary files with the release version.

In both cases move the copied changes to the new modules, because the old file is no longer called. After the upgrade:

1. **Install the libraries** (PyYAML, jsonschema, referencing; they need Python >= 3.10, and pip resolves the transitive dependencies). The system Python refuses `pip install` (PEP 668), so use a virtual environment: `python3 -m venv .venv`, `source .venv/bin/activate`, `python3 -m pip install -r .reqq/validator/requirements.txt`, and add `.venv/` to `.gitignore`. The hook uses `python3` from `PATH`, so the environment must be active when committing. Without the libraries the validator exits with code `3`.
2. **Rename the calls.** The old entry point disappears without a shim under the old name: replace every call of `reqq_validate_stdlib.py` from the command line, scripts included, with `reqq_validate.py`. This does not cover imports: `reqq_validate.py` does not expose the internals of the old module. Move the import to the module where the code lies now (the `.reqq/validator` directory must be in `sys.path`): rules are in `reqq_check_*.py` (e.g. `validate_doc` in `reqq_check_frontmatter`), toolkit commands in `reqq_toolkit_*.py` (e.g. `cmd_upgrade` and `_UPGRADE_STATE_LABELS` in `reqq_toolkit_upgrade`, `_ALIGN_ACTION_LABELS` in `reqq_toolkit_align`, `_compute_upgrade_plan` in `reqq_toolkit_merge`), shared code in `reqq_common.py`, `reqq_config.py`, `reqq_yaml.py` and `reqq_toolkit_core.py`. For example, `import reqq_toolkit_align as AL` and `import reqq_toolkit_upgrade as UP` replace the former `import reqq_validate_stdlib as V` in code that reads these labels.
3. **The hook and CI** make one call instead of three (validator, link check, `reqq_owners.py --check`). `--check <name>` runs only the given checks: `frontmatter`, `schema`, `graph`, `layout`, `links`, `owners` and `owners-host` (V6, a separate step in CI).
4. **`status: accepted` is an error** — use `approved`. The value `accepted` in `conflict[].resolution` stays allowed.
5. **YAML is read strictly:** anchors and aliases are rejected, a value starting with `&` or `*` needs quotes, invalid front matter is a file error that does not stop checking the other files, and a key written twice in one mapping is a `frontmatter` error (formerly the last value won, without a trace).
6. **Schema:** violations that no other rule reports are `schema.contract` warnings.
7. **The `requirements-toolkit-update.yml` workflow.** If it was kept by a local override, take the new one in full; renaming is not enough. The old workflow calls the removed `reqq_validate_stdlib.py check` in its very first step (without the result it does not recognise the update), has no `pip install` step for the libraries, and the step with the PR body reads labels from the removed entry point.

## Ownership governance — `reqq_owners.py`

Roles from the catalog `requirements/00-context/roles.yaml` are responsible for areas of `requirements/`, and a block in `.github/CODEOWNERS` translates this into approvers at the host. The rules are described in [`conventions.md`](../docs/framework/conventions.md), section "Ownership governance".

```bash
# Standalone: offline rules of the level from config.yaml (the hook and CI do this with the validator's `owners` check):
python3 .reqq/validator/reqq_owners.py --check

# CODEOWNERS block from roles.yaml, appended at the end of .github/CODEOWNERS (only there):
python3 .reqq/validator/reqq_owners.py generate

# Standalone: rule V6 at the enforce level, CI only (GitHub Actions);
# the validator's CI step is `reqq_validate.py --check owners-host`:
python3 .reqq/validator/reqq_owners.py --verify-handles
```

The level is set by `ownership.mode` in `config.yaml`; the levels add up:

| Level | Rules | `generate` |
|---|---|---|
| no `ownership` key | none — `undetected` warning, code `0` | writes nothing |
| `off` | none; requires `decided` and `decided_by` | writes nothing |
| `catalog` | `roles`, `io`, V1, V4, V5, V8 | writes nothing |
| `generate` | as `catalog` + V2, V3, V7 | writes the block |
| `enforce` | as `generate` + V6 (`owners-host` check, CI only) | writes the block |

| Rule | What it checks |
|---|---|
| `roles` | `roles.yaml` has the shape from `.reqq/schema/roles.schema.json`, without duplicated role keys |
| `io` | the requirement file can be read as UTF-8 text; from the `catalog` level an unreadable file is a violation, because it is unknown who its `owner` is |
| V1 | the `owner` of every requirement is a role key from `roles.yaml` |
| V4 | `handle` has the format of the host from `toolkit.host` (default `github`): `@user` or `@org/team`; on GitLab also `@group/subgroup/...` |
| V5 | `responsible_for` points to existing directories, and two roles do not share a directory or its subdirectory |
| V8 | every role is assigned to a stakeholder in the last column of the table in `stakeholders.md`, and the table does not point to roles outside `roles.yaml` |
| V2 | `.github/CODEOWNERS` ends with a freshly generated `# reqq:begin … # reqq:end` block |
| V3 | the directory of every requirement has a responsible role |
| V7 | the block contains complete self-protection |
| V6 | the branch (`GITHUB_BASE_REF`, on push `GITHUB_REF_NAME`) requires code owner approval, and `codeowners/errors` reports no `handle` from the block. An uncertain result gives a warning. In a native PR stack `GITHUB_BASE_REF` is the base of the stack; after adding an open PR to the stack, run the workflow again |

`reqq_owners.py` takes the requirements and their exclusions from the same sources as the validator: `config.yaml` (`exclude_globs`) and `.reqqignore`.

Exit code: `0` = OK, `2` = rule violation, `3` = configuration error (e.g. no `roles.yaml` from the `catalog` level, unbalanced block markers).

**Enabling:**

1. Copy `requirements/00-context/roles.example.yaml` to `roles.yaml` in the same directory and replace the roles and `handle`s with your own; in the last column of the table in `stakeholders.md` enter the stakeholders' role keys. The toolkit ships only the example, and `roles.yaml` belongs to the repository and `upgrade` does not touch it.
2. Set `ownership.mode` in `config.yaml` (example in `config.example.yaml`).
3. At the `generate` level run `generate` and commit `.github/CODEOWNERS`. GitHub requests reviews according to `CODEOWNERS` from the target branch, so a PR that adds or changes the block does not show the new code owners yet; you see them on the next PR after the merge. V6, on the other hand, reads `CODEOWNERS` from the PR commit (`GITHUB_SHA`).
4. Run `--check`.
5. At the `enforce` level (GitHub only) you need:
   - at least 2 people with write, because GitHub does not count the PR author's approval;
   - write to the repository for every `handle`; a team must have it granted as a team and be visible (not secret). GitHub skips a `handle` that does not meet this, and V6 reports it as an error;
   - "Require review from Code Owners" in branch protection or in a ruleset. V6 checks the PR's target branch, and on push the pushed branch (in the workflow `main` and `develop`), so each of them must have the requirement; a PR to a branch without the requirement ends with an error;
   - a token that reads the branch settings. `GITHUB_TOKEN` does not read classic branch protection, so with it store as the secret `OWNERS_VERIFY_TOKEN` a fine-grained PAT limited to this repository, with the permissions Administration: read and Contents: read (with Administration: read alone GitHub refuses to read CODEOWNERS); without it V6 ends with a warning. `GITHUB_TOKEN` reads rulesets on its own;
   - a bypass for automations that push straight to the protected branch (e.g. the changelog commit in the release workflow), because a ruleset with the `pull_request` rule blocks them. `GITHUB_TOKEN` cannot be on the bypass list: add to it, in `always` mode ("Always allow"), a GitHub App with the Contents: write permission and push with its token. A bypass for the admin role or a team would exempt people from review too.

**The CODEOWNERS block** is always at the end of the file, because on GitHub the last matching rule wins. Content outside the markers stays unchanged. The block contains the self-protection `/.reqq/**`, `/.github/CODEOWNERS`, `/.github/workflows/requirements-*.yml`, `/requirements/00-context/roles.yaml` and `/.reqqignore`, owned by all `handle`s from the catalog. When `CODEOWNERS` lies in the root directory or in `docs/`, `generate` refuses: GitHub reads `.github/CODEOWNERS` first, so a new file would disable the existing one.

## Exclusions — `.reqqignore` and `config.yaml`

Two independent mechanisms that add up:

- **`.reqqignore`** (repo root directory) — format like `.gitignore` (one glob per line, `#` comments). Portable, independent of the validator implementation — see [`../docs/framework/conventions.md`](../docs/framework/conventions.md), section 6.
- **`config.yaml`** → `exclude_globs` — exclusions specific to this validator, plus `require_full_traceability` (bool), which controls whether FR/NFR without `traces_to` block validation, or only `category`/`decisions`/`derives_from` per type. The file is **local** — it lies outside the toolkit boundary (`toolkit-manifest.json`), so `upgrade` does not overwrite it; the package carries only `config.example.yaml`. The validator also works without it (`require_full_traceability` defaults to `true`, no `toolkit:` block = `check --ci` with no operation), but the toolkit examples pass only with `id_prefix: REQQF` and `short_title: true` from `config.example.yaml` (below).

## Requirements language — `language`

The `language` key in `config.yaml` declares one requirements language in the repository: a lowercase ISO 639-1 code (`en`, `pl`, ...). The validator checks only the code itself — a value outside ISO 639-1 ends validation with code `3`, and a missing key means no check. The rule and its scope: [`../docs/framework/conventions.md`](../docs/framework/conventions.md), section 8.

## Repository prefix — `id_prefix`

The `id_prefix` key in `config.yaml` declares the prefix of requirement IDs in the repository: 2–6 uppercase letters, equal to the repository key from branch and issue names (e.g. `id_prefix: REQA` → `REQA-FR-AGENT-001`). With the key, the validator requires it in the `id` of every document and the prefix in every reference (`traces_to`, `derives_from`, `conflict[].with`). It does not check references with another repository's prefix in the graph. Without the key no ID or reference has a prefix. The `id-prefix` error also points to toolkit examples (prefix `REQQF`) left over after changing `id_prefix` to your own. An invalid value ends validation with code `3`. The `legacy_id` field keeps the document's last previous ID, without a prefix. Rules: [`../docs/framework/conventions.md`](../docs/framework/conventions.md), section 2.

## Short title — `short_title`

The `short_title: true` key in `config.yaml` requires a `short_title` field in the front matter and the file name `<id>-<short_title>.md`, e.g. `REQQF-FR-BOOKING-001-room-booking.md`. The field is 1–4 English words of lowercase letters and digits, joined by hyphens. Without the key or with `false` the file name equals the `id`, and the validator does not check the field. A missing field and a wrong pattern are a `schema` error at `short_title`, and a mismatching file name — at `id`. An invalid key value ends validation with code `3`. Rules: `conventions.md`, section 2.

## Folder layout — `enforce_layout`

The `enforce_layout: true` key in `config.yaml` requires a file in `requirements/` to lie in the folder that follows from `type` and the ID, and `category` to be consistent with them. Rule codes: `layout.path`, `layout.category`, `layout.nfr-code`. Without the key or with `false` the validator does not check the layout, and another value ends validation with code `3`. The rules are described in [`../docs/framework/conventions.md`](../docs/framework/conventions.md), section 2.

## Adding a new artifact type

1. Add the type to `TYPE_ENUM` and to the `ID_PATTERN`, `LEGACY_ID_PATTERN` and `REF_PATTERN` patterns in `reqq_common.py`, and to the same patterns in `schema/requirement.schema.json`.
2. Add `types/<TYPE>.schema.json` with the fields required for this type.
3. Register it in the `$ref` of the `allOf` block in `schema/requirement.schema.json`.
4. Add the requirements for type-specific fields in `validate_doc()` in `reqq_check_frontmatter.py` (section "Type-specific required fields").

See [`../docs/framework/conventions.md`](../docs/framework/conventions.md), section 2 ("Catalog discipline") — a new type should reflect something the repository really needs, not be imported "just in case".
