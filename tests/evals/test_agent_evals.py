import pytest

from agent_wf.config import get_settings
from tests.evals import support
from tests.evals.cases import load_cases
from tests.evals.scoring import score_case

pytestmark = pytest.mark.eval

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_agent_case(case, eval_options, agent_for):
    agent = agent_for(case.agent)
    limit = get_settings().agent_recursion_limit
    repeats = [support.run_case_once(case, agent, limit) for _ in range(eval_options.repeats)]
    result = score_case(case.id, repeats, eval_options.min_pass_rate)
    support.collected_results.append(result)
    assert result.passed, "\n" + result.failure_text()
