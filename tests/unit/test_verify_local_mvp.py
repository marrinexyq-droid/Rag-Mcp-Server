"""Unit tests for the local MVP verification helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mcp import types

from scripts.verify_local_mvp import (
    _extract_structured_references,
    _latest_query_trace,
    _validate_query_response,
)


def _query_response(source: str = "fixtures/simple.pdf") -> types.CallToolResult:
    references = {
        "citations": [{"index": 1, "source": source, "score": 0.9}],
        "metadata": {"result_count": 1},
    }
    return types.CallToolResult(
        content=[
            types.TextContent(type="text", text="## 检索结果\n\n### [1] 结果 1"),
            types.TextContent(
                type="text",
                text=f"**References (JSON):**\n```json\n{json.dumps(references)}\n```",
            ),
        ],
        isError=False,
    )


@pytest.mark.unit
def test_extract_structured_references() -> None:
    payload = _extract_structured_references(
        ["prefix\n```json\n{\"citations\": [{\"index\": 1}]}\n```"]
    )
    assert payload["citations"][0]["index"] == 1


@pytest.mark.unit
def test_validate_query_response_checks_expected_source() -> None:
    citations, preview = _validate_query_response(_query_response(), "simple.pdf")
    assert citations[0]["source"] == "fixtures/simple.pdf"
    assert "[1]" in preview


@pytest.mark.unit
def test_validate_query_response_rejects_missing_source() -> None:
    with pytest.raises(ValueError, match="Expected source substring"):
        _validate_query_response(_query_response(), "other.pdf")


@pytest.mark.unit
def test_latest_query_trace_selects_newest_matching_trace(tmp_path: Path) -> None:
    trace_path = tmp_path / "traces.jsonl"
    traces = [
        {
            "trace_id": "other",
            "trace_type": "query",
            "metadata": {"query": "question", "collection": "other"},
        },
        {
            "trace_id": "wanted",
            "trace_type": "query",
            "metadata": {"query": "question", "collection": "issue4-e2e"},
        },
    ]
    trace_path.write_text(
        "\n".join(json.dumps(trace) for trace in traces) + "\n",
        encoding="utf-8",
    )

    trace = _latest_query_trace(
        trace_path,
        query="question",
        collection="issue4-e2e",
    )

    assert trace is not None
    assert trace["trace_id"] == "wanted"
