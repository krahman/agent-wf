import pytest

from agent_wf.config import get_settings
from tests.evals import support
from tests.evals.cases import load_cases
from tests.evals.scoring import score_case

pytestmark = pytest.mark.eval

CASES = load_cases()


# A case tagged `quick` also gets the `quick` marker, so `-m "eval and quick"` selects the fast subset.
PARAMS = [pytest.param(c, id=c.id, marks=[pytest.mark.quick] if "quick" in c.tags else []) for c in CASES]


@pytest.mark.parametrize("case", PARAMS)
def test_agent_case(case, eval_options, agent_for, tracer):
    agent = agent_for(case.agent)
    limit = get_settings().agent_recursion_limit
    outcomes = [
        support.run_repeat(case, agent, limit, repeat, tracer) for repeat in range(1, eval_options.repeats + 1)
    ]
    result = score_case(case.id, [failures for failures, _ in outcomes], eval_options.min_pass_rate)
    support.collected_results.append(result)
    if tracer:
        support.collected_traces[case.id] = [trace_id for _, trace_id in outcomes]
    assert result.passed, "\n" + result.failure_text()
