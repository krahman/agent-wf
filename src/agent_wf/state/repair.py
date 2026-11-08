"""Close tool calls a cancelled or crashed run left without a result."""

import logging

from langchain_core.messages import AIMessage, ToolMessage

logger = logging.getLogger("agent_wf.state")

INTERRUPTED = "The tool call was interrupted before it finished."


def dangling_tool_calls(messages: list) -> list[dict]:
    """Tool calls of the history that no ToolMessage answers."""
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    return [
        call
        for m in messages
        if isinstance(m, AIMessage)
        for call in m.tool_calls
        if call["id"] not in answered
    ]


async def repair_thread(agent, config: dict) -> int:
    """Add an error result for every unanswered tool call; return how many were closed.

    A model rejects a history where a tool call has no result (HTTP 400), so without this a run
    cancelled by the time budget would make every later request on its thread fail."""
    snapshot = await agent.aget_state(config)
    messages = (snapshot.values or {}).get("messages", [])
    pending = dangling_tool_calls(messages)
    if not pending:
        return 0
    results = [
        ToolMessage(content=INTERRUPTED, tool_call_id=call["id"], name=call["name"], status="error")
        for call in pending
    ]
    await agent.aupdate_state(config, {"messages": results}, as_node="tools")
    logger.warning("closed %d interrupted tool call(s) on the thread", len(results))
    return len(results)
