---
title: reqQuest Framework Conventions — Starter Kit
owner: reqQuest
status: draft
last_updated: 2026-08-16
tags: [reqquest-framework, conventions, starter-kit]
---

# reqQuest Framework Conventions — Starter Kit

> **Level:** Practical — ready to copy

## How to read this document

The vision and principles document, [`artifacts-and-structure.md`](artifacts-and-structure.md), the problem-to-requirement guide, [`process-and-working-modes.md`](process-and-working-modes.md), and [`requirements-management.md`](requirements-management.md) explain the *why* — how IREB requirements translate into git mechanisms. This document is the *how* — a concrete, ready-to-copy set of conventions you can start managing requirements with immediately in any repository, regardless of whether it holds code, legal documents, or HR policy. **This is a configurable pattern, not a mandate** — the conventions below are implemented directly in this repository's root (`requirements/`, `.reqq/`, `.reqqignore` — see [`../requirements/README.md`](../requirements/README.md) and [`../.reqq/README.md`](../.reqq/README.md)), ready to copy into a new project, but the reqQuest Framework does not require exactly these prefixes or exactly these status values, only the presence of an equivalent for each category.

## 1. Front-matter schema

Minimal set of fields, implementing the "Attributes" and "Work Products" practices (artifact characterization):

```yaml
---
title: <readable title>
owner: <responsible role or person>
status: draft | review | accepted | deprecated
last_updated: <YYYY-MM-DD>
tags: [<keywords for filtering>]
---
```

Optional extensions, added when the artifact needs them (`id`/`version` fields — see section 2 below for examples of their practical use):

```yaml
id: <PREFIX-NNN>       # see section 2
version: "<major.minor>"
traces_to: [<ID>, ...]  # see section 4
```

## 2. ID and prefix convention

Pattern: `PREFIX-NNN`, where the prefix uniquely identifies the artifact type and the number is unique within the prefix. The prefix is not just a label: in practice it maps directly onto the validator configuration, which defines the fields/attributes automatically checked for that artifact type (e.g. a different set of required fields for `ADR-<CATEGORY>-NNN` than for a functional requirement). An adopter can extend the prefix catalog freely, subject to two mandatory requirements: **uniqueness** of the prefix within the repository and **stability over time** (a number once assigned is never reused, even after the artifact is deleted) — and every new prefix requires a matching validator configuration, not just a table entry.

**Catalog discipline:** the set of prefixes/categories in a given repository should reflect only what is actually used in it — do not import categories from sibling repositories or maintain a catalog much wider than the set actually in use. Unused-category sprawl makes onboarding and schema maintenance harder for no benefit.

**Convention implemented in this repo, ready to copy directly** (see [`../requirements/README.md`](../requirements/README.md) for the full directory skeleton and [`../.reqq/schema/types/`](../.reqq/schema/types/) for the JSON schema of each type):

| Prefix | Artifact type | Where |
|---|---|---|
| `BR-NNN` | Business Requirement | `requirements/business/` |
| `FR-<CATEGORY>-NNN` | Functional Requirement | `requirements/functional/<CATEGORY>/` |
| `NFR-<CATEGORY>-NNN` | Non-Functional Requirement | `requirements/nonfunctional/<category>/` |
| `ADR-<CATEGORY>-NNN` | Architecture Decision Record | `requirements/adrs/` |
| `TC-<CATEGORY>-NNN` | Test Case | `requirements/testcases/` |
| `POL-<CATEGORY>-NNN` | Policy | `requirements/policies/` |

This exact set of prefixes is independently dogfooded today across several private reqQuest repositories (per-type schema + validator + pre-commit hook + CI gate) — stronger evidence of domain neutrality and repeatability than a single example. An alternative for ADR numbering seen in practice: globally sequential `ADR-NNNN` (without a category segment) — both conventions satisfy the uniqueness and stability requirement; the choice between them depends on whether the repository has enough architectural decisions across different areas for category segmentation to make sense.

## 3. Life-cycle values (`status`)

Implementation of the "Life Cycle Management" practice. Recommended minimal set:

| Value | Meaning | Equivalent IREB concept |
|---|---|---|
| `draft` | Being created, not yet reviewed | Work product before validation |
| `review` | Submitted for approval (open PR) | Undergoing validation |
| `accepted` / `active` | Approved, in effect | Baseline |
| `deprecated` | Superseded or outdated, historical entry | Outside active scope, but still traceable |

