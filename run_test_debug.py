import asyncio

# Add src to path
import os
import sys
import traceback
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from reasoner.main import main


async def test_cli_cleanup_on_exit():
    args = MagicMock()
    args.list_presets = False
    args.list_models = False
    args.resume = ""
    args.problem = "test"
    args.force_pipeline = True
    args.output = ""
    args.save_state = ""

    with patch("reasoner.main.build_router"), \
         patch("reasoner.main.ReasonerPipeline") as mock_pipeline, \
         patch("reasoner.scraper.close_scraper_client", new_callable=AsyncMock) as mock_close_scraper, \
         patch("reasoner.llm.OpenAICompatibleProvider.close_shared_pool", new_callable=AsyncMock) as mock_close_llm:

        mock_pipeline.return_value.run = AsyncMock(return_value=MagicMock())

        try:
            await main(args)
            mock_close_scraper.assert_called_once()
            mock_close_llm.assert_called_once()
            with open("test_output.log", "w") as f:
                f.write("SUCCESS\n")
        except Exception:
            with open("test_output.log", "w") as f:
                f.write(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(test_cli_cleanup_on_exit())
