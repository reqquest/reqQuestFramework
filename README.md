# reqQuest Framework

The reqQuest Framework is a git-native methodology for managing requirements — business, functional, non-functional, architecture decisions, test cases, and policies — as version-controlled, machine-validated artifacts living alongside (or instead of) code, using the mechanisms git already provides: branches, commits, tags, and pull requests.

This repository publishes two things:

- **The methodology** — [`docs/framework/`](docs/framework/_index.md): why the framework works and how it turns requirements-engineering practice into git mechanisms.
- **The toolkit** — a ready-to-copy starter kit (`requirements/`, `.reqq/`) with a Python validator, released as the `raac-toolkit-X.Y.Z.tar.gz` asset.

This repository is also the toolkit's first adopter: its own CI validates the published examples with the published validator.

## Quick start

Download the asset from the [latest release](https://github.com/reqquest/reqQuestFramework/releases/latest) and follow the steps in [`docs/starter-kit.md`](docs/starter-kit.md#quick-start). The toolkit's structure, commands, and versioning model: [`.reqq/README.md`](.reqq/README.md).

## Contributing and security

Issues are welcome; pull requests are not accepted — see [`CONTRIBUTING.md`](CONTRIBUTING.md). Report vulnerabilities as described in [`SECURITY.md`](SECURITY.md).

## License

Licensed under the [Apache License, Version 2.0](LICENSE). See [`NOTICE`](NOTICE) for attribution.

The methodology cites the structure (not the text) of the materials of IREB e.V. (CPRE Foundation Level) and SIG-AIREB; the citation rules are in [`docs/framework/attribution-and-standards.md`](docs/framework/attribution-and-standards.md).

The Apache-2.0 license does not grant rights to the "reqQuest" name or trademarks.
