"""Pure helpers for splitting a batch input without guessing fields."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    ordinal: int
    title: str
    body: str
    needs_review: bool


def split_segments(text: str) -> list[Segment]:
    """Split on standalone --- lines; retain content and flag weak segments."""
    chunks = re.split(r"(?m)^\s*---\s*$", text.strip()) if text.strip() else []
    segments = []
    for ordinal, chunk in enumerate(chunks, 1):
        lines = [line.rstrip() for line in chunk.splitlines()]
        meaningful = [line.strip() for line in lines if line.strip()]
        if not meaningful:
            continue
        title = meaningful[0][:200]
        body = "\n".join(lines).strip()
        segments.append(Segment(ordinal, title, body, len(meaningful) < 2))
    return segments
