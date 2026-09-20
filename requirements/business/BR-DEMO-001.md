---
id: BR-DEMO-001
title: Self-service meeting room booking
type: BR
status: approved
owner: Product Owner
version: "1.0"
last_updated: 2026-08-16
tags: [demo, booking]
---

# BR-DEMO-001 — Self-service meeting room booking

> Example business requirement (fictional domain) — see [`../00-context/objectives-and-scope.md`](../00-context/objectives-and-scope.md) for the full project rationale and [`../../docs/conventions.md`](../../docs/conventions.md), section 2, for the ID convention used here.

## Context

Employees today book meeting rooms by messaging the front desk. The process is slow, error-prone, and generates double bookings when two people message the front desk at the same time.

## Requirement

An employee must be able to book any available meeting room on their own, without the front desk as an intermediary, in real time — with immediate confirmation or conflict information.

## Business rationale

Removing the front-desk intermediary shortens booking time from hours (waiting for a reply) to seconds, and eliminates a class of errors (double booking) caused by the manual, asynchronous process.

## Acceptance criteria

- An employee can book a room without contacting the front desk.
- The system does not allow two time-overlapping bookings for the same room.

## Related

- Implemented by: [`FR-DEMO-001`](../functional/DEMO/FR-DEMO-001.md)
- Constraint: [`POL-DEMO-001`](../policies/POL-DEMO-001.md) — long bookings require approval
