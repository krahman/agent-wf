from agent_wf.config import Settings
from agent_wf.llm import build_llm

SETTINGS = Settings(_env_file=None, openrouter_api_key="k")


def test_temperature_is_unset_by_default():
    assert build_llm(settings=SETTINGS).temperature is None


def test_temperature_is_passed_through_when_given():
    assert build_llm(settings=SETTINGS, temperature=0).temperature == 0


def test_model_override():
    assert build_llm("some/model", settings=SETTINGS).model_name == "some/model"
