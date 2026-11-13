# Contributing to the reqQuest Framework

Thanks for your interest in contributing.

## Reporting issues

Open a GitHub Issue describing the problem or proposal. For bugs, include steps to reproduce and what you expected instead. For methodology or toolkit proposals, explain the concrete pain point the change addresses.

## Making a change

1. Fork the repository and create a branch for your change.
2. Keep the change focused — one concern per pull request.
3. Follow [Conventional Commits](https://www.conventionalcommits.org/) for commit messages (`feat:`, `fix:`, `docs:`, `chore:`, ...); this repository's changelog is generated from them.
4. Run the validator before opening a PR:

   ```bash
   python3 .reqq/validator/reqq_validate_stdlib.py --all
   ```

5. If you changed the toolkit boundary (see `toolkit-manifest.json`), confirm the packer still resolves it:

   ```bash
   python3 scripts/pack-toolkit.py --list
   ```

6. Open a pull request against `main` describing the change and its motivation.

## Developer Certificate of Origin

Contributions are accepted under the [Developer Certificate of Origin 1.1](https://developercertificate.org/) (DCO). By signing off a commit, you certify that you wrote the change or otherwise have the right to submit it under this project's license (Apache-2.0).

Sign off every commit with `git commit -s`. This adds a line like the following to the commit message:

```text
Signed-off-by: Jane Doe <jane.doe@example.com>
```

The name and email must match the commit author. A pull request with commits that are not signed off fails the DCO check.

## Code of Conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to abide by it.
