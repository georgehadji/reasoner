"""Preset data registry — all declarative preset configurations."""

from __future__ import annotations

from reasoner.core.constants import (
    IMAGE_GEN_BUDGET_PRESET,
    IMAGE_GEN_PREMIUM_PRESET,
    MODEL_GEMINI_PRO_IMAGE,
)
from reasoner.domain.preset_core import PipelinePreset
from reasoner.domain.saas import SubscriptionTier


_PRESET_CONFIGS: list[dict] = [
    # ── Multi-Perspective ───────────────────────────────────────────
    {
        "id": "multi-perspective-budget",
        "name": "Multi-Perspective (Budget)",
        "description": "Standard 6-phase pipeline with 3-lab Phase 2 diversity. Gemini 3.5 Flash (constructive) + Mistral Small (destructive) + Zhipu GLM (systemic) + StepFun 3.7 Flash (minimalist). Qwen scores independently. Ultra-low cost per run.",
        "primary_id": "gemini-flash",
        "routing": {
            "prompt_enhancement": "stepfun-3.7-flash",
            "classification": "gpt-5-mini",
            "decomposition": "deepseek-v3",
            "constructive": "gemini-flash",
            "destructive": "mistral-small",
            "systemic": "glm-5.1",
            "minimalist": "stepfun-3.7-flash",  # v3.2: Ministral-3B → StepFun ($0.20/$1.15)
            "scoring": "qwen3.5-flash",
            "stress_testing": "mistral-small",
            "synthesis": "qwen3.7-max"
        },
        "fallback_routing": {
            "prompt_enhancement": "ring-2.6-1t",
            "classification": "ring-2.6-1t",
            "decomposition": "ring-2.6-1t",
            "constructive": "qwen3.7-max",
            "destructive": "deepseek-v3",
            "systemic": "qwen3.7-max",
            "minimalist": "deepseek-v3",
            "scoring": "qwen3.5-flash",
            "stress_testing": "qwen3.7-max",
            "synthesis": "ring-2.6-1t"
        },
        "notes": [
            "v3.2: StepFun 3.7 Flash replaces Ministral-3B/GLM-4-Air — 196B MoE at $0.20/$1.15 per M, vastly better VFM",
            "v3.2: Gemini 3.5 Flash replaces Gemini Flash Lite — near-Pro coding at Flash cost ($1.50/$9.00)",
            "v3.2: Ring-2.6-1T as fallback — 63B active thinking model at $0.075/$0.625 per M",
            "Phase 2: Google + Mistral + Zhipu = 3 labs; StepFun (minimalist) adds 4th independent lab",
            "Scoring: Qwen 3.5 Flash (Alibaba) — independent lab, prevents same-lab scorer bias",
            "Stress testing: Mistral Small — stronger adversarial reasoning",
            "Full run estimated at <$0.015 total — cheaper and better than v3.1",
        ],
    },
    {
        "id": "multi-perspective-ultra-budget",
        "name": "Multi-Perspective (Ultra-Budget)",
        "description": "Minimal 5-phase pipeline with ultra-cheap models. StepFun 3.7 Flash + Ring-2.6-1T + Nex-N2-Pro (free). No prompt enhancement, stress test, or deep read. Sub-penny per run.",
        "primary_id": "stepfun-3.7-flash",
        "routing": {
            "fusion": "stepfun-3.7-flash",
            "context_vetting": "stepfun-3.7-flash",
            "perspective": "stepfun-3.7-flash",
            "constructive": "stepfun-3.7-flash",
            "destructive": "stepfun-3.7-flash",
            "systemic": "stepfun-3.7-flash",
            "minimalist": "stepfun-3.7-flash",
            "scoring": "ring-2.6-1t",
            "synthesis": "ring-2.6-1t"
        },
        "fallback_routing": {
            "fusion": "nex-n2-pro-free",
            "context_vetting": "nex-n2-pro-free",
            "perspective": "nex-n2-pro-free",
            "constructive": "nex-n2-pro-free",
            "destructive": "nex-n2-pro-free",
            "systemic": "nex-n2-pro-free",
            "minimalist": "nex-n2-pro-free",
            "scoring": "stepfun-3.7-flash",
            "synthesis": "stepfun-3.7-flash"
        },
        "notes": [
            "v3.2: Complete overhaul — StepFun 3.7 Flash ($0.20/$1.15) + Ring-2.6-1T ($0.075/$0.625)",
            "v3.2: Fallback: Nex-N2-Pro (FREE — 17B active/397B MoE) + StepFun",
            "StepFun 3.7 Flash: 196B MoE, 11B active, native image/video understanding",
            "Ring-2.6-1T: 63B active thinking model, tool-use native, $0.075/$0.625 per M",
            "Scoring + Synthesis: Ring-2.6-1T (independent lab from StepFun for bias reduction)",
            "Full run estimated at <$0.005 total — 5x cheaper than v3.1 with better models",
        ],
        "top_k": 1,
        "parallel_perspectives": False,
        "enhance_prompt": False,
        "skip_stress_test": True,
        "skip_deep_read": True,
        "batch_critique_jury": True,
        "cascading_routing": {
            "fusion": ["ministral-3b", "glm-4-air"],
            "context_vetting": ["ministral-3b", "glm-4-air"],
            "perspective": ["ministral-3b", "glm-4-air"],
            "scoring": ["deepseek-v4-flash", "qwen3-plus"],  # v3.3: gemini-flash-lite → deepseek-v4-flash
            "synthesis": ["deepseek-v4-flash", "qwen3-plus"],  # v3.3: gemini-flash-lite → deepseek-v4-flash
        },
    },
    {
        "id": "multi-perspective-premium",
        "name": "Multi-Perspective (Premium)",
        "description": "Best available model per phase. Perplexity Sonar fact-checks candidates in Phase 3. Gemini Pro and GLM-5.1 dual-check synthesis. Cross-ecosystem for maximum epistemic diversity.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "constructive": "kimi-k2-6",
            "destructive": "deepseek-r1t2-chimera",
            "systemic": "qwen3.6-plus",
            "minimalist": "gemini-flash",
            "scoring": "sonar-pro",
            "stress_testing": "qwen3.6-plus",
            "synthesis": "gemini-pro"
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "deepseek-r1",
            "decomposition": "gemini-flash",
            "constructive": "qwen3-plus",
            "destructive": "qwen3-plus",
            "systemic": "deepseek-r1",
            "minimalist": "deepseek-r1",
            "scoring": "qwen3-plus",
            "stress_testing": "deepseek-r1",
            "synthesis": "mimo-v2-pro"
        },
        "required_tier": "pro",
        "notes": [
            "Phase 2: Moonshot + DeepSeek + Anthropic + Mistral — 4 different training lineages",
            "Gemini Pro: 1.6T MoE with 1M context, state-of-the-art reasoning effort.",
            "Sonar Pro in scoring phase enables live fact-checking of candidates",
            "GLM-5.1 for synthesis fallback: 200K context, 34% hallucination, 3x cheaper than GPT-5",
            "Kimi K2.6 for constructive: 1T MoE, 256K context, strongest agentic reasoning in Chinese OSS",
            "DeepSeek for destructive: 85K+ adversarial RL environments",
            "Ministral-8b for minimalist: order-of-magnitude fewer tokens by design",
            "MiMo V2 Pro for high-quality synthesis fallback."
        ],
    },

    # ── Debate ───────────────────────────────────────────────────────
    {
        "id": "debate-budget",
        "name": "Debate (Budget)",
        "description": "Adversarial debate with 3 cheap cross-lab models. Mistral Small (Model A) vs Qwen 3.7 Max (Model B), judged by GLM-5.1. 3 different training lineages.",
        "primary_id": "gemini-flash",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",
            "decomposition": "deepseek-v3",
            "constructive": "mistral-small",  # v3.4: seed-2.0-mini → mistral-small (seed-2.0-mini saturates 120s timeout)
            "destructive": "qwen3.7-max",
            "systemic": "glm-5.1",
            "minimalist": "minimax-m3",
            "scoring": "qwen3.5-flash",
            "stress_testing": "mistral-small",
            "synthesis": "deepseek-v3"
        },
        "fallback_routing": {
            "prompt_enhancement": "glm-4-air",
            "classification": "glm-4-air",
            "decomposition": "glm-4-air",
            "constructive": "qwen3-plus",
            "destructive": "deepseek-v3",
            "systemic": "deepseek-v3",
            "minimalist": "deepseek-v3",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-4-air"
        },
        "notes": [
            "Mistral Small (Model A) + Qwen 3.7 Max (Model B) — different training lineages",
            "Mistral Small already known-working in this preset (stress_testing), typical latency <30s",
            "seed-2.0-mini removed — consistently saturated 120s timeout in testing",
            "HyperGate primary: gemini-flash (was gemini-flash-lite) — faster preflight, fresher model",
            "GLM-5.1: debate judge — uses explicit CritiqueScore schema for reliable JSON output",
            "Full run estimated <$0.02"
        ],
    },
    {
        "id": "debate-premium",
        "name": "Debate (Premium)",
        "description": "Elite debate. Gemini Pro vs Kimi K2.6, judged by Perplexity Sonar Pro. 3 different training paradigms + live fact-checking. GLM-5.1 synthesis fallback for low-hallucination summary.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "constructive": "gemini-pro",
            "destructive": "kimi-k2-6",
            "systemic": "gemini-pro",
            "minimalist": "gemini-flash",
            "scoring": "sonar-pro",
            "stress_testing": "gemini-pro",
            "synthesis": "gemini-pro"
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "deepseek-r1",
            "decomposition": "gemini-flash",
            "constructive": "qwen3-plus",
            "destructive": "claude-sonnet",
            "systemic": "qwen3-plus",
            "minimalist": "deepseek-r1",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-5.1"
        },
        "required_tier": "pro",
        "notes": [
            "Gemini Pro: 1.6T MoE with 1M context, state-of-the-art reasoning effort.",
            "MiMo V2 Flash for efficient early-phase prompt enhancement and classification.",
            "Claude Sonnet: constitutional AI, self-critique training",
            "Kimi K2.6: 1T MoE, 256K context, strongest agentic reasoning in Chinese OSS",
            "Sonar Pro judge: live web fact-checking of both positions",
            "GLM-5.1 fallback synthesis: 200K context, low-hallucination summary.",
            "DeepSeek R1 for stress-testing: 85K+ adversarial RL environments",
        ],
    # ── Jury ─────────────────────────────────────────────────────────
    },
    {
        "id": "jury-budget",
        "name": "Jury / Orchestrated (Budget)",
        "description": "6-model jury with cheap cross-lab diversity. DeepSeek + Qwen + GLM + Gemma + Mistral + Ministral. All different labs.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini for JSON adherence
            "decomposition": "deepseek-v3",
            "constructive": "seed-2.0-mini",  # v3.3: gemini-flash-lite → seed-2.0-mini (ByteDance, Feb 2026)
            "destructive": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "systemic": "glm-5.1",  # v3.1: upgraded from glm-4.7-flash
            "minimalist": "minimax-m3",  # v3.1: upgraded from minimax-m2.5
            "scoring": "mistral-medium",  # v3.1: upgraded from mistral-small for critic JSON
            "stress_testing": "mistral-small",
            "synthesis": "qwen3.7-max"  # v3.1: upgraded to qwen3.7
        },
        "fallback_routing": {
            "prompt_enhancement": "glm-4-air",
            "classification": "glm-4-air",
            "decomposition": "glm-4-air",
            "constructive": "qwen3-plus",
            "destructive": "deepseek-v3",
            "systemic": "deepseek-v3",
            "minimalist": "deepseek-v3",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-4-air"
        },
        "notes": [
            "MiniMax M2.5: minimalist pilot — MiniMax lab diversity, fallback to ministral-3b if unavailable",
            "6 different labs = genuine epistemic diversity",
            "Ministral-8b for minimalist: order-of-magnitude fewer tokens",
            "Estimated <$0.02 per jury run",
            "DeepSeek V3: decomposition backbone — stronger structured reasoning than Gemini Flash Lite at comparable cost.",
            "Gemini Flash Lite: reserved for coordination roles (prompt_enhancement, constructive) — JSON formatting, low-stakes structure."
        ],
    },
    {
        "id": "jury-premium",
        "name": "Jury / Orchestrated (Premium)",
        "description": "Elite 6-model jury with live fact-checking. Claude + Kimi K2.6 + DeepSeek + Gemini + Perplexity + GLM. Cross-ecosystem for maximum coverage. GLM-5.1 synthesis fallback for low-hallucination consensus.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "constructive": "gemini-pro",
            "destructive": "kimi-k2-6",
            "systemic": "gemini-pro",
            "minimalist": "gemini-flash",
            "scoring": "sonar-pro",
            "stress_testing": "gemini-pro",
            "synthesis": "qwen3.6-plus",
            "expert_1": "claude-sonnet",
            "expert_2": "kimi-k2-6",
            "expert_3": "deepseek-r1t2-chimera",
            "expert_4": "qwen3.6-plus",
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "deepseek-r1",
            "decomposition": "gemini-flash",
            "constructive": "qwen3-plus",
            "destructive": "claude-sonnet",
            "systemic": "qwen3-plus",
            "minimalist": "deepseek-r1",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-5.1",
            "expert_1": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "expert_2": "deepseek-v3",
            "expert_3": "qwen3-plus",
            "expert_4": "deepseek-v3",
        },
        "required_tier": "pro",
        "notes": [
            "MiMo V2 Flash for efficient early-phase prompt enhancement and classification.",
            "Claude Sonnet: expert_1 — constitutional AI training, distinct reasoning style",
            "Kimi K2.6: expert_2 — 1T MoE, 256K context, strongest OSS agentic reasoning",
            "DeepSeek R1T2 Chimera: expert_3 — 85K+ adversarial RL environments, adversarial perspective",
            "Qwen 3.6 Plus: expert_4 — Alibaba lab, 4th genuinely distinct training lineage",
            "Claude + Kimi + DeepSeek + Qwen = 4 genuinely different labs (no duplicates)",
            "Sonar Pro for scoring: live web fact-checking of every candidate",
            "GLM-5.1 for synthesis fallback: 200K context, 34% hallucination, honest consensus synthesis",
        ],
    },
    # ── Research ─────────────────────────────────────────────────────
    {
        "id": "research-budget",
        "name": "Research (Budget)",
        "description": "Deep iterative search with cheap models. DeepSeek for reasoning, Qwen for synthesis, Gemma for classification.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini for JSON adherence
            "decomposition": "deepseek-v3",
            "constructive": "seed-2.0-mini",  # v3.3: gemini-flash-lite → seed-2.0-mini (ByteDance, Feb 2026)
            "destructive": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "systemic": "glm-5.1",  # v3.1: upgraded from glm-4.7-flash
            "minimalist": "ministral-3b",
            "scoring": "qwen3.5-flash",
            "stress_testing": "mistral-small",
            "synthesis": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            # Article pipeline: cross-model diversity
            "article_decompose": "deepseek-v3",
            "article_synthesize": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "article_pre_mortem": "mistral-small",
            "article_critic": "qwen3.5-flash",
            "article_revise": "seed-2.0-mini",  # v3.3: gemini-flash-lite → seed-2.0-mini (ByteDance, revision)
            "article_humanize": "ministral-3b",
        },
        "fallback_routing": {
            "prompt_enhancement": "glm-4-air",
            "classification": "glm-4-air",
            "decomposition": "glm-4-air",
            "constructive": "qwen3-plus",
            "destructive": "deepseek-v3",
            "systemic": "deepseek-v3",
            "minimalist": "deepseek-v3",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-4-air",
            "article_synthesize": "glm-4-air",
            "article_pre_mortem": "deepseek-v3",
            "article_critic": "qwen3-plus",
        },
        "notes": [
            "DeepSeek for iterative search reasoning",
            "Qwen for synthesis: strong multilingual output",
            "Gemma for classification: cheap but capable",
            "DeepSeek V3: decomposition backbone — stronger structured reasoning than Gemini Flash Lite at comparable cost.",
            "Gemini Flash Lite: reserved for coordination roles (prompt_enhancement, constructive) — JSON formatting, low-stakes structure."
        ],
    },
    {
        "id": "research-premium",
        "name": "Research (Premium)",
        "description": "Elite research with live fact-checking. Claude for reasoning, Perplexity for evidence evaluation, GLM for synthesis.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "constructive": "claude-sonnet",
            "destructive": "kimi-k2-6",
            "systemic": "deepseek-r1t2-chimera",
            "minimalist": "gemini-flash",
            "scoring": "sonar-pro",
            "stress_testing": "deepseek-r1t2-chimera",
            "synthesis": "mimo-v2-pro",
            # Article pipeline: cross-model diversity
            "article_decompose": "gemini-pro",
            "article_synthesize": "mimo-v2-pro",
            "article_pre_mortem": "deepseek-r1t2-chimera",
            "article_critic": "sonar-pro",
            "article_revise": "claude-sonnet",
            "article_humanize": "gemini-flash",
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "deepseek-r1",
            "decomposition": "gemini-flash",
            "constructive": "qwen3-plus",
            "destructive": "claude-sonnet",
            "systemic": "qwen3-plus",
            "minimalist": "deepseek-r1",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "gpt-5",
            "article_synthesize": "gpt-5",
            "article_pre_mortem": "claude-sonnet",
            "article_critic": "qwen3-plus",
        },
        "required_tier": "pro",
        "notes": [
            "MiMo V2 Pro for deep reasoning and synthesis.",
            "MiMo V2 Flash for efficient early-phase prompt enhancement and classification.",
            "Claude for deep reasoning: constitutional AI training",
            "Perplexity Sonar Pro for live evidence evaluation",
            "GLM-5 for synthesis: top of Artificial Analysis Intelligence Index",
        ],
    },
    # ── Scientific ───────────────────────────────────────────────────
    {
        "id": "scientific-budget",
        "name": "Scientific (Budget)",
        "description": "Hypothesis-test-evaluate cycle with cheap models. DeepSeek for hypothesis generation, Qwen for testing, GLM for evaluation.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini for JSON adherence
            "decomposition": "deepseek-v3",
            "constructive": "seed-2.0-mini",  # v3.3: gemini-flash-lite → seed-2.0-mini (ByteDance, Feb 2026)
            "destructive": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "systemic": "glm-5.1",  # v3.1: upgraded from glm-4.7-flash
            "minimalist": "ministral-3b",
            "scoring": "qwen3.5-flash",
            "stress_testing": "mistral-small",
            "synthesis": "qwen3.7-max"  # v3.1: upgraded to qwen3.7
        },
        "fallback_routing": {
            "prompt_enhancement": "glm-4-air",
            "classification": "glm-4-air",
            "decomposition": "glm-4-air",
            "constructive": "qwen3-plus",
            "destructive": "deepseek-v3",
            "systemic": "deepseek-v3",
            "minimalist": "deepseek-v3",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-4-air"
        },
        "notes": [
            "DeepSeek for hypothesis generation: strong reasoning",
            "Qwen for testing: good at structured evaluation",
            "GLM for scoring: cheap but capable",
            "DeepSeek V3: decomposition backbone — stronger structured reasoning than Gemini Flash Lite at comparable cost.",
            "Gemini Flash Lite: reserved for coordination roles (prompt_enhancement, constructive) — JSON formatting, low-stakes structure."
        ],
    },
    {
        "id": "scientific-premium",
        "name": "Scientific (Premium)",
        "description": "Elite scientific reasoning. Claude for hypothesis generation, Kimi K2.6 for testing, Perplexity for evidence evaluation.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "constructive": "claude-sonnet",
            "destructive": "kimi-k2-6",
            "systemic": "deepseek-r1t2-chimera",
            "minimalist": "gemini-flash",
            "scoring": "sonar-pro",
            "stress_testing": "deepseek-r1t2-chimera",
            "synthesis": "mimo-v2-pro"
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "deepseek-r1",
            "decomposition": "gemini-flash",
            "constructive": "qwen3-plus",
            "destructive": "claude-sonnet",
            "systemic": "qwen3-plus",
            "minimalist": "deepseek-r1",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "gpt-5"
        },
        "required_tier": "pro",
        "notes": [
            "MiMo V2 Pro for hypothesis generation and synthesis: strong reasoning capabilities.",
            "MiMo V2 Flash for efficient early-phase prompt enhancement and classification.",
            "Claude for hypothesis generation: constitutional AI training",
            "Kimi K2.6 for testing: 1T MoE, agentic evaluation with 256K context",
            "Perplexity Sonar Pro for evidence evaluation: live web fact-checking",
        ],
    },
    # ── Socratic ─────────────────────────────────────────────────────
    {
        "id": "socratic-budget",
        "name": "Socratic (Budget)",
        "description": "Socratic questioning with cheap models. DeepSeek for questions, Qwen for answers, GLM for evaluation.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini for JSON adherence
            "decomposition": "deepseek-v3",
            "constructive": "seed-2.0-mini",  # v3.3: gemini-flash-lite → seed-2.0-mini (ByteDance, Feb 2026)
            "destructive": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "systemic": "glm-5.1",  # v3.1: upgraded from glm-4.7-flash
            "minimalist": "ministral-3b",
            "scoring": "qwen3.5-flash",
            "stress_testing": "mistral-small",
            "synthesis": "qwen3.7-max"  # v3.1: upgraded to qwen3.7
        },
        "fallback_routing": {
            "prompt_enhancement": "glm-4-air",
            "classification": "glm-4-air",
            "decomposition": "glm-4-air",
            "constructive": "qwen3-plus",
            "destructive": "deepseek-v3",
            "systemic": "deepseek-v3",
            "minimalist": "deepseek-v3",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-4-air"
        },
        "notes": [
            "DeepSeek for Socratic questions: strong reasoning",
            "Qwen for answers: good at structured response",
            "GLM for evaluation: cheap but capable",
            "DeepSeek V3: decomposition backbone — stronger structured reasoning than Gemini Flash Lite at comparable cost.",
            "Gemini Flash Lite: reserved for coordination roles (prompt_enhancement, constructive) — JSON formatting, low-stakes structure."
        ],
    },
    {
        "id": "socratic-premium",
        "name": "Socratic (Premium)",
        "description": "Elite Socratic dialogue. Claude for questions, Kimi K2.6 for answers, Perplexity for evidence evaluation.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "constructive": "claude-sonnet",
            "destructive": "kimi-k2-6",
            "systemic": "deepseek-r1t2-chimera",
            "minimalist": "gemini-flash",
            "scoring": "sonar-pro",
            "stress_testing": "deepseek-r1t2-chimera",
            "synthesis": "mimo-v2-pro"
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "deepseek-r1",
            "decomposition": "gemini-flash",
            "constructive": "qwen3-plus",
            "destructive": "claude-sonnet",
            "systemic": "qwen3-plus",
            "minimalist": "deepseek-r1",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "gpt-5"
        },
        "required_tier": "pro",
        "notes": [
            "MiMo V2 Pro for Socratic questions and synthesis: strong reasoning capabilities.",
            "MiMo V2 Flash for efficient early-phase prompt enhancement and classification.",
            "Claude for Socratic questions: constitutional AI training",
            "Kimi K2.6 for answers: 1T MoE, agentic reasoning with 256K context",
            "Perplexity Sonar Pro for evidence evaluation: live web fact-checking",
        ],
    },
    # ── Pre-Mortem ───────────────────────────────────────────────────
    {
        "id": "pre-mortem-budget",
        "name": "Pre-Mortem (Budget)",
        "description": "Failure-mode analysis with cheap models. DeepSeek for failure scenarios, Qwen for backtracking, GLM for signals.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini for JSON adherence
            "decomposition": "deepseek-v3",
            "constructive": "seed-2.0-mini",  # v3.3: gemini-flash-lite → seed-2.0-mini (ByteDance, Feb 2026)
            "destructive": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "systemic": "glm-5.1",  # v3.1: upgraded from glm-4.7-flash
            "minimalist": "ministral-3b",
            "scoring": "qwen3.5-flash",
            "stress_testing": "mistral-small",
            "synthesis": "qwen3.7-max"  # v3.1: upgraded to qwen3.7
        },
        "fallback_routing": {
            "prompt_enhancement": "glm-4-air",
            "classification": "glm-4-air",
            "decomposition": "glm-4-air",
            "constructive": "qwen3-plus",
            "destructive": "deepseek-v3",
            "systemic": "deepseek-v3",
            "minimalist": "deepseek-v3",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-4-air"
        },
        "notes": [
            "DeepSeek for failure scenarios: strong adversarial reasoning",
            "Qwen for backtracking: good at structured analysis",
            "GLM for signals: cheap but capable",
            "DeepSeek V3: decomposition backbone — stronger structured reasoning than Gemini Flash Lite at comparable cost.",
            "Gemini Flash Lite: reserved for coordination roles (prompt_enhancement, constructive) — JSON formatting, low-stakes structure."
        ],
    },
    {
        "id": "pre-mortem-premium",
        "name": "Pre-Mortem (Premium)",
        "description": "Elite pre-mortem analysis. Claude for failure scenarios, Kimi K2.6 for backtracking, Perplexity for evidence evaluation.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "constructive": "claude-sonnet",
            "destructive": "kimi-k2-6",
            "systemic": "deepseek-r1t2-chimera",
            "minimalist": "gemini-flash",
            "scoring": "sonar-pro",
            "stress_testing": "deepseek-r1t2-chimera",
            "synthesis": "mimo-v2-pro"
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "deepseek-r1",
            "decomposition": "gemini-flash",
            "constructive": "qwen3-plus",
            "destructive": "claude-sonnet",
            "systemic": "qwen3-plus",
            "minimalist": "deepseek-r1",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "gpt-5"
        },
        "required_tier": "pro",
        "notes": [
            "MiMo V2 Pro for failure scenarios and synthesis: strong reasoning capabilities.",
            "MiMo V2 Flash for efficient early-phase prompt enhancement and classification.",
            "Claude for failure scenarios: constitutional AI training",
            "Kimi K2.6 for backtracking: 1T MoE, agentic reasoning with 256K context",
            "Perplexity Sonar Pro for evidence evaluation: live web fact-checking",
        ],
    },
    # ── Bayesian ─────────────────────────────────────────────────────
    {
        "id": "bayesian-budget",
        "name": "Bayesian (Budget)",
        "description": "Probabilistic reasoning with cheap models. DeepSeek for priors, Qwen for likelihood, GLM for posterior.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini for JSON adherence
            "decomposition": "deepseek-v3",
            "constructive": "seed-2.0-mini",  # v3.3: gemini-flash-lite → seed-2.0-mini (ByteDance, Feb 2026)
            "destructive": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "systemic": "glm-5.1",  # v3.1: upgraded from glm-4.7-flash
            "minimalist": "ministral-3b",
            "scoring": "qwen3.5-flash",
            "stress_testing": "mistral-small",
            "synthesis": "qwen3.7-max"  # v3.1: upgraded to qwen3.7
        },
        "fallback_routing": {
            "prompt_enhancement": "glm-4-air",
            "classification": "glm-4-air",
            "decomposition": "glm-4-air",
            "constructive": "qwen3-plus",
            "destructive": "deepseek-v3",
            "systemic": "deepseek-v3",
            "minimalist": "deepseek-v3",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-4-air"
        },
        "notes": [
            "DeepSeek for priors: strong reasoning",
            "Qwen for likelihood: good at structured analysis",
            "GLM for posterior: cheap but capable",
            "DeepSeek V3: decomposition backbone — stronger structured reasoning than Gemini Flash Lite at comparable cost.",
            "Gemini Flash Lite: reserved for coordination roles (prompt_enhancement, constructive) — JSON formatting, low-stakes structure."
        ],
    },
    {
        "id": "bayesian-premium",
        "name": "Bayesian (Premium)",
        "description": "Elite Bayesian reasoning. Claude for priors, Kimi K2.6 for likelihood, Perplexity for evidence evaluation.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "constructive": "claude-sonnet",
            "destructive": "kimi-k2-6",
            "systemic": "deepseek-r1t2-chimera",
            "minimalist": "gemini-flash",
            "scoring": "sonar-pro",
            "stress_testing": "deepseek-r1t2-chimera",
            "synthesis": "mimo-v2-pro"
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "deepseek-r1",
            "decomposition": "gemini-flash",
            "constructive": "qwen3-plus",
            "destructive": "claude-sonnet",
            "systemic": "qwen3-plus",
            "minimalist": "deepseek-r1",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "gpt-5"
        },
        "required_tier": "pro",
        "notes": [
            "MiMo V2 Pro for priors and synthesis: strong reasoning capabilities.",
            "MiMo V2 Flash for efficient early-phase prompt enhancement and classification.",
            "Claude for priors: constitutional AI training",
            "Kimi K2.6 for likelihood: 1T MoE, agentic reasoning with 256K context",
            "Perplexity Sonar Pro for evidence evaluation: live web fact-checking",
        ],
    },
    # ── Dialectical ──────────────────────────────────────────────────
    {
        "id": "dialectical-budget",
        "name": "Dialectical (Budget)",
        "description": "Thesis-antithesis-synthesis with cheap models. DeepSeek for thesis, Qwen for antithesis, GLM for synthesis.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini for JSON adherence
            "decomposition": "deepseek-v3",
            "constructive": "seed-2.0-mini",  # v3.3: gemini-flash-lite → seed-2.0-mini (ByteDance, Feb 2026)
            "destructive": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "systemic": "glm-5.1",  # v3.1: upgraded from glm-4.7-flash
            "minimalist": "ministral-3b",
            "scoring": "qwen3.5-flash",
            "stress_testing": "mistral-small",
            "synthesis": "qwen3.7-max"  # v3.1: upgraded to qwen3.7
        },
        "fallback_routing": {
            "prompt_enhancement": "glm-4-air",
            "classification": "glm-4-air",
            "decomposition": "glm-4-air",
            "constructive": "qwen3-plus",
            "destructive": "deepseek-v3",
            "systemic": "deepseek-v3",
            "minimalist": "deepseek-v3",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-4-air"
        },
        "notes": [
            "DeepSeek for thesis: strong reasoning",
            "Qwen for antithesis: good at structured opposition",
            "GLM for synthesis: cheap but capable",
            "DeepSeek V3: decomposition backbone — stronger structured reasoning than Gemini Flash Lite at comparable cost.",
            "Gemini Flash Lite: reserved for coordination roles (prompt_enhancement, constructive) — JSON formatting, low-stakes structure."
        ],
    },
    {
        "id": "dialectical-premium",
        "name": "Dialectical (Premium)",
        "description": "Elite dialectical reasoning. Claude for thesis, Kimi K2.6 for antithesis, Perplexity for evidence evaluation.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "constructive": "claude-sonnet",
            "destructive": "kimi-k2-6",
            "systemic": "deepseek-r1t2-chimera",
            "minimalist": "gemini-flash",
            "scoring": "sonar-pro",
            "stress_testing": "deepseek-r1t2-chimera",
            "synthesis": "mimo-v2-pro"
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "deepseek-r1",
            "decomposition": "gemini-flash",
            "constructive": "qwen3-plus",
            "destructive": "claude-sonnet",
            "systemic": "qwen3-plus",
            "minimalist": "deepseek-r1",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "gpt-5"
        },
        "required_tier": "pro",
        "notes": [
            "MiMo V2 Pro for thesis and synthesis: strong reasoning capabilities.",
            "MiMo V2 Flash for efficient early-phase prompt enhancement and classification.",
            "Claude for thesis: constitutional AI training",
            "Kimi K2.6 for antithesis: 1T MoE, agentic reasoning with 256K context",
            "Perplexity Sonar Pro for evidence evaluation: live web fact-checking",
        ],
    },
    # ── Analogical ───────────────────────────────────────────────────
    {
        "id": "analogical-budget",
        "name": "Analogical (Budget)",
        "description": "Structure-mapping and transfer with cheap models. DeepSeek for abstraction, Qwen for domain search, GLM for mapping.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini for JSON adherence
            "decomposition": "deepseek-v3",
            "constructive": "seed-2.0-mini",  # v3.3: gemini-flash-lite → seed-2.0-mini (ByteDance, Feb 2026)
            "destructive": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "systemic": "glm-5.1",  # v3.1: upgraded from glm-4.7-flash
            "minimalist": "ministral-3b",
            "scoring": "qwen3.5-flash",
            "stress_testing": "mistral-small",
            "synthesis": "qwen3.7-max"  # v3.1: upgraded to qwen3.7
        },
        "fallback_routing": {
            "prompt_enhancement": "glm-4-air",
            "classification": "glm-4-air",
            "decomposition": "glm-4-air",
            "constructive": "qwen3-plus",
            "destructive": "deepseek-v3",
            "systemic": "deepseek-v3",
            "minimalist": "deepseek-v3",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-4-air"
        },
        "notes": [
            "DeepSeek for abstraction: strong reasoning",
            "Qwen for domain search: good at structured search",
            "GLM for mapping: cheap but capable",
            "DeepSeek V3: decomposition backbone — stronger structured reasoning than Gemini Flash Lite at comparable cost.",
            "Gemini Flash Lite: reserved for coordination roles (prompt_enhancement, constructive) — JSON formatting, low-stakes structure."
        ],
    },
    {
        "id": "analogical-premium",
        "name": "Analogical (Premium)",
        "description": "Elite analogical reasoning. Claude for abstraction, Kimi K2.6 for domain search, Perplexity for evidence evaluation.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "constructive": "claude-sonnet",
            "destructive": "kimi-k2-6",
            "systemic": "deepseek-r1t2-chimera",
            "minimalist": "gemini-flash",
            "scoring": "sonar-pro",
            "stress_testing": "deepseek-r1t2-chimera",
            "synthesis": "mimo-v2-pro"
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "deepseek-r1",
            "decomposition": "gemini-flash",
            "constructive": "qwen3-plus",
            "destructive": "claude-sonnet",
            "systemic": "qwen3-plus",
            "minimalist": "deepseek-r1",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "gpt-5"
        },
        "required_tier": "pro",
        "notes": [
            "MiMo V2 Pro for abstraction and synthesis: strong reasoning capabilities.",
            "MiMo V2 Flash for efficient early-phase prompt enhancement and classification.",
            "Claude for abstraction: constitutional AI training",
            "Kimi K2.6 for domain search: 1T MoE, agentic reasoning with 256K context",
            "Perplexity Sonar Pro for evidence evaluation: live web fact-checking",
        ],
    },
    # ── Delphi ───────────────────────────────────────────────────────
    {
        "id": "delphi-budget",
        "name": "Delphi Method (Budget)",
        "description": "Structured expert consensus with cheap models. 4 cheap models (DeepSeek, Qwen, GLM, Gemma) in round-robin consensus.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini for JSON adherence
            "decomposition": "deepseek-v3",
            "constructive": "seed-2.0-mini",  # v3.3: gemini-flash-lite → seed-2.0-mini (ByteDance, Feb 2026)
            "destructive": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "systemic": "glm-5.1",  # v3.1: upgraded from glm-4.7-flash
            "minimalist": "ministral-3b",
            "scoring": "qwen3.5-flash",
            "stress_testing": "mistral-small",
            "synthesis": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "expert_1": "deepseek-v3",
            "expert_2": "deepseek-v4-flash",  # v3.1: faster critic, avoids Qwen 45s timeouts  # v3.1: upgraded from qwen3-max
            "expert_3": "glm-4-air",
            "expert_4": "mistral-small",
        },
        "fallback_routing": {
            "prompt_enhancement": "glm-4-air",
            "classification": "glm-4-air",
            "decomposition": "glm-4-air",
            "constructive": "qwen3-plus",
            "destructive": "deepseek-v3",
            "systemic": "deepseek-v3",
            "minimalist": "deepseek-v3",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-4-air",
            "expert_1": "deepseek-v3",
            "expert_2": "glm-4-air",
            "expert_3": "qwen3-plus",
            "expert_4": "deepseek-v3",
        },
        "notes": [
            "4 cheap models in round-robin = genuine diversity",
            "DeepSeek + Qwen + GLM + Gemma: 4 different labs",
            "Estimated <$0.03 per Delphi run",
            "DeepSeek V3 for expert_1 + decomposition: strong reasoning at budget cost.",
            "Mistral Small for expert_4: European lab — 4th genuinely distinct perspective.",
            "Gemini Flash Lite: reserved for coordination roles only."
        ],
    },
    {
        "id": "delphi-premium",
        "name": "Delphi Method (Premium)",
        "description": "Elite Delphi consensus. 4 top models (Claude, Kimi K2.6, DeepSeek, Gemini) with Perplexity Sonar Pro for fact-checking.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "constructive": "claude-sonnet",
            "destructive": "kimi-k2-6",
            "systemic": "deepseek-r1t2-chimera",
            "minimalist": "gemini-flash",
            "scoring": "sonar-pro",
            "stress_testing": "deepseek-r1t2-chimera",
            "synthesis": "gemini-pro",
            "expert_1": "claude-sonnet",
            "expert_2": "kimi-k2-6",
            "expert_3": "deepseek-r1t2-chimera",
            "expert_4": "qwen3.6-plus",
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "deepseek-r1",
            "decomposition": "gemini-flash",
            "constructive": "qwen3-plus",
            "destructive": "claude-sonnet",
            "systemic": "qwen3-plus",
            "minimalist": "deepseek-r1",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "gpt-5",
            "expert_1": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "expert_2": "deepseek-v3",
            "expert_3": "qwen3-plus",
            "expert_4": "deepseek-v3",
        },
        "required_tier": "pro",
        "notes": [
            "MiMo V2 Flash for efficient early-phase prompt enhancement and classification.",
            "Claude Sonnet: expert_1 — constitutional AI training, distinct reasoning style",
            "Kimi K2.6: expert_2 — 1T MoE, 256K context, strongest OSS agentic reasoning",
            "DeepSeek R1T2 Chimera: expert_3 — 85K+ adversarial RL environments, adversarial perspective",
            "Qwen 3.6 Plus: expert_4 — Alibaba lab, 4th genuinely distinct training lineage",
            "Claude + Kimi + DeepSeek + Qwen = 4 genuinely different labs (no duplicates)",
            "Claude + Kimi K2.6 + DeepSeek + Gemini: 4 top ecosystems",
            "Perplexity Sonar Pro for fact-checking: live web verification",
            "GLM-5 for synthesis: top of Artificial Analysis Intelligence Index",
        ],
    },
    # ── CoVe ─────────────────────────────────────────────────────────
    {
        "id": "cove-budget",
        "name": "Chain-of-Verification (Budget)",
        "description": "Draft-verify-revise cycle with cheap models. DeepSeek for drafting, Qwen for verification, GLM for revision.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini for JSON adherence
            "decomposition": "deepseek-v3",
            "cove_draft": "deepseek-v3",
            "cove_verify": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "cove_answer": "glm-5.1",
            "cove_revise": "seed-2.0-mini",  # v3.3: gemini-flash-lite → seed-2.0-mini (ByteDance, revision)
            "scoring": "qwen3.5-flash",
            "stress_testing": "mistral-small",
            "synthesis": "qwen3.7-max"  # v3.1: upgraded to qwen3.7
        },
        "fallback_routing": {
            "prompt_enhancement": "glm-4-air",
            "classification": "glm-4-air",
            "decomposition": "glm-4-air",
            "cove_draft": "qwen3-plus",
            "cove_verify": "deepseek-v3",
            "cove_answer": "deepseek-v3",
            "cove_revise": "deepseek-v3",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-4-air"
        },
        "notes": [
            "DeepSeek for drafting: strong reasoning",
            "Qwen for verification: good at structured checking",
            "GLM for revision: cheap but capable",
            "DeepSeek V3: decomposition backbone — stronger structured reasoning than Gemini Flash Lite at comparable cost.",
            "Gemini Flash Lite: reserved for coordination roles (prompt_enhancement, constructive) — JSON formatting, low-stakes structure."
        ],
    },
    {
        "id": "cove-premium",
        "name": "Chain-of-Verification (Premium)",
        "description": "Elite CoVe. Claude for drafting, Kimi K2.6 for verification, Perplexity for evidence evaluation.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "cove_draft": "claude-sonnet",
            "cove_verify": "kimi-k2-6",
            "cove_answer": "deepseek-r1t2-chimera",
            "cove_revise": "qwen3.6-plus",
            "scoring": "sonar-pro",
            "stress_testing": "deepseek-r1t2-chimera",
            "synthesis": "mimo-v2-pro"
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "deepseek-r1",
            "decomposition": "gemini-flash",
            "cove_draft": "qwen3-plus",
            "cove_verify": "claude-sonnet",
            "cove_answer": "qwen3-plus",
            "cove_revise": "deepseek-r1",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "gpt-5"
        },
        "required_tier": "pro",
        "notes": [
            "MiMo V2 Pro for decomposition and synthesis: strong reasoning capabilities.",
            "MiMo V2 Flash for efficient early-phase prompt enhancement and classification.",
            "Claude for drafting: constitutional AI training",
            "Kimi K2.6 for verification: 1T MoE, DeepSearchQA 92.5%, agentic verification with 256K context",
            "Perplexity Sonar Pro for evidence evaluation: live web fact-checking",
        ],
    },
    # ── SoT ──────────────────────────────────────────────────────────
    {
        "id": "sot-budget",
        "name": "Skeleton-of-Thought (Budget)",
        "description": "Skeleton-then-flesh reasoning with cheap models. DeepSeek for skeleton, Qwen for solving, GLM for assembly.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini for JSON adherence
            "decomposition": "deepseek-v3",
            "sot_skeleton": "deepseek-v3",
            "sot_solve": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "sot_assemble": "glm-5.1",
            "scoring": "qwen3.5-flash",
            "stress_testing": "mistral-small",
            "synthesis": "qwen3.7-max"  # v3.1: upgraded to qwen3.7
        },
        "fallback_routing": {
            "prompt_enhancement": "glm-4-air",
            "classification": "glm-4-air",
            "decomposition": "glm-4-air",
            "sot_skeleton": "qwen3-plus",
            "sot_solve": "deepseek-v3",
            "sot_assemble": "deepseek-v3",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-4-air"
        },
        "notes": [
            "DeepSeek for skeleton: strong reasoning",
            "Qwen for solving: good at structured problem-solving",
            "GLM for assembly: cheap but capable",
            "DeepSeek V3: decomposition backbone — stronger structured reasoning than Gemini Flash Lite at comparable cost.",
            "Gemini Flash Lite: reserved for coordination roles (prompt_enhancement, constructive) — JSON formatting, low-stakes structure."
        ],
    },
    {
        "id": "sot-premium",
        "name": "Skeleton-of-Thought (Premium)",
        "description": "Elite SoT. Claude for skeleton, Kimi K2.6 for solving, Perplexity for evidence evaluation.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "sot_skeleton": "claude-sonnet",
            "sot_solve": "kimi-k2-6",
            "sot_assemble": "deepseek-r1t2-chimera",
            "scoring": "sonar-pro",
            "stress_testing": "deepseek-r1t2-chimera",
            "synthesis": "mimo-v2-pro"
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "deepseek-r1",
            "decomposition": "gemini-flash",
            "sot_skeleton": "qwen3-plus",
            "sot_solve": "claude-sonnet",
            "sot_assemble": "qwen3-plus",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "gpt-5"
        },
        "required_tier": "pro",
        "notes": [
            "MiMo V2 Pro for decomposition and synthesis: strong reasoning capabilities.",
            "MiMo V2 Flash for efficient early-phase prompt enhancement and classification.",
            "Claude for skeleton: constitutional AI training",
            "Kimi K2.6 for solving: 1T MoE, SWE-Bench 80.2%, agentic problem solving with 256K context",
            "Perplexity Sonar Pro for evidence evaluation: live web fact-checking",
        ],
    },
    # ── ToT ──────────────────────────────────────────────────────────
    {
        "id": "tot-budget",
        "name": "Tree-of-Thought (Budget)",
        "description": "Branching reasoning with cheap models. DeepSeek for decomposition, Qwen for generation, GLM for evaluation.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini for JSON adherence
            "decomposition": "deepseek-v3",
            "tot_decompose": "deepseek-v3",
            "tot_generate": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "tot_evaluate": "glm-4-air",
            "tot_backtrack": "seed-2.0-mini",  # v3.3: gemini-flash-lite → seed-2.0-mini (ByteDance, avoids double-DeepSeek)
            "scoring": "qwen3.5-flash",
            "stress_testing": "mistral-small",
            "synthesis": "qwen3.7-max"  # v3.1: upgraded to qwen3.7
        },
        "fallback_routing": {
            "prompt_enhancement": "glm-4-air",
            "classification": "glm-4-air",
            "decomposition": "glm-4-air",
            "tot_decompose": "qwen3-plus",
            "tot_generate": "deepseek-v3",
            "tot_evaluate": "deepseek-v3",
            "tot_backtrack": "deepseek-v3",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-4-air"
        },
        "notes": [
            "DeepSeek for decomposition: strong reasoning",
            "Qwen for generation: good at structured generation",
            "GLM for evaluation: cheap but capable",
            "DeepSeek V3: decomposition backbone — stronger structured reasoning than Gemini Flash Lite at comparable cost.",
            "Gemini Flash Lite: reserved for coordination roles (prompt_enhancement, constructive) — JSON formatting, low-stakes structure."
        ],
    },
    {
        "id": "tot-premium",
        "name": "Tree-of-Thought (Premium)",
        "description": "Elite ToT. Claude for decomposition, Kimi K2.6 for generation, Perplexity for evidence evaluation.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "tot_decompose": "claude-sonnet",
            "tot_generate": "kimi-k2-6",
            "tot_evaluate": "deepseek-r1t2-chimera",
            "tot_backtrack": "qwen3.6-plus",
            "scoring": "sonar-pro",
            "stress_testing": "deepseek-r1t2-chimera",
            "synthesis": "mimo-v2-pro"
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "deepseek-r1",
            "decomposition": "gemini-flash",
            "tot_decompose": "qwen3-plus",
            "tot_generate": "claude-sonnet",
            "tot_evaluate": "qwen3-plus",
            "tot_backtrack": "deepseek-r1",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "gpt-5"
        },
        "required_tier": "pro",
        "notes": [
            "MiMo V2 Pro for decomposition and synthesis: strong reasoning capabilities.",
            "MiMo V2 Flash for efficient early-phase prompt enhancement and classification.",
            "Claude for decomposition: constitutional AI training",
            "Kimi K2.6 for generation: 1T MoE, agentic generation with 256K context",
            "Perplexity Sonar Pro for evidence evaluation: live web fact-checking",
        ],
    },
    # ── PoT ──────────────────────────────────────────────────────────
    {
        "id": "pot-budget",
        "name": "Program-of-Thought (Budget)",
        "description": "Code-first reasoning with cheap models. DeepSeek for generation, Qwen for execution, GLM for interpretation.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini for JSON adherence
            "decomposition": "deepseek-v3",
            "pot_generate": "deepseek-v3",
            "pot_execute": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "pot_interpret": "glm-5.1",
            "scoring": "qwen3.5-flash",
            "stress_testing": "mistral-small",
            "synthesis": "qwen3.7-max"  # v3.1: upgraded to qwen3.7
        },
        "fallback_routing": {
            "prompt_enhancement": "glm-4-air",
            "classification": "glm-4-air",
            "decomposition": "glm-4-air",
            "pot_generate": "qwen3-plus",
            "pot_execute": "deepseek-v3",
            "pot_interpret": "deepseek-v3",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-4-air"
        },
        "notes": [
            "DeepSeek for generation: strong reasoning",
            "Qwen for execution: good at structured execution",
            "GLM for interpretation: cheap but capable",
            "DeepSeek V3: decomposition backbone — stronger structured reasoning than Gemini Flash Lite at comparable cost.",
            "Gemini Flash Lite: reserved for coordination roles (prompt_enhancement, constructive) — JSON formatting, low-stakes structure."
        ],
    },
    {
        "id": "pot-premium",
        "name": "Program-of-Thought (Premium)",
        "description": "Elite PoT. Claude for generation, Kimi K2.6 for execution, Perplexity for evidence evaluation.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "pot_generate": "claude-sonnet",
            "pot_execute": "kimi-k2-6",
            "pot_interpret": "deepseek-r1t2-chimera",
            "scoring": "sonar-pro",
            "stress_testing": "deepseek-r1t2-chimera",
            "synthesis": "mimo-v2-pro"
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "deepseek-r1",
            "decomposition": "gemini-flash",
            "pot_generate": "qwen3-plus",
            "pot_execute": "claude-sonnet",
            "pot_interpret": "qwen3-plus",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "gpt-5"
        },
        "required_tier": "pro",
        "notes": [
            "MiMo V2 Pro for decomposition and synthesis: strong reasoning capabilities.",
            "MiMo V2 Flash for efficient early-phase prompt enhancement and classification.",
            "Claude for generation: constitutional AI training",
            "Kimi K2.6 for execution: 1T MoE, SWE-Bench 80.2%, agentic code execution with 256K context",
            "Perplexity Sonar Pro for evidence evaluation: live web fact-checking",
        ],
    },
    # ── Self-Discover ────────────────────────────────────────────────
    {
        "id": "self-discover-budget",
        "name": "Self-Discover (Budget)",
        "description": "Self-adaptive reasoning with cheap models. DeepSeek for selection, Qwen for adaptation, GLM for implementation.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini for JSON adherence
            "decomposition": "deepseek-v3",
            "sd_select": "deepseek-v3",
            "sd_adapt": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "sd_implement": "deepseek-v3",
            "scoring": "qwen3.5-flash",
            "stress_testing": "mistral-small",
            "synthesis": "qwen3.7-max"  # v3.1: upgraded to qwen3.7
        },
        "fallback_routing": {
            "prompt_enhancement": "glm-4-air",
            "classification": "glm-4-air",
            "decomposition": "glm-4-air",
            "sd_select": "qwen3-plus",
            "sd_adapt": "deepseek-v3",
            "sd_implement": "deepseek-v3",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-4-air"
        },
        "notes": [
            "DeepSeek for selection: strong reasoning",
            "Qwen for adaptation: good at structured adaptation",
            "GLM for implementation: cheap but capable",
            "DeepSeek V3: decomposition backbone — stronger structured reasoning than Gemini Flash Lite at comparable cost.",
            "Gemini Flash Lite: reserved for coordination roles (prompt_enhancement, constructive) — JSON formatting, low-stakes structure."
        ],
    },
    {
        "id": "self-discover-premium",
        "name": "Self-Discover (Premium)",
        "description": "Elite self-discovery. Claude for selection, Kimi K2.6 for adaptation, Perplexity for evidence evaluation.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "sd_select": "claude-sonnet",
            "sd_adapt": "kimi-k2-6",
            "sd_implement": "deepseek-r1t2-chimera",
            "scoring": "sonar-pro",
            "stress_testing": "deepseek-r1t2-chimera",
            "synthesis": "mimo-v2-pro"
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "deepseek-r1",
            "decomposition": "gemini-flash",
            "sd_select": "qwen3-plus",
            "sd_adapt": "claude-sonnet",
            "sd_implement": "qwen3-plus",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "gpt-5"
        },
        "required_tier": "pro",
        "notes": [
            "MiMo V2 Pro for decomposition and synthesis: strong reasoning capabilities.",
            "MiMo V2 Flash for efficient early-phase prompt enhancement and classification.",
            "Claude for selection: constitutional AI training",
            "Kimi K2.6 for adaptation: 1T MoE, agentic adaptation with 256K context",
            "Perplexity Sonar Pro for evidence evaluation: live web fact-checking",
        ],
    },
    # ── SubAgent presets (v2.2) ──────────────────────────────────────
    # These presets are designed for the PhaseSubAgent architecture.
    # They route each subagent to a specific model with cross-lab fallbacks.
    {
        "id": "subagent-budget",
        "name": "SubAgent (Budget)",
        "description": "Per-subagent routing with cheap cross-lab models. Each subagent gets a dedicated model + fallback.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini for JSON adherence
            "decomposition": "deepseek-v3",
            "constructive": "seed-2.0-mini",  # v3.3: gemini-flash-lite → seed-2.0-mini (ByteDance, Feb 2026)
            "destructive": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "systemic": "glm-5.1",  # v3.1: upgraded from glm-4.7-flash
            "minimalist": "ministral-3b",
            "scoring": "qwen3.5-flash",
            "stress_testing": "mistral-small",
            "synthesis": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "subagent_synthesis_analysis": "deepseek-v3",
            "subagent_synthesis_writer": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "subagent_critique_logic": "glm-4-air",
            "subagent_critique_evidence": "deepseek-v3",
            "subagent_critique_bias": "mistral-small",
            "subagent_critique_counter": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "subagent_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi, consistent with prompt_enhancement)
            "subagent_decomposition": "deepseek-v3",
            "subagent_search_query": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "subagent_search_eval": "glm-4-air",
        },
        "fallback_routing": {
            "prompt_enhancement": "glm-4-air",
            "classification": "glm-4-air",
            "decomposition": "glm-4-air",
            "constructive": "qwen3-plus",
            "destructive": "deepseek-v3",
            "systemic": "deepseek-v3",
            "minimalist": "deepseek-v3",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-4-air",
            "subagent_synthesis_analysis": "qwen3-plus",
            "subagent_synthesis_writer": "deepseek-v3",
            "subagent_critique_logic": "deepseek-v3",
            "subagent_critique_evidence": "glm-4-air",
            "subagent_critique_bias": "qwen3-plus",
            "subagent_critique_counter": "deepseek-v3",
            "subagent_enhancement": "glm-4-air",
            "subagent_decomposition": "glm-4-air",
            "subagent_search_query": "deepseek-v3",
            "subagent_search_eval": "qwen3-plus",
        },
        "notes": [
            "Every subagent has a cross-lab fallback (different provider)",
            "DeepSeek + Qwen + GLM + Gemma: 4 different labs",
            "Estimated <$0.02 per subagent run",
            "Gemini Flash Lite: low-cost primary workhorse with reliable JSON output in subagent roles."
        ],
    },
    {
        "id": "subagent-premium",
        "name": "SubAgent (Premium)",
        "description": "Elite per-subagent routing with top models. Each subagent gets a dedicated top model + fallback.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "constructive": "claude-sonnet",
            "destructive": "kimi-k2-6",
            "systemic": "deepseek-r1t2-chimera",
            "minimalist": "gemini-flash",
            "scoring": "sonar-pro",
            "stress_testing": "deepseek-r1t2-chimera",
            "synthesis": "gemini-pro",
            "subagent_synthesis_analysis": "deepseek-r1t2-chimera",
            "subagent_synthesis_writer": "claude-sonnet",
            "subagent_critique_logic": "gemini-pro",
            "subagent_critique_evidence": "sonar-pro",
            "subagent_critique_bias": "deepseek-r1t2-chimera",
            "subagent_critique_counter": "claude-sonnet",
            "subagent_enhancement": "gemini-pro",
            "subagent_decomposition": "deepseek-r1t2-chimera",
            "subagent_search_query": "gemini-pro",
            "subagent_search_eval": "claude-sonnet",
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "deepseek-r1",
            "decomposition": "gemini-flash",
            "constructive": "qwen3-plus",
            "destructive": "claude-sonnet",
            "systemic": "qwen3-plus",
            "minimalist": "deepseek-r1",
            "scoring": "qwen3-plus",
            "stress_testing": "qwen3-plus",
            "synthesis": "gpt-5",
            "subagent_synthesis_analysis": "qwen3-plus",
            "subagent_synthesis_writer": "deepseek-r1",
            "subagent_critique_logic": "deepseek-r1",
            "subagent_critique_evidence": "qwen3-plus",
            "subagent_critique_bias": "qwen3-plus",
            "subagent_critique_counter": "deepseek-r1",
            "subagent_enhancement": "deepseek-r1",
            "subagent_decomposition": "qwen3-plus",
            "subagent_search_query": "deepseek-r1",
            "subagent_search_eval": "qwen3-plus",
        },
        "notes": [
            "Gemini Pro: 1.6T MoE with 1M context, state-of-the-art reasoning effort.",
            "MiMo V2 Flash for efficient early-phase prompt enhancement and classification.",
            "SubAgent overhead: ~11.5 cents per run vs monolithic",
            "No Qwen 3.6 Plus — Sonnet handles writer tasks at 60% lower cost",
            "Gemini Flash for all parallel analysis: fast, cheap, high throughput",
            "DeepSeek R1 for reasoning tasks: 85K+ adversarial RL environments",
            "Sonar Pro for evidence/source evaluation: live web fact-checking",
            "Every subagent has cross-lab fallback (different provider)",
        ],
    },
    # ── Writing (Research-Backed Article) ────────────────────────────
    {
        "id": "writing-budget",
        "name": "Writing / Article (Budget)",
        "description": "Research-backed article generation with CoVE, Pre-Mortem, and SoT using cheap cross-lab models. DeepSeek decomposes + CoVE verifies, Mistral extracts, Kimi K2.6 synthesizes via SoT, DeepSeek-R1 criticizes with Pre-Mortem. Estimated <$0.05 per article.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "article_decompose": "deepseek-v3",
            "article_claim_extract": "mistral-small",
            "article_cove_verify": "deepseek-v3",
            "article_cove_answer": "seed-2.0-mini",  # v3.3: gemini-flash-lite → seed-2.0-mini (ByteDance, short structured answers)
            "article_cove_revise": "glm-4-air",
            "article_verifier": "glm-4-air",
            "article_sot_skeleton": "deepseek-v3",
            "article_sot_solve": "kimi-k2-6",
            "article_synthesize": "kimi-k2-6",
            "article_pre_mortem": "mistral-small",
            "article_critic": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "article_assemble": "kimi-k2-6",
            "article_revise": "kimi-k2-6",
            "article_humanize": "kimi-k2-6",
        },
        "fallback_routing": {
            "article_decompose": "glm-4-air",
            "article_claim_extract": "deepseek-v3",
            "article_cove_verify": "mistral-large-3",
            "article_cove_answer": "glm-4-air",
            "article_cove_revise": "glm-4-air",
            "article_verifier": "mistral-large-3",
            "article_sot_skeleton": "glm-4-air",
            "article_sot_solve": "deepseek-v3",
            "article_synthesize": "deepseek-v3",
            "article_pre_mortem": "mistral-large-3",
            "article_critic": "mistral-large-3",
            "article_assemble": "deepseek-v3",
            "article_revise": "deepseek-v3",
            "article_humanize": "deepseek-v3",
        },
        "notes": [
            "DeepSeek V3: decompose + sot_skeleton + cove_verify — reasoning backbone for article structure",
            "Mistral Small: claim extraction + pre_mortem — adversarial/factual European-lab perspective",
            "Qwen3-Max: critic — independent adversarial review from different lab than generator",
            "Kimi K2.6: SoT section writing, synthesis, assembly — 1T MoE, 256K context, best OSS writing model",
            "GLM-4-Air: cove_revise + verifier — light correction/verification tasks",
            "Gemini Flash Lite: cove_answer only — short structured answer, low stakes",
            "Estimated <$0.05 per article"
        ],
    },
    {
        "id": "writing-premium",
        "name": "Writing / Article (Premium)",
        "description": "Elite article generation with CoVE, Pre-Mortem, and SoT. Claude Sonnet handles decomposition, CoVE, and verification. GLM-5.1 synthesizes, critiques, and assembles with 200K context and 34% hallucination rate. Estimated $0.15-0.20 per article.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "article_decompose": "mimo-v2-flash",
            "article_claim_extract": "claude-sonnet",
            "article_cove_verify": "claude-sonnet",
            "article_cove_answer": "claude-sonnet",
            "article_cove_revise": "claude-sonnet",
            "article_verifier": "claude-sonnet",
            "article_sot_skeleton": "claude-sonnet",
            "article_sot_solve": "glm-5.1",
            "article_synthesize": "gemini-pro",
            "article_pre_mortem": "gemini-pro",
            "article_critic": "gemini-pro",
            "article_assemble": "glm-5.1",
            "article_revise": "glm-5.1",
            "article_humanize": "glm-5.1",
        },
        "fallback_routing": {
            "article_decompose": "gpt-5",
            "article_claim_extract": "gpt-5",
            "article_cove_verify": "gpt-5",
            "article_cove_answer": "gpt-5",
            "article_cove_revise": "gpt-5",
            "article_verifier": "grok-4.20",
            "article_sot_skeleton": "gpt-5",
            "article_sot_solve": "claude-sonnet",
            "article_synthesize": "claude-sonnet",
            "article_pre_mortem": "claude-sonnet",
            "article_critic": "claude-sonnet",
            "article_assemble": "claude-sonnet",
            "article_revise": "claude-sonnet",
            "article_humanize": "claude-sonnet",
        },
        "notes": [
            "MiMo V2 Pro for decomposition, synthesis, pre-mortem, and critique.",
            "MiMo V2 Flash for efficient early-phase article decomposition.",
            "Claude Sonnet: decomposition, claim extract, CoVE all steps, verification — best reasoning",
            "GLM-5.1: SoT section writing, synthesis, assembly, pre-mortem, critic — 200K context, 34% hallucination rate, SWE-bench 77.8%, honest self-criticism",
            "Grok 4.20: fallback for hostile review — xAI adversarial training excels at contradiction detection",
            "Every phase has cross-provider fallback (Anthropic ↔ OpenAI ↔ xAI)",
            "Critical bottleneck (CoVE verify + verifier): Claude's constitutional AI for contradiction detection",
        ],
    },
    # ── Article (4-Phase Source-Grounded Article) ───────────────────
    {
        "id": "article-budget",
        "name": "Article (Budget)",
        "description": "4-phase source-grounded article pipeline: retrieve sources, draft, adversarial verify, refine. DeepSeek V3 plans retrieval and drafts, Mistral Small adversarially verifies claims, Qwen3.7-Max synthesizes. Estimated <$0.05 per article.",
        "primary_id": "deepseek-v3",
        "routing": {
            "writing_draft":    "deepseek-v3",
            "writing_factcheck": "mistral-small",
            "writing_assemble": "qwen3-plus",
            "synthesis":        "qwen3.7-max",
        },
        "fallback_routing": {
            "writing_draft":    "qwen3-plus",
            "writing_factcheck": "deepseek-v3",
            "writing_assemble": "glm-4-air",
            "synthesis":        "glm-4-air",
        },
        "notes": [
            "DeepSeek V3: retrieval planning + drafting — HumanEval 82.6%, strong structured prose",
            "Mistral Small: adversarial verification — different lab prevents same-model confirmation bias",
            "Qwen3-Plus: refinement assembly — 32B MoE, coherent long-form editing",
            "Qwen3.7-Max: synthesis — state-of-the-art Alibaba model for final polish",
            "3-lab diversity: DeepSeek + Mistral + Alibaba",
            "Estimated <$0.05 per article",
        ],
    },
    {
        "id": "article-premium",
        "name": "Article (Premium)",
        "description": "4-phase premium source-grounded article pipeline: retrieve sources, draft, adversarial verify, refine. Claude Sonnet plans and drafts, Gemini Pro adversarially verifies, GLM-5.1 refines and synthesizes. Estimated $0.15–$0.25 per article.",
        "primary_id": "claude-sonnet",
        "required_tier": "pro",
        "routing": {
            "writing_draft":    "claude-sonnet",
            "writing_factcheck": "gemini-pro",
            "writing_assemble": "glm-5.1",
            "synthesis":        "gemini-pro",
        },
        "fallback_routing": {
            "writing_draft":    "gemini-pro",
            "writing_factcheck": "claude-sonnet",
            "writing_assemble": "claude-sonnet",
            "synthesis":        "claude-sonnet",
        },
        "notes": [
            "Claude Sonnet: retrieval planning + drafting — best long-form coherence and source integration",
            "Gemini Pro: adversarial fact verification + synthesis — 2M context, strong reasoning",
            "GLM-5.1: refinement assembly — 200K context, 34% hallucination rate, excellent editing",
            "Cross-ecosystem: Anthropic + Google + Zhipu for maximum epistemic diversity",
            "Fallback maintains cross-lab independence: Anthropic ↔ Google on failure",
            "Estimated $0.15–$0.25 per article",
        ],
    },
    # ── Coding (Production Code Generation) ─────────────────────────
    {
        "id": "coding-budget",
        "name": "Coding / Code Generation (Budget)",
        "description": "5-phase production code generation: spec → parallel file generation → adversarial security review → test generation → final assembly. DeepSeek V3 generates (HumanEval 82.6%), Qwen3-Max reviews adversarially, Kimi K2.6 assembles. Cross-lab diversity enforced.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "coding_spec": "deepseek-v4-flash",  # v3.3: gemini-flash-lite → deepseek-v4-flash (DeepSeek code spec, Apr 2026)
            "coding_generate": "deepseek-v3",
            "coding_review": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "coding_tests": "deepseek-v3",
            "coding_assemble": "kimi-k2-6",
            "synthesis": "kimi-k2-6",
        },
        "fallback_routing": {
            "coding_spec": "glm-4-air",
            "coding_generate": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "coding_review": "deepseek-v3",
            "coding_tests": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "coding_assemble": "deepseek-v3",
            "synthesis": "deepseek-v3",
        },
        "notes": [
            "DeepSeek V3: code generation + tests — HumanEval 82.6%, MBPP 84.2%, strong chain-of-thought",
            "Qwen3-Max: adversarial security review — different lab prevents same-model blind spots",
            "Kimi K2.6: spec analysis + final assembly — 1T MoE, SWE-bench 77.8%, 256K context",
            "Gemini Flash Lite: structural spec decomposition — reliable JSON, low cost",
            "3-lab diversity: Google (spec) + DeepSeek (generate) + Alibaba/Zhipu (review/assemble)",
            "Estimated <$0.05 per run",
        ],
    },
    {
        "id": "coding-premium",
        "name": "Coding / Code Generation (Premium)",
        "description": "Elite 5-phase code generation. Claude Sonnet specs (Anthropic RLHF + constitutional AI), Kimi K2.6 generates (SWE-bench 80.2%), DeepSeek R1T2 reviews adversarially, Claude Sonnet writes tests (best TDD reasoning), GPT-5 assembles final delivery (strongest integration pass). 4-lab cross-ecosystem. Estimated $0.20–$0.35 per run.",
        "primary_id": "claude-sonnet",
        "required_tier": "pro",
        "routing": {
            "coding_spec": "claude-sonnet",
            "coding_generate": "kimi-k2-6",
            "coding_review": "deepseek-r1t2-chimera",
            "coding_tests": "claude-sonnet",
            "coding_assemble": "gpt-5",
            "synthesis": "gpt-5",
        },
        "fallback_routing": {
            "coding_spec": "gemini-pro",
            "coding_generate": "claude-sonnet",
            "coding_review": "qwen3.6-plus",
            "coding_tests": "deepseek-r1t2-chimera",
            "coding_assemble": "claude-sonnet",
            "synthesis": "claude-sonnet",
        },
        "required_tier": "pro",
        "notes": [
            "Claude Sonnet: spec + tests — Anthropic RLHF produces safe architecture + thorough TDD coverage",
            "Kimi K2.6: code generation — 1T MoE, SWE-bench 80.2%, 256K context, best OSS coder",
            "DeepSeek R1T2 Chimera: adversarial review — adversarial RL training catches subtle security flaws",
            "GPT-5: final assembly — strongest cross-file integration, catches import/type inconsistencies",
            "4-lab cross-ecosystem: Anthropic + Moonshot + DeepSeek + OpenAI",
            "Fallback: Gemini Pro (Google) + Claude Sonnet — maintains cross-lab independence on failure",
            "Estimated $0.20–$0.35 per run",
        ],
    },
    # ── Cross-Language ───────────────────────────────────────────────
    {
        "id": "cross-language-budget",
        "name": "Cross-Language (Budget)",
        "description": "Multi-perspective reasoning with DeepL translation. Non-English problems are translated to English for reasoning, then the synthesis is translated back to the source language. Uses cheapest cross-lab models.",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini for JSON adherence
            "decomposition": "deepseek-v3",
            "constructive": "seed-2.0-mini",  # v3.3: gemini-flash-lite → seed-2.0-mini (ByteDance, Feb 2026)
            "destructive": "mistral-small",
            "systemic": "glm-5.1",  # v3.1: upgraded from glm-4.7-flash
            "minimalist": "ministral-3b",
            "scoring": "qwen3.5-flash",
            "stress_testing": "mistral-small",
            "synthesis": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
        },
        "fallback_routing": {
            "prompt_enhancement": "glm-4-air",
            "classification": "glm-4-air",
            "decomposition": "glm-4-air",
            "constructive": "qwen3-plus",
            "destructive": "deepseek-v3",
            "systemic": "qwen3-plus",
            "minimalist": "deepseek-v3",
            "scoring": "qwen3.5-flash",
            "stress_testing": "qwen3-plus",
            "synthesis": "glm-4-air",
        },
        "required_env_vars": ["OPENROUTER_API_KEY", "DEEPL_API_KEY"],
        "notes": [
            "Phase 2: Google + Mistral Small (destructive) + Zhipu GLM (systemic) = 3 labs",
            "Scoring: Qwen 3.5 Flash (Alibaba) — independent lab scorer",
            "DeepL free tier: 500K chars/month — sufficient for most use cases",
            "DeepL paid tier: 50M chars/month with next-gen model support",
            "Translation preserves formatting and line breaks",
            "DeepSeek V3: decomposition backbone — stronger structured reasoning than Gemini Flash Lite at comparable cost.",
            "Gemini Flash Lite: reserved for coordination roles (prompt_enhancement, constructive) — JSON formatting, low-stakes structure."
        ],
    },

    {
        "id": "cross-language-premium",
        "name": "Cross-Language (Premium)",
        "description": "Best available multi-perspective reasoning with DeepL translation. Non-English problems are translated to English for reasoning, then the synthesis is translated back with the highest-quality models.",
        "primary_id": "gemini-pro",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",
            "classification": "mimo-v2-flash",
            "decomposition": "gemini-pro",
            "constructive": "qwen3.6-plus",
            "destructive": "claude-sonnet",
            "systemic": "qwen3.6-plus",
            "minimalist": "gemini-pro",
            "scoring": "qwen3.6-plus",
            "stress_testing": "qwen3.6-plus",
            "synthesis": "gemini-pro",
        },
        "fallback_routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "claude-sonnet",
            "decomposition": "claude-sonnet",
            "constructive": "claude-sonnet",
            "destructive": "gemini-pro",
            "systemic": "claude-sonnet",
            "minimalist": "claude-sonnet",
            "scoring": "claude-sonnet",
            "stress_testing": "claude-sonnet",
            "synthesis": "claude-sonnet",
        },
        "required_env_vars": ["OPENROUTER_API_KEY", "DEEPL_API_KEY"],
        "notes": [
            "MiMo V2 Pro for decomposition and synthesis: strong reasoning capabilities.",
            "MiMo V2 Flash for efficient early-phase prompt enhancement and classification.",
            "DeepL paid tier recommended for high-volume usage",
            "Perplexity Sonar fact-checks candidates in Phase 3 (if enabled)",
            "Qwen 3.6 Plus and GLM-5.1 dual-check synthesis",
            "Cross-ecosystem for maximum epistemic diversity",
        ],
    },
    # ── NVIDIA NIM (Experimental) ────────────────────────────────────
    {
        "id": "nvidia-nemotron-test",
        "name": "NVIDIA Nemotron (Test)",
        "description": "Experimental preset using NVIDIA Nemotron-3-Super-120B-A12B via NIM free tier. Designed for --sequential mode to stay within 40 RPM limit. NOT for production use.",
        "primary_id": "nvidia-nemotron-super",
        "routing": {
            "prompt_enhancement": "nvidia-nemotron-super",
            "classification": "nvidia-nemotron-super",
            "decomposition": "nvidia-nemotron-super",
            "constructive": "nvidia-nemotron-super",
            "destructive": "nvidia-nemotron-super",
            "systemic": "nvidia-nemotron-super",
            "minimalist": "nvidia-nemotron-super",
            "scoring": "nvidia-nemotron-super",
            "stress_testing": "nvidia-nemotron-super",
            "synthesis": "nvidia-nemotron-super",
        },
        "fallback_routing": {
            "prompt_enhancement": "gemma-4-26b",
            "classification": "gemma-4-26b",
            "decomposition": "deepseek-v3",
            "constructive": "deepseek-v3",
            "destructive": "mistral-large-3",
            "systemic": "deepseek-v3",
            "minimalist": "gemma-4-26b",
            "scoring": "qwen3.5-flash",
            "stress_testing": "deepseek-v3",
            "synthesis": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
        },
        "required_env_vars": ["NVIDIA_API_KEY"],
        "notes": [
            "NVIDIA NIM free tier: 1,000 credits, 40 RPM hard cap",
            "Use ONLY with --sequential flag: python main.py --preset nvidia-nemotron-test --sequential",
            "Parallel mode will hit 429 rate limit errors instantly",
            "Nemotron-3-Super: 120B MoE / 12B active. NVIDIA-developed model — new lab diversity",
            "Fallback chain uses OpenRouter models if NVIDIA API fails",
        ],
    },
    # ── Image Generation ─────────────────────────────────────────────
    # ── Brainstorming / Verbalized Sampling ────────────────────────────────────
    {
        "id": "brainstorming-budget",
        "name": "Brainstorming (Budget)",
        "description": (
            "Verbalized Sampling idea generator. Qwen3-Max runs 3 VS rounds × 5 ideas = 15 raw ideas. "
            "Gemini Flash Lite clusters and scores. DeepSeek-V3 develops the top 3. "
            "Designed for creative and open-ended problems. ~$0.03/run."
        ),
        "primary_id": "gemini-flash-lite",
        "routing": {
            "prompt_enhancement":  "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification":      "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini
            "decomposition":       "deepseek-v3",
            "brainstorm_generate": "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "brainstorm_cluster":  "seed-2.0-mini",  # v3.3: gemini-flash-lite → seed-2.0-mini (ByteDance, clustering)
            "brainstorm_develop":  "deepseek-v3",
            "synthesis":           "qwen3.7-max",  # v3.1: upgraded from qwen3-max
        },
        "fallback_routing": {
            "prompt_enhancement":  "glm-4-air",
            "classification":      "glm-4-air",
            "decomposition":       "glm-4-air",
            "brainstorm_generate": "deepseek-v3",
            "brainstorm_cluster":  "glm-4-air",
            "brainstorm_develop":  "qwen3-plus",
            "synthesis":           "glm-4-air",
        },
        "notes": [
            "VS-Standard variant: single-turn k=5 per round, 3 rounds = 15 raw ideas",
            "Qwen3-Max: strong semantic diversity for idea generation",
            "DeepSeek-V3: concrete implementation reasoning for development phase",
            "Full run estimated at ~$0.03",
        ],
        "brainstorming_config": {
            "rounds": 3, "k": 5, "threshold": 0.10, "n_tail": 2,
            "max_develop": 3, "use_cot": False,
        },
    },
    {
        "id": "brainstorming-premium",
        "name": "Brainstorming (Premium)",
        "description": (
            "VS-CoT + VS-Multi: Claude Sonnet runs 5 VS-CoT rounds × 5 ideas = 25 raw ideas "
            "with chain-of-thought reasoning before each generation. "
            "Gemini Pro clusters. Kimi k2 develops the top 5 most innovative ideas. ~$0.25/run."
        ),
        "primary_id": "claude-sonnet",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement":  "claude-sonnet",
            "classification":      "gpt-5-mini",  # v3.1: upgraded from gpt-4o-mini
            "decomposition":       "claude-sonnet",
            "brainstorm_generate": "claude-sonnet",
            "brainstorm_cluster":  "gemini-pro",
            "brainstorm_develop":  "kimi-k2-6",
            "synthesis":           "claude-sonnet",
        },
        "fallback_routing": {
            "prompt_enhancement":  "gemini-pro",
            "classification":      "gemini-pro",
            "decomposition":       "gemini-pro",
            "brainstorm_generate": "gemini-pro",
            "brainstorm_cluster":  "qwen3.7-max",  # v3.1: upgraded from qwen3-max
            "brainstorm_develop":  "deepseek-v3",
            "synthesis":           "gemini-pro",
        },
        "notes": [
            "VS-CoT + VS-Multi: chain-of-thought prefix + multi-turn diversity",
            "Claude Sonnet: best emergent probability introspection capability",
            "Kimi k2 for development: strong at structured long-form concrete reasoning",
            "5 rounds × 5 ideas = 25 raw ideas before clustering",
            "Full run estimated at ~$0.25",
        ],
        "brainstorming_config": {
            "rounds": 5, "k": 5, "threshold": 0.05, "n_tail": 3,
            "max_develop": 5, "use_cot": True,
        },
    },
    {
        "id": IMAGE_GEN_BUDGET_PRESET,
        "name": "Image Generation (Budget)",
        "description": "Generate images using Riverflow v2 Fast Preview and Gemini Flash Image as primary models, with Seedream 4.5 and Flux 2 Pro as fallbacks.",
        "primary_id": "riverflow-v2-fast-preview",
        "routing": {},
        "fallback_routing": {},
        "notes": [
            "Riverflow v2 Fast Preview: optimized for speed with good quality",
            "Gemini Flash Image: Google multimodal model with fast generation and strong instruction following",
            "Seedream 4.5 fallback: ByteDance's capable image model",
            "Flux 2 Pro fallback: higher quality with more detail",
        ],
    },
    {
        "id": IMAGE_GEN_PREMIUM_PRESET,
        "name": "Image Generation (Premium)",
        "description": "Generate images using Gemini 3 Pro Image Preview and GPT-5 Image as primary models, with Gemini 3.1 Flash Image Preview and Gemini Flash Image as fallbacks.",
        "primary_id": MODEL_GEMINI_PRO_IMAGE,
        "required_tier": "pro",
        "routing": {},
        "fallback_routing": {},
        "notes": [
            "Gemini 3 Pro Image Preview primary: $2/M input, $12/M output — best text-in-image, 2K/4K support",
            "GPT-5 Image primary: OpenAI flagship with excellent instruction following",
            "Gemini 3.1 Flash Image Preview fallback: fast high-quality safety net",
            "Gemini Flash Image final fallback: speed-optimized multimodal safety net",
        ],
    },
    # v3.1: Iterative Critique (LLM Debate)
    {
        "id": "iterative-critique-budget",
        "name": "Iterative Critique / LLM Debate (Budget)",
        "description": "Adversarial generator-critic loop with convergence detection. DeepSeek generator, Qwen critic.",
        "primary_id": "deepseek-v3",
        "required_tier": "free",
        "routing": {
            "prompt_enhancement": "mimo-v2-flash",  # v3.3: gemini-flash-lite → mimo-v2-flash (Xiaomi lab diversity)
            "classification": "gpt-5-mini",
            "decomposition": "deepseek-v3",
            "expert_1": "deepseek-v3",
            "expert_2": "deepseek-v4-flash",  # v3.1: faster critic, avoids Qwen 45s timeouts
            "synthesis": "qwen3.7-max",
        },
        "fallback_routing": {
            "expert_1": "glm-5.1",
            "expert_2": "glm-5.1",
            "synthesis": "glm-5.1",
        },
    },
    {
        "id": "iterative-critique-premium",
        "name": "Iterative Critique / LLM Debate (Premium)",
        "description": "GPT-5 generator, Claude Sonnet critic - maximum cross-lab adversarial quality.",
        "primary_id": "gpt-5",
        "required_tier": "pro",
        "routing": {
            "prompt_enhancement": "claude-sonnet",
            "classification": "gpt-5",
            "decomposition": "claude-sonnet",
            "expert_1": "gpt-5",
            "expert_2": "claude-sonnet",
            "synthesis": "gpt-5",
        },
        "fallback_routing": {
            "expert_1": "deepseek-v3",
            "expert_2": "deepseek-v4-flash",  # v3.1: faster critic, avoids Qwen 45s timeouts
            "synthesis": "deepseek-v3",
        },
    },

]


