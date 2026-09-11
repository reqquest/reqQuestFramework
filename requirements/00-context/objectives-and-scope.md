# Objectives and Scope — business rationale document

> This file follows the pattern described in [`../../docs/conventions.md`](../../docs/conventions.md), section 7 ("Business rationale document"). The content below is an **example** (fictional domain: meeting room booking system) — replace it with your own project's real content, keeping the three sections below.

## Objective and business rationale

Employees today book meeting rooms by messaging the front desk, which causes delays and double bookings. The project's objective is a self-service room booking system available to every employee, removing the front-desk intermediary and eliminating double bookings. All requirements in this repository relate to this objective — see [`BR-DEMO-001`](../business/BR-DEMO-001.md) as the top-level business requirement.

## Adopted combination of process facets (see [`../../docs/process-and-working-modes.md`](../../docs/process-and-working-modes.md))

- **Time:** Iterative — scope emerges as work progresses, functional categories added in separate PRs.
- **Purpose:** Explorative until the first production release, then switched to Prescriptive for the scope covered by an SLA.
- **Business purpose:** Customer-specific — the repository is maintained for a single, internal customer (the company's IT department).

## Role catalog

Extends the minimal catalog from the methodology documentation (scope and roles) (human as author/reviewer, AI agent under human supervision) with roles specific to this project's domain:

| Role | Responsibility | Reviews |
|---|---|---|
| Product Owner | Prioritization, acceptance of business requirements | `requirements/business/**` |
| Tech Lead | Technical feasibility, architectural consistency | `requirements/functional/**`, `requirements/nonfunctional/**` |
| Architect | Design decisions and their consequences | `requirements/adrs/**` |
