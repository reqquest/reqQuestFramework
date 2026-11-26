---
id: REQQF-NFR-SEC-001
legacy_id: NFR-SEC-001
title: Session expiry after inactivity
short_title: session-timeout
type: NFR
status: approved
owner: role-tech-lead
version: "1.1"
last_updated: 2026-11-22
tags: [example, security]
category: security
traces_to: [REQQF-FR-AUTH-001]
---

# REQQF-NFR-SEC-001 — Session expiry after inactivity

> Example non-functional requirement (fictional domain) — complements [`REQQF-FR-AUTH-001-sso-login`](../../functional/AUTH/REQQF-FR-AUTH-001-sso-login.md).

## Description

An employee's session expires after 30 minutes of inactivity. After expiry every operation requires logging in again through SSO.

## Acceptance criteria

- A request from a session inactive for more than 30 minutes is rejected and redirects to the login.
- A booking not saved at the moment the session expires is not created.

## Related

- Complements: [`REQQF-FR-AUTH-001-sso-login`](../../functional/AUTH/REQQF-FR-AUTH-001-sso-login.md)
- Design decision: [`REQQF-ADR-AUTH-001-oidc-login`](../../adrs/REQQF-ADR-AUTH-001-oidc-login.md)
