import os

from reasoner.core.settings import settings

keys = [
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "MISTRAL_API_KEY",
    "PERPLEXITY_API_KEY",
    "NVIDIA_API_KEY",
    "SEARXNG_SECRET_KEY"
]

print("Loaded API Keys (Redacted):")
for key in keys:
    val = getattr(settings, key, None)
    if val:
        print(f"{key}: {val[:5]}...{val[-5:]} (Length: {len(val)})")
    else:
        # Check direct env just in case
        env_val = os.getenv(key)
        if env_val:
            print(f"{key} (from os.getenv): {env_val[:5]}...{env_val[-5:]} (Length: {len(env_val)})")
        else:
            print(f"{key}: NOT SET")
