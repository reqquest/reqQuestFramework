---
id: REQQF-FR-BOOKING-001
legacy_id: FR-BOOKING-001
title: Booking a room for a time slot
short_title: room-booking
type: FR
status: approved
owner: role-tech-lead
version: "1.1"
last_updated: 2026-11-22
tags: [example, booking]
category: BOOKING
traces_to: [REQQF-BR-BOOKING-001]
---

# REQQF-FR-BOOKING-001 — Booking a room for a time slot

> Example functional requirement (fictional domain) — implements [`REQQF-BR-BOOKING-001-self-service-booking`](../../business/REQQF-BR-BOOKING-001-self-service-booking.md).

## Description

The system shall allow an employee to create a room booking by specifying the room, the date, the start time and the end time. The system rejects an attempt to create a booking if the specified time slot overlaps an existing booking of the same room.

## Acceptance criteria

- A booking is created only when the specified slot does not overlap any existing booking of the same room.
- An attempt to create an overlapping booking returns an unambiguous error message that identifies the conflicting booking.
- A booking is visible to all employees immediately after it is created.

## Related

- Derives from: [`REQQF-BR-BOOKING-001-self-service-booking`](../../business/REQQF-BR-BOOKING-001-self-service-booking.md)
- Design decision on the locking mechanism: [`REQQF-ADR-BOOKING-001-concurrent-booking-lock`](../../adrs/REQQF-ADR-BOOKING-001-concurrent-booking-lock.md)
- Covered by test: [`REQQF-TC-BOOKING-001-reject-conflicting-booking`](../../testcases/REQQF-TC-BOOKING-001-reject-conflicting-booking.md)
- Related non-functional requirement: [`REQQF-NFR-PERF-001-room-list-load-time`](../../nonfunctional/performance/REQQF-NFR-PERF-001-room-list-load-time.md)
