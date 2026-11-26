# Objectives and scope — business case document

> This file implements the pattern described in [`conventions.md`](https://github.com/reqquest/reqQuestFramework/blob/main/docs/framework/conventions.md), section 7 ("Business case document"). The content below is an **example** (fictional domain: a meeting-room booking system) — replace it with the real content of your project and keep the three sections below.
>
> **Direction of dependencies:** this document sits above the requirements and ADRs. Requirements and ADRs refer to it, and it does not refer to them. Add a new high-level topic here first, then carry its consequences into ADRs, NFRs and FRs.

## Objective and business case

Today employees book meeting rooms by sending messages to reception, which causes delays and double bookings. The project's objective is a self-service room booking system, available to every employee, that removes reception as an intermediary and eliminates double bookings. All requirements in this repository relate to this objective.

## Chosen combination of process facets (see [`process-and-working-modes.md`](https://github.com/reqquest/reqQuestFramework/blob/main/docs/framework/process-and-working-modes.md))

- **Time:** Iterative — the scope emerges as work progresses; further functional categories are added in separate PRs.
- **Purpose:** Explorative until the first production release, then a switch to Prescriptive for the scope covered by the SLA.
- **Business goal:** Customer-specific — the repository is run for one internal customer (the company's IT department).

## Role catalog

The project's roles, the requirements areas they are responsible for and their `handle` on the host are recorded in the role catalog `roles.yaml`, the only source of roles in the repository; it is created as a copy of the example [`roles.example.yaml`](roles.example.yaml). Who holds which role is shown in the "Role" column of [`stakeholders.md`](stakeholders.md). The catalog extends the minimal role catalog from [`_index.md`](https://github.com/reqquest/reqQuestFramework/blob/main/docs/framework/_index.md#scope-and-roles).
