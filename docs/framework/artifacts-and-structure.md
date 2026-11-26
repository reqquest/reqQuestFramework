---
title: Artifacts and Structure
owner: reqQuest
status: approved
last_updated: 2026-11-23
tags: [reqquest-framework, ireb, work-products, documentation]
---

# Artifacts and Structure

> **Level:** Foundation of the methodology
> **Owner:** reqQuest
> **Implements:** CPRE Foundation Level Handbook, chapter Work Products and Documentation Practices (see [`attribution-and-standards.md`](attribution-and-standards.md#handbook-mapping-table))

IREB distinguishes three forms of documenting a requirement: natural language, a structured template and a model. reqQuest Framework does not impose one of them — all three coexist as file types in the same repository, chosen according to the piece of knowledge they describe best.

## Mapping table

| IREB practice | reqQuest Framework mechanism | Proof of compliance | What breaks without it |
|---|---|---|---|
| **Work Products** — an artifact has a characteristic, a level of abstraction, a level of detail | Every file has front matter declaring its role (`title`, `owner`, `status`, `tags`); the level of abstraction follows from its place in the reqQuest Framework directory hierarchy: **L0 = artifact type** (Discovery, ADR, Requirement), **L1 = category** — required conditionally, where it makes sense (e.g. for Requirements: functional/non-functional/business), and omitted for types that do not need it (Discovery) | A file without front matter or without a clear place in the L0/L1 hierarchy is detectable (lint, structure review) | Documents mix levels of abstraction in one file — the reader does not know whether they are reading strategy or an implementation detail |
| **Natural-Language-Based Work Products** | Markdown prose — a description of context, rationale, narrative (e.g. a "Goal" or "Context" section in each document) | Readable for a human without an intermediary tool — a `.md` file opened in any editor is complete | Contextual knowledge (why, not only what) is lost; dry data without rationale remains |
| **Template-Based Work Products** | Front matter as a "phrase template" (standardised fields) + template files as a "form template" for whole documents | A schema that can be validated by machine — see `.reqq/schema/types/*.schema.json` in this repo | Every author invents their own document structure; comparison and aggregation become manual |
| **Model-Based Work Products** | Diagrams as code — Mermaid embedded directly in Markdown instead of binary files, split into four kinds of model (see the section below) | The diagram renders from text in the repo — a model change is a commit with a readable diff, not a swapped image | The architecture diagram lives outside the repo (Miro, Confluence) and drifts from reality over time |
| **Glossaries** | One logical glossary, made of the logical union of two physical files: the base one (delivered by the methodology/product, `requirements/00-context/glossary.md` in the toolkit boundary) and the client extension (specific to the project, `requirements/00-context/glossary.project.md` outside the toolkit boundary). Definitions flow from the glossary to the requirements documents: a term used in more than one document is defined only in the glossary (rules — [`../../requirements/README.md`](../../requirements/README.md), "Glossary and the direction of definitions") — the first concrete example of the "reqQuest Framework native vs client extensions" pattern (see [`vision-and-principles.md`](vision-and-principles.md), principle 7 — Evolution) | Every term has one source of definition within its layer (base or client), and a change goes through the same PR review as any other change | The same term means something different in different documents — see the principle "Shared understanding" in [`vision-and-principles.md`](vision-and-principles.md#3-shared-understanding) |
| **Requirements Documents & Documentation Structures** | The permitted documentation structure is **data, not an unwritten convention**: a schema (`schema.json` or equivalent) declares the permitted file types, the required fields and the relations between them, regardless of the specific tool that enforces it (see [`tooling.md`](tooling.md)) | The validator fails CI on a broken structure/schema mismatch | Documents exist but do not form a coherent, navigable whole — the reader has no way to go from the general to the detail; without a declarative schema the structure depends on the authors' memory, not on a rule that can be verified by machine |
| **Prototypes** | A two-state model: every new branch/requirement/idea has status **draft** by default; only after approval by an authorised person does it get status **approved**, and only then is it recognised as a source for further work, including by AI agents. A feature branch is in itself already a safe place to experiment until it reaches `approved` — reqQuest Framework deliberately does not introduce a separate, third status "prototype"/"SPIKE" | The `status` field in the front matter (see [`conventions.md`](conventions.md)): no `approved` = not recognised as a source of requirements | An experimental concept without a clear status reaches the main branch or is treated as a source of requirements before anyone has approved it |
| **Quality Criteria for Work Products and Requirements** | Two independent mechanisms: **quality of form** (consistent formatting, correct links, schema compliance) enforced automatically by lint + CI, regardless of the reviewer's attention; **quality of content** (whether the content reflects a real need, whether it is consistent) is always a human decision made at the approval of the Pull Request — even when supported by a recommendation from an AI agent or a tool (see [`tooling.md`](tooling.md), [`ai-in-framework.md`](ai-in-framework.md)). The human acts as the gate of content quality, not as the guardian of form — that is already automated | Form: lint, JSON schema validation — every check ends with a deterministic exit code (`0` = OK), not an opinion. Content: a PR approval by a specific person recorded in the git history — lasting proof that content validation took place | The quality of form depends on whether someone happened to check it by hand — unsystematic, unrepeatable; skipping content validation or blindly trusting an AI recommendation leads to requirements that do not reflect real needs |

## Four kinds of models — the difference between types of diagrams

The CPRE Foundation Level Handbook splits "model" into four kinds, depending on what exactly it is meant to describe — reqQuest Framework adopts this split, because without it "let's make a diagram" is a question without an answer (a diagram of what?):

| Kind of model | What it shows | Mermaid pattern in reqQuest Framework | Example in this documentation |
|---|---|---|---|
| **Context** | The system boundary and its environment — who/what is outside, which relations cross the boundary | `flowchart` with one system frame and environment nodes outside it | [`_index.md`](_index.md#context-diagram) — reqQuest Framework as a system in relation to CPRE Foundation Level and its applications |
| **Data structure** | Which elements an artifact consists of and how they relate to each other (not behaviour over time) | `classDiagram` or `erDiagram` | The front-matter schema — see [`conventions.md`](conventions.md), section 1 |
| **Function/flow** | How data/decisions flow through successive process steps | sequential `flowchart` | The flow problem→requirement→ADR — see [`from-problem-to-requirement.md`](from-problem-to-requirement.md) |
| **State/behaviour** | The possible states of an artifact and the permitted transitions between them | `stateDiagram-v2` | The lifecycle `draft → review → approved → deprecated` — see [`requirements-management.md`](requirements-management.md) |

Matching the right kind of model to the question it should answer matters more than the mere presence of a diagram — a state diagram drawn as a flowchart answers the wrong question, even if it technically renders.

## L0/L1 hierarchy and the Discovery type

Level L0 defines the set of permitted artifact types in a reqQuest Framework repository, covering at least: **Discovery** (an early, informal record of discovering a problem or a source), **Requirement** (the formalised product of elicitation) and **ADR** (an architecture/design decision). Level L1 refines the category within a given L0 type where that is justified — for Requirements it is usually functional/non-functional/business; ADR and Discovery usually do not need an L1 category. Levels deeper than L1 (further decomposition of categories) deliberately remain undefined today — a later iteration of the hierarchy adds them where a specific project actually needs them, in line with the catalog discipline rule (see [`conventions.md`](conventions.md), section 2): a level of detail is not defined in advance, before real use appears.

Discovery is a formal but deliberately lightweight type: it is always an **input** to elicitation, never its **product** — the product of elicitation is a requirement (see [`from-problem-to-requirement.md`](from-problem-to-requirement.md)). In the repository it can materialise as a Markdown file (a note with a date and participants) or as an Issue on the git hosting platform — both forms are the same L0 artifact in a different technical shell; reqQuest Framework does not prefer one over the other, as long as it is unambiguously identifiable and linkable from the requirement that came out of it.

**Proposed minimal field schema for Discovery** *(a recommendation for approval, not an established mandate):*
```yaml
id: <DISC-NNN>
source: <link to the meeting / conversation / observation / source document>
date: <YYYY-MM-DD>
participants: [<list of participants or sources, if applicable>]
status: open | promoted | archived   # promoted = a requirement came out of it
leads_to: [<ID of the requirement(s), if status: promoted>]
```

Rationale for the choice of fields: `source` is the only hard requirement already today (without it Discovery does not fulfil its role as proof of origin — see [`from-problem-to-requirement.md`](from-problem-to-requirement.md)); `status`/`leads_to` close the Discovery→Requirement loop with an explicit link instead of a guess based on date or content. The remaining fields (`date`, `participants`) repeat the pattern already adopted for other artifact types (see [`conventions.md`](conventions.md), section 1) — deliberately, so that Discovery does not require learning a separate schema.

## Why this matters for reqQuest Framework

The most important consequence of this page: **in reqQuest Framework, quality of form is something CI can check automatically**, not something that depends on the reviewer's attention. This directly implements principle 9 of [`vision-and-principles.md`](vision-and-principles.md#9-systematic-and-disciplined-work) ("systematic and disciplined work") — discipline stops being a matter of memory and becomes a check that blocks the merge.

## Related documents

- [`_index.md`](_index.md) — map of the whole methodology
- [`conventions.md`](conventions.md) — the concrete front-matter and ID schema that implements the practices described above
- [`from-problem-to-requirement.md`](from-problem-to-requirement.md) — where the artifacts described here come from
