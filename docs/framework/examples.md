---
title: Examples — reqQuest Framework
owner: CTO
status: approved
last_updated: 2026-11-23
tags: [reqquest-framework, examples]
---

# Examples / Case Studies

> **Level:** Proof, not declaration
> **Owner:** CTO

**This section is deliberately separate from the core of the methodology** ([`vision-and-principles.md`](vision-and-principles.md), [`artifacts-and-structure.md`](artifacts-and-structure.md), [`from-problem-to-requirement.md`](from-problem-to-requirement.md), [`process-and-working-modes.md`](process-and-working-modes.md), [`requirements-management.md`](requirements-management.md), [`conventions.md`](conventions.md)) — the core rests only on the hard principles of IREB and on generic illustrations; the Case Studies below prove that it works in practice, they are not a source of examples for the core. The main reference point for someone who wants to adopt reqQuest Framework in their own repository straight away is a different one: the toolkit (`requirements/` + `.reqq/`) installed from a release (see [`../starter-kit.md`](../starter-kit.md)) — a working skeleton, not just a description. Below, short and to the point, evidence from reqQuest practice — without explaining basic domain terms, only the application of the methodology:

1. **reqQuestGov** — reqQuest corporate documentation managed like requirements.
2. **Contracts as Code** — legal documents (contracts, policies) as reqQuest Framework, traced end to end from the legal basis to the rendered clause.
3. **reqClient** — a reqQuest web application whose requirements live next to the code, traced from the business requirement to the source files.

## Case Study: reqQuestGov as reqQuest Framework

`reqQuestGov` — the sister, internal repository of reqQuest organisational knowledge — is a dogfooded instance of the same methodology you are reading now. It implements it literally:

| reqQuest Framework practice | What it looks like in reqQuestGov |
|---|---|
| Artifacts as files (see [`artifacts-and-structure.md`](artifacts-and-structure.md)) | All corporate knowledge — mission, strategies, processes, contracts — as Markdown in `docs/`, not in Word or Confluence |
| Glossary as a single source of truth | One file, one definition per term |
| Version control | The full change history of every strategic document is in `git log` — who changed the company mission, when and why can be reconstructed |
| Validation through review (see [`from-problem-to-requirement.md`](from-problem-to-requirement.md)) | A change to a strategic document goes through a Pull Request and a review by the document owner |
| Quality enforced in CI | Lint and a strict-mode build block merging a document with errors |
| Traceability (see [`requirements-management.md`](requirements-management.md)) | Strategic documents link to the sources they rely on — from the CPRE Foundation Level Handbook to specific internal files |

## Case Study: Contracts as Code as reqQuest Framework

Contracts as Code is a working, production reqQuest system that manages legal documents (contracts, policies) in the model *Requirements as Code → Compliance as Code → Contracts as Code → Documents*, kept in a separate, private reqQuest repository. It contains not a single line of production code in the software sense — and yet it implements traceability, conflict management and template-based work products exactly as described in [`requirements-management.md`](requirements-management.md), [`from-problem-to-requirement.md`](from-problem-to-requirement.md) and [`artifacts-and-structure.md`](artifacts-and-structure.md). Below: one real thread, traced from the legal basis to the rendered clause in the document — the confidentiality obligation in an NDA.

