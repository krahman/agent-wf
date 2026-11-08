# Continuous Integration Delta

## ADDED Requirements

### Requirement: Database-backed tests run in CI
The system SHALL run the tests that need a real PostgreSQL in the CI test check, against a database provided by the CI run itself, and those tests SHALL be skipped, not failed, when no database is configured so that the default offline test run still passes. A CI run SHALL fail, not skip them, when its database is missing.

#### Scenario: CI run
- **WHEN** the CI test check runs
- **THEN** the database-backed tests run against the run's own database and a failure in them fails the check

#### Scenario: CI run without its database
- **WHEN** the CI test check runs without a configured test database
- **THEN** the check fails instead of skipping the database-backed tests

#### Scenario: Local run without a database
- **WHEN** the test suite runs on a machine without a configured test database
- **THEN** the database-backed tests are skipped and the run can pass
