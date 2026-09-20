---
id: NFR-DEMO-001
title: Room list load time
type: NFR
status: approved
owner: Tech Lead
version: "1.0"
last_updated: 2026-08-16
tags: [demo, performance]
category: performance
traces_to: [FR-DEMO-001]
---

# NFR-DEMO-001 — Room list load time

> Example non-functional requirement (fictional domain) — complements [`FR-DEMO-001`](../../functional/DEMO/FR-DEMO-001.md).

## Description

The list of available rooms, together with their occupancy status for the next 24h, must load in no more than 2 seconds under typical load (up to 200 concurrent users).

## Acceptance criteria

- P95 response time of the room list endpoint ≤ 2s at 200 concurrent users.
- Exceeding the threshold is detectable via monitoring, not only through a user report.

## Related

- Complements: [`FR-DEMO-001`](../../functional/DEMO/FR-DEMO-001.md)
- Covered by test: [`TC-DEMO-001`](../../testcases/TC-DEMO-001.md)
