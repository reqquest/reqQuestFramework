---
id: REQQF-ADR-AUTH-001
legacy_id: ADR-AUTH-001
title: Login through OIDC with the company identity provider
short_title: oidc-login
type: ADR
status: approved
owner: role-architect
version: "1.1"
last_updated: 2026-11-22
tags: [example, auth, sso]
traces_to: [REQQF-FR-AUTH-001, REQQF-NFR-SEC-001]
decisions:
  - "Authentication through OpenID Connect with the company identity provider (IdP); the system stores no passwords."
---

# REQQF-ADR-AUTH-001 — Login through OIDC with the company identity provider

> Example architecture decision (fictional domain) — implements [`REQQF-FR-AUTH-001-sso-login`](../functional/AUTH/REQQF-FR-AUTH-001-sso-login.md) and [`REQQF-NFR-SEC-001-session-timeout`](../nonfunctional/security/REQQF-NFR-SEC-001-session-timeout.md).

## Context

Employees already have accounts with the company identity provider (IdP). Separate passwords for the booking system would mean a second set of credentials to maintain and to revoke when an employee leaves the company.

## Options considered

- **Own accounts and passwords** — full control over login, but a second set of credentials and own handling of password resets.
- **OpenID Connect with the company IdP** — a single login for the employee; disabling the account in the IdP also cuts off access to bookings.

## Decision

OpenID Connect with the company IdP. The system stores no passwords; the application sets the session lifetime in line with [`REQQF-NFR-SEC-001-session-timeout`](../nonfunctional/security/REQQF-NFR-SEC-001-session-timeout.md).

## Consequences

- Login availability depends on IdP availability.
- Revoking access comes down to disabling the account in the IdP.

## Related

- Implements: [`REQQF-FR-AUTH-001-sso-login`](../functional/AUTH/REQQF-FR-AUTH-001-sso-login.md), [`REQQF-NFR-SEC-001-session-timeout`](../nonfunctional/security/REQQF-NFR-SEC-001-session-timeout.md)
