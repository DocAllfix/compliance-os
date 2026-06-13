"""
Fast regression for the optional "deep" provider profile (gpt-4.1 full).

Pins: profile registry shape, COMPLIANCE_DEEP_PROVIDER resolution, per-model
env resolution (endpoint/key/deployment), and the make_client graceful
fallback to the standard provider when the deep profile is unconfigured.
No network calls — client construction only.
"""
from __future__ import annotations

import pytest

from v2.azure_openai_client_v2 import AzureOpenAIClientV2, _env_suffix, _model_env, make_client
from v2.provider_profiles_v2 import (
    DEFAULT_PROVIDER,
    PROFILES,
    resolve_deep_provider_key,
)


def test_deep_profile_registered():
    assert "gpt-4.1-azure" in PROFILES
    p = PROFILES["gpt-4.1-azure"]
    assert p.name == "gpt-4.1"
    assert p.api_kind == "azure_openai"
    assert DEFAULT_PROVIDER == "gpt-4.1-mini-azure", "la mini resta il default"


def test_env_suffix_scheme():
    assert _env_suffix("gpt-4.1") == "GPT_41"
    assert _env_suffix("gpt-4.1-mini") == "GPT_41_MINI"


def test_resolve_deep_provider_key(monkeypatch):
    monkeypatch.delenv("COMPLIANCE_DEEP_PROVIDER", raising=False)
    assert resolve_deep_provider_key() is None

    monkeypatch.setenv("COMPLIANCE_DEEP_PROVIDER", "gpt-4.1-azure")
    assert resolve_deep_provider_key() == "gpt-4.1-azure"

    monkeypatch.setenv("COMPLIANCE_DEEP_PROVIDER", "not-a-profile")
    assert resolve_deep_provider_key() is None, "profilo ignoto → disattivato"


def test_model_env_specific_overrides_generic(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://generic/openai/v1")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT_GPT_41", "https://deep/openai/v1")
    assert _model_env("gpt-4.1", "AZURE_OPENAI_ENDPOINT") == "https://deep/openai/v1"
    assert _model_env("gpt-4.1-mini", "AZURE_OPENAI_ENDPOINT") == "https://generic/openai/v1"


@pytest.fixture
def azure_env(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com/openai/v1")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_GPT_41_MINI", "gpt-4.1-mini")


def test_make_client_deep_active(azure_env, monkeypatch):
    monkeypatch.setenv("COMPLIANCE_DEEP_PROVIDER", "gpt-4.1-azure")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_GPT_41", "gpt-4.1")
    client = make_client(deep=True)
    assert client.profile.key == "gpt-4.1-azure"
    assert client.deployment == "gpt-4.1"
    # il provider standard non è influenzato
    std = make_client(deep=False)
    assert std.profile.key == "gpt-4.1-mini-azure"
    assert std.deployment == "gpt-4.1-mini"


def test_make_client_deep_unconfigured_falls_back(azure_env, monkeypatch):
    monkeypatch.delenv("COMPLIANCE_DEEP_PROVIDER", raising=False)
    client = make_client(deep=True)
    assert client.profile.key == "gpt-4.1-mini-azure", "deep spento → mini"


def test_make_client_deep_missing_deployment_falls_back(azure_env, monkeypatch):
    """COMPLIANCE_DEEP_PROVIDER attivo ma deployment mancante: la pipeline
    NON deve rompersi — degrada al provider standard con warning."""
    monkeypatch.setenv("COMPLIANCE_DEEP_PROVIDER", "gpt-4.1-azure")
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_GPT_41", raising=False)
    client = make_client(deep=True)
    assert client.profile.key == "gpt-4.1-mini-azure"


def test_gpt41_pricing_registered():
    from v2.token_meter import PRICING
    assert "gpt-4.1" in PRICING
    assert PRICING["gpt-4.1"]["input"] > PRICING["gpt-4.1-mini"]["input"]
