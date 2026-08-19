"""Tests for settings loading and validation."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.core.settings import SettingsError, load_settings

VALID_SETTINGS_YAML = """
llm:
  provider: openai
  model: gpt-4o-mini
  temperature: 0.0
  max_tokens: 1024
embedding:
  provider: openai
  model: text-embedding-3-small
  dimensions: 1536
vector_store:
  provider: chroma
  persist_directory: ./data/db/chroma
  collection_name: knowledge_hub
retrieval:
  dense_top_k: 20
  sparse_top_k: 20
  fusion_top_k: 10
  rrf_k: 60
rerank:
  enabled: false
  provider: none
  model: cross-encoder/ms-marco-MiniLM-L-6-v2
  top_k: 5
evaluation:
  enabled: false
  provider: custom
  metrics:
    - hit_rate
    - mrr
observability:
  log_level: INFO
  trace_enabled: true
  trace_file: ./logs/traces.jsonl
  structured_logging: true
ingestion:
  chunk_size: 1000
  chunk_overlap: 200
  splitter: recursive
  batch_size: 100
"""


def _write_yaml(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def test_load_settings_success(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.yaml"
    _write_yaml(settings_path, VALID_SETTINGS_YAML)

    settings = load_settings(settings_path)

    assert settings.llm.provider == "openai"
    assert settings.embedding.dimensions == 1536
    assert settings.vector_store.collection_name == "knowledge_hub"
    assert settings.retrieval.rrf_k == 60
    assert settings.rerank.provider == "none"
    assert settings.evaluation.metrics == ["hit_rate", "mrr"]
    assert settings.observability.log_level == "INFO"
    assert settings.ingestion is not None


def test_environment_selects_default_settings_path(tmp_path: Path, monkeypatch) -> None:
    settings_path = tmp_path / "environment-settings.yaml"
    _write_yaml(settings_path, VALID_SETTINGS_YAML.replace("gpt-4o-mini", "env-model"))
    monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(settings_path))

    settings = load_settings()

    assert settings.llm.model == "env-model"


def test_explicit_settings_path_overrides_environment(tmp_path: Path, monkeypatch) -> None:
    environment_path = tmp_path / "environment-settings.yaml"
    explicit_path = tmp_path / "explicit-settings.yaml"
    _write_yaml(environment_path, VALID_SETTINGS_YAML.replace("gpt-4o-mini", "env-model"))
    _write_yaml(explicit_path, VALID_SETTINGS_YAML.replace("gpt-4o-mini", "explicit-model"))
    monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(environment_path))

    settings = load_settings(explicit_path)

    assert settings.llm.model == "explicit-model"


def test_missing_required_field_raises_error(tmp_path: Path) -> None:
    config = """
    llm:
      provider: openai
      model: gpt-4o-mini
      temperature: 0.0
      max_tokens: 1024
    embedding:
      model: text-embedding-3-small
      dimensions: 1536
    vector_store:
      provider: chroma
      persist_directory: ./data/db/chroma
      collection_name: knowledge_hub
    retrieval:
      dense_top_k: 20
      sparse_top_k: 20
      fusion_top_k: 10
      rrf_k: 60
    rerank:
      enabled: false
      provider: none
      model: cross-encoder/ms-marco-MiniLM-L-6-v2
      top_k: 5
    evaluation:
      enabled: false
      provider: custom
      metrics:
        - hit_rate
    observability:
      log_level: INFO
      trace_enabled: true
      trace_file: ./logs/traces.jsonl
      structured_logging: true
    """
    settings_path = tmp_path / "settings.yaml"
    _write_yaml(settings_path, config)

    with pytest.raises(SettingsError, match="embedding.provider"):
        load_settings(settings_path)
