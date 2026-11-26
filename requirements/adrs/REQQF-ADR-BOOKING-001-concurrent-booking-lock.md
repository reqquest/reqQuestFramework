---
id: REQQF-ADR-BOOKING-001
legacy_id: ADR-BOOKING-001
title: Locking mechanism for concurrent bookings
short_title: concurrent-booking-lock
type: ADR
status: approved
owner: role-architect
version: "1.1"
last_updated: 2026-11-22
tags: [example, booking, concurrency]
traces_to: [REQQF-FR-BOOKING-001]
decisions:
  - "A booking conflict is detected through optimistic locking (a `version` field on the room), not pessimistic locking."
---

# REQQF-ADR-BOOKING-001 — Locking mechanism for concurrent bookings

> Example architecture decision (fictional domain) — implements [`REQQF-FR-BOOKING-001-room-booking`](../functional/BOOKING/REQQF-FR-BOOKING-001-room-booking.md).

## Context

Two employees may try to book the same room for an overlapping slot almost at the same time. The system must resolve the conflict deterministically, without blocking other users from reading the room list while they wait for the outcome.

## Options considered

- **Pessimistic locking** — a lock on the room row for the duration of the booking transaction. Simpler to implement, but it blocks concurrent reads/writes of other bookings of the same room.
- **Optimistic locking** — every booking carries the expected version of the room's state; the write is rejected if the version has changed in the meantime. It requires retry handling on the client side, but does not block reads.

## Decision

Optimistic locking with a `version` field on the room entity — the booking write is conditional on the current version, and a conflict returns an error to the client instead of blocking other users.

## Consequences

- The client must handle the conflict error and offer the user another attempt.
- No locks while waiting — better throughput with a large number of concurrent users (see [`REQQF-NFR-PERF-001-room-list-load-time`](../nonfunctional/performance/REQQF-NFR-PERF-001-room-list-load-time.md)).

## Related

- Implements: [`REQQF-FR-BOOKING-001-room-booking`](../functional/BOOKING/REQQF-FR-BOOKING-001-room-booking.md)
