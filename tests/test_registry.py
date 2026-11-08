import pytest

from agent_wf.agents import AGENT_SPECS
from agent_wf.tools import TOOLSETS, get_tools


def test_every_agent_toolset_is_registered():
    for spec in AGENT_SPECS.values():
        assert get_tools(*spec.toolsets)


def test_unknown_toolset_raises():
    with pytest.raises(KeyError):
        get_tools("nope")


def test_tool_names_unique():
    names = [t.name for ts in TOOLSETS.values() for t in ts]
    assert len(names) == len(set(names))
