---
title: Tooling
owner: reqQuest
status: approved
last_updated: 2026-11-23
tags: [reqquest-framework, tooling, ireb]
---

# Tooling

> **Level:** Foundation of the methodology
> **Owner:** reqQuest
> **Implements:** CPRE Foundation Level Handbook, chapter Tool Support (see [`attribution-and-standards.md`](attribution-and-standards.md#handbook-mapping-table))

IREB treats tools as a reinforcement of a well-designed process, not a substitute — a tool is useless if it is not accompanied by a mastered practice. reqQuest Framework keeps to this order: first the principles and conventions ([`vision-and-principles.md`](vision-and-principles.md), [`conventions.md`](conventions.md)), only then the tools that enforce them.

## Generic layer — zero mandate

No specific implementation is required. reqQuest Framework can be adopted at a client with any stack, as long as it meets the functional contract below:

| Need (IREB) | reqQuest Framework mechanism |
|---|---|
| Storing and versioning requirements | Git (host: GitHub or equivalent) |
| Enforcing quality and conventions | CI (linter, schema validation, link checking) |
| Publishing and searchability | Any static site generator, or plain Markdown read by the git host |

**Evidence of compliance:** a client repository may use none of the reqQuest tools below and still be fully compliant with reqQuest Framework — the contract concerns the core of the methodology (from Work Products to Management Practices), not a specific implementation. This starter kit (`requirements/` + `.reqq/` in the root of this repo) is one, reference implementation of this contract using plain Python and JSON Schema — not the only acceptable one.

**Licensing.** The reqQuest Framework repository (this contract, this starter kit) is released under the Open Source licence Apache-2.0 (see the [README of the public repository](https://github.com/reqquest/reqQuestFramework/blob/main/README.md#license)) — a client may adopt the methodology on its own, with no requirement to use reqQuest tools. The reqQuest tools listed below (reqAgent, reqClient, reqWizard) are separate commercial products — using their functionality is paid, even though the methodology itself is not.

## reqQuest tools implementing the same layer

Beyond the generic layer described above, reqQuest applies reqQuest Framework in its own, private products (dogfooding) — listed here as evidence that the contract is real and feasible, not as part of the core of this methodology or as a dependency reqQuest Framework would have to wait for. **Naming split: validator vs reqAgent** — these are two separate tools distinguished by *how* they work, not only *what* they check: the validator is a deterministic script (exit codes `0` / `2` / `3`, no LLM involved), reqAgent is an interactive AI assistant. Detecting semantic duplicates/conflicts and generating acceptance criteria — tasks that need interpretation, not mere schema compliance — belong to reqAgent, not to the validator:

| Need (IREB) | reqQuest tool | What exactly it delivers |
|---|---|---|
| Enforcing the quality and schema of requirements (validation) | git hook + validation scripts (validator) | Only deterministic validation of front matter/structure/schema — exit code `0` (OK), `2` (validation errors) or `3` (configuration error), no LLM. The arbiter of the quality of *form*, never of content (see [`artifacts-and-structure.md`](artifacts-and-structure.md), "Quality Criteria for Work Products and Requirements") |
| Dynamic coverage calculation and dependency verification in an existing requirements base | CI scripts | Deterministic examination of links, plus heuristic calculation of the parameters needed to assess how far requirements are covered by code and tests, and the inverse parameter showing what share of the code has no defined requirements — identifies the project's areas of examination: API methods, frontend routes, tests etc. |
| Access for non-technical stakeholders, and traceability/coverage as a view | reqClient | A requirements wizard that ends with a Pull Request, a traceability graph, a coverage scorecard, a PR dashboard — on top of the same git repository, without its own content store |
| Assessment of the maturity of the client's RE process (all chapters of the Handbook) | reqWizard | A structured review (modelled on the AWS Well-Architected Review) mapped to IREB/BABOK; itself also a dogfooded instance of reqQuest Framework |
| AI support for elicitation and drafting content | reqAgent | Content suggestions based on the target repository, working in the context of the content of requirements and design documents: drafting, detecting potential semantic duplicates/conflicts, proposed acceptance criteria — always as a proposal to accept, never a commit without human approval |
| AI chat help for expanding on methodology topics | reqXio — an assistant pattern built into reqClient and reqWizard | Answers questions about the broader context of the questions in a needs assessment with reqWizard; in reqClient it gives information about the context of the tool's individual features |

**Evidence of compliance:** none of the tools above — generic or reqQuest's own — is a mandatory requirement of this methodology. The role of AI is the same everywhere: support under human supervision, never autonomous approval (see [`vision-and-principles.md`](vision-and-principles.md), principles 6 and 9, and [`ai-in-framework.md`](ai-in-framework.md)).

## Diagrams — Mermaid and draw.io

Diagrams live in the repository as versioned source files, not as binary images (PNG). Both formats are allowed: simple diagrams — Mermaid embedded in Markdown (see [`artifacts-and-structure.md`](artifacts-and-structure.md), "Model-Based Work Products"); complex ones that Mermaid cannot render legibly — draw.io (a `.drawio` file in the repository). Architecture diagrams of the reqQuest tools listed above do not belong on the methodology pages — if they are needed, their place is in the separate, internal product documentation of the given tool: the methodology describes the role of a tool in the RE process, not its internal implementation architecture.

## How to choose and adopt a tool — not only what it does

The IREB source material (the Handbook, the chapter on tool support) stresses something a plain feature table leaves out: choosing an RE tool is a decision whose cost goes beyond the licence price, and a failed tool rollout is a more frequent cause of failure than the lack of a suitable tool on the market. reqQuest Framework adopts this discipline as a checklist, not as a sales slogan:

1. **Count the whole lifecycle cost, not only the licence** — migrating existing requirements, training the team, maintaining the CI integration, the cost of leaving the tool if it does not work out.
2. **Define the selection criteria before the market review, not after it** — if the core of the methodology (from Work Products to Management Practices) is a contract (see above), the criteria are: does the tool read/write directly to the git repository, does it enforce the schema, does it generate traceability views, does it work without moving the content to its own store.
3. **Pilot on one, limited scope before the full rollout** — one module, one team, one sprint — before the tool becomes a dependency of the whole repository.
4. **Assess the pilot result against the criteria from step 2, not against the enthusiasm of the pilot team** — it is easy to confuse "we like it" with "it meets the contract".
5. **Plan training and support as part of the rollout, not as an afterthought** — a tool without a mastered practice (see the opening paragraph of this page) is useless regardless of its quality.

**Evidence of compliance:** the decision to adopt an RE tool (generic or reqQuest) is documented as an ADR — context, options considered, selection criteria, decision — with exactly the same mechanism reqQuest Framework uses to document every other architecture decision (see [`requirements-management.md`](requirements-management.md)).

## Related documents

- [`_index.md`](_index.md) — entry point of reqQuest Framework
- [`ai-in-framework.md`](ai-in-framework.md) — the role of AI in the tools above, developed as principles
- [`attribution-and-standards.md`](attribution-and-standards.md) — the full mapping table CPRE Foundation Level Handbook → reqQuest Framework
- [`../../.reqq/README.md`](../../.reqq/README.md) — reference implementation of the generic layer in this repo
