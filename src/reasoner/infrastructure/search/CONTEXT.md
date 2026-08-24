# Context: Search

## Directory: `src/reasoner/infrastructure/search`

## Description
Search API clients (Perplexity, Tavily, Google, Bing) executing context-vetting queries.

## Files
- **`brave_adapter.py`**: Brave caps `count` per endpoint. Requesting more is a 422, so clamp.
- **`discovery.py`**: ── Lazy build_provider accessor (avoids circular import at module load) ──
- **`tavily_adapter.py`**: Code or resource asset facilitating system functionality.

## Subfolders
*No subfolders in this directory.*
