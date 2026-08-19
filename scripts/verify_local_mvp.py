#!/usr/bin/env python
"""Verify the local MVP through a real MCP stdio session.

The script starts the production MCP server with the selected committed
configuration, discovers its tools, checks the target collection, performs a
hybrid query, and validates both Markdown and structured citations.

It intentionally does not ingest data or call an LLM. Run ``scripts/ingest.py``
first so that paid ingestion remains an explicit action.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_REPO_ROOT))

from src.core.settings import SETTINGS_PATH_ENV, load_settings, resolve_path  # noqa: E402

REQUIRED_TOOLS = {
    "get_document_summary",
    "list_collections",
    "query_knowledge_hub",
}
_JSON_FENCE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


@dataclass(frozen=True)
class VerificationEvidence:
    """Evidence returned by a successful MCP verification."""

    tools: list[str]
    citation_count: int
    first_source: str
    elapsed_ms: float
    response_preview: str


def _configure_windows_console() -> None:
    """Use UTF-8 for command-line output without mutating streams on import."""
    if sys.platform != "win32":
        return

    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Verify a populated local collection through the production MCP server."
    )
    parser.add_argument(
        "--query",
        default="What does the document say about MarkItDown conversion and metadata?",
        help="Query sent to query_knowledge_hub.",
    )
    parser.add_argument(
        "--collection",
        default="issue4-e2e",
        help="Existing collection to verify (default: issue4-e2e).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Maximum results requested from the MCP tool (default: 3).",
    )
    parser.add_argument(
        "--expect-source",
        help="Optional source substring that must appear in a structured citation.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=_REPO_ROOT / "config" / "settings.yaml",
        help="Settings YAML used by the child MCP server.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=90.0,
        help="Overall MCP session timeout (default: 90).",
    )
    return parser.parse_args()


def _extract_structured_references(text_blocks: list[str]) -> dict[str, Any]:
    """Extract the JSON references block from MCP text content."""
    for block in text_blocks:
        match = _JSON_FENCE.search(block)
        if match:
            payload = json.loads(match.group(1))
            if isinstance(payload, dict):
                return payload
    raise ValueError("MCP response did not contain a structured JSON references block")


def _validate_query_response(
    response: types.CallToolResult,
    expected_source: str | None,
) -> tuple[list[dict[str, Any]], str]:
    """Validate citation-bearing query output and return citations plus preview."""
    if response.is_error:
        raise ValueError("query_knowledge_hub returned isError=true")

    text_blocks = [
        block.text for block in response.content if isinstance(block, types.TextContent)
    ]
    if not text_blocks or "[1]" not in text_blocks[0]:
        raise ValueError("MCP response did not contain citation marker [1]")

    structured = _extract_structured_references(text_blocks)
    raw_citations = structured.get("citations")
    if not isinstance(raw_citations, list) or not raw_citations:
        raise ValueError("MCP response contained no structured citations")

    citations = [item for item in raw_citations if isinstance(item, dict)]
    if not citations:
        raise ValueError("MCP response citations were not JSON objects")

    if expected_source:
        sources = [str(item.get("source", "")) for item in citations]
        if not any(expected_source in source for source in sources):
            raise ValueError(
                f"Expected source substring {expected_source!r}; received {sources!r}"
            )

    preview = " ".join(text_blocks[0].split())[:240]
    return citations, preview


async def _verify_mcp(
    *,
    query: str,
    collection: str,
    top_k: int,
    config_path: Path,
    expected_source: str | None,
) -> VerificationEvidence:
    """Run one official ClientSession against the production stdio server."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env[SETTINGS_PATH_ENV] = str(config_path)
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp_server.server"],
        cwd=_REPO_ROOT,
        env=env,
    )

    started = time.perf_counter()
    async with stdio_client(server, errlog=sys.stderr) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools_response = await session.list_tools()
            tools = sorted(tool.name for tool in tools_response.tools)
            missing_tools = REQUIRED_TOOLS.difference(tools)
            if missing_tools:
                raise ValueError(f"MCP server is missing tools: {sorted(missing_tools)!r}")

            collections_response = await session.call_tool(
                "list_collections",
                {"include_stats": True},
            )
            collection_text = " ".join(
                block.text
                for block in collections_response.content
                if isinstance(block, types.TextContent)
            )
            if collections_response.is_error or collection not in collection_text:
                raise ValueError(f"Collection {collection!r} was not listed by the MCP server")

            query_response = await session.call_tool(
                "query_knowledge_hub",
                {"query": query, "top_k": top_k, "collection": collection},
            )
            citations, preview = _validate_query_response(query_response, expected_source)

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return VerificationEvidence(
        tools=tools,
        citation_count=len(citations),
        first_source=str(citations[0].get("source", "")),
        elapsed_ms=elapsed_ms,
        response_preview=preview,
    )


def _latest_query_trace(
    trace_path: Path,
    *,
    query: str,
    collection: str,
) -> dict[str, Any] | None:
    """Return the newest matching query trace without loading the whole log."""
    if not trace_path.exists():
        return None

    with trace_path.open("r", encoding="utf-8") as handle:
        recent_lines = deque(handle, maxlen=200)

    for line in reversed(recent_lines):
        try:
            raw_trace = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw_trace, dict):
            continue
        trace = cast(dict[str, Any], raw_trace)
        metadata = trace.get("metadata", {})
        if (
            trace.get("trace_type") == "query"
            and metadata.get("query") == query[:200]
            and metadata.get("collection") == collection
        ):
            return trace
    return None


def main() -> int:
    """Run the local MCP verification and print concise acceptance evidence."""
    _configure_windows_console()
    args = parse_args()
    config_path = args.config.resolve()
    if not config_path.is_file():
        print(f"[FAIL] Configuration file not found: {config_path}")
        return 2
    if not 1 <= args.top_k <= 20:
        print("[FAIL] --top-k must be between 1 and 20")
        return 2
    if args.timeout_seconds <= 0:
        print("[FAIL] --timeout-seconds must be positive")
        return 2

    try:
        settings = load_settings(config_path)
        trace_path = resolve_path(settings.observability.trace_file)
        evidence = asyncio.run(
            asyncio.wait_for(
                _verify_mcp(
                    query=args.query,
                    collection=args.collection,
                    top_k=args.top_k,
                    config_path=config_path,
                    expected_source=args.expect_source,
                ),
                timeout=args.timeout_seconds,
            )
        )
    except Exception as exc:
        print(f"[FAIL] Local MVP verification failed: {exc}")
        return 1

    trace = _latest_query_trace(
        trace_path,
        query=args.query,
        collection=args.collection,
    )
    print("[OK] Official MCP ClientSession verification passed")
    print(f"tools={','.join(evidence.tools)}")
    print(f"collection={args.collection}")
    print(f"citation_count={evidence.citation_count}")
    print(f"first_source={evidence.first_source}")
    print(f"mcp_elapsed_ms={evidence.elapsed_ms:.2f}")
    print(f"response_preview={evidence.response_preview}")
    if trace:
        print(f"trace_id={trace.get('trace_id', '')}")
        print(f"trace_elapsed_ms={trace.get('total_elapsed_ms', '')}")
    else:
        print(f"[WARN] Matching query trace not found in {trace_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
