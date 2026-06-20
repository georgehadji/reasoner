# Reasoner - Setup Mindmap

```
                                    ┌─────────────────────────────────────┐
                                    │         REASONER SETUP              │
                                    │    AI Reasoning Platform v2.0       │
                                    └─────────────────┬───────────────────┘
                                                      │
            ┌─────────────────────────────────────────┼─────────────────────────────────────────┐
            │                                         │                                         │
            ▼                                         ▼                                         ▼
┌───────────────────────┐                 ┌───────────────────────┐                 ┌───────────────────────┐
│   1. PREREQUISITES    │                 │   2. INSTALLATION     │                 │   3. CONFIGURATION    │
└───────────┬───────────┘                 └───────────┬───────────┘                 └───────────┬───────────┘
            │                                         │                                         │
            ▼                                         ▼                                         ▼
┌───────────────────────┐                 ┌───────────────────────┐                 ┌───────────────────────┐
│ • Python 3.10+        │                 │ pip install -r        │                 │ Create .env file      │
│ • Git (optional)      │                 │   requirements.txt    │                 │ with API keys         │
│ • API Keys (1+)       │                 │                       │                 │                       │
│                       │                 │ Key packages:         │                 │ Required:             │
│ Windows/Mac/Linux     │                 │ • fastapi             │                 │ • ANTHROPIC_API_KEY   │
│ supported             │                 │ • uvicorn             │                 │ • OPENAI_API_KEY      │
│                       │                 │ • anthropic           │                 │ • GOOGLE_API_KEY      │
│                       │                 │ • openai              │                 │                       │
│                       │                 │ • httpx               │                 │ Optional:             │
│                       │                 │ • pydantic            │                 │ • XAI_API_KEY         │
│                       │                 │ • asyncpg             │                 │ • PERPLEXITY_API_KEY  │
│                       │                 │ • aiosqlite           │                 │ • MISTRAL_API_KEY     │
└───────────────────────┘                 └───────────────────────┘                 │ • DEEPSEEK_API_KEY    │
                                                                                    │ • DASHSCOPE_API_KEY   │
                                                                                    │ • MOONSHOT_API_KEY    │
                                                                                    │ • ZHIPUAI_API_KEY     │
                                                                                    │ • MINIMAX_API_KEY     │
                                                                                    └───────────────────────┘
                                                      │
            ┌─────────────────────────────────────────┼─────────────────────────────────────────┐
            │                                         │                                         │
            ▼                                         ▼                                         ▼
┌───────────────────────┐                 ┌───────────────────────┐                 ┌───────────────────────┐
│   4. VERIFICATION     │                 │   5. START SERVER     │                 │   6. ACCESS           │
└───────────┬───────────┘                 └───────────┬───────────┘                 └───────────┬───────────┘
            │                                         │                                         │
            ▼                                         ▼                                         ▼
┌───────────────────────┐                 ┌───────────────────────┐                 ┌───────────────────────┐
│ python server_check.py│                 │ Option A:             │                 │ Web UI:               │
│                       │                 │   python start_server │                 │ http://localhost:8000 │
│ Checks:               │                 │                       │                 │                       │
│ ✓ Domain Events       │                 │ Option B:             │                 │ API Docs:             │
│ ✓ Persistence         │                 │   python -m uvicorn   │                 │ http://localhost:8000 │
│ ✓ Handlers            │                 │   asgi:app --port 8000 │                 │ /docs                 │
│ ✓ WebSocket           │                 │                       │                 │                       │
│ ✓ API App             │                 │ Option C:             │                 │ WebSocket:            │
│ ✓ LLM Providers       │                 │   run.bat (Windows)   │                 │ ws://localhost:8000   │
│ ✓ Widgets             │                 │                       │                 │ /ws                   │
│                       │                 │ Option D:             │                 │                       │
│ All checks must pass  │                 │   start_server.py     │                 │ ReDoc:                │
│ before starting       │                 │                       │                 │ http://localhost:8000 │
└───────────────────────┘                 └───────────────────────┘                 │ /redoc                │
                                                                                    └───────────────────────┘
                                                      │
            ┌─────────────────────────────────────────┼─────────────────────────────────────────┐
            │                                         │                                         │
            ▼                                         ▼                                         ▼
┌───────────────────────┐                 ┌───────────────────────┐                 ┌───────────────────────┐
│   7. CLI USAGE        │                 │   8. API USAGE        │                 │   9. TROUBLESHOOTING  │
└───────────┬───────────┘                 └───────────┬───────────┘                 └───────────┬───────────┘
            │                                         │                                         │
            ▼                                         ▼                                         ▼
┌───────────────────────┐                 ┌───────────────────────┐                 ┌───────────────────────┐
│ List presets:         │                 │ Run pipeline:         │                 │ Import errors:        │
│ python main.py        │                 │ POST /api/run         │                 │ pip install -r        │
│ --list-presets        │                 │                       │                 │ requirements.txt      │
│                       │                 │ Get presets:          │                 │                       │
│ List models:          │                 │ GET /api/presets      │                 │ API key errors:       │
│ python main.py        │                 │                       │                 │ Check .env file       │
│ --list-models         │                 │ Get models:           │                 │                       │
│                       │                 │ GET /api/models       │                 │ Port in use:          │
│ Run pipeline:         │                 │                       │                 │ Change port:          │
│ python main.py        │                 │ WebSocket:            │                 │ --port 8001           │
│ --problem "Question"  │                 │ WS /ws                │                 │                       │
│ --preset max-quality  │                 │                       │                 │ Module not found:     │
│                       │                 │ History:              │                 │ python server_check.py│
│ With options:         │                 │ GET /api/history      │                 │                       │
│ --top-k 3             │                 │                       │                 │ Startup errors:       │
│ --sequential          │                 │ Widgets:              │                 │ Check logs above      │
│ --source-type academic│                 │ GET /api/weather      │                 │                       │
│ --domain github.com   │                 │ GET /api/stocks       │                 │ Database errors:      │
└───────────────────────┘                 │ GET /api/calculate    │                 │ Check permissions     │
                                          └───────────────────────┘                 └───────────────────────┘
```

