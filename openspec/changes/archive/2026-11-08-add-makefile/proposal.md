# Proposal

## Why

The commands needed to work on this project are spread over six sections of `AGENTS.md` (the "Commands" section lists only four of them), and several are long enough to be easy to get wrong: the eval options, the image build with its `GIT_SHA` argument, the compose validation that needs a `.env` file, generating an API key, or the smoke test of the Wikipedia tool. There is also no single command that does what CI does, so a change can pass locally and still fail the pipeline. A Makefile gives one discoverable entry point (`make help`) and a `make check` that mirrors CI.

## What Changes

- Add a `Makefile` at the repository root with a self-documenting `help` as the default target and targets grouped by purpose:
  - **Setup:** `install` (locked sync), `lock`, `env` (create `.env` from `.env.example` without overwriting), `keygen` (print a new API key).
  - **Run:** `dev` (local server), `up`, `down`, `logs`, `ps` (the compose stack), and `health` (probe the running API).
  - **Quality:** `test`, `lint`, `fix`, `eval`, `eval-list`, `smoke` (live check of the Wikipedia tool), `spec-check` (validate the OpenSpec changes and specs).
  - **Build and release:** `build` (image tagged with the project version and git commit), `version`.
  - **Cleanup:** `clean` (caches and eval reports only) and `reset` (also deletes the Langfuse data volumes, only with `CONFIRM=yes`).
- Add `check`, which runs the same checks as the CI jobs (locked install, tests, lint, image build, compose validation) and needs no API key and no `.env`.
- Let arguments pass through (`make test ARGS="-k limits"`, `make eval ARGS="--eval-repeats 1"`), and keep the tool names overridable (`UV`, `COMPOSE`, `IMAGE`).
- Keep the Makefile compatible with the GNU Make 3.81 that ships with macOS (and Linux make): no newer features.
- Add tests that run the Makefile in dry-run mode and guard against drift from `ci.yml`, and replace the scattered command list in `AGENTS.md` with a pointer to `make help` plus the target table.

Out of scope, with the reason:
- Making the CI workflow call `make`: it works today and its docker job uses GitHub actions that have no shell equivalent; a parity test catches drift instead.
- Windows without a Unix shell, and any task runner other than `make`.
- Deployment, release tagging and publishing targets (no deployment target exists yet).

## Capabilities

### New Capabilities
- `developer-commands`: the single entry point for the project's day-to-day commands: how targets are discovered, which commands they run, how `check` relates to CI, and what safety guarantees destructive and secret-touching targets give.

### Modified Capabilities

None. `continuous-integration` is unchanged: the pipeline's behaviour does not change, and `make check` is a local mirror of it.

## Impact

- New files: `Makefile` and `tests/test_makefile.py`.
- Doc change: the Commands section of `AGENTS.md` now points to `make help` and lists the targets.
- No change to application code, dependencies, CI or the Docker setup.
- Needs `make` plus the tools the targets call (`uv`, `docker`, `curl`, `openssl`, and the `openspec` CLI for `spec-check`); a missing tool fails only its own target with the tool's own error.
- `reset` is the one destructive target (it deletes Langfuse traces, users and projects); it refuses to run without `CONFIRM=yes`.
