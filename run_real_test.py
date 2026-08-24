import os
import subprocess
import sys

from reasoner.core.settings import settings

# Load API keys into environment
env = os.environ.copy()
env["PYTHONPATH"] = "src"
if settings.OPENROUTER_API_KEY:
    env["OPENROUTER_API_KEY"] = settings.OPENROUTER_API_KEY
if settings.OPENAI_API_KEY:
    env["OPENAI_API_KEY"] = settings.OPENAI_API_KEY
if settings.ANTHROPIC_API_KEY:
    env["ANTHROPIC_API_KEY"] = settings.ANTHROPIC_API_KEY

# Run pytest
cmd = ["pytest", "tests/test_e2e_real_api.py::TestRealAPIRunStream::test_api_run_stream_completes[multi_perspective-multi-perspective-budget]", "-v", "-s"]
print(f"Running: {' '.join(cmd)}")
result = subprocess.run(cmd, env=env)
sys.exit(result.returncode)
