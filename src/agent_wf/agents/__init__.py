from agent_wf.agents.math import MATH_AGENT
from agent_wf.agents.spec import AgentSpec

AGENT_SPECS: dict[str, AgentSpec] = {spec.name: spec for spec in (MATH_AGENT,)}
