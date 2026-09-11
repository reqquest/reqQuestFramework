# .reqq — reqQuest Framework validator (starter kit)

A generic, stdlib-only front-matter schema validator for the `BR/FR/NFR/ADR/TC/POL` convention described in [`../docs/conventions.md`](../docs/conventions.md). Works out of the box, with no dependencies to install (`python3` with the standard library is enough).

**Installation:** download the `raac-toolkit-X.Y.Z.tar.gz` asset from the [`toolkit-vX.Y.Z`](https://github.com/reqquest/reqQuestFramework/releases) release and extract it **in the repo root**:

```bash
# The tarball's content sits inside a raac-toolkit-X.Y.Z/ directory — --strip-components=1
# removes that wrapper, so the files land in the repo root instead of a subdirectory.
tar xzf raac-toolkit-X.Y.Z.tar.gz --strip-components=1

# The validator configuration is local (not part of the package, `upgrade` never touches it):
cp .reqq/validator/config.example.yaml .reqq/validator/config.yaml

# Record the adopted toolkit version:
python3 .reqq/validator/reqq_validate_stdlib.py adopt --version X.Y.Z
```

The package boundary — a closed list of paths — is defined by [`../toolkit-manifest.json`](../toolkit-manifest.json). A manual `cp -r .reqq/ requirements/ .reqqignore` also works, but it won't record `toolkit.lock`, so `check` / `upgrade` will have no reference point.

## Structure

```
.reqq/
  schema/
    requirement.schema.json    # base front-matter schema (shared fields + references to types/*)
    types/
      BR.schema.json
      FR.schema.json            # requires `category`
      NFR.schema.json           # requires `category`
      ADR.schema.json           # requires `decisions`
      TC.schema.json             # requires `derives_from`
      POL.schema.json           # requires `category`
  validator/
    reqq_validate_stdlib.py     # the validator — the only file CI/the hook runs
    config.example.yaml         # config template — copy to config.yaml
    config.yaml                 # local config (outside the toolkit boundary, not in the package)
  hooks/
    pre-commit                  # runs the validator on staged files
```

`schema/*.json` is contract documentation (readable, useful in code review and for integrating with external tools that read JSON Schema) — `reqq_validate_stdlib.py` implements the same contract independently, to work without a dependency on the `jsonschema` library. Changing the requirements for a given type requires updating both places.

## Usage

```bash
# Install the hook (once, per repository clone):
git config core.hooksPath .reqq/hooks

# Full validation:
python3 .reqq/validator/reqq_validate_stdlib.py --all

# Validate only staged files (same as the pre-commit hook):
python3 .reqq/validator/reqq_validate_stdlib.py --staged-only

# JSON output (for CI integration):
python3 .reqq/validator/reqq_validate_stdlib.py --all --format json
```

Exit code: `0` = OK, `2` = validation errors, `3` = configuration error.

## Toolkit versioning (ADR-TOOLKIT-001)

Managing the toolkit version in an adopting repository:

```bash
# Init — record the current toolkit state as v1.0.0
python3 .reqq/validator/reqq_validate_stdlib.py adopt --version 1.0.0

# Check — is a newer version available, have files drifted
python3 .reqq/validator/reqq_validate_stdlib.py check

# Same, as a CI step — honors `toolkit.update_check` from config.yaml
python3 .reqq/validator/reqq_validate_stdlib.py check --ci
```

### `adopt`

Creates `.reqq/toolkit.lock` — a manifest of the version and checksums of the toolkit boundary
files (D3). Two consecutive runs produce an identical file apart from the `installed_at` field.

`--local-override PATH ...` marks files that should go through a 3-way merge on upgrade instead
of a hard replace. Relative paths are resolved against the working directory, so
`--local-override README.md` from `requirements/` means the same as `--local-override
requirements/README.md` from the repo root. A path outside the toolkit boundary is rejected
with a warning — a silently accepted override would be overwritten on the first upgrade anyway.

### `check`

Compares the local state against `toolkit.lock` and the latest `toolkit-v*` release on the
`stable` / `next` channel. Exit codes:

| Code | Meaning |
|---|---|
| `0` | no drift (an available newer version is reported as a warning, **not** an error) |
| `2` | local drift relative to `toolkit.lock` |
| `3` | missing or corrupt `toolkit.lock`, failure fetching the release list |

`--ci` enables a CI-step mode controlled by the `toolkit:` key in `config.yaml` (D5):

| `update_check` | Behavior |
|---|---|
| no `toolkit:` key / `manual` | no-op, exit `0` |
| `ci-notify` | `::warning::` annotations, **never** fails |
| `ci-pr` | same as above, but an available update → exit `2` (signal to open a PR) |

### `upgrade`

Downloads the `raac-toolkit-*.tar.gz` assets for the version currently recorded in
`toolkit.lock` and for the target version, verifies each against the `SHA256SUMS` block in the
release body, then runs a per-file 3-way merge. The reference point is the first release —
[`toolkit-v1.0.0`](https://github.com/reqquest/reqQuestFramework/releases/tag/toolkit-v1.0.0).
Without `toolkit.lock` it exits with code `3` (run `adopt` first); a checksum mismatch also
aborts the upgrade instead of merging from an unverified package.

Per-file states the engine distinguishes at `vA → vB` (D6):

| Condition | Action |
|---|---|
| unchanged locally | replace with the `vB` version |
| changed and listed in `local_overrides` | 3-way merge, conflicts marked `<<<<<<< local` / `\|\|\|\|\|\|\| vA` / `>>>>>>> vB` |
| changed, not in `local_overrides` | replace + warning |
| new in `vB` | added (or recreated, if the adopter had deleted it) |
| new in `vB`, but the adopter already has this file | local version kept + collision reported |
| removed in `vB`, unchanged locally | removed |
| removed in `vB`, changed locally | kept + reported for manual decision |

`--dry-run` runs the merge into a temporary file, so it reports the real conflict count without
touching the working tree.

### `min_toolkit_version`

An optional key at the root of `.reqq/schema/requirement.schema.json`. When set, validation
exits with code `3` if `toolkit.lock.toolkit_version` is older (D7). No key = no constraint; a
repository without `toolkit.lock` gets a warning, not an error.

The `.reqq/toolkit.lock` file is listed in `.reqqignore` and `exclude_globs` (D3). This
validator would not touch it anyway (it only scans `requirements/**/*.md`), but the contract
binds several copies of the validator, so the exclusion is declared, not assumed.

Details: the ADR-TOOLKIT-001 architecture decision record (outside this toolkit's boundary).

## Exclusions — `.reqqignore` and `config.yaml`

Two independent, additive mechanisms:

- **`.reqqignore`** (repo root) — a format like `.gitignore` (one glob per line, `#` comments). Portable, independent of the validator implementation — see [`../docs/conventions.md`](../docs/conventions.md), section 6.
- **`config.yaml`** → `exclude_globs` — exclusions specific to this validator, plus `require_full_traceability` (bool) controlling whether an FR/NFR without `traces_to` blocks validation, or only `category`/`decisions`/`derives_from` per type. The file is **local** — it lies outside the toolkit boundary (ADR-TOOLKIT-001 D1), so `upgrade` never overwrites it; the package only ships `config.example.yaml`. The validator also works without it (`require_full_traceability` defaults to `true`, no `toolkit:` block = `check --ci` is a no-op).

## Adding a new artifact type

1. Add the prefix to `ID_PATTERN` and `TYPE_ENUM` in `reqq_validate_stdlib.py`.
2. Add `types/<PREFIX>.schema.json` with the fields required for that type.
3. Register it in the `$ref` of the `allOf` block in `schema/requirement.schema.json`.
4. Add the type-specific field requirements in `validate_doc()` (the "Type-specific required fields" section).

See [`../docs/conventions.md`](../docs/conventions.md), section 2 ("Catalog discipline") — a new prefix should reflect something the repository actually needs, not be imported "just in case".
