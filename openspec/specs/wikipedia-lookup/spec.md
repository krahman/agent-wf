# wikipedia-lookup Specification

## Purpose

Defines how the agent's Wikipedia lookup tool answers a query: the shape and limits of the result, what it leaves out, and how it reports failures, so the agent gets predictable text and the tool can change its internals without changing what the agent sees.

## Requirements

### Requirement: Results are page summaries in a fixed format
The system SHALL answer a lookup with the introductory summary of each matching Wikipedia page, each formatted as `Page: <title>` on one line followed by `Summary: <text>`, with consecutive pages separated by a blank line, and SHALL return the text under the `result` key.

#### Scenario: Matching query
- **WHEN** the query "Eiffel Tower" is looked up
- **THEN** the result begins `Page: Eiffel Tower` followed by a line starting `Summary: ` and the page's introduction

### Requirement: Results are limited in count and size
The system SHALL include at most 3 pages, in the order Wikipedia ranks them, and SHALL cut the whole result to at most 4000 characters.

#### Scenario: Many matches
- **WHEN** a query matches more than 3 pages
- **THEN** only the 3 highest-ranked pages appear, best match first

#### Scenario: Long summaries
- **WHEN** the combined text of the pages exceeds 4000 characters
- **THEN** the result is cut to exactly 4000 characters

### Requirement: Unhelpful pages are skipped
The system SHALL leave out disambiguation pages and pages that have no summary text, so the result contains only real article content.

#### Scenario: Disambiguation page ranks first
- **WHEN** the top-ranked match for a query is a disambiguation page
- **THEN** that page does not appear and the remaining matches are returned in order

### Requirement: No match is reported as such
The system SHALL return the text "No good Wikipedia Search Result was found" under the `result` key when a query has no usable match, and MUST NOT return an error for that case.

#### Scenario: Nonsense query
- **WHEN** a query matches nothing
- **THEN** the result is "No good Wikipedia Search Result was found"

### Requirement: Failures are returned as errors, not raised
The system SHALL return `{"error": "Wikipedia lookup failed: <reason>"}` when the lookup cannot be completed (timeout, network failure, an error status from Wikipedia, or a response that cannot be read), and MUST NOT raise an exception to the agent.

#### Scenario: Wikipedia unreachable
- **WHEN** the request cannot reach Wikipedia
- **THEN** the tool returns an error value starting with "Wikipedia lookup failed" and the agent run continues

#### Scenario: Unreadable response
- **WHEN** Wikipedia answers with a body that is not valid data
- **THEN** the tool returns an error value instead of raising

### Requirement: Requests are bounded and identify the caller
The system SHALL give every request a timeout of 10 seconds and SHALL attempt a lookup up to 3 times when the failure is transient (network error, rate limiting, server error or unreadable response) and not otherwise. It SHALL send a User-Agent that names the application and its version and includes a project URL, which an operator can change by configuration.

#### Scenario: Transient failure then success
- **WHEN** the first attempt fails with a server error and the second succeeds
- **THEN** the lookup returns the successful result

#### Scenario: Persistent failure
- **WHEN** all 3 attempts fail
- **THEN** the tool returns the error value after the third attempt and makes no further attempt

#### Scenario: Client error is not retried
- **WHEN** Wikipedia answers with a client error other than rate limiting
- **THEN** the tool returns the error value after a single attempt

#### Scenario: Caller identified
- **WHEN** a request is sent
- **THEN** its User-Agent header contains the application name, its version and a project URL

#### Scenario: Contact URL configured
- **WHEN** an operator sets a different contact URL
- **THEN** requests carry that URL in the User-Agent instead of the default

#### Scenario: Request refused
- **WHEN** Wikipedia refuses a request with a 403 response (for example because the caller is not identified acceptably)
- **THEN** the tool returns the error value after a single attempt, and the response body is not parsed as data

### Requirement: Long queries are shortened
The system SHALL cut a query to its first 300 characters before searching.

#### Scenario: Oversized query
- **WHEN** the query is 1000 characters long
- **THEN** the search sent to Wikipedia contains only its first 300 characters

### Requirement: The tool's interface to the agent is unchanged
The system SHALL keep the tool named `search_wikipedia`, taking one text argument `query`, with its existing description, and loading the tool MUST NOT make a network request or alter any other library.

#### Scenario: Tool definition
- **WHEN** the agent is given its tools
- **THEN** it sees `search_wikipedia` with one `query` argument and the description "Search Wikipedia for factual information about a topic and return a summary."

#### Scenario: Loading the tool
- **WHEN** the tool module is imported
- **THEN** no request is made to any network host
