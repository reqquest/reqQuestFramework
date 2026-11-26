---
title: Attribution and Standards — reqQuest Framework
owner: reqQuest
status: approved
last_updated: 2026-11-23
tags: [reqquest-framework, ireb, standards, attribution]
---

# Attribution and Standards

> **Level:** Foundation — a convention that applies across the whole `docs/`
> **Owner:** reqQuest

## Why this document exists

reqQuest Framework bases its skeleton on **CPRE Foundation Level**, published by the International Requirements Engineering Board (IREB e.V.). This dependency carries legal consequences that must be taken into account deliberately before this documentation grows — that is why this document exists first, not as an appendix at the end.

## Correction: the Handbook as the citation skeleton

This page and the other pages in `docs/` from now on cite chapters/sections of the **Handbook by name** (e.g. "Management Practices for Requirements", "Traceability") as the basic, stable identifier — a chapter name is much less likely to change between editions than the numbering, and it is also what the reader actually finds in the Handbook's table of contents.

## Legal status of IREB materials

The CPRE Foundation Level Syllabus and Handbook are protected by the copyright of IREB e.V. The Terms of Use state plainly:

- the source materials may be used as the basis for training and derivative publications, provided that the copyright of IREB e.V. is acknowledged as the source,
- use in advertising materials requires **written permission from IREB**,
- reproducing the content (in whole or in substantial part) without the permission of the authors or IREB e.V. is prohibited. reqQuest does not reproduce the content of IREB materials; it only applies the topics described by the IREB methodology to reqQuest Framework, in order to use mature and recognised principles in the reqQuest Framework requirements management process.

## Rule: we cite structure, not text

**Allowed:**

- citing the name of a Handbook chapter/section (e.g. "Management Practices for Requirements"),
- referring to the name of a Handbook subsection (e.g. "Traceability") as a point of reference,
- summarising in our own words what a given chapter is about, to the extent needed to understand the context,
- listing the names of the 9 IREB principles as labels — the principle names themselves are short titles, not protected content,


**Not allowed:**

- translating or reproducing the full text of definitions, principles or examples from the Handbook or the Syllabus,
- copying tables, lists or wording of the source 1:1 (even translated),
- using the name "CPRE" or the IREB logo in a way that suggests an official certification or affiliation that reqQuest does not yet have.

Every content page achieves this through **its own wording of the triad** (IREB requirement → reqQuest Framework mechanism → proof of compliance) — see [`_index.md`](_index.md#organising-principle-of-every-page-triple-mapping). The content is inspired by the structure of the sources, not by their text. The same rule applies equally to the SIG-AIREB Booklet on RE and AI material cited in [`ai-in-framework.md`](ai-in-framework.md) — the structure (nine principles × AI-assisted practice, families of prompting patterns) is the point of reference; specific prompts and wording from the source material are not reproduced.

## Citation convention

The format used consistently across the whole `docs/`:

> *Concept name* (CPRE Foundation Level Handbook, chapter "[chapter/section name]")

Example: *Traceability (CPRE Foundation Level Handbook, chapter "Management Practices for Requirements")* — never a page number (page numbering changes between editions), never a full quotation, never an Education Unit number as the only identifier.

## Source versions

**Rule for the future:** if IREB publishes a new version of the Handbook, the chapter structure must be verified again before this documentation is extended further — do not assume automatic continuity.

## Primary sources

Two independent IREB materials, each cited by the same "structure, not text" rule:

| Material | Publisher | Version checked | Role for reqQuest Framework |
|---|---|---|---|
| **CPRE Foundation Level Handbook** | IREB e.V. | v1.3.2 (EN) | **The primary content source** of this documentation — instructional material that provides practices, e.g. the Kano model, a taxonomy of conflict types, a checklist for deploying an RE tool; see the references in [`from-problem-to-requirement.md`](from-problem-to-requirement.md) and [`tooling.md`](tooling.md) |
| **SIG-AIREB Booklet on RE and AI** | IREB AI Interest Group (SIG-AIREB) | v40.0.0 | Maps the nine fundamental RE principles to LLM-assisted practice; the source of structure (not text) for [`ai-in-framework.md`](ai-in-framework.md), including the families of prompting patterns (RTF/RISEN/CRISPE — the patterns themselves are established more widely in industry practice; the booklet organises them with respect to RE, it does not invent them) |

## Handbook mapping table

This is **the only place** in this documentation where the order of chapters organises the content as a table — deliberately, so as not to repeat it on every content page. The target pages cite the chapter/section name inline where it helps the reader verify the source, but do not carry it in their title.

| # (approximate) | Handbook chapter | Where in reqQuest Framework | Page |
|---|---|---|---|
| 1 | Introduction and Overview of Requirements Engineering | System boundary = repository boundary; the Requirements Engineer role; minimal role catalog (project roles in `roles.yaml`: [`conventions.md`](conventions.md#ownership-governance)) | [`_index.md`](_index.md#scope-and-roles) |
| 2 | Fundamental Principles of Requirements Engineering | 9 principles × reqQuest Framework implementation | [`vision-and-principles.md`](vision-and-principles.md) |
| 3 | Work Products and Documentation Practices | Artifacts as files, L0/L1 hierarchy, glossary, quality gate in CI | [`artifacts-and-structure.md`](artifacts-and-structure.md) |
| 4 | Practices for Requirements Elaboration | Sources, elicitation, conflicts, validation as Issues/PR/ADR | [`from-problem-to-requirement.md`](from-problem-to-requirement.md) |
| 5 | Process and Working Structure | 3 process facets → branch/PR/release strategy | [`process-and-working-modes.md`](process-and-working-modes.md) |
| 6 | Management Practices for Requirements | Traceability, versioning, baseline, change (approval by area owners: [`conventions.md`](conventions.md#ownership-governance)), priority | [`requirements-management.md`](requirements-management.md) — **flagship page** |
| 7 | Tool Support | reqQuest Framework tooling, the generic layer and reqQuest | [`tooling.md`](tooling.md) |

The number in the first column is approximate (the order in which these topics have been cited so far, inherited from the time when the skeleton was based on the Syllabus) until it is verified directly against the Handbook's table of contents.

## Complementary standards

IREB CPRE is the main skeleton, but not the only point of reference. The following complement the foundation of reqQuest Framework:

| Standard | Role for reqQuest Framework |
|---|---|
| **BABOK** (Business Analysis Body of Knowledge) | Complements IREB with business analysis and stakeholder modelling techniques where reqQuest Framework goes beyond pure requirements engineering towards business analysis in general |
| **IEEE 29148** (Requirements Engineering) | A point of reference for classifying requirements (BR/FR/NFR) and for quality criteria — used as a vocabulary, not as a document format |

## Related documents

- [`_index.md`](_index.md) — entry point to reqQuest Framework and the "triple mapping" principle
- [`ai-in-framework.md`](ai-in-framework.md) — application of the SIG-AIREB Booklet material
