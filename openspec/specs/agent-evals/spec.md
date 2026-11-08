# agent-evals Specification

## Purpose

Lets the team check, on demand and against a real model, that the agent still picks the right tools, passes the right arguments and answers correctly, so that prompt, model and tool changes can be judged by results instead of by hand-testing.

## Requirements

### Requirement: Evals run only on request
The system SHALL run the evals only when they are explicitly requested. The default test run and the CI pipeline MUST NOT execute them, MUST NOT call an LLM, and MUST NOT need an LLM API key.

#### Scenario: Default test run
- **WHEN** the normal test command is run with no eval selection
- **THEN** no eval case is executed and no LLM call is made

#### Scenario: Explicit eval run
- **WHEN** the evals are explicitly selected
- **THEN** every eval case runs against the real agent and model

### Requirement: Cases assert tool use and answers deterministically
Each eval case SHALL consist of a prompt and one or more deterministic checks on the run. Supported checks SHALL include the tools called, the argument values passed to a tool (numbers compared with a tolerance), tools that must not be called, text the final answer must or must not contain, and a maximum number of tool calls. The system MUST NOT use a model to grade a result.

#### Scenario: Correct tool and arguments
- **WHEN** a case expects `add_numbers` with the numbers 1 and 1 and the agent calls it with `[1, 1]`
- **THEN** the tool check passes

#### Scenario: Wrong argument order
- **WHEN** a case expects `subtract_numbers` with `[10, 3]` and the agent calls it with `[3, 10]`
- **THEN** the check fails and the failure names the expected and actual arguments

#### Scenario: Answer content
- **WHEN** a case requires the final answer to contain `2` and the answer does not
- **THEN** the check fails and the failure shows the answer

### Requirement: Cases are repeated and scored by pass rate
The system SHALL run each case several times at temperature 0 (3 times by default) and SHALL pass a case when its pass rate across the runs meets a configurable threshold (100% by default). The number of repeats and the threshold MUST be settable for a run.

#### Scenario: All repeats pass
- **WHEN** a case passes in every repeat
- **THEN** the case is reported as passed with a 100% pass rate

#### Scenario: Intermittent failure under a strict threshold
- **WHEN** a case passes in 2 of 3 repeats and the threshold is 100%
- **THEN** the case is reported as failed, with the failure reason of the failing repeat

#### Scenario: Lowered threshold
- **WHEN** the threshold is set to 60% and a case passes in 2 of 3 repeats
- **THEN** the case is reported as passed

### Requirement: The model under test can be chosen
The system SHALL run the evals with the application's configured model by default, and SHALL let a run name a different model without changing configuration, so models can be compared on the same cases.

#### Scenario: Override the model
- **WHEN** a run names a model explicitly
- **THEN** every case runs against that model and the report records it

### Requirement: Evals do not depend on external websites
The system SHALL replace the Wikipedia lookup tool with a fixed stub during evals, so that results depend only on the agent and model and never on network access to Wikipedia.

#### Scenario: Wikipedia unreachable
- **WHEN** an eval runs on a machine with no access to Wikipedia
- **THEN** cases that use the lookup tool still run and receive the stub's fixed result

### Requirement: Every run produces a report
The system SHALL write a machine-readable report for every eval run, including failing runs. It MUST record the model, application version, commit, repeat count, threshold and time of the run, and for each case its pass rate and the reason for each failed repeat. Reports MUST NOT be committed to the repository.

#### Scenario: Passing run
- **WHEN** an eval run finishes with all cases passing
- **THEN** a report exists with the run details and a pass rate for each case

#### Scenario: Failing run
- **WHEN** an eval run finishes with a failing case
- **THEN** the report still exists and names the failing case and the failed check

### Requirement: Evals fail clearly without credentials
The system SHALL stop an explicitly requested eval run before the first case when no LLM API key is configured, with an error that names the missing setting and not its value.

#### Scenario: No API key
- **WHEN** the evals are requested and no LLM API key is configured
- **THEN** the run stops immediately and the error names the missing setting

### Requirement: The seed suite covers the agent's core behaviours
The initial suite SHALL include cases for each math tool (add, subtract, multiply, divide, power); argument order for subtraction and division; a multi-step calculation; a non-English prompt; numbers written with separators and negative numbers; reporting a divide-by-zero error without inventing a result; and using a tool rather than guessing for a large calculation.

#### Scenario: Non-English prompt
- **WHEN** the prompt is the Indonesian "satu ditambah satu"
- **THEN** the case expects the add tool with the numbers 1 and 1 and an answer stating 2, as the digit or spelled out in the prompt's language (for example "dua")

#### Scenario: Divide by zero
- **WHEN** the prompt asks the agent to use the divide tool to divide 100 by 0 and report what the tool returned
- **THEN** the case expects the divide tool to be called with the zero and the answer to report that the division is not possible rather than give a number

#### Scenario: Divide by zero asked directly
- **WHEN** the prompt asks "what is 10 divided by 0?" and the model may answer without any tool (a model does not send a zero divisor to the calculator unprompted)
- **THEN** the case only requires that the answer says the division is not possible and does not give a number

### Requirement: The scoring logic is itself tested without a model
The system SHALL verify the checks, the repeat and threshold logic and the report writing with automated tests that use no LLM and run in the default test run.

#### Scenario: Scoring tests in the default run
- **WHEN** the default test run executes
- **THEN** tests for the checks, pass-rate scoring and report writing run and pass without any LLM call
