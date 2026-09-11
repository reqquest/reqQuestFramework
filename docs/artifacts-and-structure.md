---
title: Artifacts and Structure
owner: reqQuest
status: draft
last_updated: 2026-08-16
tags: [reqquest-framework, ireb, work-products, documentation]
---

# Artifacts and Structure

> **Level:** Foundation of the methodology
> **Owner:** reqQuest
> **Implements:** CPRE Foundation Level Handbook, chapter Work Products and Documentation Practices (see the methodology's standards-attribution mapping, outside this toolkit's boundary)

IREB distinguishes three forms of documenting a requirement: natural language, a structured template, and a model. The reqQuest Framework does not mandate choosing one of them — all three coexist as file types in the same repository, chosen according to whichever best describes a given piece of knowledge.

## Mapping table

| IREB practice | reqQuest Framework mechanism | Proof of compliance | What breaks without it |
|---|---|---|---|
| **Work Products** — an artifact has a characteristic, an abstraction level, a level of detail | Every file has front matter declaring its role (`title`, `owner`, `status`, `tags`); the abstraction level follows from its place in the reqQuest Framework directory hierarchy: **L0 = artifact type** (Discovery, ADR, Requirement), **L1 = category** — required conditionally, where it makes sense (e.g. for Requirements: functional/non-functional/business), skippable for types that don't need it (Discovery) | A file without front matter or without a clear place in the L0/L1 hierarchy is detectable (lint, structure review) | Documents mix abstraction levels in a single file — the reader doesn't know whether they're reading strategy or an implementation detail |
| **Natural-Language-Based Work Products** | Markdown prose — description of context, rationale, narrative (e.g. an "Objective", "Context" section in every document) | Readable by a human without an intermediary tool — a `.md` file opened in any editor is complete | Contextual knowledge (why, not just what) is lost, leaving dry data without justification |
| **Template-Based Work Products** | Front matter as a "phrase template" (standardized fields) + template files as a "form template" for whole documents | A machine-validatable schema — see `.reqq/schema/types/*.schema.json` in this repo | Every author invents their own document structure, comparison and aggregation become manual |
| **Model-Based Work Products** | Diagrams as code — Mermaid embedded directly in Markdown instead of binary files, broken down into four kinds of model (see the section below) | The diagram renders from text in the repo — a model change is a commit with a readable diff, not a swapped-out image | The architecture diagram lives outside the repo (Miro, Confluence) and drifts from reality over time |
| **Glossaries** | One logical glossary, formed as the logical union of two physical files: a base one (supplied by the methodology/product) and a client extension (project-specific) — the first concrete example of the "reqQuest Framework native vs. client extensions" pattern (see the vision and principles document, principle 7 — Evolution) | Every term has one source of definition within its layer (base or client), a change goes through the same PR review as any other change | The same term means something different across documents — see the "Shared understanding" principle in the vision and principles document, principle 3 |
| **Requirements Documents & Documentation Structures** | The allowed documentation structure is **data, not an unwritten convention**: a schema (`schema.json` or equivalent) declares the allowed file types, required fields, and relationships between them, regardless of which specific tool enforces it (see the tooling documentation) | The validator fails CI on a broken structure/schema mismatch | Documents exist but don't form a coherent, navigable whole — the reader has no way to go from the general to the specific; without a declarative schema, structure depends on authors' memory, not on a machine-verifiable rule |
| **Prototypes** | A two-state model: every new branch/requirement/idea has status **draft** by default; only after approval by an authorized person does it get status **approved/accepted**, and only then is it treated as a source for further work, including by AI agents. A feature branch is itself already a safe place to experiment until it reaches `accepted` — the reqQuest Framework deliberately does not introduce a separate, third "prototype"/"SPIKE" status | The `status` field in front matter (see [`conventions.md`](conventions.md)): no `accepted` = not recognized as a requirements source | An experimental concept without a clear status lands on the main branch, or is treated as a requirements source before anyone approved it |
| **Quality Criteria for Work Products and Requirements** | Two independent mechanisms: **form quality** (formatting consistency, link correctness, schema compliance) enforced automatically by lint + CI, regardless of reviewer attention; **substantive quality** (whether the content reflects a real need, whether it is coherent) is always a human decision made at Pull Request approval — even when supported by an AI agent's or tool's recommendation (see the tooling documentation and the documentation on AI's role in the framework). A human serves as the substantive-quality gate, not the form gatekeeper — that part is already automated | Form: lint, JSON schema validation — every check has a 0/1 exit code, not an opinion. Content: a PR approval by a specific person, recorded in git history — durable proof that substantive validation took place | Form quality depends on whether someone happened to check it manually — unsystematic, non-repeatable; skipping substantive validation or blindly trusting an AI recommendation leads to requirements that don't reflect real needs |

## Four kinds of models — the difference between diagram types

The CPRE Foundation Level Handbook breaks "model" down into four kinds, depending on exactly what it is meant to describe — the reqQuest Framework adopts this breakdown, because without it "let's make a diagram" is a question without an answer (a diagram of what?):

| Model kind | What it shows | Mermaid pattern in the reqQuest Framework | Example in this documentation |
|---|---|---|---|
| **Context** | The system boundary and its surroundings — who/what is external, which relationships cross the boundary | A `flowchart` with a single system frame and surrounding nodes outside it | The methodology documentation (context diagram) — the reqQuest Framework as a system in relation to CPRE Foundation Level and its applications |
| **Data structure** | What elements an artifact is made of and how they relate to each other (not behavior over time) | `classDiagram` or `erDiagram` | The front-matter schema — see [`conventions.md`](conventions.md), section 1 |
| **Function/flow** | How data/decisions flow through successive process steps | A sequential `flowchart` | The problem→requirement→ADR flow — see the problem-to-requirement guide |
| **State/behavior** | The possible states of an artifact and the allowed transitions between them | `stateDiagram-v2` | The `draft → review → accepted → deprecated` life cycle — see [`requirements-management.md`](requirements-management.md) |

Choosing the right kind of model for the question it needs to answer matters more than the mere presence of a diagram — a state diagram drawn as a flowchart answers the wrong question, even if it technically renders.

## The L0/L1 hierarchy and the Discovery type

The L0 level defines the set of allowed artifact types in a reqQuest Framework repository, including at least: **Discovery** (an early, informal record of a discovered problem or source), **Requirement** (a formalized elicitation product), and **ADR** (an architecture/design decision). The L1 level refines the category within a given L0 type where that is warranted — for Requirements this is usually functional/non-functional/business; ADR and Discovery generally do not need an L1 category. Levels deeper than L1 (further category decomposition) are deliberately left undefined today — the next iteration of the hierarchy adds them wherever a specific project actually needs it, following the catalog-discipline principle (see [`conventions.md`](conventions.md), section 2): a level of detail is not defined ahead of time, before real usage appears.

Discovery is a formal but deliberately lightweight type: it is always an **input** to elicitation, never its **output** — the output of elicitation is the requirement (see the problem-to-requirement guide). In the repository it may materialize as a Markdown file (a dated note with participants) or as a git-hosting-platform Issue — both forms are the same L0 artifact under a different technical shell; the reqQuest Framework does not prefer one over the other, as long as it is unambiguously identifiable and linkable from the requirement it produced.

**Proposed minimal Discovery field schema** *(recommendation pending approval, not a settled mandate):*
```yaml
id: <DISC-NNN>
source: <link to the meeting / conversation / observation / source document>
date: <YYYY-MM-DD>
participants: [<list of participants or sources, if applicable>]
status: open | promoted | archived   # promoted = a requirement was created from it
leads_to: [<ID of the requirement(s), if status: promoted>]
```

Rationale for the field choices: `source` is the only hard requirement today (without it, Discovery doesn't fulfill its role as proof of origin — see the problem-to-requirement guide); `status`/`leads_to` close the Discovery→Requirement loop with an explicit link instead of guessing from date or content. The remaining fields (`date`, `participants`) repeat the pattern already adopted for other artifact types (see [`conventions.md`](conventions.md), section 1) — deliberately, so Discovery doesn't require learning a separate schema.

## Why this matters for the reqQuest Framework

The most important consequence of this page: **in the reqQuest Framework, form quality is something CI can check automatically**, not something that depends on reviewer attention. This is a direct implementation of principle 9 from the vision and principles document ("systematic and disciplined work") — discipline stops being a matter of memory and becomes a merge-blocking check.

## Related documents

- the methodology documentation — map of the whole methodology
- [`conventions.md`](conventions.md) — the concrete front-matter and ID schema implementing the practices described above
- the problem-to-requirement guide — where the artifacts described here come from
