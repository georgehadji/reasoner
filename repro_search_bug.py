
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from src.reasoner.core.search import DiscoveryClient


class TestSearchFallbackBug(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_bug(self):
        # 1. Setup DiscoveryClient
        client = DiscoveryClient(base_url="http://localhost:8888")

        # 2. Mock the httpx response
        mock_response = MagicMock()
        # raw search results that should ALL be filtered out
        raw_results = [
            {
                "title": "A Rejected PDF",
                "url": "https://example.com/file.pdf",
                "content": "This is a PDF file content that should be filtered.",
                "engine": "google"
            }
        ]
        mock_response.json.return_value = {"results": raw_results}
        mock_response.raise_for_status = MagicMock()

        client.client.get = AsyncMock(return_value=mock_response)

        # 3. Execute _fetch_page
        # _fetch_page(self, query, pageno, num_results, categories, source_type)
        refined, raw_len = await client._fetch_page("test query", 1, 10, None, None)

        # 4. Verify behavior
        # EXPECTED (fixed): refined should be [] because the only result was a PDF.
        # ACTUAL (buggy): refined is raw_results[:10] because of the fallback.

        print(f"Refined results length: {len(refined)}")
        if len(refined) > 0:
            print("BUG REPRODUCED: Fallback occurred despite all results being filtered.")
            for r in refined:
                print(f"  Result URL: {r.get('url')}")
        else:
            print("BUG NOT REPRODUCED: No results returned (correct behavior).")

if __name__ == "__main__":
    asyncio.run(TestSearchFallbackBug().test_fallback_bug())
