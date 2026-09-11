---
id: ADR-DEMO-001
title: Locking mechanism for concurrent booking
type: ADR
status: accepted
owner: Architect
version: "1.0"
last_updated: 2026-08-16
tags: [demo, booking, concurrency]
traces_to: [FR-DEMO-001]
decisions:
  - "Booking conflict is detected via optimistic locking (a `version` field on the room), not pessimistic locking."
---

# ADR-DEMO-001 — Locking mechanism for concurrent booking

> Example architecture decision (fictional domain) — implements [`FR-DEMO-001`](../functional/DEMO/FR-DEMO-001.md).

## Context

Two employees may try to book the same room for an overlapping time slot almost simultaneously. The system must resolve the conflict deterministically, without blocking other users' reads of the room list while the conflict is being resolved.

## Options considered

- **Pessimistic locking** — locks the room row for the duration of the booking transaction. Simpler to implement, but blocks concurrent read/write of other bookings for the same room.
- **Optimistic locking** — each booking carries the expected version of the room's state; the write is rejected if the version has since drifted. Requires client-side retry handling, but does not block reads.

## Decision

Optimistic locking with a `version` field on the room entity — the booking write is conditional on the current version, a conflict returns an error to the client instead of blocking other users.

## Consequences

- The client must handle the conflict error and offer the user a retry.
- No waiting locks — better throughput under a large number of concurrent users (see [`NFR-DEMO-001`](../nonfunctional/performance/NFR-DEMO-001.md)).

## Related

- Implements: [`FR-DEMO-001`](../functional/DEMO/FR-DEMO-001.md)
