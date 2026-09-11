---
id: TC-DEMO-001
title: Reject a conflicting room booking
type: TC
status: accepted
owner: Tech Lead
version: "1.0"
last_updated: 2026-08-16
tags: [demo, booking]
derives_from: [FR-DEMO-001, NFR-DEMO-001]
---

# TC-DEMO-001 — Reject a conflicting room booking

> Example test case (fictional domain) — covers [`FR-DEMO-001`](../functional/DEMO/FR-DEMO-001.md) and [`NFR-DEMO-001`](../nonfunctional/performance/NFR-DEMO-001.md).

## Preconditions

Room "Room A" has an existing booking 10:00–11:00.

## Steps

1. An employee tries to create a booking for "Room A" for the 10:30–11:30 slot.
2. The system checks for a conflict against existing bookings.

## Expected result

- The booking is not created.
- The returned error message identifies the conflicting booking (10:00–11:00).
- The room list, refreshed after the failed attempt, still loads in ≤ 2s (see [`NFR-DEMO-001`](../nonfunctional/performance/NFR-DEMO-001.md)).

## Related

- Covers: [`FR-DEMO-001`](../functional/DEMO/FR-DEMO-001.md), [`NFR-DEMO-001`](../nonfunctional/performance/NFR-DEMO-001.md)
