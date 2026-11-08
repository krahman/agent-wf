import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Request
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver

from agent_wf import __version__
from agent_wf.agents import AGENT_SPECS
from agent_wf.api.errors import ApiError, error_response, register_error_handlers
from agent_wf.api.schemas import AgentRequest, AgentResponse, ChatRequest, ChatResponse
from agent_wf.api.security import require_api_key
from agent_wf.api.startup import check_startup
from agent_wf.config import get_settings
from agent_wf.llm import build_llm
from agent_wf.observability import (
    LoggingCallbackHandler,
    configure_logging,
    configure_tracing,
    shutdown_tracing,
    trace_callbacks,
    trace_context,
)
from agent_wf.observability.logging import request_id_var, thread_id_var

logger = logging.getLogger("agent_wf.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    check_startup(settings)
    configure_tracing(settings)
    app.state.llm = build_llm()
    checkpointer = InMemorySaver()
    app.state.agents = {
        name: spec.build(app.state.llm, checkpointer) for name, spec in AGENT_SPECS.items()
    }
    yield
    shutdown_tracing()


app = FastAPI(title="agent-wf", version=__version__, lifespan=lifespan)
register_error_handlers(app)
protected = APIRouter(dependencies=[Depends(require_api_key)])


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    request_id_var.set(request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # Handled here rather than via an Exception handler, which would run outside this
        # middleware and lose the request ID header and the request log line.
        thread_id_var.set(getattr(request.state, "thread_id", "-"))
        logger.exception("unhandled error: %s %s", request.method, request.url.path)
        response = error_response(request, 500, "internal_error", "Internal server error")
    response.headers["x-request-id"] = request_id
    logger.info(
        "%s %s -> %s %.0fms",
        request.method,
        request.url.path,
        response.status_code,
        (time.perf_counter() - start) * 1000,
    )
    return response


@app.get("/")
def root_controller():
    return {"status": "healthy", "version": __version__, "commit": get_settings().git_sha}


@protected.post("/chat", response_model=ChatResponse)
async def chat_controller(body: ChatRequest):
    response = await app.state.llm.ainvoke(
        [SystemMessage("You are a helpful assistant."), HumanMessage(body.prompt)]
    )
    return ChatResponse(statement=response.text)


@protected.post("/agents/{name}", response_model=AgentResponse)
async def agent_controller(name: str, body: AgentRequest, request: Request):
    agent = app.state.agents.get(name)
    if agent is None:
        raise ApiError(404, "agent_not_found", f"Unknown agent '{name}'")
    thread_id = body.thread_id or str(uuid.uuid4())
    request.state.thread_id = thread_id
    thread_id_var.set(thread_id)
    config = {
        "recursion_limit": get_settings().agent_recursion_limit,
        "configurable": {"thread_id": thread_id},
        "run_name": f"agent:{name}",
        "callbacks": [LoggingCallbackHandler(), *trace_callbacks()],
        "metadata": {"agent": name, "request_id": request_id_var.get()},
    }
    try:
        with trace_context(f"agent:{name}", thread_id):
            async with asyncio.timeout(get_settings().agent_timeout_seconds) as budget:
                result = await agent.ainvoke({"messages": [("human", body.prompt)]}, config)
    except TimeoutError:
        if not budget.expired():
            raise  # a timeout from inside the run, not our budget
        logger.warning("agent run exceeded its time budget: agent=%s", name)
        raise ApiError(504, "agent_timeout", "The agent run exceeded its time budget") from None
    return AgentResponse(answer=result["messages"][-1].text)


app.include_router(protected)
