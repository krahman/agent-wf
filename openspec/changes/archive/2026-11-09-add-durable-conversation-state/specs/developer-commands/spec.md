# Developer Commands Delta

## MODIFIED Requirements

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

## ADDED Requirements

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
