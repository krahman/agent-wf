# service-runtime Specification

## Purpose

Defines how the service starts and runs in its container: it refuses to run misconfigured, runs without root privileges, and lets the platform tell whether it is healthy.

## Requirements

### Requirement: Startup fails fast on missing required configuration
The system SHALL refuse to start, exiting with a non-zero status and an error that names the missing setting (never its value), when the LLM API key is not configured. When a conversation state database is configured, the system SHALL also refuse to start, with an error that never contains the database password, if the database cannot be reached or its schema has not been migrated.

#### Scenario: Missing LLM key
- **WHEN** the service starts without an LLM API key
- **THEN** startup fails and the error names the missing setting

#### Scenario: Complete configuration
- **WHEN** the service starts with the LLM key and authentication settings present
- **THEN** it starts and begins serving requests

#### Scenario: State database configured but unreachable
- **WHEN** the service starts with a state database setting and the database cannot be reached
- **THEN** startup fails and the error does not contain the database password

#### Scenario: State database not migrated
- **WHEN** the service starts with a reachable state database whose schema has not been migrated
- **THEN** startup fails and the error says to run the migration

### Requirement: Container runs as a non-root user
The system SHALL run the application process inside its container as an unprivileged user, never as root.

#### Scenario: Process user
- **WHEN** the container is running
- **THEN** the application process runs with a non-zero user ID

### Requirement: Container reports its health
The container image SHALL define a health check that probes the liveness endpoint, and the compose definition SHALL expose the same health state for the API service. The health state MUST become healthy once the service is serving requests and unhealthy if the endpoint stops responding.

#### Scenario: Healthy service
- **WHEN** the service has started and answers on its liveness endpoint
- **THEN** the container reports healthy

#### Scenario: Unresponsive service
- **WHEN** the liveness endpoint stops responding
- **THEN** the container reports unhealthy after the configured number of failed probes

### Requirement: Compose stack provides the state database
The compose definition SHALL run a state database with its own persistent volume, separate from the Langfuse database, and a one-shot migration step that completes successfully before the API service starts. The API service SHALL NOT start while the database is unhealthy or the migration has failed.

#### Scenario: Starting the stack
- **WHEN** the stack is started on an empty volume
- **THEN** the database becomes healthy, the migration completes, and only then does the API start and report healthy

#### Scenario: Data survives a restart of the stack
- **WHEN** the stack is stopped and started again
- **THEN** conversations stored before are still there
