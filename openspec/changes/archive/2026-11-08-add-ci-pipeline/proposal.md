# Proposal

## Why

The repo has tests, a linter and a Dockerfile, but nothing runs them automatically: there is no `.github/` directory, so a broken commit (failing test, lint error, or an image that no longer builds) is only found when someone happens to run the checks locally. This already bit us once: the Docker build broke on a Python version mismatch that `uv run pytest` never exercised. CI is the cheapest step toward a production-grade agent and every later step (hardening, evals, durable state) needs it as a safety net.

## What Changes

- Add a GitHub Actions workflow that runs on every push to `main` and on every pull request.
- Run the unit tests (`pytest`) against the locked dependencies (`uv sync --frozen`), with no API key and no network access to an LLM.
- Run `ruff check` scoped to the project code (`src`, `tests`, `main.py`), so the example notebook does not fail the build.
- Build the Docker image (without pushing it) and validate `docker-compose.yml`, so Dockerfile and dependency problems surface before deploy.
- Cancel superseded runs on the same branch and restrict the workflow token to read-only.
- Document the CI checks and how to reproduce them locally in `AGENTS.md`.

Out of scope: publishing images, deployment (CD), live-LLM evals, `ruff format` enforcement (the code has never been formatted with it), and branch protection settings (a GitHub repo setting, not a file in the repo).

## Capabilities

### New Capabilities
- `continuous-integration`: the checks every change must pass before it can be merged: tests, lint and a container build, run reproducibly from a clean checkout.

### Modified Capabilities

None. There are no existing specs.

## Impact

- New file: `.github/workflows/ci.yml`.
- Doc update: `AGENTS.md` (Commands / CI section).
- No change to application code, dependencies or runtime behaviour.
- Assumes the repository is hosted on GitHub; the workflow does nothing elsewhere.
- Findings from planning that shape the work: a clean checkout of `HEAD` already passes all 16 tests and `ruff check src tests main.py` with the lockfile and no `.env`; a bare `ruff check` fails (16 errors, all in the notebook under `examples/`); ruff and pytest are pinned in `uv.lock` via the `dev` group, so local and CI results match.