| Step (Handbook) | Implementation in Contracts as Code |
|---|---|
| **1. Source** (Sources for Requirements) | Legal basis: the Polish Civil Code (Art. 353¹, freedom of contract) and the Act on Combating Unfair Competition (Art. 11, trade secret) — an external normative source, not a stakeholder's wish |
| **2. Requirement as an artifact** (Work Products) | A standalone, versioned file `CAP-001-confidentiality.md`: `id`, `status`, `version`, sections `Regulatory Basis`, `Description`, `Parameters`, `Template Fragment` (template-based work product) |
| **3. Conflict identified and documented** (Resolving Conflicts) | The `Conflicts` section in the same file: `CAP-015 (audit_rights)` — the right to audit collides with the confidentiality obligation; resolution: extend the confidentiality obligation to the auditor, recorded permanently in the artifact |
| **4. Activation rule** (Traceability, direction "what includes the requirement") | `R-003-nda-scope.md`: `Trigger: contract.type == nda` → `Include capabilities: CAP-001, CAP-018, CAP-019, CAP-020`, citing the same regulatory source as step 1 |
| **5. Document configuration** (Configurations & Baselines) | `dsl/nda.yml`: `capabilities: [CAP-001, ...]`, `rules: [R-003, ...]`, plus deployment-specific parameters (`term.years: 3`, `venue: "Bydgoszcz"`) |
| **6. Rendering and evidence in the text** (Traceability, explicit form) | A source annotation right next to the rendered text: `<!-- source: CAP-001 confidentiality \| Civil Code, Act on Combating Unfair Competition \| v1.2 -->` above `## §2 Confidentiality obligation` |

```
Civil Code + Act on Combating Unfair Competition  →  CAP-001 v1.2 (conflict with CAP-015, documented)
  →  R-003 nda_scope: contract.type==nda → CAP-001,...
  →  dsl/nda.yml: capabilities:[CAP-001,...], term.years:3
  →  NDA §2 "Confidentiality obligation" + <!-- source: CAP-001 -->
```

Six steps, six different files, each versioned separately in git, each linked to its neighbours by an identifier — without a single dedicated requirements management tool. This is reqQuest Framework.

## Case Study: reqClient as reqQuest Framework

reqQuest Framework is first of all a methodology for software development, and the two examples above are corporate documentation and legal documents, not code. reqClient is a reqQuest web application for managing the requirements lifecycle, kept in a separate, private repository. Its requirements live in the same repository as the code. reqClient adopted the reqQuest Framework toolkit (the version recorded in `.reqq/toolkit.lock`) and extends it for its own needs: the front matter with relation and coverage fields (`derives_from`, `decisions`, `coverage`, `tests`), which the framework schema allows, and the validation with scripts that compute code coverage. Below: one thread, user login, traced from the business need to the code.

| Step | Implementation in reqClient |
|---|---|
| **1. Business requirement** | `BR-AUTH-001` (`approved`): every user shall authenticate, and their identity is available throughout the session lifecycle. Rationale: the application shows sensitive data — requirements, traceability, coverage metrics. A test decides the acceptance criteria, e.g. "after the session expires, the user lands on the login page" |
| **2. Design decision** (ADR) | `ADR-AUTH-001` (`approved`): OIDC + PKCE login in an in-house implementation, without a ready-made provider library. The ADR compares the rejected alternatives and sets token lifetimes that keep the 8-hour session limit |
| **3. Functional requirement** (Traceability, direction "where it comes from") | `FR-AUTH-001` (`review`), the login screen. Front matter: `derives_from: [BR-AUTH-001]`, `decisions: [ADR-AUTH-001]` (in the framework schema the link to the BR is expressed by `traces_to`) |
| **4. Code coverage** (Traceability, direction "what implements it") | The same front matter: `coverage.code` points to five application files, `coverage.api` to the identity provider calls |
| **5. Gap visible in the artifact** | `tests: []` — the missing test for `FR-AUTH-001` is visible in the requirement file itself, not only in a report at the end of the project |
| **6. Validation and approval** | Every PR that changes `requirements/` runs the validator with `--all`. The status `review` means that `FR-AUTH-001` is waiting for approval by a human |

```
BR-AUTH-001 (approved)
  →  ADR-AUTH-001 (approved): OIDC + PKCE, session up to 8 h
  →  FR-AUTH-001 (review): derives_from BR-AUTH-001, decisions ADR-AUTH-001
  →  coverage.code: 5 application files · tests: [] (gap made explicit)
```

reqClient shows the same thread in its own interactive dependency graph (`FR-TRC-003`), built from the requirements' front matter. A requirements management product thus manages its own requirements with the methodology it supports.

## Related documents

- [`conventions.md`](conventions.md) — conventions used in the examples above
- [`../../requirements/README.md`](../../requirements/README.md) — starter skeleton to adopt in your own repository
