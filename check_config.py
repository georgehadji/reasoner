
from reasoner.core.settings import settings

vars_to_check = [
    "SEARXNG_URL",
    "OLLAMA_BASE_URL",
    "SUPABASE_URL",
    "DATABASE_URL",
    "RATE_LIMITER_MODE",
    "CIRCUIT_BREAKER_MODE"
]

print("Loaded Config Vars:")
for var in vars_to_check:
    val = getattr(settings, var, "NOT SET")
    print(f"{var}: {val}")
