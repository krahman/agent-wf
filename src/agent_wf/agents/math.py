from agent_wf.agents.spec import AgentSpec

MATH_AGENT = AgentSpec(
    name="math",
    system_prompt=(
        "You are a helpful assistant that can perform various mathematical operations and look up "
        "information on Wikipedia. Use the tools precisely and explain your reasoning clearly. "
        "If a tool returns an error, report it instead of guessing."
    ),
    toolsets=("math", "wikipedia"),
)
