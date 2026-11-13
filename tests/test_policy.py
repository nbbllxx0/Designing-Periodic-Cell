"""Subscription-only model calls: no API key or API endpoint reaches a session, and Codex is forced to ChatGPT login."""
import inspect

import pytest

from amm import llm


def test_api_key_refuses_before_any_call(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with pytest.raises(llm.PolicyError):
        llm.assert_subscription_only("codex")


def test_session_env_has_no_keys_or_endpoints(monkeypatch):
    for v in llm.API_KEY_VARS + llm.ENDPOINT_VARS:
        monkeypatch.setenv(v, "x")
    env = llm._clean_env()
    assert not any(v in env for v in llm.API_KEY_VARS + llm.ENDPOINT_VARS)


def test_codex_is_forced_to_chatgpt_login():
    assert 'forced_login_method="chatgpt"' in inspect.getsource(llm.run_codex)


def test_no_sdk_imports():
    import pathlib
    root = pathlib.Path(llm.__file__).resolve().parents[1]
    for f in list((root / "amm").glob("*.py")) + list((root / "scripts").rglob("*.py")):
        src = f.read_text(encoding="utf-8")
        assert "import openai" not in src and "import anthropic" not in src, f


def test_claude_runner_is_subscription_only_and_toolless():
    import inspect
    from amm import llm
    src = inspect.getsource(llm.run_claude)
    assert 'assert_subscription_only("claude")' in src and '"--tools", ""' in src and "--strict-mcp-config" in src
