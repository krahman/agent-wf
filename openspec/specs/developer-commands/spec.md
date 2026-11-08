# developer-commands Specification

## Purpose

Gives contributors one discoverable entry point for the project's everyday commands, including a local check that mirrors CI, with clear guarantees about destructive actions and secrets, so nobody has to remember or retype long commands.

## Requirements

### Requirement: Targets are discoverable
The system SHALL make `make` with no target print a help listing of every target with a one-line description, and SHALL need no configuration, no `.env` file and no network access to do so.

#### Scenario: Running make with no target
- **WHEN** a contributor runs `make` in a fresh checkout
- **THEN** the output lists every target with a short description and the command exits successfully

#### Scenario: A target missing from the help
- **WHEN** a target is defined without a help description
- **THEN** a test fails, so every target stays documented

### Requirement: Everyday tasks have a target
The system SHALL provide a target for each everyday task: installing locked dependencies, running the server locally, running the unit tests, linting (and auto-fixing), running the evals (and listing them), running the live smoke test of the Wikipedia tool, validating the OpenSpec files, building the container image, starting, stopping, inspecting and following the compose stack, probing the running API, printing the project version, generating an API key, and creating `.env` from the example.

#### Scenario: Running the unit tests
- **WHEN** a contributor runs `make test`
- **THEN** the default test suite runs offline and the target's exit status is the test run's

#### Scenario: Generating an API key
- **WHEN** a contributor runs `make keygen`
- **THEN** it prints one new random key of 64 hexadecimal characters

### Requirement: Conversation state has operator targets
The system SHALL provide targets to migrate the conversation state database, to prune idle conversations, and to run the database-backed tests against a throwaway database.

#### Scenario: Migrating the state database
- **WHEN** a contributor runs `make migrate` against a running state database
- **THEN** the schema is created or upgraded, and running it again succeeds without changes

#### Scenario: Pruning idle conversations
- **WHEN** a contributor runs `make prune`
- **THEN** conversations idle longer than the configured retention are deleted and the number deleted is printed

#### Scenario: Running the database tests
- **WHEN** a contributor runs `make test-db` with Docker available
- **THEN** a throwaway database is started, the database-backed tests run against it, and the database is removed afterwards whether the tests pass or fail

### Requirement: Check mirrors CI
The system SHALL provide a `check` target that runs the same checks as the CI jobs (locked dependency install, the unit tests, lint, the container image build and compose file validation), SHALL fail when any of them fails, and MUST NOT need an LLM API key or an existing `.env` file.

#### Scenario: Clean checkout
- **WHEN** `make check` runs in a clean checkout with no `.env` and no API key
- **THEN** every check runs and the target passes if the CI jobs would pass

#### Scenario: One check fails
- **WHEN** the lint check fails
- **THEN** `make check` exits with a failure status

#### Scenario: CI gains a check
- **WHEN** a shell command in the CI workflow is not covered by `make check`
- **THEN** a test fails, so local and CI checks cannot silently drift apart

### Requirement: Arguments pass through
The system SHALL append the `ARGS` variable to the commands of the test, eval and lint-fix style targets that take options, so contributors can select tests or change options without editing the Makefile.

#### Scenario: Selecting tests
- **WHEN** a contributor runs `make test ARGS="-k limits"`
- **THEN** the test run receives `-k limits`

#### Scenario: Changing eval options
- **WHEN** a contributor runs `make eval ARGS="--eval-repeats 1"`
- **THEN** the eval run receives `--eval-repeats 1`

### Requirement: Destructive actions are explicit
The system SHALL give data-deleting actions their own target that refuses to run unless `CONFIRM=yes` is given, and no other target SHALL delete the compose stack's data volumes. Deleting the stack's data includes the stored conversations.

#### Scenario: Reset without confirmation
- **WHEN** a contributor runs `make reset` without `CONFIRM=yes`
- **THEN** nothing is deleted, the target exits with a failure status, and the message says how to confirm

#### Scenario: Stopping the stack
- **WHEN** a contributor runs `make down`
- **THEN** the containers stop and the data volumes are kept

#### Scenario: Cleaning
- **WHEN** a contributor runs `make clean`
- **THEN** only caches and eval reports are removed

#### Scenario: Reset with confirmation
- **WHEN** a contributor runs `make reset CONFIRM=yes`
- **THEN** the stored conversations are deleted together with the other stack data

### Requirement: Secrets and existing files are protected
The system SHALL create `.env` from the example only when it does not already exist, and MUST NOT print any secret value read from `.env` or the environment; the only secret a target may print is a key it has just generated.

#### Scenario: Existing .env
- **WHEN** a contributor runs `make env` and `.env` already exists
- **THEN** the file is left unchanged and the target says so

#### Scenario: No .env yet
- **WHEN** a contributor runs `make env` and no `.env` exists
- **THEN** `.env` is created as a copy of the example

### Requirement: The Makefile is portable
The system SHALL work with GNU Make 3.81, the version shipped with macOS, and with current GNU Make on Linux, SHALL declare every target as phony so that a file or directory with the same name never blocks it, and SHALL let `UV`, `COMPOSE` and `IMAGE` be overridden from the command line.

#### Scenario: Old make
- **WHEN** the targets run under GNU Make 3.81
- **THEN** they behave as specified

#### Scenario: A directory named like a target
- **WHEN** a directory called `test` or `build` exists in the repository
- **THEN** `make test` and `make build` still run their commands

#### Scenario: Overriding a tool
- **WHEN** a contributor runs `make test UV="uv --quiet"`
- **THEN** the test command uses the overridden tool invocation
