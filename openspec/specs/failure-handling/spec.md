# failure-handling Specification

## Purpose

Gives callers one predictable error shape and a distinct status for each class of failure, so internal services can react correctly, while keeping stack traces and provider details out of responses.

## Requirements

### Requirement: Errors use one JSON shape
The system SHALL return every error response as JSON of the form `{"error": {"code": <string>, "message": <string>, "request_id": <string>}}`, where `request_id` equals the `x-request-id` response header and `code` is a stable machine-readable identifier.

#### Scenario: Unknown agent
- **WHEN** a request names an agent that does not exist
- **THEN** the response status is 404 and the body has `error.code` `agent_not_found`

#### Scenario: Validation failure
- **WHEN** a request body fails validation
- **THEN** the response status is 422 and the body uses the error shape with code `invalid_request`

#### Scenario: Authentication failure
- **WHEN** a request is rejected for a missing or invalid API key
- **THEN** the body uses the error shape with code `unauthorized`

### Requirement: Step limit is reported distinctly
The system SHALL report an agent run that reaches its step limit with status 422 and code `step_limit_exceeded`.

#### Scenario: Agent loops past the limit
- **WHEN** an agent keeps requesting tools until the step limit is reached
- **THEN** the response status is 422 with code `step_limit_exceeded` and no partial answer is returned

### Requirement: Run timeouts are reported distinctly
The system SHALL report a run cancelled for exceeding its time budget with status 504 and code `agent_timeout`.

#### Scenario: Timed-out run
- **WHEN** a run exceeds the time budget
- **THEN** the response status is 504 with code `agent_timeout`

### Requirement: Upstream LLM failures are reported without provider detail
The system SHALL report a failure of the LLM provider (connection error, provider timeout, rate limit or provider error) with status 502 and code `upstream_error`, and MUST NOT include the provider's error message or details in the response.

#### Scenario: Provider unavailable
- **WHEN** the LLM provider cannot be reached or returns an error
- **THEN** the response status is 502 with code `upstream_error` and a generic message

### Requirement: Unexpected errors are safe and traceable
The system SHALL report any other unhandled error with status 500 and code `internal_error`. The response MUST NOT contain a stack trace or exception text. The full exception SHALL be logged server-side with the request ID and thread ID.

#### Scenario: Unexpected exception
- **WHEN** an unexpected exception occurs while handling a request
- **THEN** the response status is 500 with code `internal_error` and a generic message
- **AND** the log contains the exception and stack trace tagged with the same request ID
