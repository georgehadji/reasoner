import sys
from pathlib import Path
import re

def main():
    repo_root = Path(__file__).parent.parent.resolve()
    file_path = repo_root / "src" / "reasoner" / "domain" / "pipeline_state.py"
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find the start of to_dict
    start_match = re.search(r'    def to_dict\(self\) -> dict\[str, Any\]:', content)
    if not start_match:
        print("Could not find to_dict()")
        sys.exit(1)
        
    start_idx = start_match.start()
    
    # Extract everything from to_dict to the end
    extracted_methods = content[start_idx:]
    
    # The new content for pipeline_state.py
    new_content = content[:start_idx]
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)
        
    print("Successfully removed methods from pipeline_state.py")
    
    # Add to pipeline_service.py
    target_path = repo_root / "src" / "reasoner" / "application" / "services" / "pipeline_service.py"
    with open(target_path, "r", encoding="utf-8") as f:
        service_content = f.read()

    if "class PipelineSerializationService:" not in service_content:
        with open(target_path, "a", encoding="utf-8") as f:
            f.write("\n\n")
            f.write("import json\nfrom datetime import datetime, timezone\nfrom enum import Enum\nfrom collections import deque\nfrom dataclasses import asdict, fields as dc_fields\nfrom pathlib import Path\n")
            f.write("from reasoner.domain.core_types import (\n    SolutionCandidate, CritiqueScore, ReviewHypothesis, StressTestResult,\n    MetaCognitiveAudit, GenerationCandidate, CriticScore,\n    VerificationResult, MetaEvaluation, Decomposition, FinalSolution, SubProblem, Assumption\n)\n")
            f.write("from reasoner.domain.models import TaskType, ClaimLabel, PerspectiveType, PerspectiveRegistry, ScenarioType\n")
            f.write("\nclass PipelineSerializationService:\n")
            
            # Adjust indentation (remove 4 spaces)
            lines = extracted_methods.split("\n")
            methods_adjusted = "\n".join([line[4:] if line.startswith("    ") else line for line in lines])
            
            # Convert to static methods
            methods_adjusted = methods_adjusted.replace("def to_dict(self) -> dict[str, Any]:", "@staticmethod\n    def to_dict(state: PipelineState) -> dict[str, Any]:")
            methods_adjusted = methods_adjusted.replace("asdict(self)", "asdict(state)")
            methods_adjusted = methods_adjusted.replace("def save(self, path: str | Path) -> None:", "@staticmethod\n    def save(state: PipelineState, path: str | Path) -> None:")
            methods_adjusted = methods_adjusted.replace("self.to_dict()", "PipelineSerializationService.to_dict(state)")
            
            # Re-indent the entire block to be inside the class
            methods_adjusted = "\n".join(["    " + line if line else line for line in methods_adjusted.split("\n")])

            methods_adjusted = methods_adjusted.replace("cls._from_dict(data)", "PipelineSerializationService._from_dict(data)")
            methods_adjusted = methods_adjusted.replace("cls(**data)", "PipelineState(**data)")
            methods_adjusted = methods_adjusted.replace("    @classmethod\n    def load(cls, path: str | Path) -> \"PipelineState\":", "    @staticmethod\n    def load(path: str | Path) -> \"PipelineState\":")
            methods_adjusted = methods_adjusted.replace("    @classmethod\n    def _from_dict(cls, data: dict[str, Any]) -> \"PipelineState\":", "    @staticmethod\n    def _from_dict(data: dict[str, Any]) -> \"PipelineState\":")

            f.write(methods_adjusted)
            
        print("Successfully added to pipeline_service.py")

if __name__ == "__main__":
    main()
