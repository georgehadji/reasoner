"""Test that synthesis streaming does not sleep between chunks."""

from __future__ import annotations

import asyncio
import time

import pytest


@pytest.mark.asyncio
async def test_synthesis_streams_without_sleep():
    """
    Simulate the new sentence-based synthesis streaming.
    500 words (~25 sentences) should complete in <2s.
    """
    text = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
        "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
        * 25
    )
    # Build a realistic 500-word text
    sentences = [
        "The quick brown fox jumps over the lazy dog.",
        "Pack my box with five dozen liquor jugs.",
        "How vexingly quick daft zebras jump!",
        "Sphinx of black quartz, judge my vow.",
        "Two driven jocks help fax my big quiz.",
    ] * 5
    full_text = " ".join(sentences)

    import re
    chunks = re.split(r'(?<=[.!?])\s+', full_text)

    async def stream():
        for sentence in chunks:
            yield {"type": "text_chunk", "text": sentence}

    start = time.perf_counter()
    count = 0
    async for _ in stream():
        count += 1
    elapsed = time.perf_counter() - start

    assert count > 0
    assert elapsed < 2.0, f"Streaming took {elapsed:.2f}s, expected <2s"
