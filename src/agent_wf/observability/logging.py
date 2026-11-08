import logging
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
thread_id_var: ContextVar[str] = ContextVar("thread_id", default="-")


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.thread_id = thread_id_var.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.addFilter(_ContextFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s [req=%(request_id)s thread=%(thread_id)s] %(message)s")
    )
    root = logging.getLogger("agent_wf")
    root.handlers = [handler]
    root.setLevel(level.upper())
    root.propagate = False
