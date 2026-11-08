# Failure Handling Delta

## ADDED Requirements

### Requirement: Busy threads are reported distinctly
The system SHALL report a request refused because another run on the same thread is in progress as status 409 with the error code `thread_busy`.

#### Scenario: Thread in use
- **WHEN** a request arrives for a thread that already has a run in progress
- **THEN** the response status is 409 and the body uses the error shape with code `thread_busy`

### Requirement: State store failures are reported without detail
The system SHALL report a failure of the conversation state database as status 503 with the error code `state_unavailable`, and SHALL NOT include database addresses, credentials or driver messages in the response; the detail is logged with the request ID.

#### Scenario: Database unavailable
- **WHEN** a request that needs conversation state cannot reach the state database
- **THEN** the response status is 503, the body uses the error shape with code `state_unavailable`, and the message names no host, user or driver error
