# backward-compat shim — real module: reasoner.infrastructure.verbalized_sampling
from reasoner.infrastructure.verbalized_sampling import *  # noqa: F401, F403
# `import *` above skips underscore-prefixed names, so re-export the private
# helpers importers still rely on. _compute_entropy was renamed to
# compute_verbalized_entropy; keep the old private name as an alias.
from reasoner.infrastructure.verbalized_sampling import (  # noqa: F401
    _strip_markdown_fences,
    _extract_json_block,
    compute_verbalized_entropy as _compute_entropy,
)
