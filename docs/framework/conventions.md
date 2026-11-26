---
title: reqQuest Framework Conventions — Starter Kit
owner: reqQuest
status: approved
last_updated: 2026-11-23
tags: [reqquest-framework, conventions, starter-kit]
---

# reqQuest Framework Conventions — Starter Kit

> **Level:** Practical — ready to deploy
> **Owner:** CTO

## How to read this document

[`vision-and-principles.md`](vision-and-principles.md), [`artifacts-and-structure.md`](artifacts-and-structure.md), [`from-problem-to-requirement.md`](from-problem-to-requirement.md), [`process-and-working-modes.md`](process-and-working-modes.md) and [`requirements-management.md`](requirements-management.md) explain *why* — how IREB requirements translate into git mechanisms. This document is the *how* — a concrete, ready-to-deploy set of conventions with which you can start managing requirements right away in any repository, whether it holds code, legal documents or an HR policy. **This is a configurable pattern, not a mandate** — the conventions below are implemented in the toolkit (`requirements/`, `.reqq/`, `.reqqignore` — see [`../../requirements/README.md`](../../requirements/README.md) and [`../../.reqq/README.md`](../../.reqq/README.md)), which you install in a new project from a release asset (see [`../starter-kit.md`](../starter-kit.md)), but reqQuest Framework does not require exactly these types or exactly these status values, only the presence of an equivalent for each category.

## 1. Front-matter schema

The minimal set of fields that implements the "Attributes" and "Work Products" practices (the characteristic of an artifact):

```yaml
---
title: <readable title>
owner: <responsible role or person; from the catalog level, a role key from roles.yaml>
status: draft | review | approved | deprecated
last_updated: <YYYY-MM-DD>
tags: [<keywords for filtering>]
---
```

