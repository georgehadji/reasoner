import warnings

# backward-compat shim — real module: reasoner.infrastructure.circuit_breaker
warnings.warn(
    "reasoner.circuit_breaker is a backward-compat shim; import from reasoner.infrastructure.circuit_breaker directly.",
    DeprecationWarning, stacklevel=2,
)
from reasoner.infrastructure.circuit_breaker import *  # noqa: F401, F403
