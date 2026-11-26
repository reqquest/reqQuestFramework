---
id: REQQF-POL-PRIVACY-001
legacy_id: POL-PRIVACY-001
title: Retention of personal data in bookings
short_title: booking-data-retention
type: POL
status: approved
owner: role-product-owner
version: "1.1"
last_updated: 2026-11-22
tags: [example, privacy]
category: PRIVACY
traces_to: [REQQF-BR-BOOKING-001]
---

# REQQF-POL-PRIVACY-001 — Retention of personal data in bookings

> Example policy (fictional domain) — constrains the implementation of [`REQQF-BR-BOOKING-001-self-service-booking`](../business/REQQF-BR-BOOKING-001-self-service-booking.md).

## Policy statement

The personal data of a booking's author (first name, last name, email address) is kept for 90 days after the booking ends. After that the booking stays in the room's occupancy history, but without the author's data.

## Rationale

The room occupancy history is needed for planning, and the author's data only for handling current bookings and explaining conflicts. A shorter retention limits the scope of the personal data processed.

## Related

- Constrains: [`REQQF-BR-BOOKING-001-self-service-booking`](../business/REQQF-BR-BOOKING-001-self-service-booking.md)
- Applies to the booking author recorded by [`REQQF-FR-AUTH-001-sso-login`](../functional/AUTH/REQQF-FR-AUTH-001-sso-login.md)
