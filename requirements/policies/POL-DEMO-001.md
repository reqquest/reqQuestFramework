---
id: POL-DEMO-001
title: Approving long bookings
type: POL
status: accepted
owner: Office administrator
version: "1.0"
last_updated: 2026-08-16
tags: [demo, booking]
category: DEMO
traces_to: [BR-DEMO-001]
---

# POL-DEMO-001 — Approving long bookings

> Example policy (fictional domain) — constrains the implementation of [`BR-DEMO-001`](../business/BR-DEMO-001.md).

## Policy statement

A room booking lasting more than 4 hours (see the definition of "long booking" in the [`glossary`](../00-context/glossary.md)) requires approval from the office administrator before it is finally confirmed — self-service booking from [`BR-DEMO-001`](../business/BR-DEMO-001.md) remains the default mode, this policy is its only exception.

## Rationale

Long bookings more often block a room for the whole day or go beyond ordinary meetings (e.g. workshops, events) — the office administrator needs visibility to avoid conflicts with planned cleaning or room maintenance.

## Related

- Constrains: [`BR-DEMO-001`](../business/BR-DEMO-001.md)
