# continuous-integration Specification

## Purpose

Defines the automated checks every change to the repository must pass before it is considered mergeable, so that broken tests, lint errors and container build failures are caught on the change itself rather than after merge or deploy.

## Requirements

### Requirement: Checks run automatically on changes
The system SHALL run the full set of CI checks on every push to the main branch and on every pull request, without any manual trigger.

#### Scenario: Pull request opened
- **WHEN** a pull request is opened or updated with new commits
- **THEN** the CI checks run against that pull request's code and report a pass or fail status on it

#### Scenario: Push to main
- **WHEN** a commit is pushed to the main branch
- **THEN** the CI checks run against that commit

### Requirement: Tests must pass
The system SHALL run the project's automated tests as a CI check and fail the run when any test fails. The tests MUST NOT require an LLM API key or network access to an LLM provider.

#### Scenario: A test fails
- **WHEN** a change breaks an existing test
- **THEN** the test check fails and the CI run is reported as failed

#### Scenario: No secrets configured
- **WHEN** the CI run starts in a repository with no secrets configured
- **THEN** the test check still runs to completion and can pass

### Requirement: Code must pass lint
The system SHALL run the linter over the project's source, test and entrypoint code as a CI check and fail the run when the linter reports any error. Example notebooks MUST NOT be linted by this check.

#### Scenario: Lint error in source
- **WHEN** a change introduces a lint error in the source, tests or entrypoint
- **THEN** the lint check fails and the CI run is reported as failed

#### Scenario: Lint issue in an example notebook
- **WHEN** an example notebook contains code the linter would flag
- **THEN** the lint check is unaffected

### Requirement: Container image must build
The system SHALL build the application's container image as a CI check and fail the run when the build fails. The check MUST NOT publish the image. It SHALL also fail when the compose definition is invalid.

#### Scenario: Dependency or Dockerfile breakage
- **WHEN** a change makes the container image impossible to build
- **THEN** the build check fails and the CI run is reported as failed

#### Scenario: Invalid compose file
- **WHEN** the compose file contains an error that prevents it from being parsed
- **THEN** the build check fails

#### Scenario: Successful build
- **WHEN** the image builds successfully
- **THEN** nothing is pushed to any registry

### Requirement: Runs are reproducible from the lockfile
The system SHALL install dependencies exactly as pinned in the lockfile in every CI check, and MUST fail the run when the lockfile is out of date with the project's declared dependencies.

#### Scenario: Stale lockfile
- **WHEN** a change edits declared dependencies without updating the lockfile
- **THEN** the CI run fails instead of silently resolving newer versions

### Requirement: Runs are safe and efficient
The system SHALL run CI with read-only repository permissions, and SHALL cancel an in-progress run when a newer run starts for the same branch or pull request.

#### Scenario: Superseded run
- **WHEN** new commits are pushed to a branch while an earlier CI run for it is still in progress
- **THEN** the earlier run is cancelled and only the newest run completes

#### Scenario: Token permissions
- **WHEN** a CI run executes
- **THEN** it has no permission to write to the repository
