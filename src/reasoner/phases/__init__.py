from reasoner.phases._shared import (
    detect_language,
    get_language_instruction,
    _followup_context,
    _wrap_user_input,
    _wrap_external_content,
    PipelineState,
    PerspectiveType,
    JSON_ONLY_FOOTER,
    TRUNCATION,
    DEFAULT_SEARCH_RESULTS,
)
from reasoner.phases._universal import *
from reasoner.phases.multi_perspective import *
from reasoner.phases.debate import *
from reasoner.phases.jury import *
from reasoner.phases.research import *
from reasoner.phases._prism import *
from reasoner.phases.scientific import *
from reasoner.phases.socratic import *
from reasoner.phases.pre_mortem import *
from reasoner.phases.bayesian import *
from reasoner.phases.dialectical import *
from reasoner.phases.analogical import *
from reasoner.phases.delphi import *
from reasoner.phases.cove import *
from reasoner.phases.sot import *
from reasoner.phases.tot import *
from reasoner.phases.pot import *
from reasoner.phases.self_discover import *
from reasoner.phases.writing import *
from reasoner.phases.article import *
from reasoner.phases.coding import *
from reasoner.phases.brainstorming import (  # noqa: F401
    VS_GENERATION_SYSTEM,
    VS_CLUSTER_SYSTEM,
    VS_DEVELOP_SYSTEM,
    VS_SYNTHESIS_SYSTEM,
    vs_generation_prompt,
    vs_cluster_prompt,
    vs_develop_prompt,
    vs_synthesis_prompt,
)
