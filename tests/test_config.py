from agent_wf.config import Settings


def keys(value):
    return Settings(_env_file=None, api_keys=value).api_key_list()


def test_api_key_list_parsing():
    assert keys("a,b") == ["a", "b"]
    assert keys(" a , b ,") == ["a", "b"]
    assert keys(",,") == []


def test_api_key_list_unset_and_empty(monkeypatch):
    assert Settings(_env_file=None).api_key_list() == []
    monkeypatch.setenv("API_KEYS", "")
    assert Settings(_env_file=None).api_key_list() == []


def test_defaults_are_closed_and_bounded():
    s = Settings(_env_file=None)
    assert s.api_auth_enabled is True
    assert s.max_prompt_chars == 4000
    assert s.agent_timeout_seconds == 90


def test_keys_not_in_repr():
    assert "secret-key" not in repr(Settings(_env_file=None, api_keys="secret-key"))


def test_wikipedia_contact_default_override_and_empty(monkeypatch):
    default = Settings(_env_file=None).wikipedia_contact
    assert default.startswith("https://") and "agent-wf" in default
    monkeypatch.setenv("WIKIPEDIA_CONTACT", "ops@example.com")
    assert Settings(_env_file=None).wikipedia_contact == "ops@example.com"
    monkeypatch.setenv("WIKIPEDIA_CONTACT", "")
    assert Settings(_env_file=None).wikipedia_contact == default
