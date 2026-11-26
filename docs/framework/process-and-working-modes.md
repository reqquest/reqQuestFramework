---
title: Process and Working Modes
owner: reqQuest
status: approved
last_updated: 2026-11-23
tags: [reqquest-framework, ireb, process, delivery-style]
---

# Process and Working Modes

> **Level:** Foundation of the methodology
> **Owner:** reqQuest
> **Implements:** CPRE Foundation Level, Process and Working Structure (see [`attribution-and-standards.md`](attribution-and-standards.md#handbook-mapping-table))

IREB does not impose one RE process — instead it describes three independent facets (called IREP facets in the source material — Iterative/Prescriptive/Explorative and related), whose combination defines which process fits a given situation. reqQuest Framework maps each facet to a concrete decision about the branch/PR/release strategy, not to a separate, parallel set of documents. reqQuest Framework uses its own vocabulary (Linear/Iterative, Prescriptive/Explorative) in the narrative, and the term "IREP" only as a footnote to the source material — the three facets remain the same concept under both names.

## Mapping table

| IREB facet | Deciding question | Implementation in reqQuest Framework |
|---|---|---|
| **Time: Linear vs Iterative** | Are the requirements known up front, or do they emerge as work goes on? | *Linear* → one large, reviewed PR with the specification that closes the whole scope before implementation starts. *Iterative* → a series of small PRs, each adding/correcting a part of the requirements based on feedback from the previous one |
| **Purpose: Prescriptive vs Explorative** | Is the specification a binding contract or a hypothesis to verify? | *Prescriptive* → a release (recommended) or a tag on a frozen set of requirements serves as the contractual baseline (see [`requirements-management.md`](requirements-management.md), section "Configurations & Baselines" for the difference between the two mechanisms); a change needs a formal change request. *Explorative* → the backlog (Issues) is a living, constantly reprioritised set, without freezing |
| **Business goal: Customer-specific vs Market-oriented** | Is the system built for one, known stakeholder, or for an unspecified market segment? | *Customer-specific* → a repository/branch with a limited, explicitly defined group of approvers (the `CODEOWNERS` equivalent = the customer's team). *Market-oriented* → a broader review process, a backlog shaped by aggregated feedback from many sources, not one buyer |

**A practical IREB tip that reqQuest Framework inherits directly:** facets are combined heuristically, not rigidly — the combinations *Linear + Prescriptive* and *Iterative + Explorative* are the most common, but critical/well-understood components in an explorative project may still be specified up front (a mixed approach), and the *Customer-specific* facet does not rule out iterative work.

## Two familiar names for the same combination of facets

In software development practice the same three facets are often called, in short, the "Plan-Driven vs Discovery-Driven" axis — from the perspective of the reqQuest Framework foundation this is not a separate concept, only a trade name for a specific, recurring combination of two IREB facets: **Plan-Driven ≈ Linear + Prescriptive**, **Discovery-Driven ≈ Iterative + Explorative**. The *Customer-specific vs Market-oriented* facet is independent of this choice and chosen separately.

The distinction matters in practice: a new team adopting reqQuest Framework does not have to learn two different vocabularies. The three facets described in the table above are the only, complete set of process decisions — any trade name in the application layer is just a label for a specific combination of them.

## Evidence of compliance

The repository explicitly declares which combination of facets it has adopted for a given scope of work — the place for this declaration is the project's business case document (see [`conventions.md`](conventions.md), section "Business case document"), not an oral agreement or each participant's default expectation. A missing declaration is a common source of conflict: part of the team works as if the process were Prescriptive (does not change the frozen scope without formal consent), part as if it were Explorative (changes the scope on the go) — and both sides are "right" with respect to different assumptions that were never agreed.

## What breaks without a deliberate choice of facets

A default, unconsidered combination of facets (e.g. Iterative + Prescriptive — changing requirements treated as a binding contract) creates a constant conflict between the pace of work and the expected stability — exactly the kind IREB warns about in its description of the criteria for choosing a process.

## Related documents

- [`_index.md`](_index.md) — map of the whole methodology
- [`requirements-management.md`](requirements-management.md) — how the baseline implements the Prescriptive facet
