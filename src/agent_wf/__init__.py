from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agent-wf")  # single source of truth: pyproject.toml
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
