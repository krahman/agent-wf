# Design

## Context

See proposal.md for motivation and the `developer-commands` spec for required behaviour. What exists today:

- No Makefile. Commands live in `AGENTS.md` across the Container, Evals, Wikipedia tool, CI and Commands sections; the Commands section lists only `uv sync`, `uv run pytest`, `uv run ruff check` and `uv run fastapi dev main.py`.
- The CI workflow runs these shell commands: `uv sync --locked`, `uv run pytest -q`, `uv run ruff check`, and (docker job) `touch .env` then `docker compose config -q`, plus an image build through GitHub actions (not a shell command). `docker compose config -q` fails when `.env` is missing because the `api` service reads it.
- `uv version --short` prints the project's version; `git rev-parse --short HEAD` gives the commit that the Dockerfile accepts as `GIT_SHA`.
- This machine has GNU Make 3.81 (the version macOS ships, from 2006) and BSD awk. A directory named `tests` exists; none of the planned target names collides with a path today.
- Verified in a scratch Makefile on this machine: a `grep` plus `awk -F':.*## '` help listing works with BSD awk (which lacks non-greedy regex); `.DEFAULT_GOAL` works; phony targets still run when same-named directories exist; `ARGS` and tool overrides pass through; a guarded `reset` exits non-zero without touching anything; `[ -f .env ] || cp ...` leaves an existing file alone.

## Goals / Non-Goals

**Goals:**
- One discoverable entry point whose command list cannot silently diverge from CI.
- Safe by default: nothing destructive without an explicit flag, no secret ever echoed.
- Works unmodified on a stock Mac and on Linux.

**Non-Goals:**
- Replacing the CI workflow's own steps, a Windows (non-Unix-shell) workflow, deployment or release targets (see proposal).

## Decisions

**1. Plain GNU Make, not `just`, `task`, `poethepoet` or a `scripts/` folder.**
`make` is already installed on macOS and Linux, so contributors and CI runners need nothing new, and every contributor knows the interface. Alternatives: `just` or `task` (nicer syntax and built-in argument handling, but another tool to install); `uv` project scripts or `poe` (Python-only, awkward for docker and git commands); shell scripts under `scripts/` (no discoverability or dependency handling). Cost: Windows without a Unix shell is unsupported.

**2. Stay within Make 3.81.**
Use `.DEFAULT_GOAL`, `.PHONY`, `.NOTPARALLEL`, `?=`, recursive `=` and single-line or backslash-continued recipes. Avoid `.ONESHELL`, `$(file ...)`, grouped targets (`&:`) and `::=`, none of which exist in 3.81. A test greps the Makefile for those constructs, and every behaviour test runs under whichever `make` is on the machine (3.81 here).

**3. Help is generated from `## ` comments on the target lines.**
`help` runs `grep -E '^[a-zA-Z_-]+:.*## '` over `$(MAKEFILE_LIST)` and formats with `awk -F':.*## '`, so the description sits next to the command and cannot go stale. A test parses the Makefile and fails if any target lacks a description or is not in `.PHONY`.

**4. Overridable variables and lazy shell lookups.**
`UV ?= uv`, `COMPOSE ?= docker compose`, `IMAGE ?= agent-wf`, `ARGS ?=`, `CONFIRM ?=`. `VERSION` and `GIT_SHA` use recursive `=` with `$(shell ...)` so they are only evaluated by targets that use them: `make help` must not need `uv` or `git`. Alternative: `:=` (simple, but runs the shell on every invocation, including `help`).

**5. `check` is an ordered list of the CI checks, each its own target.**
`check: install test lint build compose-check`, with `.NOTPARALLEL` so `make -j` cannot reorder it. The recipes use the exact command strings CI uses (`uv sync --locked`, `uv run pytest -q`, `uv run ruff check`, `docker compose config -q`). `compose-check` creates an empty `.env` only when none exists and removes it afterwards, so the check works in a clean checkout like CI's `touch .env` but never leaves a stray file or touches a real one. `check` needs Docker running (for the image build); contributors without Docker use `make test lint`.

**6. A parity test instead of making CI call `make`.**
`tests/test_makefile.py` reads `.github/workflows/ci.yml`, collects its `run:` commands (ignoring `touch .env`), and asserts each appears in `make -n check` output; it also asserts the dry run contains `docker build`. Dry-run mode (`-n`) prints recipes without running them, so the test is offline and fast. Alternative: have CI run `make check`. It would remove the duplication, but the docker job uses GitHub actions for caching and build args that have no shell equivalent, and the existing pipeline is verified and working.

**7. Destructive actions need `CONFIRM=yes`; nothing else removes volumes.**
`reset` runs `docker compose down -v` only when `CONFIRM=yes` and otherwise exits non-zero with the exact command to confirm. A variable, not an interactive prompt, so scripts behave predictably and a prompt cannot hang a non-interactive shell. `down` never passes `-v`; `clean` removes only `.pytest_cache`, `.ruff_cache`, `__pycache__` folders outside `.venv`, and `tests/evals/results`.

**8. Secrets are never printed.**
`env` copies `.env.example` only if `.env` is missing; `keygen` prints only the key it just generated (`openssl rand -hex 32`); no target `cat`s or echoes `.env` or environment values. `health` and `smoke` print only public data (the version and commit, a Wikipedia summary).

**9. Image tag and build argument.**
`build` runs `docker build --build-arg GIT_SHA=$(GIT_SHA) -t $(IMAGE):$(VERSION) .`, so a local image carries the same commit label the compose build does. `up` passes `GIT_SHA` to compose the same way (`GIT_SHA=$(GIT_SHA) $(COMPOSE) up -d --build`).

**10. `AGENTS.md` points to the Makefile.**
The Commands section becomes `make help` plus a short table, so the Makefile is the single list; the other sections keep their explanations and their raw commands remain valid.

## Risks / Trade-offs

- [Makefile, CI and docs list the same commands and can drift] → The parity test fails when a CI command is not in `check`, and `AGENTS.md` now defers to `make help`.
- [A target works on this machine's tools but not elsewhere] → Only Make 3.81 features and POSIX `sh`, `grep`, `awk`, `find` and `cp` are used; CI-agnostic. The one non-POSIX dependency is `openssl` for `keygen`, which fails with its own message if missing.
- [`make check` needs Docker running] → Documented; `make test lint` is the quick loop, and a failing docker step is clearly the image build.
- [`reset` deletes traces, users and projects in Langfuse] → Requires `CONFIRM=yes` and the message names what is lost; no other target touches volumes.
- [`ARGS` is passed to the shell as written] → Quoting is the caller's responsibility, as with any make variable; the examples in the docs show the quoting.
- [A target named like an existing file would not run] → Every target is `.PHONY`, and a test enforces it.
- [`uv run` exports `UV=<path to uv>` to everything it launches, and `UV ?= uv` honours it, so `make` run under `uv run` shows the absolute path] → Harmless and consistent with how make overrides work (the path is the same uv); the tests remove the override variables from the environment so their output does not depend on how they were launched, and one test pins the behaviour.

## Migration Plan

Additive: new files plus a docs edit; nothing else changes. Rollback is deleting `Makefile` and `tests/test_makefile.py` and restoring the `AGENTS.md` section.

## Open Questions

None that would change the specs, the approach or the tasks.