## 4. Traceability convention

Implementation of the "Traceability" practice — two complementary levels:

**a) Structural (front matter)** — the `traces_to` field or equivalent, listing the IDs of source artifacts:

```yaml
traces_to: [<source-ID-1>, <source-ID-2>]
```

**b) Inline (comment in the body)** — the source cited directly next to the fragment it concerns:

```markdown
<!-- source: <source-ID> | <short source description> | <version> -->
## Fragment of the document this source concerns
...
```

The choice between (a) and (b) depends on granularity: (a) is enough when the whole file comes from a single source; (b) is needed when different fragments of the same document come from different sources. A full, end-to-end traced example of both levels at once lives in the methodology's case-study documentation (outside this toolkit's boundary).

## 5. Configurations and baselines

- **Configuration** (a consistent set in progress) = a branch.
- **Baseline** (a frozen, named reference point) = a git tag or release.

Rule: a baseline is never edited retroactively — a change after a baseline is established is always a new tag, never an overwrite of the old one (equivalent to the "Unchangeability" property of a configuration, see [`requirements-management.md`](requirements-management.md)).

## 6. Minimal set of CI checks

Implementation of the "Quality Criteria" practice as a machine-enforced check, not a declaration:

- Markdown format lint,
- front-matter schema/structure validation wherever an artifact has a rigid contract — in this repo: `.reqq/validator/reqq_validate_stdlib.py`, also run as a pre-commit hook (`.reqq/hooks/pre-commit`),
- **exclusions from validation via `.reqqignore`** — a file in a format analogous to `.gitignore` (one glob per line), in the repository root, honored by the validator regardless of which specific implementation replaces it. A portable equivalent of `exclude_globs` from `.reqq/validator/config.yaml` — the same file works regardless of which tool the repository actually uses to manage requirements.

None of the above is specific to software development — all of them work identically on a repository that does not contain a single line of production code.

## 7. Business rationale document (starter type)

The reqQuest Framework requires that every repository adopting the methodology have one, explicitly identifiable document serving as the project's **business rationale** — a place recording things that cannot be inferred from the requirement files alone. **The name and exact location of this file in a given repository is a project decision, not a mandate of this methodology** — what follows describes the required purpose and content, not a specific path.

The business rationale document should contain at least:

- The project/repository's **objective and business rationale** — the top-level business requirement all other requirements relate to.
- A **declared combination of IREP process facets** (Linear/Iterative, Prescriptive/Explorative, Customer-specific/Market-oriented) — see [`process-and-working-modes.md`](process-and-working-modes.md). Without this explicit declaration, different parts of the team easily end up working on conflicting, never-agreed assumptions about the working mode.
- The project's **role catalog**, extending the minimal catalog defined in the methodology documentation (scope and roles) (human as author/reviewer, AI agent under human supervision) with domain-specific roles, if the project needs them.

This is a **living** document — the roles it describes are relatively stable, but the specific people filling those roles change over time; a change of person should not require rewriting the rest of the documentation.

**Name and location adopted in this repo (recommendation, not a mandate):** `requirements/00-context/objectives-and-scope.md`, in the directory that numerically precedes the requirement folders, so alphabetical order reflects reading order.

**Role-responsibility matrix → reviewer assignment — proposal.** The role catalog from this document determines *who can be* a reviewer for a given area; the mechanism that *enforces* this is git's native `CODEOWNERS` mechanism (or its equivalent on another hosting platform) — a file mapping directory/file paths to roles/people, automatically requiring their approval on a Pull Request touching that path. Recommended minimal matrix row:

```
# CODEOWNERS
requirements/business/**   @role-product-owner
requirements/functional/** @role-tech-lead
requirements/adrs/**       @role-architect
```

Mapping roles to technical git permission levels (owner/maintainer/developer, beyond `CODEOWNERS` itself) remains an open, hosting-platform-specific implementation concern — not part of this convention.

## Related documents

- [`requirements-management.md`](requirements-management.md) — the full rationale behind the conventions above
- [`artifacts-and-structure.md`](artifacts-and-structure.md) — rationale for the front-matter schema
- the case-study documentation (outside this toolkit's boundary) — the conventions above applied to a live example
- [`../requirements/README.md`](../requirements/README.md), [`../.reqq/README.md`](../.reqq/README.md) — this document's implementation as a ready-to-copy starter kit
