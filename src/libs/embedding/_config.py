"""Helpers for reading optional embedding settings safely."""

from __future__ import annotations

from typing import Any


def optional_string(config: Any, name: str) -> str | None:
    """Return a non-empty string setting, ignoring dynamic mock-like values."""
    value = getattr(config, name, None)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def optional_integer(config: Any, name: str) -> int | None:
    """Return an integer setting while rejecting booleans and other objects."""
    value = getattr(config, name, None)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None
