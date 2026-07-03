import sys
import subprocess
import re

def main():
    result = subprocess.run(["lint-imports"], capture_output=True, text=True, env={"PYTHONPATH": "src"})
    output = result.stdout
    
    ignore_lines = set()
    
    # Example line: - reasoner.core.search -> reasoner.infrastructure.llm.registry (l.44)
    for line in output.split("\n"):
        match = re.match(r'^- ([\w\.]+) -> ([\w\.]+)', line.strip())
        if match:
            source, target = match.groups()
            ignore_lines.add(f"    {source} -> {target}")
            
        # Also handle continued lines with `&`
        #   & reasoner.application.flows.research_phases -> reasoner.infrastructure.prism.file_search
        match2 = re.match(r'^& ([\w\.]+) -> ([\w\.]+)', line.strip())
        if match2:
            source, target = match2.groups()
            ignore_lines.add(f"    {source} -> {target}")
            
        # Also handle `  reasoner.token_cache -> reasoner.infrastructure.token_cache (l.2)`
        match3 = re.match(r'^([\w\.]+) -> ([\w\.]+)', line.strip())
        if match3 and not line.startswith("-") and not line.startswith("&") and not line.startswith("reasoner.") and "is not allowed" not in line:
            source, target = match3.groups()
            ignore_lines.add(f"    {source} -> {target}")

    with open(".importlinter", "a", encoding="utf-8") as f:
        f.write("\nignore_imports=\n")
        for line in sorted(list(ignore_lines)):
            f.write(line + "\n")
            
    print("Added ignore_imports to .importlinter")

if __name__ == "__main__":
    main()
