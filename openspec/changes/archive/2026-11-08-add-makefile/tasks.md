# Tasks

## 1. Makefile core

- [x] 1.1 Create the `Makefile` with the header (`UV`, `COMPOSE`, `IMAGE`, `ARGS`, `CONFIRM`, lazy `VERSION` and `GIT_SHA`, `.DEFAULT_GOAL := help`, `.PHONY`, `.NOTPARALLEL`) and the generated `help`; add the setup targets (`install`, `lock`, `env`, `keygen`, `version`), run targets (`dev`, `health`), quality targets (`test`, `lint`, `fix`, `eval`, `eval-list`, `smoke`, `spec-check`) and `clean`, each with a `## ` description; verify `tests/test_makefile.py` (skipped when `make` is absent) covers: `make` with no target lists every target and exits 0 with no `.env`; every target has a description and is in `.PHONY`; no construct newer than Make 3.81 (`.ONESHELL`, `$(file`, `&:`, `::=`); `ARGS` and `UV` overrides appear in `make -n` output for `test` and `eval`; `make test` still runs with a `test/` directory present; `keygen` prints 64 hex characters; `env` creates `.env` in a temporary copy and leaves an existing one unchanged
- [x] 1.2 Make `clean` remove only `.pytest_cache`, `.ruff_cache`, `__pycache__` folders outside `.venv` and `tests/evals/results`; verify a test in a temporary copy that those are removed while `.venv`, `.env` and source files are untouched

## 2. Docker targets and check

- [x] 2.1 Add `build` (image tagged `$(IMAGE):$(VERSION)` with `GIT_SHA`), `compose-check` (creates an empty `.env` only if missing and removes it afterwards, then runs `docker compose config -q`), `up` (with `GIT_SHA`), `down` (without `-v`), `logs`, `ps` and `reset` (runs `down -v` only when `CONFIRM=yes`, otherwise exits non-zero with the confirm command); verify tests: dry-run output for `build` and `up` carries the `GIT_SHA` build argument, `down` never contains `-v`, `make reset` without `CONFIRM=yes` exits non-zero and runs no docker command (a real run, since the guard fails first), and `compose-check` leaves no `.env` behind in a temporary copy
- [x] 2.2 Add `check` (`install test lint build compose-check`, in that order) using the exact command strings CI uses; verify a parity test reads `.github/workflows/ci.yml`, takes every `run:` command except `touch .env`, and asserts each appears in the `make -n check` output, which must also contain `docker build`

## 3. Documentation

- [x] 3.1 Replace the Commands section of `AGENTS.md` with a pointer to `make help` and a table of the main targets (including `check`, `eval`, `reset` and the `ARGS`/`CONFIRM` conventions); verify every target named in the docs exists in `make help`, and that the non-destructive targets that need no Docker (`help`, `version`, `eval-list`) run as written

## 4. Verification

- [x] 4.1 Run the safe targets for real in the repository: `make`, `make version`, `make keygen`, `make env` (the existing `.env` must stay unchanged), `make test`, `make lint`, `make eval-list`, `make spec-check`, `make reset` (must refuse), and `make clean` (only caches and reports go); verify each behaves as the spec says and that no secret from `.env` appears in any output
- [x] 4.2 From a clean copy with no `.env` and no API key, run `make check` for real and verify it passes, leaves no `.env` behind and builds the image; then add a deliberate lint error in the copy and verify `make check` exits non-zero, and that it passes again after reverting
- [x] 4.3 Verify the stack targets without disturbing the running environment: dry-run `up`, `down`, `logs` and `reset CONFIRM=yes` and check the printed commands; run `make ps` and `make health` for real (read-only); do not run `up`, `down` or a confirmed `reset` against the real stack

## Workflow follow-up

- If the CI workflow is later simplified to call `make check`, the parity test can be dropped.
- Add release and deploy targets when a deployment target exists.
- Archive this change after review.
