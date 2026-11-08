# Request Limits Delta

## MODIFIED Requirements

### Requirement: Conversation IDs have a safe format
The system SHALL accept a `thread_id` only if it is 1 to 64 characters long and contains only letters, digits, hyphens and underscores, and SHALL reject any other value with status 422. When no `thread_id` is given, the system SHALL process the request as a single run without saved conversation state.

#### Scenario: Valid thread ID
- **WHEN** a request carries the thread ID `order-1234_a`
- **THEN** the request is processed and that ID continues the same conversation

#### Scenario: Unsafe thread ID
- **WHEN** a request carries a thread ID containing a space, a newline or more than 64 characters
- **THEN** the response status is 422

#### Scenario: No thread ID
- **WHEN** a request carries no thread ID
- **THEN** the request is processed without saved conversation state and nothing of it can be continued later
