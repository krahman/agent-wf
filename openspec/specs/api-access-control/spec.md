# api-access-control Specification

## Purpose

Controls which callers may use the agent endpoints, so that only trusted internal services can spend LLM budget, and so that a misconfiguration never leaves the service silently open.

## Requirements

### Requirement: Agent endpoints require an API key
The system SHALL require a valid API key, sent in the `X-API-Key` request header, on the chat endpoint and on every agent endpoint. A request with a missing or invalid key MUST be rejected with status 401 before any LLM call is made.

#### Scenario: Missing key
- **WHEN** a caller sends a request to an agent endpoint without an `X-API-Key` header
- **THEN** the response status is 401 and no LLM call is made

#### Scenario: Wrong key
- **WHEN** a caller sends a request with a key that is not configured
- **THEN** the response status is 401 and no LLM call is made

#### Scenario: Valid key
- **WHEN** a caller sends a valid request with a configured key
- **THEN** the request is processed normally

### Requirement: Multiple keys are accepted for rotation
The system SHALL accept any one of several configured API keys, so that a new key can be added and an old one removed without downtime.

#### Scenario: Old and new key both configured
- **WHEN** two keys are configured and a caller uses either one
- **THEN** both calls are accepted

#### Scenario: Key removed from configuration
- **WHEN** a key is removed from the configuration and the service is restarted
- **THEN** requests using that key are rejected with status 401

### Requirement: Liveness endpoint stays open
The system SHALL serve the liveness endpoint (`GET /`) without requiring an API key.

#### Scenario: Health probe without credentials
- **WHEN** a probe requests the liveness endpoint with no `X-API-Key` header
- **THEN** the response status is 200 and it reports the version and commit

### Requirement: Keys are never exposed
The system MUST NOT write API key values to logs or include them in any response, including error responses.

#### Scenario: Rejected request
- **WHEN** a request is rejected because its key is invalid
- **THEN** neither the log line for the rejection nor the response body contains the submitted key or any configured key

### Requirement: Authentication fails closed
The system SHALL require authentication by default and SHALL refuse to start when authentication is enabled but no API key is configured. Running without authentication MUST require an explicit setting and SHALL log a warning at startup.

#### Scenario: Enabled with no keys
- **WHEN** the service starts with authentication enabled and no keys configured
- **THEN** startup fails with an error naming the missing setting

#### Scenario: Explicit opt-out
- **WHEN** authentication is explicitly disabled
- **THEN** the service starts, a warning is logged, and agent endpoints accept requests without a key
