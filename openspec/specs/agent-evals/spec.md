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

### Requirement: Numeric answers are compared as numbers
The system SHALL support a check that an answer states a given number, comparing numeric values and not text. A number written with thousands separators, a space, or either decimal mark SHALL count as the same value, and a different number that merely contains the same digits MUST NOT count. A case MAY list spelled-out words as whole-word alternatives.

#### Scenario: Digits inside a larger number
- **WHEN** a case expects the number 2 and the answer says "12" or "20"
- **THEN** the check fails and shows the answer

#### Scenario: Separators and decimal marks
- **WHEN** a case expects 3500 and the answer says "3,500", "3.500", "3 500" or "3500"
- **THEN** the check passes

#### Scenario: Decimal comma
- **WHEN** a case expects 6.25 and the answer says "6,25" or "6.25"
- **THEN** the check passes

#### Scenario: Number inside a sentence
- **WHEN** a case expects 42 and the answer is "6 times 7 is 42."
- **THEN** the check passes

#### Scenario: Spelled-out alternative
- **WHEN** a case expects 2 with the word "dua" as an alternative and the answer says "dua"
- **THEN** the check passes, and an answer of "dua belas" still fails if the case excludes "belas"

### Requirement: Argument order can be ignored where the operation allows it
The system SHALL compare the numbers in an argument list regardless of order when a case marks that argument check as unordered, and SHALL compare them in order otherwise.

#### Scenario: Commutative operation, other order
- **WHEN** an unordered check expects `multiply_numbers` with `[6, 7]` and the agent calls it with `[7, 6]`
- **THEN** the check passes

#### Scenario: Ordered by default
- **WHEN** a check without the unordered mark expects `subtract_numbers` with `[10, 3]` and the agent calls it with `[3, 10]`
- **THEN** the check fails

#### Scenario: Different numbers
- **WHEN** an unordered check expects `[6, 7]` and the agent calls the tool with `[6, 8]`
- **THEN** the check fails

### Requirement: Eval runs can be traced on request
The system SHALL send each eval repeat to Langfuse as a trace only when the run asks for it with `--eval-trace`. Each trace SHALL be named `eval:<case-id>`, all traces of one run SHALL share one session, and each SHALL be tagged with `eval`, the case, the repeat number and the model. Tracing MUST work even when general tracing is switched off in the configuration.

#### Scenario: Normal run
- **WHEN** the evals run without `--eval-trace`
- **THEN** nothing is sent to Langfuse and Langfuse does not need to be running

#### Scenario: Traced run
- **WHEN** the evals run with `--eval-trace`
- **THEN** every repeat appears in Langfuse as a trace named `eval:<case-id>` in the run's session, with the case, repeat and model as tags

#### Scenario: Tracing disabled in configuration
- **WHEN** `LANGFUSE_TRACING` is false and the evals run with `--eval-trace`
- **THEN** the run is still traced

### Requirement: Traced repeats are scored
The system SHALL record the result of each traced repeat in Langfuse as a boolean score named `eval_pass` on that repeat's trace, with the failure reasons as the score's comment. It MUST NOT record scores when the run is not traced.

#### Scenario: Passing repeat
- **WHEN** a traced repeat passes every check
- **THEN** its trace has an `eval_pass` score of true

#### Scenario: Failing repeat
- **WHEN** a traced repeat fails a check
- **THEN** its trace has an `eval_pass` score of false whose comment lists the failed checks

#### Scenario: Untraced run
- **WHEN** the evals run without `--eval-trace`
- **THEN** no score is recorded anywhere

### Requirement: Tracing fails clearly before any case runs
The system SHALL stop a run started with `--eval-trace` before the first model call when Langfuse's keys are not configured or its server cannot be reached, with an error that names the missing setting or the unreachable address and never a secret value. A Langfuse outage after the run has started MUST NOT fail or abort any case.

#### Scenario: Keys missing
- **WHEN** the evals run with `--eval-trace` and no Langfuse keys are configured
- **THEN** the run stops immediately and the error names the missing settings

#### Scenario: Server unreachable
- **WHEN** the evals run with `--eval-trace` and the Langfuse server does not answer
- **THEN** the run stops immediately and the error names the address that could not be reached

#### Scenario: Outage during a run
- **WHEN** the Langfuse server becomes unreachable after the first case has started
- **THEN** the cases still run and pass or fail on their checks

### Requirement: Traced reports link to their traces
The system SHALL include in the report of a traced run the session, the Langfuse address and, for every repeat, the ID of its trace, so that a failed repeat can be opened directly in Langfuse. The report of an untraced run MUST NOT contain trace fields.

#### Scenario: Failing traced repeat
- **WHEN** a traced repeat fails
- **THEN** the report's failure entry contains that repeat's trace ID

#### Scenario: Untraced report
- **WHEN** a run without `--eval-trace` writes its report
- **THEN** the report has no trace IDs, session or Langfuse address
