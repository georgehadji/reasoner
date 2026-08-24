from reasoner.hypergate.sub_agents.complexity_estimator import ComplexityEstimatorSubAgent
from reasoner.hypergate.sub_agents.direct_detector import DirectDetectorSubAgent

# On-demand only (image generation) — deliberately NOT in the Phase-1 gather.
from reasoner.hypergate.sub_agents.image_model_selector import ImageModelSelector
from reasoner.hypergate.sub_agents.language_detector import LanguageDetectorSubAgent
from reasoner.hypergate.sub_agents.method_classifier import MethodClassifierSubAgent
from reasoner.hypergate.sub_agents.tie_breaker import TieBreakerSubAgent
from reasoner.hypergate.sub_agents.web_detector import WebSearchDetectorSubAgent

__all__ = [
    "LanguageDetectorSubAgent",
    "ComplexityEstimatorSubAgent",
    "DirectDetectorSubAgent",
    "WebSearchDetectorSubAgent",
    "MethodClassifierSubAgent",
    "TieBreakerSubAgent",
    "ImageModelSelector",
]