---

## Quick Start Commands

```bash
# 1. Navigate to project
cd E:\Documents\Vibe-Coding\Reasoner

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create .env file with API keys
# (copy from .env.example if available)

# 4. Verify setup
python server_check.py

# 5. Start server
python -m uvicorn asgi:app --host 0.0.0.0 --port 8000 --reload

# 6. Open browser
# http://localhost:8000
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              REASONER ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        PRESENTATION LAYER                            │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │   │
│  │  │   Web UI    │  │    CLI      │  │  WebSocket  │  │  REST API  │ │   │
│  │  │ (vanilla JS)│  │ (main.py)   │  │  (real-time)│  │ (FastAPI)  │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                       APPLICATION LAYER (CQRS)                       │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌──────────────────────────┐ │   │
│  │  │   Commands    │  │    Queries    │  │      Event Bus           │ │   │
│  │  │ (Write Ops)   │  │  (Read Ops)   │  │  (Pub-Sub)               │ │   │
│  │  └───────────────┘  └───────────────┘  └──────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                          DOMAIN LAYER                                │   │
│  │  ┌───────────────────────────────────────────────────────────────┐  │   │
│  │  │                    7 Reasoning Methods                         │  │   │
│  │  │  Multi-Perspective │ Debate │ Jury │ Research │ Socratic │... │  │   │
│  │  └───────────────────────────────────────────────────────────────┘  │   │
│  │  ┌───────────────────────────────────────────────────────────────┐  │   │
│  │  │              Event-Sourced Aggregates (28 Events)              │  │   │
│  │  └───────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                       INFRASTRUCTURE LAYER                           │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │   │
│  │  │ LLM Adapters│  │   Widgets   │  │ Persistence │  │  WebSocket │ │   │
│  │  │  (11 prov.) │  │  (6 types)  │  │ SQLite/PG   │  │  Manager   │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
Reasoner/
├── api.py                    # FastAPI server (main entry)
├── main.py                   # CLI entry point
├── pipeline.py               # Legacy pipeline orchestrator
├── llm.py                    # LLM provider registry
├── models.py                 # Data models
├── phases.py                 # Phase prompts
├── presets.py                # Preset configurations
├── parsing.py                # JSON parsing utilities
├── requirements.txt          # Dependencies
├── .env                      # API keys (create from template)
│
├── core/                     # Domain Layer
│   ├── events/
│   │   └── domain_events.py  # 28 event types
│   └── aggregates/
│       └── pipeline.py       # Event-sourced aggregate
│
├── application/              # Application Layer (CQRS)
│   ├── commands/             # Write operations
│   ├── queries/              # Read operations
│   ├── handlers/             # Command/query handlers
│   └── event_bus/            # Pub-sub event bus
│
├── infrastructure/           # Infrastructure Layer
│   ├── llm/                  # LLM adapters (11 providers)
│   │   ├── ports.py          # Protocol definitions
│   │   ├── anthropic_adapter.py
│   │   ├── openai_adapter.py
│   │   └── ...
│   ├── widgets/              # Widget plugins (6 types)
│   │   ├── weather.py
│   │   ├── stocks.py
│   │   └── ...
│   ├── persistence/          # Event storage
│   │   ├── event_store.py    # SQLite
│   │   ├── postgres_store.py # PostgreSQL
│   │   └── snapshots.py      # Snapshot strategy
│   └── websocket/            # Real-time updates
│       └── manager.py
│
└── tests/                    # Test suite
    ├── test_domain_events.py
    ├── test_aggregates.py
    └── ...
```

