---
id: REQQF-BR-BOOKING-001
legacy_id: BR-BOOKING-001
title: Self-service meeting-room booking
short_title: self-service-booking
type: BR
status: approved
owner: role-product-owner
version: "1.1"
last_updated: 2026-11-22
tags: [example, booking]
---

# REQQF-BR-BOOKING-001 — Self-service meeting-room booking

> Example business requirement (fictional domain) — see [`../00-context/objectives-and-scope.md`](../00-context/objectives-and-scope.md) for the full business case of the project and [`conventions.md`](https://github.com/reqquest/reqQuestFramework/blob/main/docs/framework/conventions.md), section 2, for the ID convention used here.

## Context

Today employees book meeting rooms by sending messages to reception. The process is slow, error-prone and produces double bookings when two people write to reception at the same time.

## Requirement

An employee shall be able to book any available meeting room on their own, without reception as an intermediary, in real time — with an immediate confirmation or information about a conflict.

## Business case

Removing reception as an intermediary cuts the booking time from hours (waiting for a reply) to seconds, and eliminates a class of errors (double booking) that comes from a manual, asynchronous process.

## Acceptance criteria

- An employee can book a room without contacting reception.
- The system does not allow two bookings of the same room that overlap in time.

## Related

- Implemented by: [`REQQF-FR-BOOKING-001-room-booking`](../functional/BOOKING/REQQF-FR-BOOKING-001-room-booking.md)
- Login of the booking's author: [`REQQF-FR-AUTH-001-sso-login`](../functional/AUTH/REQQF-FR-AUTH-001-sso-login.md)
- Constraint: [`REQQF-POL-BOOKING-001-long-booking-approval`](../policies/REQQF-POL-BOOKING-001-long-booking-approval.md) — long bookings require approval
- Constraint: [`REQQF-POL-PRIVACY-001-booking-data-retention`](../policies/REQQF-POL-PRIVACY-001-booking-data-retention.md) — retention of the booking author's personal data
