---
id: FR-DEMO-001
title: Book a room for a time slot
type: FR
status: approved
owner: Tech Lead
version: "1.0"
last_updated: 2026-08-16
tags: [demo, booking]
category: DEMO
traces_to: [BR-DEMO-001]
---

# FR-DEMO-001 — Book a room for a time slot

> Example functional requirement (fictional domain) — implements [`BR-DEMO-001`](../../business/BR-DEMO-001.md).

## Description

The system must let an employee create a room booking by specifying the room, date, start time, and end time. The system rejects an attempt to create a booking if the specified time slot overlaps with an existing booking for the same room.

## Acceptance criteria

- A booking is created only when the specified slot does not conflict with any existing booking for the same room.
- An attempt to create a conflicting booking returns an unambiguous error message identifying the conflicting booking.
- The booking is visible to all employees immediately after creation.

## Related

- Derives from: [`BR-DEMO-001`](../../business/BR-DEMO-001.md)
- Design decision on the locking mechanism: [`ADR-DEMO-001`](../../adrs/ADR-DEMO-001.md)
- Covered by test: [`TC-DEMO-001`](../../testcases/TC-DEMO-001.md)
- Related non-functional requirement: [`NFR-DEMO-001`](../../nonfunctional/performance/NFR-DEMO-001.md)
