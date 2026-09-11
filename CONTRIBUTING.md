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

## Contributor agreement

<!-- DECISION PENDING: CLA vs DCO (REQQF#48, step 0) -->

## Code of Conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to abide by it.
