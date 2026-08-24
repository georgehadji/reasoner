# Context: Watermark

## Directory: `src/reasoner/infrastructure/watermark`

## Description
Concrete utilities for watermarking generated texts, images, or documents.

## Files
- **`__init__.py`**: Python package initialization module.
- **`data_url.py`**: Data-URL <-> bytes codec.
- **`rewriter.py`**: Curated, ordered general-purpose prose models spanning all three blocs.
- **`scrubber.py`**: Default ImageMarkScrubberPort implementation: detect -> strip -> re-inspect.

## Subfolders
- **`image`**: Watermarking implementations for applying invisible pixel tags or visual overlays on images.
- **`pixel`**: Low-level pixel-level manipulation routines for cryptographic image watermarking.
