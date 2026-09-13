# Changelog

All notable changes to the **reqQuest Framework toolkit** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0/).

Toolkit releases are tagged `toolkit-vX.Y.Z` and versioned independently of the
methodology docs (`docs-vX.Y.Z`) — see the ADR-TOOLKIT-001 architecture decision record
(outside this toolkit's boundary), D1.
The tarball boundary is defined by [`toolkit-manifest.json`](toolkit-manifest.json).

## Migration

Version-specific upgrade notes. A MAJOR bump always adds a subsection here
(ADR-TOOLKIT-001 D7); MINOR/PATCH releases usually need nothing.

### toolkit-v1.1.0

Initial public release — the canonical, frozen state of the starter kit. There is
nothing to migrate _from_. A repository adopts it by generating `.reqq/toolkit.lock`:

```bash
python3 .reqq/validator/reqq_validate_stdlib.py adopt --version 1.1.0
```

Repositories that already carry a drifted copy of `.reqq/` run `adopt` to record their
current hashes, then reconcile against `v1.0.0` — either a PR that pulls the file back
to canon, or a deliberate `local_overrides` entry for a difference that is meant to stay.

---

## [toolkit-v1.2.1]() (2026-09-13)

### Fixed

* fix(ci): REQQF#9 — Nyx Publish now actually creates the GitHub Release (#10) - mkarwasz-reqquest-dev