PRESETS: dict[str, PipelinePreset] = {
    cfg["id"]: PipelinePreset(
        name=cfg["name"],
        description=cfg["description"],
        primary_id=cfg["primary_id"],
        routing=cfg.get("routing", {}),
        notes=cfg.get("notes", []),
        required_env_vars=cfg.get("required_env_vars", ["OPENROUTER_API_KEY"]),
        fallback_routing=cfg.get("fallback_routing", {}),
        required_tier=cfg.get("required_tier", SubscriptionTier.FREE),
        top_k=cfg.get("top_k", 2),
        parallel_perspectives=cfg.get("parallel_perspectives", True),
        enhance_prompt=cfg.get("enhance_prompt", False),
        skip_stress_test=cfg.get("skip_stress_test", False),
        skip_deep_read=cfg.get("skip_deep_read", False),
        batch_critique_jury=cfg.get("batch_critique_jury", False),
        cascading_routing=cfg.get("cascading_routing", {}),
        brainstorming_config=cfg.get("brainstorming_config", {}),
    )
    for cfg in _PRESET_CONFIGS
}

# Every method must have exactly one Budget and one Premium variant.
_preset_ids = list(PRESETS.keys())
assert len(_preset_ids) % 2 == 0, (
    f"Expected an even number of presets (Budget+Premium pairs), got {len(_preset_ids)}. "
    f"Add or remove a preset to restore pairing. Presets: {_preset_ids}"
)

assert len(PRESETS) % 2 == 0, (
    f"PRESETS count must be even (budget+premium pairs): got {len(PRESETS)}. "
    "Add the missing paired preset or mark the lone preset as experimental."
)
