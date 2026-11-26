# Requirements (reqQuest Framework) — starter kit

This folder is a **skeleton from the reqQuest Framework toolkit**, not just documentation — it implements the conventions described in [`conventions.md`](https://github.com/reqquest/reqQuestFramework/blob/main/docs/framework/conventions.md). You install the toolkit from the `raac-toolkit-X.Y.Z.tar.gz` asset of a public repository release and the `adopt` command — steps in [`.reqq/README.md`](https://github.com/reqquest/reqQuestFramework/blob/main/.reqq/README.md). Then replace the examples with your own content and start.

## Structure

```
requirements/
  AGENTS.md                    # instructions for AI agents — toolkit file, do not edit
  AGENTS.project.md            # project rules for AI agents — starting file, then yours (upgrade does not touch it)
  CLAUDE.md                    # imports both files for Claude Code — toolkit file
  00-context/                  # project context (no front matter, excluded from validation by .reqqignore)
    objectives-and-scope.md    # business case document (example) — starting file, then yours
    stakeholders.md            # stakeholders (example) — starting file, then yours
    roles.example.yaml         # example role catalog — copy it to roles.yaml when you enable governance
    glossary.md                # base glossary — toolkit file, do not edit
    glossary.project.md        # project glossary — starting file, then yours (upgrade does not touch it)
  business/                    # BR-<CATEGORY>-NNN — business requirements
    REQQF-BR-BOOKING-001-self-service-booking.md
  functional/                  # FR-<CATEGORY>-NNN — a folder per category (feature)
    BOOKING/
      REQQF-FR-BOOKING-001-room-booking.md
      REQQF-FR-BOOKING-002-booking-api.md   # interface requirement with an OpenAPI fragment
    AUTH/
      REQQF-FR-AUTH-001-sso-login.md
  nonfunctional/               # NFR-<ABBREV>-NNN — a folder per quality attribute
    performance/
      REQQF-NFR-PERF-001-room-list-load-time.md
    security/
      REQQF-NFR-SEC-001-session-timeout.md
  adrs/                        # ADR-<CATEGORY>-NNN — architecture decisions
    REQQF-ADR-BOOKING-001-concurrent-booking-lock.md
    REQQF-ADR-AUTH-001-oidc-login.md
  testcases/                   # TC-<CATEGORY>-NNN — test cases
    REQQF-TC-BOOKING-001-reject-conflicting-booking.md
  policies/                    # POL-<CATEGORY>-NNN — policies and constraints
    REQQF-POL-BOOKING-001-long-booking-approval.md
    REQQF-POL-PRIVACY-001-booking-data-retention.md
```

**Type and category:** the type (`BR`, `FR`, `NFR`, `ADR`, `TC`, `POL`) sets the folder and the ID part after the repository prefix, and the next ID part is the category. Functional requirements have a folder per category, i.e. feature (`functional/BOOKING/`, `functional/AUTH/`), and non-functional ones a folder per quality attribute: an abbreviation in the ID (`REQQF-NFR-PERF-001`, at most 10 characters), the full name in the folder and in the `category` field (`performance`). The other types lie flat in the type folder, and only the ID carries the category. With `enforce_layout: true` in `.reqq/validator/config.yaml` the validator requires this layout.

**Examples:** the requirements files in the tree come from a fictional domain (a meeting-room booking system) and start with the note "Example … (fictional domain)". They have the numbers `001`–`099`, the tag `example`, the `REQQF` prefix of the framework repository and a short title in the file name (`config.example.yaml` declares `id_prefix: REQQF` and `short_title: true`). Once you set `id_prefix` to your own repository's key, the validator reports every example left behind. Together with `objectives-and-scope.md`, `stakeholders.md`, `roles.example.yaml` and `glossary.project.md` they are starting files: they arrive with the first toolkit install, then belong to the project — replace or delete them; upgrade will neither restore nor overwrite them.

**Instructions for AI agents:** an agent working in this folder reads [`AGENTS.md`](AGENTS.md) with the framework rules and `AGENTS.project.md` with the project rules, which take precedence; `CLAUDE.md` imports both files for Claude Code. Add project rules to `AGENTS.project.md`, not to `AGENTS.md`. How they work in Claude Code and Codex: [`starter-kit.md`](https://github.com/reqquest/reqQuestFramework/blob/main/docs/starter-kit.md#instructions-for-ai-agents), section "Instructions for AI agents".

**Deliberately left out:** `metrics/` (traceability.csv/coverage.json as committed files) — see [`requirements-management.md`](https://github.com/reqquest/reqQuestFramework/blob/main/docs/framework/requirements-management.md), section "Coverage — a proposed definition": committed files that aggregate metrics cause merge conflicts in proportion to how often requirements change. Traceability/coverage is a function of tooling (grep over `traces_to`/`derives_from`, or a dedicated tool), not a file in this folder.

**Owners:** the `owner` field names the role responsible for the requirement. From the governance level `catalog` (`ownership.mode` in `.reqq/validator/config.yaml`) it is a role key from `00-context/roles.yaml` (a copy of the example `00-context/roles.example.yaml` with your roles and `handle`s), e.g. `role-architect`, and from the level `generate` the CODEOWNERS block is built from this catalog. The levels and how to enable them are described in [`.reqq/README.md`](https://github.com/reqquest/reqQuestFramework/blob/main/.reqq/README.md).

## Glossary and the direction of definitions

The glossary is **one logical glossary from two files** in `00-context/`:

- [`glossary.md`](00-context/glossary.md) — **base**: methodology terms and the glossary rules. The toolkit delivers it; a local change is drift and will be overwritten on upgrade.
- [`glossary.project.md`](00-context/glossary.project.md) — **project**: the terms of your domain and architecture. A starting file: it arrives with the first toolkit install as a template, then belongs to the project — upgrade does not touch it.

**Definitions flow from the glossary to the requirements, not the other way.** You define a term used in more than one document only in the glossary — nowhere in a document, not only in a "Definitions" section — and the documents refer to it. A normative statement (a requirement or decision that sets a rule for the term) stays in the document as the source the glossary cites. A "Definitions" section in a requirements document contains only terms used solely in it, or a narrowing of a glossary term with a reference. When a local term appears in a second document, move it to the glossary in the same PR. Field names, error codes and contract constants stay in the requirement that defines the contract. Full rules: [`glossary.md`](00-context/glossary.md), "Direction of definitions: glossary → requirements".

## Requirement file format

Every requirement file starts with a YAML front matter block — full description of the fields in [`conventions.md`](https://github.com/reqquest/reqQuestFramework/blob/main/docs/framework/conventions.md), sections 1–2:

```yaml
---
id: REQQF-FR-BOOKING-001
title: <readable title>
type: FR
status: draft | review | approved | deprecated
owner: <role or person; from the catalog level a role key from 00-context/roles.yaml>
version: "1.0"
last_updated: <YYYY-MM-DD>
tags: [<keywords>]
category: <CATEGORY>          # required for FR/NFR/POL
traces_to: [REQQF-BR-BOOKING-001]        # optional, but required for FR/NFR with require_full_traceability: true
---
```

Type-specific fields (`category` for FR/NFR/POL, `decisions` for ADR, `derives_from` for TC) are enforced by `.reqq/schema/types/*.schema.json` and `.reqq/validator/reqq_validate.py` — see [`.reqq/README.md`](https://github.com/reqquest/reqQuestFramework/blob/main/.reqq/README.md).

The optional `conflict` field records a conflict with another requirement; an entry without `resolution` blocks the status `approved` — see [`conventions.md`](https://github.com/reqquest/reqQuestFramework/blob/main/docs/framework/conventions.md), section 1.

## How to verify it

```bash
python3 -m venv .venv                                        # once (PEP 668); add .venv/ to .gitignore
source .venv/bin/activate                                    # the hook uses python3 on PATH: keep the environment active when committing
python3 -m pip install -r .reqq/validator/requirements.txt   # once: the validator's libraries (Python >= 3.10)
python3 .reqq/validator/reqq_validate.py --all
```

All examples in this folder pass validation without exceptions — this is both proof that the schema and the validator work and a model to follow when you write your own requirements.
