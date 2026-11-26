---
id: REQQF-TC-BOOKING-001
legacy_id: TC-BOOKING-001
title: Rejecting a conflicting room booking
short_title: reject-conflicting-booking
type: TC
status: approved
owner: role-tech-lead
version: "1.1"
last_updated: 2026-11-22
tags: [example, booking]
derives_from: [REQQF-FR-BOOKING-001@1.1, REQQF-NFR-PERF-001]
---

# REQQF-TC-BOOKING-001 — Rejecting a conflicting room booking

> Example test case (fictional domain) — covers [`REQQF-FR-BOOKING-001-room-booking`](../functional/BOOKING/REQQF-FR-BOOKING-001-room-booking.md) and [`REQQF-NFR-PERF-001-room-list-load-time`](../nonfunctional/performance/REQQF-NFR-PERF-001-room-list-load-time.md).

## Preconditions

The room "Room A" has an existing booking 10:00–11:00.

## Steps

1. An employee tries to create a booking of "Room A" for the slot 10:30–11:30.
2. The system checks for overlaps with existing bookings.

## Expected result

- The booking is not created.
- The returned error message identifies the conflicting booking (10:00–11:00).
- The room list, refreshed after the failed attempt, still loads in ≤ 2s (see [`REQQF-NFR-PERF-001-room-list-load-time`](../nonfunctional/performance/REQQF-NFR-PERF-001-room-list-load-time.md)).

## Related

- Covers: [`REQQF-FR-BOOKING-001-room-booking`](../functional/BOOKING/REQQF-FR-BOOKING-001-room-booking.md), [`REQQF-NFR-PERF-001-room-list-load-time`](../nonfunctional/performance/REQQF-NFR-PERF-001-room-list-load-time.md)
