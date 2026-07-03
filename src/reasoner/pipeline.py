import warnings

# backward-compat shim — real module: reasoner.application.pipeline
warnings.warn(
    "reasoner.pipeline is a backward-compat shim; import from reasoner.application.pipeline directly.",
    DeprecationWarning, stacklevel=2,
)
from reasoner.application.pipeline import *  # noqa: F401, F403
