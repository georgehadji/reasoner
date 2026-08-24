# backward-compat shim — real module: reasoner.infrastructure.uploader
from reasoner.infrastructure.uploader import *  # noqa: F401, F403
from reasoner.infrastructure.uploader import (  # noqa: F401  (private re-export)  # noqa: F401  (private re-export)
    _extract_pdf,
    _get_file_extension,
    _ocr_image,
    _ocr_scanned_pdf,
)
