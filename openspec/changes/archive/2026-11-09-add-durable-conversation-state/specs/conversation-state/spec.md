# Conversation State

## Purpose

Defines how conversations are stored and continued: which requests keep state, how that state is shared across service instances and survives restarts, how interrupted runs are repaired, how concurrent use of one conversation is handled, and how old state is bounded and removed.

## ADDED Requirements

### Requirement: Conversations with a thread ID are durable
The system SHALL store the conversation of every request that carries a `thread_id` in a database shared by all service instances, so that a later request with the same `thread_id` continues that conversation on any instance and after any restart of the service.

#### Scenario: Continue after a restart
- **WHEN** a request with thread ID `order-1` is answered, the service restarts, and a second request with `order-1` is sent
- **THEN** the second run sees the messages of the first

#### Scenario: Continue on another instance
- **WHEN** a request with thread ID `order-1` is answered by one instance and the next request with `order-1` reaches a different instance
- **THEN** the second run sees the messages of the first

#### Scenario: Different conversations stay separate
- **WHEN** requests with thread IDs `a` and `b` are sent
- **THEN** neither run sees the messages of the other

### Requirement: Requests without a thread ID keep no state
The system SHALL run a request that carries no `thread_id` without storing any conversation state, and such a request SHALL NOT depend on the state database being available.

#### Scenario: Anonymous request leaves nothing behind
- **WHEN** a request without a thread ID is answered
- **THEN** no conversation data for it exists in the state database afterwards

#### Scenario: Anonymous request with the database down
- **WHEN** the state database is unreachable and a request without a thread ID is sent
- **THEN** the request is processed normally

### Requirement: Interrupted runs do not break their thread
The system SHALL, before running a request on an existing thread, close every assistant tool call that has no tool result (as left by a run that was cancelled by the time budget or lost to a crash) with an error result, so that the new request is sent to the model with a consistent history and is not rejected for it.

#### Scenario: Run cancelled during a tool call
- **WHEN** a run on thread `t1` is cancelled by the time budget while a tool call is pending, and a new request with `t1` is sent
- **THEN** the new request is processed and answered, and the earlier tool call appears in the history with an error result

#### Scenario: Healthy thread
- **WHEN** a request is sent on a thread whose history has no pending tool call
- **THEN** the history is not altered

### Requirement: One run per thread at a time
The system SHALL allow at most one run on a given `thread_id` at any moment across all instances, and SHALL refuse a request that arrives while another run on the same thread is in progress, with status 409 and code `thread_busy`, without running it. The lock MUST be released when the run ends for any reason, including cancellation, timeout and instance failure.

#### Scenario: Simultaneous requests on one thread
- **WHEN** two requests with the same thread ID arrive while the first is still running
- **THEN** the second gets status 409 with code `thread_busy`, and the stored conversation contains the messages of the first run only

#### Scenario: Retry after the first run finished
- **WHEN** the refused request is sent again after the first run has ended
- **THEN** it is processed and its messages are added to the conversation

#### Scenario: Run ends with an error
- **WHEN** a run ends by timeout or failure
- **THEN** the next request on that thread is not refused as busy

#### Scenario: Different threads run in parallel
- **WHEN** two requests with different thread IDs are in progress at the same time
- **THEN** neither is refused

### Requirement: Stored state stays bounded
The system SHALL keep only the latest state of a conversation once a run on it has finished, instead of every intermediate step, and SHALL delete the state of conversations idle for longer than the configured retention, 30 days by default. Deletion of idle conversations SHALL be done by a command that can be run on a schedule, and SHALL run once per schedule tick no matter how many instances exist.

#### Scenario: Long conversation
- **WHEN** a conversation has had many turns
- **THEN** the conversation continues with its full message history and the database holds only its latest state

#### Scenario: Idle conversation past retention
- **WHEN** the prune command runs and a conversation has not been used for longer than the retention
- **THEN** that conversation is deleted, and a later request with its thread ID starts a new conversation

#### Scenario: Recent conversation
- **WHEN** the prune command runs and a conversation was used within the retention
- **THEN** it is kept unchanged

### Requirement: Schema migrations run once, apart from the instances
The system SHALL create and upgrade the state database schema in a separate migration step that is run before the instances start, and instances SHALL NOT change the schema. An instance that finds the schema missing or outdated SHALL refuse to start with an error that says to run the migration.

#### Scenario: Several instances start together
- **WHEN** several instances start at the same moment on a migrated database
- **THEN** all of them start and none changes the schema

#### Scenario: Database not migrated
- **WHEN** an instance starts against a database whose schema is missing
- **THEN** startup fails and the error says the migration has not been run

#### Scenario: Migration run twice
- **WHEN** the migration step runs on an already migrated database
- **THEN** it succeeds and changes nothing

### Requirement: State database failures are contained
The system SHALL report a state database that is unreachable or fails during a request that carries a `thread_id` as status 503 with code `state_unavailable`, with no database detail in the response, and SHALL keep serving requests that need no state. Its connections per instance SHALL be bounded by a configured limit.

#### Scenario: Database unreachable for a conversation request
- **WHEN** the state database is unreachable and a request with a thread ID is sent
- **THEN** the response status is 503 with code `state_unavailable`, and no LLM call is made

#### Scenario: Database returns after an outage
- **WHEN** the database becomes reachable again
- **THEN** requests with a thread ID are processed without restarting the service

### Requirement: Local development works without a database
The system SHALL keep conversations in process memory, and log a warning at startup, when no state database is configured, so local development and the offline tests need no database.

#### Scenario: No database configured
- **WHEN** the service starts without a state database setting
- **THEN** it starts, logs a warning that conversations are not durable, and continues conversations with the same thread ID within the process
