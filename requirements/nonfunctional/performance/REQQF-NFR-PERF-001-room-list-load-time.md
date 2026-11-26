---
id: REQQF-NFR-PERF-001
legacy_id: NFR-PERF-001
title: Load time of the available-room list
short_title: room-list-load-time
type: NFR
status: approved
owner: role-tech-lead
version: "1.1"
last_updated: 2026-11-22
tags: [example, performance]
category: performance
traces_to: [REQQF-FR-BOOKING-001]
---

# REQQF-NFR-PERF-001 — Load time of the available-room list

> Example non-functional requirement (fictional domain) — complements [`REQQF-FR-BOOKING-001-room-booking`](../../functional/BOOKING/REQQF-FR-BOOKING-001-room-booking.md).

## Description

The list of available rooms, together with their occupancy status for the next 24h, shall load in no more than 2 seconds under typical load (up to 200 concurrent users).

## Acceptance criteria

- P95 of the room-list endpoint response time ≤ 2s with 200 concurrent users.
- Exceeding the threshold is detectable by monitoring, not only by a user report.

## Related

- Complements: [`REQQF-FR-BOOKING-001-room-booking`](../../functional/BOOKING/REQQF-FR-BOOKING-001-room-booking.md)
- Covered by test: [`REQQF-TC-BOOKING-001-reject-conflicting-booking`](../../testcases/REQQF-TC-BOOKING-001-reject-conflicting-booking.md)
