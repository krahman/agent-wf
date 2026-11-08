# Spec Delta

## Purpose

Defines how the service starts and runs in its container: it refuses to run misconfigured, runs without root privileges, and lets the platform tell whether it is healthy.

## ADDED Requirements

### Requirement: Startup fails fast on missing required configuration
The system SHALL refuse to start, exiting with a non-zero status and an error that names the missing setting (never its value), when the LLM API key is not configured.

#### Scenario: Missing LLM key
- **WHEN** the service starts without an LLM API key
- **THEN** startup fails and the error names the missing setting

#### Scenario: Complete configuration
- **WHEN** the service starts with the LLM key and authentication settings present
- **THEN** it starts and begins serving requests

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
