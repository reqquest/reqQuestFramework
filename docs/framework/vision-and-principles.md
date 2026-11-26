---
title: Vision and Principles — reqQuest Framework
owner: reqQuest
status: approved
last_updated: 2026-11-23
tags: [reqquest-framework, vision, principles, ireb, spec-driven-development]
---

# Vision and Principles

> **Level:** Foundation of the methodology
> **Owner:** reqQuest

## Why reqQuest Framework

Requirements Engineering has a well-described, internationally recognised theory — IREB has formalised it since 2007 as CPRE Foundation Level. The problem is not the theory but the practice: in most organisations requirements live in outdated ALM-class tools, in Word documents, Excel sheets and e-mail threads, detached from the code they are meant to describe and from the decisions that justified them. Traceability — the ability to trace a requirement from a business need to the deployed solution — is then a report produced by hand at the end of the project, not a property of the system.

**reqQuest Framework** — the *Requirements as a Code* approach, close to the *Requirements as Code* movement (RaC for short) — is the answer: requirements, decisions and their rationale recorded as versioned files in a git repository, subject to the same mechanisms as code — change history, branches, pull requests, code review, CI. **reqQuest Framework** is the discipline that says **how** to do it well.

This mapping is deliberately domain-neutral. Nothing in the IREB theory assumes that the "system" has to be software — and git today stores much more than code. The same mechanism that manages software requirements can also manage legal documents and a company's corporate knowledge — see [`examples.md`](examples.md), two independent production proofs from reqQuest.

## Lineage: two independent movements, one observation

reqQuest Framework is not a reqQuest invention from scratch — it makes two lineages concrete, and reqQuest gives them one consistent, auditable form:

**IREB / CPRE Foundation Level** — an independent academic and industry standard of requirements engineering that has formalised since 2007 nine fundamental principles of RE (see below) and the practices that implement them, independent of process, tool or domain. reqQuest Framework does not depart from this foundation or "modernise" it — it maps it directly onto git-native mechanisms (see [`attribution-and-standards.md`](attribution-and-standards.md) for the rules on citing the source material).

**Requirements as Code and the related Spec-Driven Development family** — a movement of engineering practice that grew independently of IREB, from the same observation seen from another side: the specification as a first-class artifact, versioned together with the code, in the same repository and the same review process — not a parallel document living in a separate tool and quickly drifting away from reality. Where IREB provides the theory (*what* makes a requirement good, how to manage it), Requirements as a Code / Spec-Driven Development provide the tooling practice (*where* the specification physically lives and *how* to keep it up to date with what was actually built).

Both movements grew from the same observation: the quality of a system depends on the quality of its requirements, and the quality of requirements depends on whether they can be traced, verified and maintained over time. What has changed since these ideas emerged is not their validity but the cost of neglecting them: in an era in which a significant share of code and design decisions is made with the help of AI agents, loosely linked, unversioned requirements stop being only an organisational problem — they become a hard limit on the quality of what an agent can generate at all. reqQuest Framework treats both lineages as equal inputs, not as a foundation (IREB) with a footnote (SDD): IREB is responsible for the rigour of defining and managing requirements, Requirements as Code / Spec-Driven Development are responsible for this rigour living where the code lives — in the same git repository.

**reqQuest Framework and AI agents:** the structured, versioned and explicitly linked context of reqQuest Framework is not only a convenience for people — it is a direct input for language models. An AI agent that gets as context a requirement file with a clear `id`, `status`, `traces_to` and a decision history in `git log` works more precisely than an agent forced to guess the intent from scattered prose in a text document or an e-mail thread. reqQuest Framework is thus not only a requirements engineering discipline — it is a way to feed LLM context that measurably improves the quality of the work of agents supporting the architects, developers and analysts who use this repository. This is exactly the point where the IREB lineage (rigour of the requirement) and the Spec-Driven Development lineage (specification where the code is) join: the AI agent uses one consistent source of truth, not two diverging ones.

## Nine IREB principles, nine implementations in reqQuest Framework

The CPRE Foundation Level Handbook defines nine fundamental principles of requirements engineering that apply regardless of process, practices or tools. Below — each principle with its own description (not a translation of the source text, see [`attribution-and-standards.md`](attribution-and-standards.md)) and how reqQuest Framework implements it concretely. Where the Handbook develops a principle into a specific technique or taxonomy, the further pages of this methodology follow that lead: the Kano model and conflict types for principle 5 ([`from-problem-to-requirement.md`](from-problem-to-requirement.md)), the four kinds of models for artifacts ([`artifacts-and-structure.md`](artifacts-and-structure.md)), the tool selection checklist for principle 9 ([`tooling.md`](tooling.md)).

### 1. Value orientation

A requirement is not a value in itself — it is a means to an end, and its cost (elicitation, documentation, validation, maintenance) shall be lower than the benefit it brings.

