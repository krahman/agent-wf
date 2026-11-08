# request-limits Specification

## Purpose

Bounds what a single request can ask of the service (input size, conversation identifier shape and run duration), so one bad or runaway request cannot exhaust LLM budget, memory or worker time.

## Requirements

### Requirement: Prompt length is capped
The system SHALL reject a prompt longer than the configured maximum number of characters with status 422, before any LLM call is made. The default maximum SHALL be 4000 characters.

#### Scenario: Prompt at the limit
- **WHEN** a prompt of exactly the maximum length is sent
- **THEN** the request is processed normally

#### Scenario: Prompt over the limit
- **WHEN** a prompt one character longer than the maximum is sent
- **THEN** the response status is 422 and no LLM call is made

### Requirement: Conversation IDs have a safe format
The system SHALL accept a `thread_id` only if it is 1 to 64 characters long and contains only letters, digits, hyphens and underscores, and SHALL reject any other value with status 422. When no `thread_id` is given, the system SHALL generate one.

#### Scenario: Valid thread ID
- **WHEN** a request carries the thread ID `order-1234_a`
- **THEN** the request is processed and that ID continues the same conversation

#### Scenario: Unsafe thread ID
- **WHEN** a request carries a thread ID containing a space, a newline or more than 64 characters
- **THEN** the response status is 422

#### Scenario: No thread ID
- **WHEN** a request carries no thread ID
- **THEN** the request is processed under a newly generated ID

### Requirement: Agent runs are time-bounded
The system SHALL cancel an agent run that exceeds the configured time budget and SHALL report it as a timeout (status 504). The default budget SHALL be 90 seconds.

#### Scenario: Run exceeds the budget
- **WHEN** an agent run is still in progress after the time budget has elapsed
- **THEN** the run is cancelled and the response status is 504
