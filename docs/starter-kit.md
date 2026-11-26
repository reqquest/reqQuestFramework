---
title: Starter Kit
owner: reqQuest
status: approved
last_updated: 2026-11-23
tags: [starter-kit, reqquest-framework]
---

# Starter Kit

**A reqQuest Framework skeleton ready to adopt.** Not just a description of conventions — a working set of folders, schemas, a validator and CI workflows that you install in your repository from a single archive. Open source, no registration.

[Download the Starter Kit →](https://github.com/reqquest/reqQuestFramework/releases/latest){ .md-button .md-button--primary } [See the conventions →](framework/conventions.md){ .md-button }

The Starter Kit is the asset `raac-toolkit-X.Y.Z.tar.gz` attached to every `toolkit-vX.Y.Z` release of the public reqQuest Framework repository.

## What it contains

<div class="grid cards" markdown>

- :material-file-tree: **`requirements/`**

    ---

    A folder skeleton for requirements (`business/`, `functional/`, `nonfunctional/`, `adrs/`, `testcases/`, `policies/`) + the project context (`00-context/`), with examples in a fictional domain (e.g. `REQQF-BR-BOOKING-001`) to replace with your own content, and instructions for AI agents.

- :material-shield-check: **`.reqq/`**

    ---

    A requirements validator with a single entry point (front matter, schema, graph, folder layout, Markdown links, owners) — Python with three pinned libraries (PyYAML, jsonschema, referencing) — plus JSON schemas for every artifact type and a pre-commit hook.

- :material-source-branch-check: **`.github/workflows/`**

    ---

    CI workflows: requirements validation on every PR, plus checking and updating the toolkit version.

- :material-file-cog: **`.reqqignore`**

    ---

    A list of exclusions from validation (in `.gitignore` format) — the project context and `README` files are not requirements and do not go through schema validation.

</div>

## Structure

```text
requirements/
  AGENTS.md                    # instructions for AI agents (part of the toolkit)
  AGENTS.project.md            # project rules for AI agents (yours)
  CLAUDE.md                    # imports both files for Claude Code (part of the toolkit)
  00-context/                  # project context, excluded from validation by .reqqignore
    objectives-and-scope.md    # business case document
    stakeholders.md
    roles.example.yaml         # example role catalog (governance) — copy it to roles.yaml
    glossary.md                # base glossary (part of the toolkit)
    glossary.project.md        # project glossary (yours)
  business/                    # BR — business requirements
  functional/                  # FR — in category folders (e.g. AUTH/, BOOKING/)
  nonfunctional/               # NFR — in category folders (e.g. performance/, security/)
  adrs/                        # ADR-<CATEGORY>-NNN — architecture decisions
  testcases/                   # TC — test cases
  policies/                    # POL — policies and constraints

.reqq/
  schema/
    requirement.schema.json    # base front-matter schema
    roles.schema.json          # role catalog (roles.yaml)
    types/                     # BR/FR/NFR/ADR/TC/POL — field requirements per type
  validator/
    reqq_validate.py           # the single entry point: all checks, adopt/check/upgrade; called by CI and the hook
    reqq_check_*.py            # rules: front matter, schema, graph, folder layout, Markdown links
    reqq_common.py, reqq_config.py, reqq_yaml.py  # shared code: configuration and YAML loading
    reqq_owners.py             # ownership governance and the CODEOWNERS block (check `owners`)
    reqq_owners_github.py      # GitHub API client for rule V6 (enforce level)
    reqq_toolkit_*.py          # toolkit adopt, check and upgrade
    requirements.txt           # the validator's pinned libraries: PyYAML, jsonschema, referencing
    config.example.yaml        # configuration template — copy it to config.yaml
  hooks/
    pre-commit                 # runs the validator on staged files

.github/workflows/
  requirements-validate.yml        # requirements validation, link check and ownership check in CI
  requirements-toolkit-check.yml   # toolkit version check
  requirements-toolkit-update.yml  # toolkit update

LICENSES/
  Apache-2.0.txt               # text of the Apache-2.0 licence of the toolkit files
  NOTICE-reqQuest-Framework.txt  # NOTICE: the licence covers only the files in .reqq/toolkit.lock

.reqqignore                    # exclusions from validation, .gitignore format
toolkit-manifest.json          # toolkit boundary — the files under versioning
```

## Quick start

```bash
# 1. Download raac-toolkit-X.Y.Z.tar.gz and unpack it in the repository root
tar xzf raac-toolkit-X.Y.Z.tar.gz --strip-components=1

# 2. Create the local validator configuration (not part of the package)
cp .reqq/validator/config.example.yaml .reqq/validator/config.yaml

# 3. Install the validator's libraries (they need Python >= 3.10; pinned in requirements.txt)
#    in a virtual environment: the system Python refuses `pip install` (PEP 668). Add `.venv/` to .gitignore.
python3 -m venv .venv
source .venv/bin/activate   # the hook uses python3 from PATH: keep the environment active when committing
python3 -m pip install -r .reqq/validator/requirements.txt

# 4. Record the adopted toolkit version in .reqq/toolkit.lock
python3 .reqq/validator/reqq_validate.py adopt --version X.Y.Z

# 5. Install the pre-commit validation hook (once)
git config core.hooksPath .reqq/hooks

# 6. Verify that everything works (the examples pass right away)
python3 .reqq/validator/reqq_validate.py --all

# 7. When you replace the examples with your own requirements, set the repository prefix in config.yaml,
#    e.g. id_prefix: REQA — the validator points out the examples that are left
```

The examples (numbers `001`–`099`, tag `example`) have the prefix `REQQF` of the framework repository and a short title in the file name, and `config.example.yaml` declares `id_prefix: REQQF` and `short_title: true`, which is why step 6 passes. The prefix of your own repository equals its key from branch and issue names — rules in [`conventions.md`](framework/conventions.md), section 2.

The validator needs the libraries from `.reqq/validator/requirements.txt` (step 3); the `requirements-validate.yml` workflow installs them itself. You install later versions with the `upgrade` command — details in [`.reqq/README.md`](https://github.com/reqquest/reqQuestFramework/blob/main/.reqq/README.md).

## Instructions for AI agents

AI agents (e.g. Claude Code, Codex) read instructions from the folder they work in. The toolkit delivers them in `requirements/`, so an agent that changes requirements gets the framework rules, while your `AGENTS.md` and `CLAUDE.md` in the repository root stay untouched.

| File | Whose | What it contains |
|---|---|---|
| `requirements/AGENTS.md` | the toolkit's — do not edit, `upgrade` replaces it | framework rules: how to write and verify requirements, the agent's limits |
| `requirements/AGENTS.project.md` | yours — `upgrade` does not touch it | project rules, e.g. domain categories and exceptions |
| `requirements/CLAUDE.md` | the toolkit's | imports of both files for Claude Code |

Project rules take precedence over framework rules, and the instructions from the repository root take precedence over both.

- **Claude Code** loads both files when the agent opens or changes a file in `requirements/`.
- **Codex** has no imports: it finds the project file by the path given in `requirements/AGENTS.md`, and it adds the instructions from a subfolder on its own only when it works in that subfolder.

`upgrade` does not add starting files. If you installed the toolkit before this version and want project rules, copy `requirements/AGENTS.project.md` from the release package.

Do you run the agent from the repository root? Add one sentence to your `AGENTS.md` so that the agent reaches for the rules before it starts planning a change:

```markdown
Before changing anything in `requirements/`, read and follow `requirements/AGENTS.md`.
```

## Why it works

The Starter Kit directly implements the conventions described in [`conventions.md`](framework/conventions.md): the front-matter schema, the ID and prefix convention, the lifecycle values, traceability, configurations and baseline, the minimal set of CI checks. It is not a separate product to learn — it is a reference, running implementation of what the methodology documentation describes.

## Licence

reqQuest Framework — the methodology and this starter kit — is released under the Open Source licence Apache-2.0. The reqQuest tools that support its adoption (reqAgent, reqClient, reqWizard) are separate commercial products — using their functionality is paid. Details in [`tooling.md`](framework/tooling.md).

## Related documents

- [`framework/conventions.md`](framework/conventions.md) — the full description of the conventions this skeleton implements
- [`framework/requirements-management.md`](framework/requirements-management.md) — the rationale behind the choices (traceability, baseline, coverage)
- [`framework/tooling.md`](framework/tooling.md) — reqQuest tools that support working with this skeleton at a larger scale