**In reqQuest Framework:** every requirement is a file or an entry whose maintenance cost is directly visible — the change history in git shows how many times the requirement was modified and how much discussion (PR comments) it generated. A requirement that is never referenced by code, a test or an ADR is easy to detect (no entries in the Traceability Matrix) and to challenge.

**What breaks without it:** the repository swells with requirements nobody needs, because nothing signals their cost — without traceability these "dead" requirements cannot be told apart from active ones.

### 2. Stakeholders

Requirements engineering exists to meet the needs and expectations of stakeholders — not only end users, but every role that affects the system or is affected by it.

**In reqQuest Framework:** stakeholders and their roles are an explicit, versioned artifact (e.g. a stakeholder register as a file in the repo), not oral knowledge. A pull request that requires approval by a specific role (e.g. `CODEOWNERS`) is the git-native implementation of the principle "the right person approves the right part".

**What breaks without it:** requirements are written from the perspective of one loud group of stakeholders (usually the buyer), and roles such as the operator, the regulator or the maintenance team learn about their overlooked needs only after deployment.

### 3. Shared understanding

Successful system development is impossible without a shared basis of understanding between stakeholders, requirements engineers and the delivery team.

**In reqQuest Framework:** the glossary of terms as one logical glossary — implemented as a base file (delivered by the methodology/product) and a client extension file, added together logically (see principle 7 — Evolution, the pattern "reqQuest Framework native vs client extensions") — is the explicit implementation of "explicit shared understanding": every term has one definition within its layer, one source of truth, and a change of definition goes through the same review process as a code change.

**What breaks without it:** the same term means something different in the SRS, in the code and in the conversation with the client — a discrepancy found only at acceptance testing, at the highest possible cost.

### 4. Context

A system cannot be understood apart from its context — the boundary between the system and its environment shall be drawn deliberately, not by default.

**In reqQuest Framework:** the system boundary corresponds to the repository boundary (or a clearly defined module in a monorepo) — what is "inside" has its requirements and tests here; what is "outside" is documented as a context assumption or an external dependency, explicitly linked.

**What breaks without it:** requirements grow beyond the actual scope of the system, or the other way round — critical assumptions about the environment (another system, a regulation, an integration) are recorded nowhere, because "everybody knows it".

**Integration contracts** *(not a separate L0 artifact type)*: an API/integration contract between the system and its environment is exactly the kind of context assumption that shall be an explicitly maintained artifact. reqQuest Framework does not introduce a separate type for it. The contract is described by a **functional requirement (FR)** in the category of its domain: the prose speaks about meaning and behaviour, and the OpenAPI fragment embedded in it about structure. This gives every field one source that can be pointed to. The contract file (e.g. `openapi.yaml`) is assembled from the fragments and the shared parts; it is not maintained separately. The choice of integration technology or protocol, if it needs a rationale, goes into an ADR, as in the problem–requirement–solution separation (principle 5, below). The fragment convention is described in [`conventions.md`](conventions.md), section 9.

**Out of scope:** managing tasks/the project backlog (Jira-style work tracking) is not part of this methodology — reqQuest Framework manages requirements, not the work done to implement them. This boundary is deliberate, not accidental: mixing the two concepts blurs the distinction between "what is to be built" (requirement) and "who will do it and when" (task).

### 5. The problem–requirement–solution triangle

Problem, requirement and solution are inseparably intertwined, but good requirements engineering deliberately separates them in thinking, communication and documentation.

**In reqQuest Framework:** this separation has the form of artifacts — an Issue/note from Discovery describes the problem, the requirement file (SRS) describes the need, and an ADR or the code describes the adopted solution. Three different file types, explicitly linked, instead of one document mixing all three layers. For the formal artifact type and the place of Discovery in the reqQuest Framework folder hierarchy (L0/L1), see [`artifacts-and-structure.md`](artifacts-and-structure.md), section "L0/L1 hierarchy and the Discovery type".

**What breaks without it:** a solution is written directly as a "requirement" ("the system shall use PostgreSQL"), which closes the solution space before anyone has explored it.

For recognising *which* expectation deserves to be formalised as a requirement at all (the Kano model) and how to classify the *type* of tension between two already formalised requirements, see [`from-problem-to-requirement.md`](from-problem-to-requirement.md).

### 6. Validation

Unvalidated requirements are useless — you have to check whether they reflect the real needs of stakeholders before they become the basis for work.

**In reqQuest Framework:** validation is a step of the process, not an afterthought — a Pull Request with new/changed requirements needs approval (review) by a role representing the stakeholder before it is merged. The approval history in git is permanent evidence that validation took place.

**What breaks without it:** requirements go into implementation unchecked, and the error is found only at acceptance — the most expensive moment possible.

