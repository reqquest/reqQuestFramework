# reqQuest Framework

The reqQuest Framework is a git-native methodology for managing requirements — business, functional, non-functional, architecture decisions, test cases, and policies — as version-controlled, machine-validated artifacts living alongside (or instead of) code, using the mechanisms git already provides: branches, commits, tags, and pull requests.

This repository ships the **toolkit**: a ready-to-copy starter kit (`requirements/`, `.reqq/`, `toolkit-manifest.json`) plus a stdlib-only Python validator that enforces the front-matter schema for the `BR/FR/NFR/ADR/TC/POL` convention. No third-party dependencies required.

## Quick start

Download the `raac-toolkit-X.Y.Z.tar.gz` asset from the [latest release](https://github.com/reqquest/reqQuestFramework/releases) and extract it in your repository root:

```bash
tar xzf raac-toolkit-X.Y.Z.tar.gz --strip-components=1

# Local validator config (not part of the package):
cp .reqq/validator/config.example.yaml .reqq/validator/config.yaml

# Record the adopted toolkit version:
python3 .reqq/validator/reqq_validate_stdlib.py adopt --version X.Y.Z
```

Then validate at any time:

```bash
python3 .reqq/validator/reqq_validate_stdlib.py --all
```

And check for a newer toolkit release:

```bash
python3 .reqq/validator/reqq_validate_stdlib.py check
```

Upgrading an adopted repository to a newer toolkit version:

```bash
python3 .reqq/validator/reqq_validate_stdlib.py upgrade --version X.Y.Z
```

Full documentation of the toolkit's structure, commands, and versioning model: [`.reqq/README.md`](.reqq/README.md).

## Toolkit lock

`adopt` writes `.reqq/toolkit.lock` into the adopting repository: a small JSON manifest recording the toolkit version currently in place, the channel (`stable`/`next`), and a checksum per boundary file. It is the record a repository uses to track drift and to check for or apply upgrades (`check`, `upgrade`) — see [`.reqq/README.md`](.reqq/README.md#toolkit-versioning-adr-toolkit-001) for the full command reference.

A repository with no `.reqq/toolkit.lock` simply has not adopted a toolkit version yet — that is not an error condition, just a starting point. Run `adopt` (see Quick start above) to create one.

## Documentation

- [`requirements/README.md`](requirements/README.md) — the requirements starter kit, with worked examples
- [`docs/conventions.md`](docs/conventions.md) — the ID, front-matter, and life-cycle conventions the toolkit enforces
- [`docs/requirements-management.md`](docs/requirements-management.md) — how these conventions map onto IREB requirements-management practices
- [`docs/artifacts-and-structure.md`](docs/artifacts-and-structure.md) — artifact types and the L0/L1 directory hierarchy
- [`docs/process-and-working-modes.md`](docs/process-and-working-modes.md) — choosing a process that fits your project

## License

Licensed under the [Apache License, Version 2.0](LICENSE). See [`NOTICE`](NOTICE) for attribution.

The Apache-2.0 license does not grant rights to the "reqQuest" name or trademarks.
