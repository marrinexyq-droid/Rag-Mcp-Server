"""Deterministic stdio MCP server used by wire-level protocol tests."""

from __future__ import annotations

import asyncio
import sys

import mcp.server.stdio

from src.mcp_server.protocol_handler import ProtocolHandler, create_mcp_server


async def echo(value: str, delay_ms: int = 0) -> str:
    """Return a value after an optional delay to exercise response routing."""
    await asyncio.sleep(delay_ms / 1000)
    return value


async def run() -> int:
    """Run the in-memory protocol adapter over real stdio transport."""
    protocol_handler = ProtocolHandler(
        server_name="mcp-protocol-test-server",
        server_version="1.0.0",
    )
    protocol_handler.register_tool(
        name="echo",
        description="Return the supplied value.",
        input_schema={
            "type": "object",
            "properties": {
                "value": {"type": "string"},
                "delay_ms": {"type": "integer", "minimum": 0},
            },
            "required": ["value"],
        },
        handler=echo,
    )
    server = create_mcp_server(
        "mcp-protocol-test-server",
        "1.0.0",
        protocol_handler=protocol_handler,
        register_tools=False,
    )

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
