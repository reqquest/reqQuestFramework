# Requirements (reqQuest Framework) — starter kit

This directory is a **ready-to-copy starter kit**, not just documentation — it implements the conventions described in [`../docs/conventions.md`](../docs/conventions.md). Copy the whole `requirements/` directory (together with `.reqq/` and `.reqqignore` from the repo root) into a new project, replace the examples (`*-DEMO-*`) with your own content, and start.

## Struktura

```
requirements/
  00-context/                  # project context (no front matter, excluded from validation via .reqqignore)
    objectives-and-scope.md    # business rationale document — see conventions.md, section 7
    stakeholders.md
    glossary.md
  business/                    # BR — business requirements
    BR-DEMO-001.md
  functional/
    DEMO/                      # category placeholder — replace with your own (e.g. AUTH/, BOOKING/)
      FR-DEMO-001.md
  nonfunctional/
    performance/                # NFR-* grouped by non-functional category
      NFR-DEMO-001.md
  adrs/                        # ADR-<CATEGORY>-NNN — architecture decisions
    ADR-DEMO-001.md
  testcases/                   # TC-* — test cases
    TC-DEMO-001.md
  policies/                    # POL-* — policies and constraints
    POL-DEMO-001.md
```

**Deliberately omitted:** `metrics/` (traceability.csv/coverage.json as committed files) — see [`../docs/requirements-management.md`](../docs/requirements-management.md), section "Coverage — proposed definition": committed metric-aggregation files generate merge conflicts proportional to how often requirements change. Traceability/coverage is a function of tooling (grep over `traces_to`/`derives_from`, or a dedicated tool), not a file in this directory.

## Requirement file format

Every requirement file starts with a YAML front-matter block — full field description in [`../docs/conventions.md`](../docs/conventions.md), section 1–2:

```yaml
---
id: FR-DEMO-001
title: <readable title>
type: FR
status: draft | review | approved | deprecated
owner: <responsible role or person>
version: "1.0"
last_updated: <YYYY-MM-DD>
tags: [<keywords>]
category: <CATEGORY>          # required for FR/NFR/POL
traces_to: [BR-DEMO-001]        # optional, but required for FR/NFR when require_full_traceability: true
---
```

Type-specific fields (`category` for FR/NFR/POL, `decisions` for ADR, `derives_from` for TC) are enforced by `.reqq/schema/types/*.schema.json` and `.reqq/validator/reqq_validate_stdlib.py` — see [`../.reqq/README.md`](../.reqq/README.md).

## How to verify

```bash
python3 .reqq/validator/reqq_validate_stdlib.py --all
```

All examples (`*-DEMO-*`) in this directory pass validation without exceptions — this is both proof that the schema and validator work, and a pattern to follow when writing your own requirements.
