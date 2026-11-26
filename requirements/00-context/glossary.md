# Base glossary (reqQuest Framework)

> **Native toolkit file — do not edit it in your repository.** The toolkit ships and updates it (boundary in `toolkit-manifest.json`), and a local change is drift against `.reqq/toolkit.lock`. Put your project's terms in [`glossary.project.md`](glossary.project.md) next to it.

## One glossary, two files

| File | Content | Maintained by |
|---|---|---|
| `glossary.md` (this file) | Methodology terms, terms shared by reqQuest products and the glossary rules | The toolkit; changed only through a toolkit release |
| `glossary.project.md` | Terms of the project's domain and architecture | The project. A starting file (`seed` in `toolkit-manifest.json`): it arrives with the first toolkit install; after that `adopt`, `check` and `upgrade` never touch it |

Both files form **one logical glossary**. Every term has exactly one definition in it: the project glossary does not redefine a term from this file. At most it narrows the term for the project, with a reference to the base definition.

## Direction of definitions: glossary → requirements

Definitions flow **from the glossary to the requirements documents**, never the other way:

1. **A term used in more than one document is defined only in the glossary.** This applies everywhere in a document, not only in a "Definitions" section: documents refer to the glossary and do not repeat definitions. A normative statement — a requirement or decision that sets a rule for the term — stays in the document, and the glossary points to it as the source of the definition.
2. **A "Definitions" section in a document** may contain only:
   - terms used only in that document;
   - a narrowing of a glossary term, with a reference and no new definition (e.g. "**Principal** — see the glossary; in this document only the user of route X").
3. **A local term that appears in a second document moves to the glossary** in the same PR, and both documents replace it with a reference.
4. **Field names, error codes and contract constants** are contract, not vocabulary: they stay in the requirement that defines the contract.
5. **An ambiguous term** gets separate glossary entries with a qualifier (e.g. "Chunk (KB)" and "Ingest chunk"), never one entry with two meanings.

## Methodology terms

| Term | Definition |
|---|---|
| **Requirements artifact** | A Markdown file with front matter in `requirements/`, identified by an `id` in the format `[PREFIX-]TYPE-CATEGORY-NNN`, where the (optional) prefix identifies the repository. Types: `BR` (business requirement), `FR` (functional), `NFR` (non-functional), `ADR` (architecture decision), `TC` (test case), `POL` (policy). The required fields of each type are set by the schemas in `.reqq/schema/types/`. |
| **Front matter** | The YAML block at the top of an artifact file, with attributes validated by `.reqq/validator/`: among others `id`, `title`, `type`, `status`, `owner`, `version`, `last_updated`. |
| **Status** | The lifecycle stage of an artifact: `draft` (being written), `review` (submitted for approval), `approved` (approved, in the baseline), `deprecated` (superseded, a historical entry). |
| **Baseline** | The set of artifacts with status `approved` — the only source of requirements for further work, AI agents included. |
| **`traces_to`** | A front-matter field: the IDs of the artifacts that the artifact implements or derives from (e.g. FR → BR). Required for FR and NFR under `require_full_traceability`. |
| **`derives_from`** | A front-matter field of a test case (`TC`): the IDs of the `FR`/`NFR` requirements the test verifies. Required. |
| **`short_title`** | A front-matter field: a short title of 1–4 English words joined by hyphens. With `short_title: true` in `config.yaml` it is required and appended to the file name: `<id>-<short_title>.md`. It is not part of the ID. |
| **Integration contract** | A description of an interface (API) between the system and its environment. A functional requirement (`FR`) describes it: prose for meaning and behaviour, an embedded **OpenAPI fragment** for structure. The contract file is assembled from the fragments and the shared parts. |
| **OpenAPI fragment** | A code block in a requirement's body tagged `yaml openapi id=<ID>.<name>`, with the keys `paths` and `components` at its root. The validator's `openapi` check checks its syntax. |
| **Toolkit** | A versioned set of methodology files delivered to the adopter (schemas, validator, hooks, CI templates, this glossary), released as `toolkit-vX.Y.Z`. Its boundary is set by `toolkit-manifest.json`. |
| **`toolkit.lock`** | The file `.reqq/toolkit.lock` in the adopter's repo: the toolkit version and the hashes of the boundary files. A hash difference is **drift**. |
| **`local_overrides`** | A list in `toolkit.lock` of boundary files deliberately changed locally; on upgrade they go through a 3-way merge instead of being replaced. The project glossary does not need it, since it lies outside the boundary. |

## Terms shared by reqQuest products

| Term | Definition |
|---|---|
| **Engine** (`reqAgent Engine`) | The cloud backend of reqAgent, which is also the backend of reqClient. It stores the Source Config and PATs, runs git operations and answers the assistant's queries. |
| **Client** / **client** | Client (capital letter) is a company that deploys the Engine in its AWS account. client (lower case) is an application that calls the Engine, e.g. reqClient. |
| **reqAgent** | The L1 product: Engine, CLI and the VSCode extension. It works without reqClient; it is not a synonym of Engine. |
| **Layers L0 / L1 / L2** | The product split: L0 is the reqQuest Framework toolkit, L1 is reqAgent, L2 is reqClient. Dependencies go only L2 → L1 → L0. |
