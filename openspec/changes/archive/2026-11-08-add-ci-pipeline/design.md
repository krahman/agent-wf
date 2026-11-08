# Design

## Context

See proposal.md for motivation and the `continuous-integration` spec for the required behaviour. Facts verified against a clean checkout of `HEAD`, with no `.env` and the lockfile only:

- `uv sync --frozen`, `pytest` (16 tests) and `ruff check src tests main.py` all pass. Tests use a fake LLM, so they need no key or network.
- A bare `ruff check` fails with 16 errors, all in `examples/*.ipynb`.
- `docker compose config` fails on a clean checkout: the `api` service has `env_file: .env`, and `.env` is gitignored.
- The Docker base image ships Python 3.14.2, while local development uses 3.14.7 (`.python-version`). `requires-python` is `>=3.14`.
- ruff and pytest are pinned in `uv.lock` through the `dev` dependency group, so CI and local runs use identical tool versions.

## Goals / Non-Goals

**Goals:**
- One workflow whose per-check statuses are individually visible on a pull request.
- Local and CI commands that are literally the same, so "works on my machine" and "fails in CI" cannot diverge.
- Fast feedback: checks run in parallel and dependency downloads are cached.

**Non-Goals:**
- A Python version matrix. The project targets one interpreter today.
- Running tests inside the built image, image publishing, or deployment.
- Coverage thresholds or `ruff format` enforcement.

## Decisions

**1. One workflow file, three parallel jobs (`test`, `lint`, `docker`).**
Separate jobs give a distinct red/green status per check and run concurrently. Alternative: a single job running all steps in sequence. It is simpler and avoids repeated setup, but a lint failure would hide whether tests pass, and the total time is the sum of the steps. The cost of the chosen option is one extra dependency install, which the uv cache makes cheap.

**2. Install with `uv sync --locked`, not `--frozen`.**
`--frozen` uses the lockfile without checking it, so a stale lock passes silently. `--locked` fails when `pyproject.toml` and `uv.lock` disagree, which is what the spec's reproducibility requirement needs. Alternative: `--frozen` plus a separate `uv lock --check` step. It does the same thing in two steps.

**3. Take the interpreter from `.python-version`, via uv itself.**
The test and lint jobs need no Python setup step: `uv sync` reads `.python-version` (3.14.7) from the project and downloads that interpreter, so CI runs the same Python as local development with one place to bump it. `astral-sh/setup-uv` has no input for this (a `python-version-file` input was tried and ignored, which the first CI run revealed). Alternative: hard-code `3.14` in the workflow. That would duplicate the version and let it drift.

**4. Exclude `examples/` in `pyproject.toml` rather than listing paths in the workflow.**
Add `[tool.ruff] extend-exclude = ["examples"]` and run plain `uv run ruff check` in CI. Local `uv run ruff check` then passes too, which it currently does not. Alternative: CI runs `ruff check src tests main.py` and the config stays untouched. That keeps the change smaller but leaves bare `ruff check` failing locally, and a new top-level folder would silently be left unlinted.

**5. Docker job: `docker/build-push-action` with `push: false`, GitHub Actions layer cache, and `GIT_SHA` build arg set to the commit SHA.**
This exercises the exact Dockerfile path the app ships through, including the `GIT_SHA` argument. Alternative: plain `docker build`, which works but has no layer cache and slower reruns.

**6. Validate compose by creating an empty `.env` first.**
`docker compose config -q` needs the file to exist. The CI step runs `touch .env` before validating, leaving `docker-compose.yml` and runtime behaviour unchanged. Alternative: make the env file optional (`required: false`) in compose. That is a runtime change that lets the stack start without a key and should be its own decision.

**7. Workflow hygiene.**
`permissions: contents: read` at the workflow level and `concurrency` keyed on the workflow and ref, with `cancel-in-progress: true`. Triggers are `push` on `main` and `pull_request`, so a branch with an open PR is not run twice.

## Risks / Trade-offs

- [The image runs Python 3.14.2 while tests run on 3.14.7] → The docker job proves the image builds and installs, not that tests pass on its interpreter. Revisit with a smoke test of the built image when hardening the container.
- [Third-party actions can change or be compromised] → Pin actions to a major version tag now and consider commit SHAs later; the read-only token limits the damage.
- [A branch protection rule is needed for CI to actually block merges] → It is a repository setting outside this change; call it out in the task list as a manual step.
- [No LLM-quality coverage] → Intentional. Unit tests prove wiring only; evals are a separate planned change.

## Migration Plan

1. Merge the workflow and the ruff config change in one pull request. That pull request is the first run, so it validates itself.
2. Afterwards, mark the three checks as required in the repository's branch protection.
3. Rollback: delete `.github/workflows/ci.yml`. Nothing in the application depends on it.
