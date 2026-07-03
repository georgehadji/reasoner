import warnings

# backward-compat shim — real module: reasoner.core.logging_utils
warnings.warn(
    "reasoner.logging_utils is a backward-compat shim; import from reasoner.core.logging_utils directly.",
    DeprecationWarning, stacklevel=2,
)
from reasoner.core.logging_utils import *  # noqa: F401, F403
