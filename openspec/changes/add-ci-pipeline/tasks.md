# Tasks

## 1. Lint scope

- [x] 1.1 Add `[tool.ruff] extend-exclude = ["examples"]` to `pyproject.toml`; verify a bare `uv run ruff check` exits 0 and still reports an error when a deliberate unused import is added to `src/` (then remove it)

## 2. Workflow: test and lint jobs

- [x] 2.1 Create `.github/workflows/ci.yml` with triggers `push` on `main` and `pull_request`, workflow-level `permissions: contents: read`, and `concurrency` (group on workflow and ref, `cancel-in-progress: true`); verify the file passes `actionlint` (or `uvx actionlint`)
- [x] 2.2 Add the `test` job: checkout, `astral-sh/setup-uv` with cache and the interpreter taken from `.python-version`, `uv sync --locked`, `uv run pytest -q`; verify the same three commands pass from a fresh `git clone` of the branch with no `.env`
- [x] 2.3 Add the `lint` job with the same setup and `uv run ruff check`; verify it passes on a clean clone
- [x] 2.4 Verify the lockfile gate: temporarily add a dependency to `pyproject.toml` without running `uv lock`, confirm `uv sync --locked` fails, then revert

## 3. Workflow: docker job

- [x] 3.1 Add the `docker` job: `docker/setup-buildx-action`, `docker/build-push-action` with `push: false`, GitHub Actions layer cache, and `build-args: GIT_SHA=${{ github.sha }}`; verify `docker build --build-arg GIT_SHA=test .` succeeds locally
- [x] 3.2 Add a step to the `docker` job that runs `touch .env` and then `docker compose config -q`; verify it succeeds in a clean clone, and fails when a deliberate YAML error is introduced in `docker-compose.yml` (then revert)

## 4. Documentation and integration

- [x] 4.1 Add a CI section to `AGENTS.md` listing the three checks and the local equivalents (`uv sync --locked`, `uv run pytest`, `uv run ruff check`, `docker build .`); verify every command shown runs as written
- [x] 4.2 Open a pull request with these changes; verify the three jobs (`test`, `lint`, `docker`) appear on it, all pass, and a second push to the same branch cancels the in-progress run
- [x] 4.3 On that pull request, push a throwaway commit with a failing test and confirm the `test` job fails and the PR shows a failed check; then drop the commit

## Workflow follow-up

- In the GitHub repository settings, mark `test`, `lint` and `docker` as required status checks on `main` (a repository setting, not a file in the repo).
- Archive the change after PR #1 (which carries the two fixes found by the first real run) is merged.
