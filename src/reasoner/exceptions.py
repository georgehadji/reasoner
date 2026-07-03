import warnings

# backward-compat shim — real module: reasoner.core.exceptions
warnings.warn(
    "reasoner.exceptions is a backward-compat shim; import from reasoner.core.exceptions directly.",
    DeprecationWarning, stacklevel=2,
)
from reasoner.core.exceptions import *  # noqa: F401, F403
