---
id: REQQF-FR-AUTH-001
legacy_id: FR-AUTH-001
title: Employee login through company SSO
short_title: sso-login
type: FR
status: approved
owner: role-tech-lead
version: "1.1"
last_updated: 2026-11-22
tags: [example, auth]
category: AUTH
traces_to: [REQQF-BR-BOOKING-001]
---

# REQQF-FR-AUTH-001 — Employee login through company SSO

> Example functional requirement (fictional domain) — implements [`REQQF-BR-BOOKING-001-self-service-booking`](../../business/REQQF-BR-BOOKING-001-self-service-booking.md).

## Description

The system shall authenticate an employee through the company single sign-on (SSO), without a separate password for the booking system. A booking is always created by a logged-in employee, and the system records them as its author.

## Acceptance criteria

- A user who is not logged in sees only the login screen.
- After logging in through SSO, the employee lands on the room list without entering an additional password.
- Every booking has its author recorded — the logged-in employee.

## Related

- Derives from: [`REQQF-BR-BOOKING-001-self-service-booking`](../../business/REQQF-BR-BOOKING-001-self-service-booking.md)
- Design decision on the login mechanism: [`REQQF-ADR-AUTH-001-oidc-login`](../../adrs/REQQF-ADR-AUTH-001-oidc-login.md)
- Related non-functional requirement: [`REQQF-NFR-SEC-001-session-timeout`](../../nonfunctional/security/REQQF-NFR-SEC-001-session-timeout.md)