When the repository enables ownership governance at the `catalog` level or higher, `owner` is a role key from the catalog `requirements/00-context/roles.yaml`, e.g. `role-architect` (section 7, ["Ownership governance"](#ownership-governance)).

Optional extensions, added when the artifact needs them (the `id`/`version` fields — see section 2 below for examples of their practical use):

```yaml
id: <[PREFIX-]TYPE-CATEGORY-NNN>    # see section 2
legacy_id: <TYPE-CATEGORY-NNN>      # the last previous ID, see section 2
short_title: <1–4 English words>    # short title in the file name, see section 2
version: "<major.minor>"
traces_to: [<ID>, ...]  # see section 4
conflict:
  - with: <ID>
    resolution: accepted | rejected | superseded
    rationale: "<PR or ADR with the rationale>"
```

Write the `version` field in quotes: without them the YAML parser reads `1.10` as the number `1.1`. A change to the substance of the content bumps `version`; an editorial change (a typo, formatting) need not. The validator does not enforce this rule — the author and the reviewer keep to it. Marking dependent documents for review depends on it (section 4).

A `conflict` entry without `resolution` blocks the `approved` status — the validator reports an error. The field's lifecycle and the meaning of its values are described in [`from-problem-to-requirement.md`](from-problem-to-requirement.md), section "The `conflict` field".

## 2. ID and prefix convention

Pattern: `[PREFIX-]TYPE-CATEGORY-NNN`, where:

- the **prefix** (optional) identifies the repository — see "Repository prefix" below,
- the **type** identifies the kind of artifact,
- the **category** is the area (a feature, a quality attribute, a policy domain),
- the **number** is unique within the type and category.

The type is not just a label: in practice it maps directly onto the validator configuration, which defines which fields/attributes are required and checked automatically for a given artifact type (e.g. a different set of required fields for `ADR-<CATEGORY>-NNN` than for a functional requirement). The client can extend the type catalog freely, with two mandatory requirements: **uniqueness** of the ID within the repository and **stability over time** (a number once assigned is never reused, even after the artifact is removed) — and every new type needs a matching validator configuration, not only an entry in the table.

**Catalog discipline:** the set of types/categories in a given repository should reflect only what is actually used in it — do not import categories from sibling repositories or maintain a catalog much wider than the set actually in use. A growing number of unused categories makes onboarding and schema maintenance harder with no benefit.

**Convention implemented in the toolkit** (see [`../../requirements/README.md`](../../requirements/README.md) for the full directory skeleton and [`../../.reqq/schema/types/`](../../.reqq/schema/types/) for the JSON schemas of each type):

| ID (without prefix) | Artifact type | Where |
|---|---|---|
| `BR-<CATEGORY>-NNN` | Business Requirement | `requirements/business/` |
| `FR-<CATEGORY>-NNN` | Functional Requirement | `requirements/functional/<CATEGORY>/` |
| `NFR-<CODE>-NNN` | Non-Functional Requirement | `requirements/nonfunctional/<attribute>/` |
| `ADR-<CATEGORY>-NNN` | Architecture Decision Record | `requirements/adrs/` |
| `TC-<CATEGORY>-NNN` | Test Case | `requirements/testcases/` |
| `POL-<CATEGORY>-NNN` | Policy | `requirements/policies/` |

**Category:** in the ID it has 2–10 characters `[A-Z0-9]` (e.g. `BOOKING`, `AUTH`, `PRIVACY`). The `category` field (required for FR, NFR and POL) has, for FR and POL, the same value as the category in the ID, and an FR lies in the folder of that name (`functional/BOOKING/REQQF-FR-BOOKING-001-room-booking.md`). A non-functional requirement is grouped by quality attribute: its ID carries the attribute's code, and the folder and the `category` field carry the full name (`nonfunctional/performance/REQQF-NFR-PERF-001-room-list-load-time.md`, `category: performance`), because the full name often does not fit in 10 characters. The validator always checks the ID pattern, that its type part matches the `type` field, and that `category` is present. It checks the match with the folder once the `enforce_layout` key is enabled (below).

This exact set of types is dogfooded today independently in several private reqQuest repositories (a schema per type + validator + pre-commit hook + CI gate) — stronger proof of domain neutrality and repeatability than a single example. An alternative ADR numbering seen in practice: globally sequential `ADR-NNNN` (without a category segment) — both conventions meet the uniqueness and stability requirement; the choice between them depends on whether the repository has enough architecture decisions in different areas for segmenting by category to make sense.

**Repository prefix.** A repository can declare a prefix with the `id_prefix` key in `.reqq/validator/config.yaml`, e.g. `id_prefix: REQA`. The prefix precedes the whole ID (`REQA-FR-AGENT-001`), and the file name still equals the `id` (`REQA-FR-AGENT-001.md`) or, with a short title, starts with it (below). Thanks to it, the same `TYPE-CATEGORY-NNN` in two repositories of an organisation is two different IDs, and a link to a requirement of another repository can be written in `traces_to` (section 4). Rules:

- the prefix is 2–6 uppercase letters `[A-Z]`, **unique within the organisation** and equal to the repository key used in branch and issue names (branch `REQA#12` → prefix `REQA`); the organisation keeps its own register of prefixes,
- with `id_prefix`, every `id` in the repository has exactly this prefix, and every reference (`traces_to`, `derives_from`, `conflict[].with`) has either its own prefix or that of another repository; a reference without a prefix is an error, because one form of ID applies in a repository,
- a reference with another prefix points to a requirement of another repository; the validator does not check its existence, status or version (section 6),
- without `id_prefix`, no `id` or reference has a prefix,
- an invalid `id_prefix` value is a configuration error (exit code `3`).

The examples in the toolkit (numbers `001`–`099`, tag `example`) have the `REQQF` prefix of the framework repository, and `config.example.yaml` declares `id_prefix: REQQF`, so a freshly deployed toolkit passes validation. After you change `id_prefix` to your own repository's key, the validator points out the examples that are left to remove.

**Short title — `short_title`.** A repository can require a short title with the `short_title: true` key in `.reqq/validator/config.yaml`. The short title in the file name and in the link text tells a human what the requirement is about without opening the file. Rules:

- the `short_title` field has one to four English words of lowercase letters `a-z` and digits, joined by hyphens (`room-booking`, `sso-login`), regardless of `language` (section 8),
- with `short_title: true` the field is required, and the file name is `<id>-<short_title>.md`, e.g. `REQQF-FR-BOOKING-001-room-booking.md`,
- without the key or with `short_title: false` the file name equals the `id`, and the validator does not check the field,
- links (`traces_to`, `derives_from`, `conflict[].with`) contain only the ID, and the text of a Markdown link to a requirement file is the full file name without `.md`: `[REQQF-BR-BOOKING-001-self-service-booking](../../business/REQQF-BR-BOOKING-001-self-service-booking.md)`,
- changing `short_title` changes the file name and the links to it, but not the ID, so `legacy_id` does not record it,
- the validator checks the field's pattern and its match with the file name; the match with `title` and the link text are judged by the reviewer,
- a key value other than `true` or `false` is a configuration error (exit code `3`).

The examples in the toolkit have short titles, and `config.example.yaml` declares `short_title: true`, so a freshly deployed toolkit passes validation.

**Folder layout — `enforce_layout`.** A repository can require the folder layout with the `enforce_layout: true` key in `.reqq/validator/config.yaml`. The rules cover the files in `requirements/`:

- a BR lies in `business/`, an FR in `functional/<CATEGORY from the ID>/`, an NFR in `nonfunctional/<quality attribute>/`, an ADR in `adrs/`, a TC in `testcases/` and a POL in `policies/`,
- the `category` of an FR and a POL equals the category from the ID, and the `category` of an NFR equals the folder name,
- every NFR folder has one code in the ID, and every code one folder; the validator compares the whole corpus also when validating staged files, and the error goes to the validated files involved in the conflict,
- without the key or with `enforce_layout: false` the layout stays a convention and the validator does not check it,
- a key value other than `true` or `false` is a configuration error (exit code `3`).

The examples in the toolkit keep this layout, and `config.example.yaml` declares `enforce_layout: true`.

**ID change — `legacy_id`.** Introducing a prefix in an existing repository changes the IDs of all requirements: the file names, the `id` and the references. The optional `legacy_id` field stores **only the last** previous identifier, without a prefix, so that commits, PRs and issues from the history can be linked to the new ID. Earlier identifiers stay in the git history. `legacy_id` is not an ID in the requirements graph — a reference to it is dangling.

## 3. Lifecycle values (`status`)

Implementation of the "Life Cycle Management" practice. Recommended minimal set:

| Value | Meaning | Analogous IREB concept |
|---|---|---|
| `draft` | Being written, not reviewed | Work product before validation |
| `review` | Submitted for approval (open PR) | Under validation |
| `approved` | Approved, in force | Baseline |
| `deprecated` | Superseded or out of date, a historical entry | Outside the active scope, but still traceable |

## 4. Traceability convention

Implementation of the "Traceability" practice — two complementary levels:

**a) Structural (front matter)** — the `traces_to` field or an equivalent, listing the IDs of the source artifacts:

```yaml
traces_to: [<source-ID-1>, <source-ID-2>]
```

**b) Inline (a comment in the content)** — the source cited directly next to the fragment it concerns:

```markdown
<!-- source: <source-ID> | <short description of the source> | <version> -->
## The document fragment this source concerns
...
```

The choice between (a) and (b) depends on granularity: (a) is enough when the whole file comes from one source; (b) is needed when different fragments of the same document come from different sources. A full, end-to-end traced example of both levels at once: [`examples.md`](examples.md#case-study-contracts-as-code-as-reqquest-framework).

**Source version in a link.** An element of `traces_to` and, in a TC, of `derives_from` can name the version of the source the document last matched — `ID@major.minor`:

```yaml
derives_from: [REQQF-FR-BOOKING-001@1.1, REQQF-NFR-PERF-001]
```

When the source bumps `version` (section 1), the validator marks the document for review (`graph.suspect`, section 6). The author reviews the document, corrects its content if needed and, in the same PR, changes `@1.1` to the current version of the source — this change is the trace of the review. The version is optional: a link without it works as before, only the versions are not compared.

**Link to another repository.** A requirement of another repository is referenced by its ID with that repository's prefix (section 2), also with a version: `traces_to: [REQC-FR-AGENT-001@1.2]`. The validator cannot see that repository, so it does not check such a link.

## 5. Configurations and baseline

- **Configuration** (a consistent set during work) = branch.
- **Baseline** (a frozen, named point of reference) = a git **tag** (a lightweight marker pinned to a commit) or a git **release** (an independent object referencing a tag/commit, with packaged artifacts and release notes) — the full distinction and a recommendation on choosing between them: [`requirements-management.md`](requirements-management.md), section "Configurations and baseline".

Rule: a baseline is never edited retroactively — a change after a baseline is established is always a new tag/release, never an overwrite of the old one (identical to the "Unchangeability" property of a configuration, see [`requirements-management.md`](requirements-management.md)). reqQuest Framework does not decide how the client versions its own product or repository — the above applies only to the requirements baseline, not to reqQuest Framework toolkit releases (`toolkit-vX.Y.Z`).

## 6. Minimal set of CI checks

Implementation of the "Quality Criteria" practice as machine enforcement, not a declaration:

- Markdown format lint,
- validation of the front-matter schema/structure where an artifact has a rigid contract — in this repo: `.reqq/validator/reqq_validate.py`, the single entry point of the validator (one report and one exit code for CI and for the pre-commit hook, `.reqq/hooks/pre-commit`). Front matter is checked against the JSON schema from `.reqq/schema/`; a schema violation that no other rule reports is a `schema.contract` warning,
- **requirements graph integrity** — references between requirement identifiers (`traces_to`, `derives_from` in a TC, `conflict[].with`) point to existing documents in a consistent state. This is a different check from the Markdown links in the item below. Rules:
    - `graph.dangling` (error) — the reference points to an `id` that does not exist in any document of the corpus,
    - `graph.duplicate-id` (error) — the same `id` occurs in more than one file,
    - `graph.status-draft` (warning) — an `approved` document points to a `draft` or `review` document,
    - `graph.status-deprecated` (warning) — a document in a state other than `deprecated` points to a `deprecated` document,
    - `graph.suspect` (warning) — an `ID@version` link points to a version lower than the source's current `version`, so the document is due for review (section 4),
    - `graph.suspect-version` (error) — the version in an `ID@version` link cannot be compared: it is higher than the source's `version` or the source has no valid `version`.

    The corpus is the whole `requirements/` without excluded files (`.reqqignore`, `exclude_globs`), so a reference to an excluded file is dangling. The graph rules do not check references with another repository's prefix (section 2). The graph is built from the whole corpus also when validating single files or staged files, and only the validated files get the results. The state rules are warnings so as not to block the CI of repositories that already have such references, and `graph.suspect` is a warning so that a change of the source does not block CI. When validating staged files (pre-commit hook), only the files in the commit get `graph.suspect`, so bumping a source's `version` does not immediately mark the documents that depend on it; the validation of the whole corpus in CI does that. The rule alone does not detect a duplicate `id` from two parallel PRs: it shows up only in the CI of the second of them, and only when that PR is up to date with the target branch, which requires a repository setting (requiring an up-to-date branch before merging, or a merge queue). In this repo: `.reqq/validator/reqq_validate.py`, the rule code in the `kind` field of the result,
- **folder layout** — with `enforce_layout` enabled (section 2) the validator reports the errors `layout.path` (a file outside the expected folder), `layout.category` (`category` inconsistent with the ID or the folder) and `layout.nfr-code` (an NFR folder with several codes, or a code in several folders),
- **OpenAPI fragments** — a `yaml openapi` block in the content of a requirement is checked separately: `openapi.yaml`, `openapi.root`, `openapi.id` and `openapi.schema`, as warnings by default (section 9),
- **exclusions from validation through `.reqqignore`** — a file in a format analogous to `.gitignore` (one glob per line), in the root directory of the repository, honoured by the validator regardless of which specific implementation you replace it with. A portable equivalent of `exclude_globs` from `.reqq/validator/config.yaml` — the same file works regardless of the tool the repository actually uses to manage requirements,
- **internal link integrity check** — a deterministic script that checks that every relative Markdown link (`[...](*.md)`, with an optional anchor) resolves to an existing file in the repository (root-relative links, `/x.md`, are skipped — their base is set by the renderer; links with a title, in angle brackets `<...>` and reference-style `[...][ref]` links are not checked — use the plain form `[...](path.md)`); run locally and as a CI step, with the same mechanism as the other checks in this section — in this repo: the `links` check of the entry point `.reqq/validator/reqq_validate.py` (the pre-commit hook and the `requirements-validate.yml` workflow; the same check runs on its own as `.reqq/validator/reqq_check_links.py`; scanned folders: `link_check_paths` in `.reqq/validator/config.yaml`, by default `requirements/`, an empty list disables the check). This applies especially to documentation published as a site (a static generator, a wiki), where a dead link gives no immediate error signal the way `git mv` or deleting a file does.

None of the above is specific to software development — they all work the same way on a repository that contains not a single line of production code.

## 7. Business case document (starter type)

reqQuest Framework requires every repository that deploys the methodology to have one explicitly identifiable document that serves as the project's **business case** — the place where things are written down that cannot be inferred from the requirement files alone. **The name and exact location of this file in a specific repository are a project decision, not a mandate of this methodology** — what is described below is the required purpose and content, not a specific path.

The business case document should contain at least:

- **The goal and business case** of the project/repository — the overriding business requirement to which all other requirements refer.
- **A declaration of the adopted combination of IREP process facets** (Linear/Iterative, Prescriptive/Explorative, Customer-specific/Market-oriented) — see [`process-and-working-modes.md`](process-and-working-modes.md). Without this explicit declaration, different parts of the team easily work on contradictory, never agreed assumptions about the working mode.
- **A reference to the project's role catalog.** The roles that extend the minimal catalog from [`_index.md`](_index.md#scope-and-roles) (a human as author/reviewer, an AI agent under human supervision) with domain-specific roles are recorded in `requirements/00-context/roles.yaml`, the only role catalog in the repository (["Ownership governance"](#ownership-governance) below). The business case document does not repeat it.

**Direction of dependency.** The document is superior to the requirements and ADRs and may be more general than they are. Requirements and ADRs refer to it, and it does not refer to them. A new high-level topic goes into this document first, and then flows down to ADRs, NFRs and FRs — the flow of changes is described in [`requirements-management.md`](requirements-management.md), section "Source of truth and views".

It is a **living** document: it changes together with the project's goal and working mode. Roles are relatively stable, while the people who perform them change over time. That is why a requirement names a role, not a person: a change of person is a change of `handle` in `roles.yaml` and of the "Role" column in `stakeholders.md`, without rewriting the requirements.

**Name and location adopted in this repo (a recommendation, not a mandate):** `requirements/00-context/objectives-and-scope.md`, in the directory that numerically precedes the requirements folders, so that alphabetical order reflects the reading order. A filled-in example of such a document (fictional domain: a meeting-room booking system) — [`../../requirements/00-context/objectives-and-scope.md`](../../requirements/00-context/objectives-and-scope.md), part of the starter kit, not just a description of the concept. The toolkit delivers it as a starting file (`seed`) — after installation it belongs to the client.

**Rule for starting files — `boundary` and `seed`:** what the toolkit delivers to the client's repository is set by `toolkit-manifest.json`. The files on the `boundary` list belong to the toolkit — their hashes are recorded in `.reqq/toolkit.lock`, and `upgrade` replaces them, so the client does not edit them. The files on the `seed` list (e.g. `glossary.project.md`) are starting templates — they go into the toolkit package, but from the first installation they belong to the client, and `upgrade` does not add, replace or remove them. An example file that the client is meant to replace with their own content therefore belongs to `seed`, not to `boundary`. Filled-in example content makes onboarding easier than a bare description of the convention, which is why it is delivered with the toolkit — only `.reqqignore` excludes it from **validation** (see section 6), never from **delivery**.

### Ownership governance

The role catalog decides *who can be* the reviewer of a given area of requirements. The host's native mechanism enforces it: the `CODEOWNERS` file, which on a Pull Request touching a given path assigns its owners as reviewers and, with the requirement enabled, blocks the merge without their approval. Ownership governance connects the two. It is optional, and the repository chooses its strength. The commands and the rules `V1`–`V8` are described in [`../../.reqq/README.md`](../../.reqq/README.md), section "Ownership governance".

**Role catalog.** `requirements/00-context/roles.yaml` is the only role catalog in the repository. A role key has the form `role-<name>`. A role has a name (`title`), accounts on the host (`handle`: a user or a team) and areas of requirements (`responsible_for`: subdirectories of `requirements/` or `*` for the whole directory):

```yaml
roles:
  role-product-owner:
    title: "Product Owner"
    handle: "@example-org/product-owners"
    responsible_for:
      - "business"
      - "policies"

  role-architect:
    title: "Architect"
    handle: "@example-org/architects"
    responsible_for:
      - "adrs"
```

The catalog is used by:

- the `owner` field in a requirement — from the `catalog` level it is a role key (section 1);
- `requirements/00-context/stakeholders.md` — the last column of the table ("Role") gives the roles the stakeholder performs;
- the block in `.github/CODEOWNERS` — from the `generate` level it is built from `handle` and `responsible_for`.

The toolkit delivers the example `roles.example.yaml`, and you create `roles.yaml` as a copy of it with your own roles and `handle`. A small team can have one role with a list of accounts in `handle` and `responsible_for: ["*"]`.

**Levels.** The strength of governance is set by `ownership.mode` in `.reqq/validator/config.yaml`. The levels add up:

| Level | What it gives | When to choose it |
|---|---|---|
| no key (`undetected`) | only a warning that nobody has made a decision | the state right after installing the toolkit |
| `off` | nothing; a recorded opt-out with a date and an author (`decided`, `decided_by`) | a repository where splitting ownership makes no sense |
| `catalog` | checks the role catalog, `owner` in requirements and the roles in `stakeholders.md`; offline, independent of the host | a one-person repository or a host without code owner enforcement (GitLab CE/Free, a private repository on GitHub Free) |
| `generate` | + generates the CODEOWNERS block and checks that it is up to date, covers every requirements directory and protects the governance files | a team that wants reviewers assigned automatically without a hard gate |
| `enforce` | + checks in CI that the host requires code owner approval and recognises every `handle` | a team on a host with code owner enforcement, when a change of requirements must have the area owner's approval |

A missing `ownership` key does not mean "disabled": an opt-out is recorded explicitly as `off`, so that deleting the file does not silently disable governance.

**Conditions for `enforce`.** Today only on GitHub; `enforce` with `toolkit.host: gitlab` ends with a configuration error.

- At least two people meet the host's code owner threshold (GitHub: write, GitLab: Developer), because the host does not count the approval of the PR's author. The adopter checks the number of people, not the toolkit.
- Every branch that receives changes requires code owner approval, in branch protection or in a ruleset. A PR to a branch without this requirement ends with an error.
- CI has a token that reads the branch settings. `GITHUB_TOKEN` reads rulesets, but not classic branch protection; with the latter the adopter stores as the secret `OWNERS_VERIFY_TOKEN` a token with the permissions Administration: read and Contents: read.

When the toolkit cannot determine whether the host enforces the requirement, it reports a warning, never a silent success. A declared `enforce` on a host that does not enforce it ends with an error, not a silent downgrade of the level. The framework does not assign host permission levels to roles: `enforce` checks only the threshold from which the host recognises a code owner.

**CODEOWNERS block.** `reqq_owners.py generate` appends the block at the end of `.github/CODEOWNERS`, because on GitHub the last matching rule wins. The content outside the markers stays unchanged. For the catalog from the example above, the block looks like this:

```text
# reqq:begin - generated from requirements/00-context/roles.yaml by .reqq/validator/reqq_owners.py, do not edit
# requirements: responsible_for in roles.yaml
/requirements/business/** @example-org/product-owners
/requirements/policies/** @example-org/product-owners
/requirements/adrs/** @example-org/architects
# governance self-protection
/.reqq/** @example-org/product-owners @example-org/architects
/.github/CODEOWNERS @example-org/product-owners @example-org/architects
/.github/workflows/requirements-*.yml @example-org/product-owners @example-org/architects
/requirements/00-context/roles.yaml @example-org/product-owners @example-org/architects
/.reqqignore @example-org/product-owners @example-org/architects
# reqq:end
```

The `governance self-protection` section protects the files whose editing would disable governance. Its owners are all the `handle` values from the catalog, regardless of `responsible_for`.

**IREB mapping.**

| IREB requirement | reqQuest Framework mechanism | Proof of compliance | What omitting it risks |
|---|---|---|---|
| Roles in requirements engineering (chapter "Introduction and Overview of Requirements Engineering") | `roles.yaml` extends the minimal role catalog from [`_index.md`](_index.md#scope-and-roles) with the project's roles, and `owner` names a role | the `owners` check of the `reqq_validate.py` validator in the pre-commit hook and in CI (`V1`, `V8`; on its own `reqq_owners.py --check`) | `owner` has an arbitrary value that names nobody responsible for the requirement |
| The principles "Stakeholders" and "Validation" ([`vision-and-principles.md`](vision-and-principles.md), principles 2 and 6) | the "Role" column in `stakeholders.md` links a stakeholder to a role, and the CODEOWNERS block makes its `handle` the reviewer of the area | a PR that changes an area has owners from the catalog assigned | the change is approved by a person who does not represent the stakeholder |
| Handling Change (chapter "Management Practices for Requirements") | the `enforce` level: merging a change requires the area owner's approval | the validator's `--check owners-host` step in CI confirms the requirement on the branch; approvals in the PR history | `CODEOWNERS` declares owners, but nothing blocks a merge without them |

## 8. Language convention

Both the methodology documentation and the `requirements/` skeleton may need to be kept in more than one language. Rule: **the directory structure and file names take precedence over language** — they stay constant (in English) whatever locale is chosen. Individual files that need translation get variants distinguished by a language suffix (e.g. `-en`, `-pl`); the bootstrap/onboarding process picks the right set of files based on the chosen language version. This convention currently describes the target mechanism — it is not yet implemented in this repository (there are no files with a language suffix today). The documents and example requirements of this framework are written in English, and `config.example.yaml` declares `language: en`.

**One language of requirements per repository.** The requirements of a given repository are written in one language, declared with the `language` key in `.reqq/validator/config.yaml`. The value is a lowercase ISO 639-1 code, e.g. `en` or `pl`. The author, the reviewer and the AI agent then know which language to write in, and documents do not mix languages, which implements the principle of shared understanding ([`vision-and-principles.md`](vision-and-principles.md), principle 3).

- Covers: the value of `title` and other text fields of the front matter, and the whole content of the document.
- Does not cover: front-matter keys, `id`, `short_title` (always in English, because it goes into the file name), values from closed lists (e.g. `type`, `status`), code and contract identifiers (field names, error codes, constants) or quotations. These stay in their original form.

The validator checks only the setting itself: a value outside ISO 639-1 is a configuration error (exit code `3`). It does not check the language of the content. A missing key means no declaration and no check, and the validator works as before. The two levels of this section complement each other: suffixes distinguish variants of the files delivered by the framework, and `language` sets the language of the requirements written in the repository.

## 9. OpenAPI fragments in requirements

An integration contract is described by a functional requirement ([`vision-and-principles.md`](vision-and-principles.md), principle 4): prose speaks of meaning and behaviour, and an embedded OpenAPI fragment of structure. The fragment is part of the L0 contract, so it has a fixed tag:

````markdown
```yaml openapi id=REQQF-FR-BOOKING-002.create-booking
paths:
  /bookings:
    post:
      responses:
        201:
          description: Booking created.
```
````

- The block tag is `yaml openapi id=<ID>.<name>`: `<ID>` equals the requirement's `id`, and `<name>` consists of lowercase letters and digits joined by hyphens. The identifier is unique within the file.
- The fragment's root contains only `paths` and `components`. The other parts of an OpenAPI document (`openapi`, `info`, `servers`, `security`) belong to the shared parts of the contract.
- A fragment can refer (`$ref`) to schemas from other fragments. The contract file is assembled from the fragments and the shared parts in the CI of the product repository.
- The OpenAPI version of the fragments is declared by the `openapi.version` key in `.reqq/validator/config.yaml`: `3.0`, `3.1` or `3.2` (default `3.2`).

The validator (the `openapi` check) checks each fragment separately: valid YAML (`openapi.yaml`), the root keys (`openapi.root`), the identifier (`openapi.id`) and compliance with the OpenAPI schema of the declared version (`openapi.schema`). The reporting level is set by `openapi.level`: `off`, `warning` (default) or `error`; an invalid value of any of these keys is a configuration error (exit code `3`). The validator does not resolve `$ref` and does not check the completeness of the assembled contract — those are cross-file checks, outside the scope of the toolkit.

## Related documents

- [`requirements-management.md`](requirements-management.md) — the full rationale behind the conventions above
- [`artifacts-and-structure.md`](artifacts-and-structure.md) — the rationale for the front-matter schema
- [`examples.md`](examples.md#case-study-contracts-as-code-as-reqquest-framework) — the conventions above on a live example
- [`../../requirements/README.md`](../../requirements/README.md), [`../../.reqq/README.md`](../../.reqq/README.md) — the implementation of this document in the toolkit (installation: [`../starter-kit.md`](../starter-kit.md))
