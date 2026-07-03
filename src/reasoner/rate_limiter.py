import warnings

# backward-compat shim — real module: reasoner.infrastructure.rate_limiter
warnings.warn(
    "reasoner.rate_limiter is a backward-compat shim; import from reasoner.infrastructure.rate_limiter directly.",
    DeprecationWarning, stacklevel=2,
)
from reasoner.infrastructure.rate_limiter import *  # noqa: F401, F403
