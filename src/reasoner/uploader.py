# backward-compat shim — real module: reasoner.infrastructure.uploader
from reasoner.infrastructure.uploader import *  # noqa: F401, F403
from reasoner.infrastructure.uploader import _extract_pdf, _get_file_extension  # noqa: F401  (private re-export)
from reasoner.infrastructure.uploader import _ocr_scanned_pdf, _ocr_image  # noqa: F401  (private re-export)
from reasoner.infrastructure.uploader import _get_upload_dir, get_upload_dir  # noqa: F401  (lazy path accessor)
