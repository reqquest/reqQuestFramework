---
title: Process and Working Modes
owner: reqQuest
status: draft
last_updated: 2026-08-16
tags: [reqquest-framework, ireb, process, delivery-style]
---

# Process and Working Modes

> **Level:** Foundation of the methodology
> **Owner:** reqQuest
> **Implements:** CPRE Foundation Level, Process and Working Structure (see the methodology's standards-attribution mapping, outside this toolkit's boundary)

IREB does not mandate a single RE process — instead it describes three independent facets (called IREP facets in the source material — Iterative/Prescriptive/Explorative and related terms), whose combination defines which process fits a given situation. The reqQuest Framework maps each facet onto a concrete branch/PR/release strategy decision, not onto a separate, parallel set of documents. The reqQuest Framework uses its own vocabulary (Linear/Iterative, Prescriptive/Explorative) in its narrative, and the term "IREP" only as a citation to the source material — the three facets remain the same concept under both names.

## Mapping table

| IREB facet | Deciding question | Implementation in the reqQuest Framework |
|---|---|---|
| **Time: Linear vs Iterative** | Are the requirements known up front, or do they emerge as work progresses? | *Linear* → one large, reviewed PR with a specification closing the entire scope before implementation starts. *Iterative* → a series of small PRs, each adding/correcting a fragment of requirements based on feedback from the previous one |
| **Purpose: Prescriptive vs Explorative** | Is the specification a binding contract, or a hypothesis to be verified? | *Prescriptive* → a tag/release on a frozen set of requirements serves as a contractual baseline (see [`requirements-management.md`](requirements-management.md), section "Configurations & Baselines"), a change requires a formal change request. *Explorative* → the backlog (Issues) is a living, continuously reprioritized set, with no freezing |
| **Business purpose: Customer-specific vs Market-oriented** | Is the system built for one, known stakeholder, or for an undefined market segment? | *Customer-specific* → a repository/branch with a limited, explicitly defined set of approvers (the `CODEOWNERS` equivalent = the customer's team). *Market-oriented* → a broader review process, a backlog shaped by aggregated feedback from many sources, not a single customer |

**Practical IREB guidance the reqQuest Framework inherits directly:** facets are combined heuristically, not rigidly — the combinations *Linear + Prescriptive* and *Iterative + Explorative* are the most common, but critical/well-understood components in an exploratory project can still be specified up front (a mixed approach), and the *Customer-specific* facet does not rule out iterative work.

## Two familiar names for the same combination of facets

In software-development practice, the same three facets are sometimes shorthanded as the "Plan-Driven vs Discovery-Driven" axis — from the perspective of the reqQuest Framework's foundation, this is not a separate concept, just a commercial name for a specific, recurring combination of two IREB facets: **Plan-Driven ≈ Linear + Prescriptive**, **Discovery-Driven ≈ Iterative + Explorative**. The *Customer-specific vs Market-oriented* facet is independent of this choice and selected separately.

This distinction matters in practice: a new team adopting the reqQuest Framework does not need to learn two different vocabularies. The three facets described in the table above are the complete, full set of process decisions — any commercial name at the application layer is just a label on their specific combination.

## Proof of compliance

A repository explicitly declares which combination of facets it has adopted for a given scope of work — the place for this declaration is the project's business rationale document (see [`conventions.md`](conventions.md), section "Business rationale document"), not a verbal agreement or each participant's own default expectation. The absence of such a declaration is a common source of conflict: part of the team works as if the process were Prescriptive (not changing the frozen scope without formal approval), part as if it were Explorative (changing scope on the fly) — and both sides are "right" relative to different, never-agreed assumptions.

## What breaks without a deliberate choice of facets

A default, unconsidered combination of facets (e.g. Iterative + Prescriptive — changing requirements treated as a binding contract) generates constant conflict between pace of work and expected stability — exactly what IREB warns about in its description of process-selection criteria.

## Related documents

- the methodology documentation — map of the whole methodology
- [`requirements-management.md`](requirements-management.md) — how a baseline implements the Prescriptive facet