**Who validates:** choosing the right reviewer for a given requirements change relies on the project's role responsibility matrix — whoever is the subject-matter owner of a given area of requirements approves them. The mechanism (the role catalog `roles.yaml` and the `CODEOWNERS` generated from it) is described in [`conventions.md`](conventions.md#ownership-governance), section 7, "Ownership governance".

### 7. Evolution

Changing requirements are not an accident at work — they are the normal state of things, which has to be handled deliberately instead of pretending it does not happen.

**In reqQuest Framework:** a requirement change is a commit, not an overwrite of the file — the previous version stays in the git history, available for audit and comparison. A new branch or Issue represents the change request, which goes through the same review process as the original requirement.

**What breaks without it:** the requirement is overwritten without a trace, so nobody can reconstruct why the system does something different today from what was agreed at the start of the project.

**Evolution of the methodology's structure itself:** the same approach applies to the structure of reqQuest Framework, not only to individual requirements. The model structure of folders, conventions and starting files (front-matter schema, example requirements, validators) — exactly what this repository delivers as `requirements/` and `.reqq/` — lives as a versioned "golden copy": a reference skeleton from which new projects bootstrap their structure, while the git tags/releases of this repository mark successive, consistent versions of this structure (the same mechanism as the baseline of a single requirement, see [`requirements-management.md`](requirements-management.md), section "Configurations & Baselines" — only applied at the level of the whole structure, not a single file).

Updating this structure at a client without losing its local extensions requires splitting the files into two categories: **reqQuest Framework native** (delivered and maintained by the methodology/product, enforced by the validator, not for manual editing) and **client extensions** (freely editable, project-specific) — analogous to merging configuration files. The first, fully agreed example of this pattern: the glossary (see [`artifacts-and-structure.md`](artifacts-and-structure.md), section "Glossaries") — one logical glossary, made of a base file and a client extension file, added together logically.

### 8. Innovation

Giving stakeholders exactly what they asked for is not enough — good requirements engineering looks for opportunities to build something that exceeds expectations.

**In reqQuest Framework:** the open structure of the repository (Issues, Discussions, proposals in PRs) is the place where an idea that goes beyond the literal request can be proposed, discussed and — if accepted — become a new requirement with the full history of its rationale, instead of getting lost in a hallway conversation.

**What breaks without it:** the system formally meets every recorded requirement and still disappoints — because nobody had a place to propose a better solution.

The notes section in the body of a requirement (`## Notes`) formally distinguishes at least two categories of intent: **Out of Scope** (deliberately rejected at this stage) and **Future Improvement** (an idea beyond the current scope, worth noting for later) — the classification is a task for the person or AI agent interpreting the content, not a rigid form with separate fields. This is a deliberate trade-off: flexible classification by a human or an LLM costs some precision compared to a rigid form, but gains from the note not having to fit a predefined structure up front — for content that is unstructured by nature (free text of an observation, an idea) this loss is worth it.

### 9. Systematic and disciplined work

There is no single requirements engineering process that fits every situation — but without system and discipline (fitted to the context, not copied thoughtlessly from the previous project) the quality of the system suffers whatever process is chosen.

**In reqQuest Framework:** discipline is enforced structurally, not only declared — a validation script checks that every requirement file has the expected fields (front matter), lint checks the format, branch protection rules require review before merge. What in a paper process needs reminders is, in reqQuest Framework, a check that blocks the merge. This automation concerns only the quality of form — the quality of content always remains a human decision at PR approval, never automated (the full separation of the two: [`artifacts-and-structure.md`](artifacts-and-structure.md), section "Quality Criteria for Work Products and Requirements").

**What breaks without it:** discipline depends on the memory and good will of individuals — and degrades exactly when the team is busiest.

Discipline also covers the choice of the tools that enforce these rules, not only the rules themselves — see [`tooling.md`](tooling.md), section "How to choose and adopt a tool".

## How these principles lead to the rest of the methodology

These nine principles are the *why*. The *how* — the concrete git-native mechanisms that implement the individual IREB practices (documentation, elicitation, process, requirements management) — is developed on the further pages of this methodology (see [`_index.md`](_index.md), section "Structure of this area"), with [`requirements-management.md`](requirements-management.md) as the one most densely mapped onto git mechanisms.

## Related documents

- [`_index.md`](_index.md) — what reqQuest Framework is and how to read this area
- [`artifacts-and-structure.md`](artifacts-and-structure.md), [`from-problem-to-requirement.md`](from-problem-to-requirement.md), [`process-and-working-modes.md`](process-and-working-modes.md), [`requirements-management.md`](requirements-management.md) — CPRE Foundation Level Handbook × reqQuest Framework implementation, chapter by chapter
- [`ai-in-framework.md`](ai-in-framework.md) — the role of AI, developed as principles
- [`attribution-and-standards.md`](attribution-and-standards.md) — the IREB citation convention, the legal status of the source materials
