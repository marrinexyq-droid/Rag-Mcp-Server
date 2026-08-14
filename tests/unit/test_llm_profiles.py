"""Tests for selectable LLM configuration profiles."""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

import pytest

from src.core.settings import Settings, SettingsError
from src.libs.llm.deepseek_llm import DeepSeekLLM
from src.libs.llm.openai_llm import OpenAILLM


def _settings_data() -> dict:
    return {
        "llm": {
            "active_profile": "vectorengine",
            "temperature": 0.0,
            "max_tokens": 4096,
            "profiles": {
                "vectorengine": {
                    "provider": "openai",
                    "model": "deepseek-v4-flash",
                    "base_url": "https://api.vectorengine.ai/v1",
                    "api_key_env": "VECTORENGINE_API_KEY",
                },
                "deepseek-direct": {
                    "provider": "deepseek",
                    "model": "deepseek-v4-flash",
                    "base_url": "https://api.deepseek.com",
                    "api_key_env": "DEEPSEEK_API_KEY",
                },
            },
        },
        "embedding": {
            "provider": "ollama",
            "model": "nomic-embed-text",
            "dimensions": 768,
        },
        "vector_store": {
            "provider": "chroma",
            "persist_directory": "./data/db/chroma",
            "collection_name": "knowledge_hub",
        },
        "retrieval": {
            "dense_top_k": 20,
            "sparse_top_k": 20,
            "fusion_top_k": 10,
            "rrf_k": 60,
        },
        "rerank": {
            "enabled": False,
            "provider": "none",
            "model": "unused",
            "top_k": 5,
        },
        "evaluation": {
            "enabled": False,
            "provider": "custom",
            "metrics": ["hit_rate"],
        },
        "observability": {
            "log_level": "INFO",
            "trace_enabled": True,
            "trace_file": "./logs/traces.jsonl",
            "structured_logging": True,
        },
    }


def test_active_profile_selects_relay_and_shared_defaults() -> None:
    settings = Settings.from_dict(_settings_data())

    assert settings.llm.profile == "vectorengine"
    assert settings.llm.provider == "openai"
    assert settings.llm.base_url == "https://api.vectorengine.ai/v1"
    assert settings.llm.api_key_env == "VECTORENGINE_API_KEY"
    assert settings.llm.temperature == 0.0
    assert settings.llm.max_tokens == 4096


def test_unknown_active_profile_raises_readable_error() -> None:
    data = _settings_data()
    data["llm"]["active_profile"] = "missing"

    with pytest.raises(SettingsError, match=r"llm\.profiles\.missing"):
        Settings.from_dict(data)


def test_relay_client_reads_profile_endpoint_and_key_environment() -> None:
    settings = Settings.from_dict(_settings_data())

    with patch.dict("os.environ", {"VECTORENGINE_API_KEY": "relay-key"}, clear=True):
        llm = OpenAILLM(settings)

    assert llm.api_key == "relay-key"
    assert llm.base_url == "https://api.vectorengine.ai/v1"


def test_direct_profile_uses_its_own_endpoint_and_key_environment() -> None:
    data = deepcopy(_settings_data())
    data["llm"]["active_profile"] = "deepseek-direct"
    settings = Settings.from_dict(data)

    with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "direct-key"}, clear=True):
        llm = DeepSeekLLM(settings)

    assert llm.api_key == "direct-key"
    assert llm.base_url == "https://api.deepseek.com"
