"""Real project MCP server with a deterministic test embedding provider."""

from __future__ import annotations

import asyncio
import sys
from typing import Any, cast

from src.libs.embedding.base_embedding import BaseEmbedding
from src.libs.embedding.embedding_factory import EmbeddingFactory
from src.mcp_server.server import run_stdio_server_async


class DeterministicTestEmbedding(BaseEmbedding):
    """Return stable local vectors without network or provider credentials."""

    def __init__(self, settings: Any, **_kwargs: Any) -> None:
        self.dimension: int = int(settings.embedding.dimensions)

    def embed(
        self,
        texts: list[str],
        trace: Any | None = None,
        **_kwargs: Any,
    ) -> list[list[float]]:
        del trace
        self.validate_texts(texts)
        vector = [1.0] + [0.0] * (self.dimension - 1)
        return [list(vector) for _ in texts]

    def get_dimension(self) -> int:
        return self.dimension


def main() -> int:
    """Register the local provider, then run the production stdio server."""
    EmbeddingFactory.register_provider("deterministic-test", DeterministicTestEmbedding)
    return cast(int, asyncio.run(run_stdio_server_async()))


if __name__ == "__main__":
    sys.exit(main())
