
import pytest
from unittest.mock import AsyncMock, MagicMock
from reasoner.core.search import DiscoveryClient

@pytest.mark.asyncio
async def test_search_no_fallback_to_junk():
    """
    BUG-FALLBACK: Verify that search does NOT fall back to unfiltered results
    when all results fail the quality gate.
    """
    client = DiscoveryClient(base_url="http://localhost:8888")
    
    # Mock response with only a PDF (should be filtered)
    mock_response = MagicMock()
    raw_results = [
        {
            "title": "A Rejected PDF",
            "url": "https://example.com/file.pdf",
            "content": "Junk content",
            "engine": "google"
        }
    ]
    mock_response.json.return_value = {"results": raw_results}
    mock_response.raise_for_status = MagicMock()
    client.client.get = AsyncMock(return_value=mock_response)
    
    # Test _fetch_page directly
    refined, raw_len = await client._fetch_page("test", 1, 10, None, None)
    
    assert len(refined) == 0, "Should NOT have fallen back to returning the PDF"
    assert raw_len == 1

@pytest.mark.asyncio
async def test_search_partial_filtering():
    """
    Verify that valid results ARE returned.
    """
    client = DiscoveryClient(base_url="http://localhost:8888")
    
    mock_response = MagicMock()
    # Content must be > 50 chars (_MIN_SNIPPET_LEN)
    valid_content = "This is a valid article content that is long enough to pass the snippet length filter check. " * 3
    raw_results = [
        {
            "title": "Valid Article",
            "url": "https://example.com/article",
            "content": valid_content,
            "engine": "google"
        },
        {
            "title": "Rejected PDF",
            "url": "https://example.com/file.pdf",
            "content": "Junk",
            "engine": "google"
        }
    ]
    mock_response.json.return_value = {"results": raw_results}
    mock_response.raise_for_status = MagicMock()
    client.client.get = AsyncMock(return_value=mock_response)
    
    refined, raw_len = await client._fetch_page("test", 1, 10, None, None)
    
    assert len(refined) == 1
    assert refined[0]["url"] == "https://example.com/article"
