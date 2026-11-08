import logging

import pytest

from agent_wf.api.startup import check_startup
from agent_wf.config import Settings


def make(**kw):
    return Settings(_env_file=None, **kw)


def test_missing_llm_key_names_the_setting():
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        check_startup(make(api_keys="k"))


def test_auth_enabled_without_keys_names_the_setting():
    with pytest.raises(RuntimeError, match="API_KEYS") as exc:
        check_startup(make(openrouter_api_key="llm-secret-value"))
    assert "llm-secret-value" not in str(exc.value)


def test_error_never_contains_secret_values():
    with pytest.raises(RuntimeError) as exc:
        check_startup(make(api_keys="top-secret"))
    assert "top-secret" not in str(exc.value)


def test_valid_configuration_starts():
    check_startup(make(openrouter_api_key="x", api_keys="k"))


def test_auth_disabled_starts_with_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="agent_wf.api"):
        check_startup(make(openrouter_api_key="x", api_auth_enabled=False))
    assert "API_AUTH_ENABLED=false" in caplog.text
