---
id: REQQF-POL-BOOKING-001
legacy_id: POL-BOOKING-001
title: Approval of long bookings
short_title: long-booking-approval
type: POL
status: approved
owner: role-product-owner
version: "1.3"
last_updated: 2026-11-22
tags: [example, booking]
category: BOOKING
traces_to: [REQQF-BR-BOOKING-001]
conflict:
  - with: REQQF-BR-BOOKING-001
    resolution: accepted
    rationale: "PR #14"
---

# REQQF-POL-BOOKING-001 — Approval of long bookings

> Example policy (fictional domain) — constrains the implementation of [`REQQF-BR-BOOKING-001-self-service-booking`](../business/REQQF-BR-BOOKING-001-self-service-booking.md).

## Policy statement

A room booking that lasts longer than 4 hours (see the definition of "long booking" in the [project glossary](../00-context/glossary.project.md)) requires approval by the office administrator before it is finally confirmed — self-service booking from [`REQQF-BR-BOOKING-001-self-service-booking`](../business/REQQF-BR-BOOKING-001-self-service-booking.md) remains the default mode, and this policy is its only exception.

## Rationale

Long bookings more often block a room for a whole day or go beyond ordinary meetings (e.g. workshops, events) — the office administrator needs visibility to avoid a conflict with planned cleaning or maintenance of the room.

## Notes

- **Conflict with [`REQQF-BR-BOOKING-001-self-service-booking`](../business/REQQF-BR-BOOKING-001-self-service-booking.md), resolved (`accepted`, PR #14):** self-service with immediate confirmation clashes with the administrator approving long bookings. The policy was accepted as the only exception to self-service; the entry stays in `conflict` as a permanent record of the decision.

## Related

- Constrains: [`REQQF-BR-BOOKING-001-self-service-booking`](../business/REQQF-BR-BOOKING-001-self-service-booking.md)
