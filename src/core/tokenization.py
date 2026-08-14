"""Shared deterministic tokenization for BM25 indexing and querying."""

from __future__ import annotations

import re

import jieba

_TOKEN_PATTERN = re.compile(
    r"\d+(?:\.\d+)+|[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*|[\u4e00-\u9fff]+"
)
_CHINESE_PATTERN = re.compile(r"^[\u4e00-\u9fff]+$")


def tokenize_for_bm25(text: str) -> list[str]:
    """Tokenize mixed Chinese/English text without breaking ASCII compounds.

    Chinese spans are segmented with jieba. English identifiers, hyphenated
    terms, underscored terms, and decimal version numbers remain intact so the
    index-side and query-side BM25 vocabulary stays consistent.
    """
    tokens: list[str] = []
    for match in _TOKEN_PATTERN.finditer(text):
        value = match.group(0)
        if _CHINESE_PATTERN.fullmatch(value):
            tokens.extend(token.strip() for token in jieba.lcut(value) if token.strip())
        else:
            tokens.append(value)
    return tokens