---

## API Keys Required

| Provider | Env Variable | Get From |
|----------|-------------|----------|
| Anthropic | `ANTHROPIC_API_KEY` | console.anthropic.com |
| OpenAI | `OPENAI_API_KEY` | platform.openai.com |
| Google | `GOOGLE_API_KEY` | aistudio.google.com |
| xAI | `XAI_API_KEY` | x.ai |
| Perplexity | `PERPLEXITY_API_KEY` | perplexity.ai |
| Mistral | `MISTRAL_API_KEY` | mistral.ai |
| DeepSeek | `DEEPSEEK_API_KEY` | deepseek.com |
| Qwen | `DASHSCOPE_API_KEY` | dashscope.aliyun.com |
| Kimi | `MOONSHOT_API_KEY` | moonshot.cn |
| GLM | `ZHIPUAI_API_KEY` | open.bigmodel.cn |
| MiniMax | `MINIMAX_API_KEY` | minimax.chat |
| Ollama | `OLLAMA_BASE_URL` | localhost:11434 |

---

## Reasoning Methods

| Method | Best For | Structure |
|--------|----------|-----------|
| **Multi-Perspective** | General decisions | 4 perspectives (constructive, destructive, systemic, minimalist) |
| **Debate** | A vs B decisions | Opening → Rebuttals → Closing → Judge |
| **Jury** | High-stakes | 3 generators → 3 critics → Verifier |
| **Research** | Evidence-based | 3 search iterations → Analysis |
| **Socratic** | Deep inquiry | Position → Elenchus → Aporia → Maieutics |
| **Scientific** | Hypotheses | Hypothesis → Falsification → Experiment |
| **Iterative** | Optimization | Generate → Critique → Refine (loop) |

---

## Widgets

| Widget | Trigger Example | API Used |
|--------|-----------------|----------|
| Weather | "weather in Athens" | Open-Meteo |
| Stocks | "AAPL stock price" | Yahoo Finance |
| Calculator | "calculate 25% of 200" | mathjs |
| Discover | "trending tech news" | SearXNG |
| Image Search | "show images of cats" | SearXNG |
| Video Search | "videos about AI" | SearXNG |

---

## Common Commands

```bash
# Server
python -m uvicorn asgi:app --port 8000 --reload    # Start with auto-reload
python server_check.py                             # Verify setup
python list_models.py                              # List LLM models

# CLI
python main.py --list-presets                      # List presets
python main.py --list-models                       # List models
python main.py --problem "Question" --preset max-quality

# Testing
python -m pytest tests/ -v                         # Run all tests
python -m pytest tests/test_domain_events.py -v   # Specific test
```

---

## Support Files

| File | Purpose |
|------|---------|
| `run.bat` | Windows startup script |
| `start_server.py` | Python startup script |
| `server_check.py` | Readiness verification |
| `list_models.py` | List available LLMs |
| `test_import.py` | Import verification |
| `test_api.py` | API endpoint test |