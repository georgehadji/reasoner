"""
Backward-compat shim — serializers moved to application/services/serializers.py.
New code should import from reasoner.application.services.serializers directly.
"""
from reasoner.application.services.serializers import (  # noqa: F401, F811
    _ser_0, _ser_1, _ser_1_5, _ser_2, _ser_3, _ser_4, _ser_5,
    _ser_synthesis, _ser_writing_premortem, _ser_writing_critic,
    _is_orchestrated, _is_debate, _is_scientific, _is_socratic,
)
from reasoner.api.sse_utils import _event  # noqa: F401
