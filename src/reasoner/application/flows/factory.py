"""Factory for creating workflow strategies."""

from __future__ import annotations

from typing import Dict, Type
from reasoner.application.flows.base import WorkflowStrategy
from reasoner.application.flows.multi_perspective import MultiPerspectiveFlow
from reasoner.application.flows.debate import DebateFlow
from reasoner.application.flows.research import ResearchFlow
from reasoner.application.flows.writing import WritingFlow
from reasoner.application.flows.coding import CodingFlow
from reasoner.application.flows.brainstorming import BrainstormingFlow
from reasoner.application.flows.jury import JuryFlow
from reasoner.application.flows.delphi import DelphiFlow
from reasoner.application.flows.dialectical import (
    ScientificFlow,
    SocraticFlow,
    PreMortemFlow,
    BayesianFlow,
    DialecticalFlow,
    AnalogicalFlow
)
from reasoner.application.flows.cognitive import (
    CoVEFlow,
    SoTFlow,
    ToTFlow,
    PoTFlow,
    SelfDiscoverFlow
)
from reasoner.application.flows.iterative_critique import IterativeCritiqueFlow
from reasoner.application.flows.article import ArticleFlow

class WorkflowFactory:
    """Registry for workflow strategies."""
    
    def __init__(self) -> None:
        self._strategies: Dict[str, Type[WorkflowStrategy]] = {
            "multi_perspective": MultiPerspectiveFlow,
            "debate": DebateFlow,
            "research": ResearchFlow,
            "writing": WritingFlow,
            "coding": CodingFlow,
            "brainstorming": BrainstormingFlow,
            "jury": JuryFlow,
            "delphi": DelphiFlow,
            "scientific": ScientificFlow,
            "socratic": SocraticFlow,
            "pre_mortem": PreMortemFlow,
            "bayesian": BayesianFlow,
            "dialectical": DialecticalFlow,
            "analogical": AnalogicalFlow,
            "cove": CoVEFlow,
            "sot": SoTFlow,
            "tot": ToTFlow,
            "pot": PoTFlow,
            "self_discover": SelfDiscoverFlow,
            "iterative_critique": IterativeCritiqueFlow,
            "article": ArticleFlow,
        }
        
    def get_strategy(self, method: str) -> WorkflowStrategy:
        """Get an instance of the requested strategy."""
        norm_method = method.replace("-", "_")
        strategy_cls = self._strategies.get(norm_method, MultiPerspectiveFlow)
        return strategy_cls()
        
    def is_migrated(self, method: str) -> bool:
        """Check if a method has been migrated to the strategy pattern."""
        norm_method = method.replace("-", "_")
        return norm_method in self._strategies
