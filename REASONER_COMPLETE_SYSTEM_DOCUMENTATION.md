# Reasoner: Complete System Documentation

**Version:** 2.2 | **Python:** 3.12+ | **Frontend:** Next.js 16 / React 19 / TypeScript 5

> This document provides a comprehensive description of the Reasoner adaptive reasoning architecture: its philosophy, methodology, pipeline workflow, model routing strategy, and orchestration patterns.

---

## 1. PHILOSOPHY & CORE PRINCIPLES

### Foundational Philosophy

**Reasoning as a First-Class Engineering Problem**

Reasoner treats complex problem-solving not as a simple chatbot interaction but as a structured, multi-phase reasoning system. The core premise: high-quality reasoning requires decomposition, multi-perspective analysis, independent critique, stress-testing, and epistemic labeling.

### Core Tenets

1. **Multi-Perspective Reasoning (Ensemble Cognition)**
   - Generate 4 independent cognitive perspectives on each problem:
     - **Constructive**: Build best-case solution
     - **Destructive**: Identify weaknesses, attack assumptions
     - **Systemic**: Holistic interactions, second-order effects
     - **Minimalist**: Simplest viable approach
   - No single model monopolizes output
   - Jury scoring aggregates perspectives (not consensus, but evidence-based selection)

2. **Cross-Bloc Epistemic Diversity** 
   - Research (Buyl et al., npj AI 2026) shows LLM responses are shaped by company geopolitical bloc
   - **Bloc taxonomy**: 🇺🇸 US labs (Anthropic, OpenAI, Google, xAI) | 🇪🇺 European (Mistral, Perplexity) | 🇨🇳 Chinese (DeepSeek, Qwen, Tencent, MiniMax)
   - Presets enforce:
     - Synthesis model ≠ scoring model blocs (prevent bloc consensus distortion)
     - Perspective generators span ≥2 blocs, ≤2 models per bloc (echo-chamber resistance)
   - Failing to enforce bloc diversity = echo chamber masquerading as ensemble

3. **Immutable State Flow**
   - `PipelineState` is append-only between phases; no backward mutation
   - Phase results collected in `phase_results[]` array
   - Sequential reducers (`PhaseOutput.apply_to()`) transform state deterministically
   - Enables event-sourced replay, audit trails, reproducibility

4. **Event-Sourced Execution**
   - All transitions, fallbacks, cost tracking emit `DomainEvent` objects
   - Event store captures: PHASE_STARTED, PHASE_COMPLETED, MODEL_FALLBACK, COST_TRACKED, CRITERIA_MET
   - Replay possible: reconstruct state from event log for post-hoc analysis or debugging

5. **Composable Workflows**
   - Strategy pattern: each reasoning method (debate, research, scientific) is a distinct workflow
   - WorkflowFactory.create(method) → method-specific flow object
   - No God Object; method-specific state stored in `state.method_state[method_name]`
   - Enables A/B testing, method-specific optimizations, clear separation of concerns

### Epistemological Approach

**Safety via Validation Pipeline**

1. **Input Layer**: `sanitize_for_prompt()`
   - Strip URLs, email addresses, phone numbers
   - Remove suspicious patterns (SQL keywords, shell commands)
   - Normalize Unicode (NFKC)
   - Defend against prompt injection

2. **Output Layer**: `extract_json()`, `safe_list()`, `safe_float()`
   - Graceful degradation if LLM output malformed
   - Fallback to backup parsing strategies
   - Never crash on unexpected model output

3. **Claim Labeling**: `ClaimLabel` enum
   - **VERIFIED**: Cross-validated, sourced, independent confirmation
   - **HYPOTHESIS**: Plausible but untested, requires verification
   - **UNKNOWN**: Insufficient evidence, explicit uncertainty
   - Enables consumer-side filtering and decision-making

**Iterative Refinement & Feedback Loops**

1. **Critique→Synthesis Loop**
   - Phase 4 (Critique) scores candidates across 4 dimensions
   - Phase 5 (Synthesis) synthesizes top candidates + review hypotheses
   - Optional review hypotheses (premium tier): independent failure analysis with confidence

2. **Stress-Testing**
   - Optimal scenario: best-case constraints, all assumptions hold
   - Constraint-violation scenario: what breaks? edge cases?
   - Adversarial scenario: intelligent opponent finding weaknesses
   - Builds confidence that recommendation is robust

3. **Language Pivot (Multilingual)**
   - Non-English queries translated to English for core reasoning
   - Core reasoning in English (most models fine-tuned here)
   - Results translated back to source language at output
   - Reduces hallucination from reasoning in lower-resource languages

---

## 2. PIPELINE ARCHITECTURE (PHASES 0–5)

### Complete Phase Sequence

```
Request → Preflight (preset resolution, Neuro recall, HyperGate) →
Phase 0: HyperGate Pre-Router (direct/web_search/pipeline decision) →
Phase 1: Enhancement (optional problem rewrite) →
Phase 2: Decomposition (sub-problems, assumptions, failure modes) →
Phase 3: Generation (method-specific candidate generation) →
Phase 4: Critique (scoring, stress-testing, review hypotheses) →
Phase 5: Synthesis (aggregate candidates, finalize answer) →
Postflight (Neuro learn, history save, telemetry)
```

### Phase 0: HyperGate Pre-Router

**Concept**: Five parallel sub-agents run in parallel with intelligent tie-breaking. Goal: classify problem intent before expensive reasoning.

**Architecture**:

```
Problem → [
  DirectDetector (pattern-match factual queries, creative requests),
  WebSearchDetector (temporal/news/real-time patterns),
  ComplexityEstimator (decompose problem structure, assess depth),
  LanguageDetector (identify non-English, activate translation),
  MethodClassifier (recommend method: debate, research, etc.)
] (async, independent budgets)
     ↓ TieBreaker (reconcile conflicts)
     ↓
GateDecision(action: "direct"|"web_search"|"pipeline", method, reasoning)
```

**Sub-Agent Roles**:

| Sub-Agent | Input | Output | Decision Trigger |
|-----------|-------|--------|------------------|
| **DirectDetector** | Problem | `confidence: [0,1]` | >0.8 → direct answer, skip pipeline |
| **WebSearchDetector** | Problem | `needs_web: bool` | True → invoke web_search, real-time grounding |
| **ComplexityEstimator** | Problem | `depth: [1,5]` | 1–2 → budget method, 4–5 → premium |
| **LanguageDetector** | Problem | `lang: str, needs_pivot: bool` | Non-English ∧ needs_pivot=True → translate |
| **MethodClassifier** | Problem | `method: str` | Recommended method (debate, research, etc.) |
| **TieBreakerSubAgent** | All above | `tiebreak_reasoning: str` | Reconciles conflicts, breaks ambiguity |

**Fast-Path Optimization**:
Before any sub-agent fires:
1. Short prompt (<50 words) → assume direct answer
2. Writing intent keywords ("write", "compose", "draft") → writing method
3. Realtime patterns ("latest", "recent", "today") → web_search
4. Factual patterns ("define", "who is", "what is") → direct detector

**Output**: `GateDecision` stored in state.hypergate_decision; controls downstream phase skipping

### Phase 1: Enhancement (Optional)

**Trigger**: Explicit flag or adaptive (complexity > threshold)

**Sub-Agent**: Enhancement Agent

**Process**:
1. Reads problem.problem text
2. Generates improved version:
   - Adds missing context hints
   - Highlights implicit constraints
   - Clarifies ambiguous terms
   - Suggests relevant frameworks

**Output**: Enhanced problem text stored in `state.core.enhanced_problem`; used in Phases 3–5

**Cost**: Minimal (single model call); skipped by default in budget preset

### Phase 2: Decomposition (Optional, Async)

**Sub-Agent**: Decomposition Sub-Agent

**Process**:

1. **Sub-Problem Extraction**:
   - Identifies ≤5 independent sub-problems
   - Builds dependency DAG
   - Marks critical path

2. **Assumption Surfacing**:
   - Lists problem assumptions (e.g., "Assumes X availability")
   - Tags each with claim label (VERIFIED | HYPOTHESIS | UNKNOWN)
   - Surfaces hidden assumptions

3. **Failure Mode Analysis**:
   - What could break this solution?
   - Which assumptions are most brittle?
   - What external dependencies are risky?

**Output**: `Decomposition` object with:
```python
{
  "sub_problems": [SubProblem(text, criticality, dependencies)],
  "assumptions": [Assumption(text, claim_label, risk_level)],
  "failure_modes": [FailureMode(scenario, impact, mitigation)]
}
```

**Stored in**: `state.phase_results[2].decomposition`

### Phase 3: Generation (Method-Specific Candidate Generation)

**Concept**: Core reasoning phase; output depends entirely on method.

#### Generation by Method

| Method | Process | Candidate Count | Output Type |
|--------|---------|-----------------|------------|
| **multi-perspective** | 4 parallel perspectives, each generates solution | 4 | SolutionCandidate[] |
| **debate** | Side A (pro) → Side B (con) → Judge analysis | 3 | DebateRound[] + JudgeAnalysis |
| **jury** | Orchestrated multi-critic: generator, critic, verifier | 3 | JuryVote[] + ranking |
| **research** | Web search → context retrieval → draft | 1–3 | ResearchCandidate[] + citations |
| **article** | Source retrieval → outline → draft → fact-check | 1 | ArticleCandidate + metadata |
| **coding** | Spec analysis → code generation → review analysis | 3–5 | CodeCandidate[] + explanations |
| **sot** (Skeleton-of-Thought) | Outline skeleton → parallel detailed solves | 3–5 | SkeletonCandidate[] + fills |
| **tot** (Tree-of-Thought) | Explore reasoning tree, evaluate paths | Variable | TreePath[] + scores |
| **pot** (Program-of-Thought) | Convert problem to executable program | 1–3 | ProgramCandidate[] + traces |
| **scientific** | Hypothesis → test → falsification | 3–5 | HypothesisCandidate[] + evidence |
| **debate** | Adversarial exchange, pro/con analysis | 2–3 | DebatePosition[] |
| **socratic** | Iterative questioning, assumption surfacing | Variable | SocraticDialogue + insights |
| **pre-mortem** | Failure scenario analysis, recovery plans | 3–5 | FailureScenario[] + mitigations |
| **bayesian** | Prior → likelihood → posterior belief | 1–2 | BayesianUpdate + probabilities |
| **dialectical** | Thesis-antithesis-synthesis cycles | 3 | DialecticalPhase[] |
| **analogical** | Cross-domain pattern mapping | 3–5 | AnalogyMapping[] + insights |
| **delphi** | Iterative expert consensus | 2–3 | DelphiRound[] + consensus |
| **cove** | Claim verification, fact-checking cycles | 1 | VerificationChain[] |
| **brainstorming** | Divergent idea generation via Verbalized Sampling | 10–20 | Idea[] + clusters |
| **writing** | Outline → draft → revise → final | 1 | WritingCandidate + drafts |
| **cross-language** | Multilingual reasoning with bloc diversity | 2–4 | CandidateByLanguage[] |
| **iterative-critique** | Adversarial rounds, convergence detection | Variable | ConvergencePath[] |

**Key Invariants**:

1. **Bloc Diversity Enforcement**: At generation time, perspective generators span ≥2 blocs, ≤2 models per bloc
2. **Token Budget**: Each generation constrained by `PHASE_TOKEN_BUDGETS["gen"]` (e.g., 8000 for budget, 16000 for premium)
3. **Timeout Enforcement**: Each generation model call respects `ROLE_TIMEOUTS["generation_perspective_*"]`
4. **Fallback Routing**: If primary model unavailable, cascading router tries alternate models in same bloc, then cross-bloc

**Output**: `state.phase_results[3].candidates = SolutionCandidate[]`

### Phase 4: Critique (Multi-Critic Scoring & Stress Testing)

**Concept**: Independent evaluation of candidates using multiple scoring dimensions and stress scenarios.

#### Scoring Dimensions

| Dimension | Question | Range | Model Role |
|-----------|----------|-------|-----------|
| **Factuality** | Is this factually accurate? Evidence-based? | 0–10 | Bias-checker |
| **Reasoning Quality** | Sound logic? Valid inferences? Gaps? | 0–10 | Logic-verifier |
| **Completeness** | Does it address all aspects? Missing pieces? | 0–10 | Completeness-reviewer |
| **Helpfulness** | Actionable? Relevant? Practical? | 0–10 | Usefulness-evaluator |

#### Stress-Testing Scenarios

1. **Optimal Case**: All assumptions hold, all constraints satisfied
   - Does solution thrive or just survive?
   - Hidden optimization opportunities?

2. **Constraint Violation**: What if one key assumption breaks?
   - Solution resilience?
   - Graceful degradation?

3. **Adversarial**: Intelligent opponent attacking solution
   - Weakest links in reasoning?
   - Counter-evidence?

#### Review Hypotheses (Premium Tier Only)

Independent failure analysis:
- "What if assumption X is actually false?"
- "Probability of failure: [0, 0.3, 0.5, 0.7, 1.0]?"
- "Most likely failure mode?"

**Output**: 

```python
state.phase_results[4].critique = {
  "scores": CritiqueScore[],  # [candidate_id, dimension, score, reasoning]
  "stress_tests": StressTestResult[],  # [scenario, outcome, resilience]
  "review_hypotheses": ReviewHypothesis[]  # (premium only)
}
```

**Pruning Strategy**:
- Compute aggregate score per candidate (weighted average of dimensions)
- Retain top-k candidates (k=1 for budget, k=2–3 for premium)
- Candidates with review hypotheses marked as "requires verification"

### Phase 5: Synthesis (Final Voice & Claim Labeling)

**Concept**: Aggregate top candidates + scores + review hypotheses into a single, labeled final answer.

#### Synthesis Process

1. **Candidate Aggregation**:
   - Synthesize top candidates into unified solution
   - Identify overlapping insights (areas of agreement)
   - Highlight divergences (areas of disagreement)

2. **Critical Insights Extraction**:
   - Pull non-obvious, high-value insights from candidates and critiques
   - Limit to ≤5 insights (avoid overwhelming user)
   - Each insight must have evidence pointer

3. **Claim Labeling**:
   - Classify each key claim as VERIFIED | HYPOTHESIS | UNKNOWN
   - Cite supporting evidence
   - Flag high-uncertainty areas

4. **Action Blueprint**:
   - Convert abstract insights into concrete steps
   - Prioritize by impact and feasibility
   - Include resource estimates

5. **Open Questions** (Premium Only):
   - Unresolved aspects for follow-up
   - Key unknowns that would benefit further research
   - Suggests refinement queries

#### Cross-Model Verification (Premium)

Optional secondary verification:
- Route final synthesis to different model (`cross_verify_synthesis` role)
- Model reviews synthesis for coherence and soundness
- Flags inconsistencies if found

**Output**: 

```python
state.phase_results[5].final_solution = FinalSolution(
  core_solution: str,
  critical_insights: Insight[],
  action_blueprint: ActionStep[],
  open_questions: Question[],
  claim_labels: dict[str, ClaimLabel],
  meta_audit: dict  # model used, tokens, duration, quality hints
)
```

**State Flow Invariant**: `(candidates) → (scores) → (top_candidates) → (final_solution)` (no backward jumps)

---

## 3. WORKFLOW: Request to Final Answer

### Preflight Phase (Request Ingestion)

```python
def preflight(req: RunPipelineRequest) -> PreflightDecision:
    # 1. Resolve preset (explicit or auto-select via method classifier)
    preset = resolve_preset(req.preset_name or "auto")
    
    # 2. Build provider router from preset routing table
    router = ProviderRouter.from_preset(preset)
    
    # 3. Neuro recall (async, independent budget)
    neuro_context = await neuro.recall(req.problem, req.user_id)
    
    # 4. Run HyperGate (async, independent budget)
    gate_decision = await hypergate.decide(req.problem, preset.method)
    
    # 5. ACR override (Adaptive Cost-Aware Routing, if enabled)
    if req.use_acr and preset.cost_usd > ACR_THRESHOLD:
        gate_decision = acr_override(gate_decision, preset)
    
    return PreflightDecision(
        preset=preset,
        router=router,
        neuro_context=neuro_context,
        gate_decision=gate_decision,
        budget_remaining=compute_budget_remaining(req.user_id)
    )
```

**Preflight Decisions**:

1. **Direct Answer**: Skip to Phase 5, return HyperGate summary + Neuro recall best match
2. **Web Search**: Insert web search into Phase 3 generation (research method)
3. **Pipeline**: Proceed with full 6-phase pipeline

### Execution Phase (Main Pipeline)

```python
def execute(decision: PreflightDecision, state: PipelineState) -> PipelineState:
    pipeline = ReasonerPipeline(decision.router, decision.preset)
    workflow = WorkflowFactory.create(decision.preset.method)
    
    # Phase 1: Enhancement (optional)
    if decision.preset.config.enable_enhancement:
        state = await pipeline.enhance_problem(state)
        emit_event(PHASE_COMPLETED, phase=1)
    
    # Phase 2: Decomposition (optional)
    if decision.preset.config.enable_decomposition:
        state = await pipeline.decompose(state)
        emit_event(PHASE_COMPLETED, phase=2)
    
    # Phase 3: Generation (method-specific)
    state = await workflow.generate_candidates(pipeline, state)
    emit_event(PHASE_COMPLETED, phase=3)
    
    # Phase 4: Critique
    state = await workflow.critique_candidates(pipeline, state)
    emit_event(PHASE_COMPLETED, phase=4)
    
    # Phase 5: Synthesis
    state = await workflow.synthesize(pipeline, state)
    emit_event(PHASE_COMPLETED, phase=5)
    
    return state
```

**Phase Execution Details**:

1. **Token Tracking**: Each phase tracks `phase_tokens[i]` (input + output)
2. **Duration Tracking**: `phase_durations[i]` for performance monitoring
3. **Model Tracking**: `phase_models[i]` records which LLM was used
4. **Cost Tracking**: `phase_costs[i]` accumulates USD cost per phase
5. **Error Handling**: Fallback routing on model errors, logged in events

### Postflight Phase (Results Persistence)

```python
def postflight(state: PipelineState, req: RunPipelineRequest, user_id: str):
    # 1. Neuro learn: embed final solution, store in cache
    await neuro.learn(
        problem=state.core.problem,
        solution=state.core.final_solution,
        user_id=user_id,
        cost_usd=state.cost_state.total_cost_usd
    )
    
    # 2. History save: serialize state to history DB
    await history_store.save(user_id, state, timestamp=now())
    
    # 3. Event persistence: emit all captured events to event store
    for event in state.captured_events:
        await event_store.append(user_id, event)
    
    # 4. Telemetry: push to ACR for cost optimization
    await acr_telemetry.report(
        duration=total_duration(),
        cost_usd=state.cost_state.total_cost_usd,
        models_used=state.phase_models,
        method=req.preset_name
    )
```

**Postflight Guarantees**:

1. **Neuro Learn**: Enables future recall of similar problems
2. **History Preservation**: User can review prior runs via conversation history
3. **Event Audit Trail**: Full replay possible from event store
4. **ACR Learning**: Future requests benefit from cost/performance feedback

---

## 4. REASONING METHODS (19+ Strategies)

### Method Classification

**Analytical Methods** (decompose & evaluate)
- debate, jury, scientific, socratic, pre-mortem, bayesian, dialectical, delphi, cove

**Generative Methods** (create & refine)
- brainstorming, writing, article, coding

**Structured Reasoning Methods** (skeleton/tree/program)
- sot (Skeleton-of-Thought), tot (Tree-of-Thoughts), pot (Program-of-Thoughts)

**Domain-Specific Methods**
- research (web-grounded), cross-language (multilingual), image-gen

**Meta-Methods**
- self-discover (adapt reasoning modules), iterative-critique (convergence detection)

### Method Details

#### multi-perspective (Default)

**Strategy**: Four independent perspectives, jury scoring, top-2 aggregation

**Flow**:
1. Generate 4 perspectives in parallel: Constructive, Destructive, Systemic, Minimalist
2. Each perspective from different bloc (enforced)
3. Phase 4: Jury scoring (4 dimensions × 2 critics = 8 scores per perspective)
4. Phase 5: Aggregate top-2 perspectives, synthesis

**When to Use**: Balanced, non-specialized problems. Default tier.

**Bloc Requirement**: Perspectives span ≥2 blocs, ≤2 per bloc

---

#### debate

**Strategy**: Adversarial exchange (pro vs con) + systemic judge

**Flow**:
1. Opening: Side A (constructive argument), Side B (destructive argument)
2. Rebuttal: Each side attacks opponent's strongest point
3. Judge: Systemic evaluator synthesizes both, identifies weaknesses in each
4. Phase 5: Synthesize strongest elements into balanced recommendation

**When to Use**: Political, contested claims, controversial decisions. Reveals weaknesses.

**Bloc Requirement**: A ≠ B ≠ Judge blocs

---

#### research

**Strategy**: Web search → context grounding → synthesis

**Flow**:
1. Decompose problem → search queries (≤5)
2. Web search via SearXNG or Perplexity Sonar
3. Retrieve top-k results per query, parse content
4. Fact-check candidate claims against retrieved context
5. Phase 5: Synthesize grounded solution with citations

**When to Use**: Temporal queries (news, current events), factual questions requiring live data

**Integration**: Inserts into Phase 3 generation via research-specific flow

---

#### scientific

**Strategy**: Hypothesis → falsification → evidence-based conclusion

**Flow**:
1. Extract hypotheses from problem
2. For each hypothesis: identify falsification tests, predictions
3. Generate counter-evidence, alternative explanations
4. Evaluate evidence strength (reproducible, peer-reviewed, statistical power)
5. Phase 5: Bayesian update of hypothesis confidence

**When to Use**: Scientific/technical claims, rigorous evaluation required

**Output**: Confidence intervals per hypothesis, uncertainty quantification

---

#### socratic

**Strategy**: Iterative questioning to expose assumptions and root causes

**Flow**:
1. Start with problem statement
2. Generate clarifying questions (≤10)
3. Hypothetically answer questions, trace implications
4. Identify hidden assumptions, re-ask deeper questions
5. Converge on core issue or conceptual gap

**When to Use**: Learning, assumption-heavy problems, conceptual clarity

**Output**: Dialogue structure showing progression of understanding

---

#### pre-mortem

**Strategy**: Prospective failure analysis + recovery planning

**Flow**:
1. Imagine plan fails (or solution breaks)
2. Brainstorm failure causes (≤10)
3. For each cause: mitigation strategy, early warning signs
4. Rank by likelihood & impact
5. Phase 5: Integrate mitigations into action blueprint

**When to Use**: High-stakes decisions (strategy, launch, projects), risk mitigation

**Output**: Failure scenarios ranked by likelihood × impact, with recovery plans

---

#### article

**Strategy**: Research-backed, source-grounded article generation

**Flow**:
1. Retrieve relevant sources (via search sub-agent)
2. Outline: hierarchical structure (H1 → H2 → H3 sections)
3. Draft: fill sections with synthesized source material
4. Fact-check: verify key claims against sources
5. Editorial: polish, add transitions, ensure flow

**When to Use**: Long-form content (essays, reports, guides), requires citations

**Output**: Article text + citation list + confidence per claim

---

#### coding

**Strategy**: Spec → generate → review → test → assemble

**Flow**:
1. Parse spec: requirements, constraints, edge cases
2. Generate: multiple code implementations
3. Review: code quality, security, performance
4. Test: generate test cases, verify correctness
5. Assemble: select best implementation, integrate tests

**When to Use**: Code generation, technical problems

**Output**: Runnable code + test suite + explanation

---

#### sot (Skeleton-of-Thought)

**Strategy**: Outline structure → parallel detailed solves → assembly

**Flow**:
1. Create skeleton: high-level outline of solution structure
2. Parallel solve: fill each skeleton node in parallel (independent models)
3. Assembly: integrate filled nodes, resolve conflicts
4. Refinement: polish transitions, check consistency

**When to Use**: Large-scale problems amenable to outline-first approach

**Output**: Skeleton structure + detailed fills + assembly trace

---

#### tot (Tree-of-Thought)

**Strategy**: Explore reasoning tree, backtrack on low-value paths

**Flow**:
1. Start with root problem
2. Generate child nodes (2–3 solution directions)
3. Evaluate each node (heuristic score)
4. Expand most promising nodes
5. Backtrack if path score drops
6. Converge on best path

**When to Use**: Puzzle-solving, exploration, complex reasoning chains

**Output**: Tree structure with path scores, final best path highlighted

---

#### pot (Program-of-Thought)

**Strategy**: Convert reasoning to executable program (pseudo-code or actual)

**Flow**:
1. Parse problem as computational problem
2. Generate program (logic, loops, conditionals)
3. Trace execution with symbolic reasoning
4. Verify correctness against examples
5. Output: program + trace + explanation

**When to Use**: Math, logic problems, computational reasoning

**Output**: Executable or pseudo-code + trace + confidence

---

#### brainstorming

**Strategy**: Divergent idea generation via Verbalized Sampling (VS)

**Flow**:
1. Generate ideas (10–20, unconstrained)
2. Cluster ideas by theme
3. Rank by novelty, feasibility, impact
4. Synthesize best ideas into actionable recommendations

**When to Use**: Creative problems, ideation, innovation

**Output**: Idea list + clusters + evaluation scores

---

#### jury

**Strategy**: Multi-critic governance (generator, critic, verifier)

**Flow**:
1. Generator: produces solution
2. Critic: independent critical review
3. Verifier: fact-checks and validates
4. Phase 4: Jury votes (each critic rates independently)
5. Phase 5: Consensus or weighted decision

**When to Use**: High-stakes decisions, requires multiple opinions

**Output**: Jury votes + reasoning per critic

---

#### cross-language

**Strategy**: Multilingual reasoning with bloc diversity

**Flow**:
1. Detect source language (HyperGate LanguageDetector)
2. Translate to English (if non-English)
3. Reason in English (full pipeline)
4. Translate solution back to source language
5. Cross-bloc diversity enforced (perspective generators span ≥2 blocs)

**When to Use**: Non-English problems, multilingual reasoning required

**Output**: Solution in source language + model used + quality hints

---

### Method Selection Strategy

**Automated Selection (HyperGate)**:
1. MethodClassifier sub-agent recommends method
2. Complexity estimator determines budget vs premium tier
3. Default fallback: multi-perspective-budget

**Manual Selection**:
- User specifies preset name (e.g., "debate-premium")
- Preset maps to method + tier + model routing

**ACR Override**:
- If cost > ACR_THRESHOLD and performance history suggests cheaper method sufficient, downgrade

---

## 5. MODEL ROUTING & PROVIDER STRATEGY

### Provider Ecosystem

**28 Directly Integrated Models** (prefer direct for cost/latency):

| Bloc | Provider | Models | Notes |
|------|----------|--------|-------|
| 🇺🇸 US | Anthropic | claude-opus-4-1, claude-sonnet-4-0327, claude-haiku-3-5 | Vision, long context, latest |
| 🇺🇸 US | OpenAI | gpt-4-turbo, gpt-3.5-turbo, gpt-4-vision | Vision, reasoning |
| 🇺🇸 US | Google | gemini-pro, gemini-flash, gemini-vision | Multimodal, fast |
| 🇺🇸 US | xAI | grok-2, grok-2-vision-1212 | Real-time, vision |
| 🇪🇺 EU | Mistral | mistral-large, mistral-nemo | EU-regulated |
| 🇪🇺 EU | Perplexity | sonar-pro, sonar-reasoning | Web-grounded |
| 🇨🇳 CN | DeepSeek | deepseek-v4, deepseek-v4-flash | Vision, reasoning |
| 🇨🇳 CN | Qwen | qwen-max, qwen-turbo | Fast, reasoning |
| 🇨🇳 CN | Tencent | hunyuan-pro, hunyuan-vision | Vision |
| 🇨🇳 CN | MiniMax | abab6.5-chat, abab6.5-vision | Vision |
| 🇨🇳 CN | Zhipu | glm-4-vision, glm-4-turbo | Vision, reasoning |
| OpenRouter | 350+ models | Fallback aggregator | Rate-limited, higher cost |

**Cost Tiers** (as of 2026-07):

| Model | Input | Output | Use Case |
|-------|-------|--------|----------|
| Claude Haiku | $0.80/M | $4/M | Budget generation |
| GPT-3.5-turbo | $0.50/M | $1.50/M | Budget generation |
| Qwen Turbo | $0.07/M | $0.14/M | Ultra-budget |
| Claude Sonnet | $3/M | $15/M | Premium generation |
| GPT-4-turbo | $10/M | $30/M | Premium reasoning |
| Gemini Pro | $2.50/M | $7.50/M | Premium multimodal |
| DeepSeek V4 | $4/M | $16/M | Premium reasoning |

### Routing Philosophy

**Principle**: Bloc-Aware Diversity

```python
class ProviderRouter:
    def route_role(self, role: str) -> LLMProvider:
        """
        Role → Model ID mapping enforces:
        1. Synthesis ≠ Scoring bloc (prevent consensus distortion)
        2. Perspective generators span ≥2 blocs
        3. ≤2 models per bloc in perspective generation
        4. Cascading fallback: primary → cross-bloc → direct API → OpenRouter
        """
```

**Role-Based Routing**:

| Role | Primary | Fallback Chain | Bloc Requirement |
|------|---------|-----------------|------------------|
| `generation_perspective_*` | Preset-specific | Bloc-aware cascade | ≥2 blocs, ≤2/bloc |
| `critique_factuality` | Different bloc from generator | Cascade | Different from synthesis |
| `critique_reasoning` | Different bloc from generator | Cascade | Different from synthesis |
| `synthesis` | Preset-specific (primary) | Cascade | Different from scoring bloc |
| `search_query_gen` | Fast model (GPT-3.5, Qwen Turbo) | Cascade | Any |
| `web_search_context` | Research method specific | Cascade | Any |
| `cross_verify_synthesis` | Different bloc from synthesis | Cascade | Different from synthesis |

### Fallback Chain

```
Primary Model (direct API) →
  [unavailable/timeout/error] →
Bloc-equivalent fallback (same bloc, different provider) →
  [unavailable] →
Cross-bloc fallback (different bloc, approved) →
  [unavailable] →
OpenRouter aggregator →
  [unavailable] →
Error logged, use cached result or degrade gracefully
```

### Budget vs Premium Routing

**Budget Tier** ($0.10–$0.30/run):
- Generation: Qwen Turbo, Claude Haiku, GPT-3.5
- Critique: Fast models (Qwen, Haiku)
- Synthesis: Claude Haiku or Qwen

**Premium Tier** ($1.00–$3.00/run):
- Generation: Claude Sonnet, GPT-4-turbo, DeepSeek V4
- Critique: Frontier models (Sonnet, GPT-4, DeepSeek)
- Synthesis: Claude Sonnet or GPT-4

**Cost Tracking**:

```python
state.cost_state = CostState(
    total_cost_usd=0.0,
    phase_costs=[],  # per phase
    detailed_token_usage={
        "input": token_count,
        "output": token_count,
        "cached": token_count  # if caching enabled
    }
)
```

### Cascading & Quality Gates

**Quality Gate**: If model output malformed or empty:
1. Log fallback event
2. Try next model in fallback chain
3. If all models fail, use cached result or degrade
4. Emit MODEL_FALLBACK event to event store

**Cascading Routing** (for critical roles):

```python
# For "coding_review" role, try models in order:
models = ["claude-sonnet", "gpt-4-turbo", "deepseek-v4"]
for model in models:
    try:
        result = call_model(model, prompt)
        if quality_gate(result):
            return result
    except Exception as e:
        log_fallback(model, e)
        continue
# Fallback to cached/degraded result
```

---

## 6. PRESET ARCHITECTURE (48 Presets)

### Preset Structure

```python
class PipelinePreset:
    name: str                           # "debate-premium"
    method: str                         # "debate"
    tier: Literal["budget", "premium"]  # Cost tier
    cost_usd: float                     # Estimated cost
    config: PresetConfig
        enable_enhancement: bool
        enable_decomposition: bool
        enable_web_search: bool
        enable_stress_testing: bool
        enable_review_hypotheses: bool (premium only)
    routing: dict[str, str]             # role → model_id
    bloc_tags: dict[str, str]           # model_id → bloc emoji
```

### Preset Taxonomy

#### Foundation Methods (10 base × 2 tiers = 20)

| Method | Budget | Premium | Cost | Key Difference |
|--------|--------|---------|------|-----------------|
| multi-perspective | ✓ | ✓ | $0.15 / $0.80 | 4 perspectives, jury scoring |
| debate | ✓ | ✓ | $0.12 / $0.75 | Pro/con/judge adversarial |
| jury | ✓ | ✓ | $0.20 / $1.00 | Generator/critic/verifier |
| research | ✓ | ✓ | $0.30 / $1.20 | Web search + synthesis |
| scientific | ✓ | ✓ | $0.25 / $0.95 | Hypothesis falsification |
| socratic | ✓ | ✓ | $0.20 / $0.85 | Iterative questioning |
| pre-mortem | ✓ | ✓ | $0.18 / $0.80 | Failure analysis |

#### Specialized Methods (13 methods × 2 tiers = 26)

| Method | Budget | Premium | Cost | Use Case |
|--------|--------|---------|------|----------|
| bayesian | ✓ | ✓ | $0.15 / $0.70 | Probabilistic reasoning |
| dialectical | ✓ | ✓ | $0.20 / $0.85 | Thesis-antithesis-synthesis |
| analogical | ✓ | ✓ | $0.22 / $0.90 | Cross-domain mapping |
| delphi | ✓ | ✓ | $0.25 / $1.00 | Expert consensus |
| cove | ✓ | ✓ | $0.20 / $0.85 | Chain of Verification |
| sot | ✓ | ✓ | $0.18 / $0.80 | Skeleton-of-Thought |
| tot | ✓ | ✓ | $0.25 / $1.00 | Tree-of-Thought |
| pot | ✓ | ✓ | $0.20 / $0.90 | Program-of-Thought |
| self-discover | ✓ | ✓ | $0.30 / $1.10 | Adaptive pattern discovery |
| brainstorming | ✓ | ✓ | $0.15 / $0.70 | Idea generation |
| writing | ✓ | ✓ | $0.25 / $1.00 | Long-form content |
| article | ✓ | ✓ | $0.35 / $1.30 | Research-backed articles |
| coding | ✓ | ✓ | $0.40 / $1.50 | Code generation + review |
| cross-language | ✓ | ✓ | $0.20 / $0.90 | Multilingual reasoning |
| iterative-critique | ✓ | ✓ | $0.30 / $1.20 | Convergence-based refinement |

#### Special/Experimental (2)

- `nvidia-nemotron-test`: Experimental Nemotron routing
- `image-gen-budget` / `image-gen-premium`: Specialized image generation

### Preset Selection Logic

```python
def select_preset(
    method: str,
    tier: str = "budget",
    complexity: int = 3,  # 1–5
) -> PipelinePreset:
    """
    Auto-selection logic:
    1. Default to budget tier (cost-conscious)
    2. Upgrade to premium if complexity > 3 (HyperGate output)
    3. User can override via explicit preset name
    4. ACR can downgrade if history shows sufficient performance at lower tier
    """
    
    preset_name = f"{method}-{tier}"
    return PRESET_REGISTRY[preset_name]
```

### Routing Table Example (multi-perspective-premium)

```python
routing = {
    "generation_perspective_constructive": "claude-sonnet",       # 🇺🇸 US
    "generation_perspective_destructive": "deepseek-v4",          # 🇨🇳 CN
    "generation_perspective_systemic": "mistral-large",           # 🇪🇺 EU
    "generation_perspective_minimalist": "gemini-pro",            # 🇺🇸 US
    "critique_factuality": "gpt-4-turbo",                         # 🇺🇸 US (diff from synthesis)
    "critique_reasoning": "qwen-max",                             # 🇨🇳 CN (diff from synthesis)
    "critique_logic": "mistral-large",                            # 🇪🇺 EU (diff from synthesis)
    "synthesis": "claude-sonnet",                                 # 🇺🇸 US (primary)
    "cross_verify_synthesis": "deepseek-v4"                       # 🇨🇳 CN (diff bloc)
}

bloc_tags = {
    "claude-sonnet": "🇺🇸",
    "deepseek-v4": "🇨🇳",
    "mistral-large": "🇪🇺",
    "gemini-pro": "🇺🇸",
    "gpt-4-turbo": "🇺🇸",
    "qwen-max": "🇨🇳"
}

# Validators enforce:
assert synthesis_bloc != scoring_bloc
assert span_at_least_2_blocs(perspectives)
assert max_2_per_bloc(perspectives)
```

### Cost Estimation

```python
cost_estimate = preset.config.base_cost_usd
if enable_enhancement: cost_estimate += 0.05
if enable_decomposition: cost_estimate += 0.08
if enable_stress_testing: cost_estimate += 0.10
if enable_review_hypotheses: cost_estimate += 0.20
if enable_web_search: cost_estimate += 0.15
```

---

## 7. ORCHESTRATION & STATE MANAGEMENT

### PipelineState (Canonical State Model)

**~60 fields organized by phase**:

```python
class PipelineState:
    # Core problem & results
    core: CorePhaseData = {
        problem: str,
        task_type: str,
        language: str,
        enhanced_problem: str (opt),
        candidates: SolutionCandidate[],
        scores: CritiqueScore[],
        top_candidates: SolutionCandidate[],
        final_solution: FinalSolution
    }
    
    # Metadata & tracking
    meta: MetaData = {
        started_at: datetime,
        phase_logs: str[6],
        phase_tokens: int[6],
        phase_durations: float[6],
        phase_models: str[6],
        phase_results: PhaseResult[6],
        quality_hints: dict
    }
    
    # Method-specific state
    method_state: dict[str, Any] = {
        "debate": DebateState,
        "jury": JuryState,
        "research": ResearchState,
        ...
    }
    
    # Cost tracking
    cost_state: CostState = {
        total_cost_usd: float,
        phase_costs: float[6],
        detailed_token_usage: dict
    }
    
    # Conversation context
    conversation_state: ConversationContext = {
        conversation_id: str,
        turn_number: int,
        previous_synthesis: str (opt),
        multi_turn_history: Message[]
    }
    
    # Long-term memory
    neuro_context: NeuroContext = {
        retrieved_similar_problems: Problem[],
        relevant_embeddings: Embedding[],
        cache_tier: "L1" | "L2" | "L3"
    }
    
    # Phase decomposition
    decomposition: Decomposition = {
        sub_problems: SubProblem[],
        assumptions: Assumption[],
        failure_modes: FailureMode[]
    }
    
    # Event capture
    captured_events: DomainEvent[]
```

### Event-Sourced Architecture

**Domain Events**:

```python
class DomainEvent:
    event_type: str  # PHASE_STARTED, PHASE_COMPLETED, MODEL_FALLBACK, etc.
    timestamp: datetime
    phase: int (opt)
    model_used: str (opt)
    tokens_used: int (opt)
    cost_usd: float (opt)
    error_message: str (opt)
    reasoning: str (opt)
```

**Event Types**:

| Type | Trigger | Data |
|------|---------|------|
| PHASE_STARTED | Phase begins | phase, model_list |
| PHASE_COMPLETED | Phase finishes | phase, model_used, tokens, duration |
| MODEL_FALLBACK | Primary model unavailable | phase, primary_model, fallback_model |
| COST_TRACKED | Token usage recorded | tokens_input, tokens_output, cost_usd |
| CRITERIA_MET | Quality gate passed | criteria, score |
| CANDIDATES_PRUNED | Scores applied | retained_count |

**Event Store**:

```python
class EventStore:
    def append(self, user_id: str, event: DomainEvent):
        """Append-only event log"""
    
    def replay(self, user_id: str, conversation_id: str) -> PipelineState:
        """Reconstruct state from events"""
```

### Phase Reducer Pattern

```python
class PhaseOutput:
    """Delta applied to PipelineState"""
    candidates: SolutionCandidate[] (opt)
    scores: CritiqueScore[] (opt)
    top_candidates: SolutionCandidate[] (opt)
    final_solution: FinalSolution (opt)
    phase_logs: str
    phase_tokens: int
    phase_duration: float
    phase_model: str
    
    def apply_to(self, state: PipelineState) -> PipelineState:
        """Deterministic reducer: apply delta, return new state"""
        new_state = state.copy(deep=True)
        if self.candidates:
            new_state.core.candidates = self.candidates
        if self.scores:
            new_state.core.scores = self.scores
        # ... apply all deltas
        new_state.meta.phase_logs[phase] = self.phase_logs
        return new_state
```

### Workflow Strategy Pattern

```python
class WorkflowStrategy:
    """Abstract base for method-specific workflows"""
    
    async def generate_candidates(
        self,
        pipeline: ReasonerPipeline,
        state: PipelineState
    ) -> PipelineState:
        """Method-specific generation logic"""
    
    async def critique_candidates(
        self,
        pipeline: ReasonerPipeline,
        state: PipelineState
    ) -> PipelineState:
        """Method-specific critique logic"""
    
    async def synthesize(
        self,
        pipeline: ReasonerPipeline,
        state: PipelineState
    ) -> PipelineState:
        """Method-specific synthesis logic"""


class DebateWorkflow(WorkflowStrategy):
    """Debate-specific implementation"""
    async def generate_candidates(self, ...):
        # Debate: pro/con/judge exchange
    
    async def critique_candidates(self, ...):
        # Judge analysis of both sides
    
    async def synthesize(self, ...):
        # Balanced synthesis from debate


class WorkflowFactory:
    @staticmethod
    def create(method: str) -> WorkflowStrategy:
        """Factory returns method-specific workflow"""
        workflows = {
            "debate": DebateWorkflow(),
            "jury": JuryWorkflow(),
            # ...
        }
        return workflows[method]
```

---

## 8. SUB-AGENTS (Specialized LLM Calls)

### Hierarchical Sub-Agent System

```
Top Level: ReasonerPipeline
├─ Phase 0: HyperGateAgent (5 parallel sub-agents)
│  ├─ DirectDetector
│  ├─ WebSearchDetector
│  ├─ ComplexityEstimator
│  ├─ LanguageDetector
│  ├─ MethodClassifier
│  └─ TieBreaker
├─ Phase 1: EnhancementAgent
├─ Phase 2: DecompositionAgent
├─ Phase 3: Method-Specific Generators
│  ├─ MultiPerspectiveAgent (4 perspective sub-agents)
│  ├─ DebateAgent (pro/con/judge)
│  ├─ ResearchAgent (search + synthesis)
│  └─ ...
├─ Phase 4: CritiqueAgents (4 dimensions)
│  ├─ BiasChecker
│  ├─ EvidenceVerifier
│  ├─ LogicValidator
│  └─ CounterArgumentFinder
├─ Phase 5: SynthesisAgent
└─ Cross-Model: VerificationAgent (cross-bloc)
```

### Sub-Agent LRU Caching

```python
class BaseSubAgent:
    def __init__(self, role: str, cache_size: int = 1024):
        self.role = role
        self.cache = LRU(capacity=cache_size)
    
    async def __call__(self, prompt: str, temperature: float = 0.7):
        cache_key = hash((prompt, temperature))
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        result = await call_llm(self.router.route(self.role), prompt)
        self.cache[cache_key] = result
        return result
```

**Benefits**:
- Avoid redundant API calls within same pipeline run
- Enable offline testing (cached responses)
- Cost savings (repeated sub-problems)

---

## 9. MEMORY & COMPRESSION SYSTEM

### Neuro L1/L2/L3 Cache

**L1 (Fast In-Memory)**:
- Capacity: ~1M tokens
- TTL: 1 hour
- Indexing: Recent bundles, persona-aware
- Latency: <1ms

**L2 (Disk-Based)**:
- Capacity: Unlimited (file system)
- TTL: 30 days
- Indexing: Semantic embeddings, JSON index
- Latency: <100ms

**L3 (Vector DB, Optional)**:
- Capacity: Unlimited (dedicated vector DB)
- TTL: Indefinite (with refresh)
- Indexing: Dense embeddings, HNSW graph
- Latency: 100–500ms

**Recall Process**:

```python
async def recall(problem: str, user_id: str) -> NeuroContext:
    # 1. Embed current problem
    query_embedding = embed(problem)
    
    # 2. Retrieve from L1 (if fresh)
    l1_results = l1_cache.retrieve(
        embedding=query_embedding,
        top_k=3,
        max_age_minutes=60
    )
    if l1_results:
        return NeuroContext(
            retrieved_problems=l1_results,
            cache_tier="L1",
            latency_ms=<1
        )
    
    # 3. Fall through to L2
    l2_results = await l2_cache.search(
        user_id=user_id,
        embedding=query_embedding,
        top_k=5,
        min_similarity=0.7
    )
    if l2_results:
        # Promote to L1 for future recalls
        l1_cache.put(l2_results[:3], ttl_minutes=60)
        return NeuroContext(
            retrieved_problems=l2_results,
            cache_tier="L2",
            latency_ms=<100
        )
    
    # 4. Fall through to L3
    l3_results = await l3_vector_db.search(
        user_id=user_id,
        embedding=query_embedding,
        top_k=10,
        threshold=0.65
    )
    return NeuroContext(
        retrieved_problems=l3_results,
        cache_tier="L3",
        latency_ms=100-500
    )
```

### Tiered Serialization

**Full State** (`to_dict()`):
- All phases, all candidates, scores, metadata
- Size: ~50–200KB per run
- Use case: Replay, debugging

**Summary** (`to_summary()`):
- Problem, task_type, final_solution, critical_insights
- Size: ~2–5KB per run
- Use case: History display, Neuro learn

**Context Compression** (`to_context_dict(compression_level)`):
- Configurable: BALANCED, AGGRESSIVE, MINIMAL
- BALANCED: Include top-2 candidates + synthesis
- AGGRESSIVE: Only synthesis + insights
- MINIMAL: Problem + final_solution only
- Use case: Few-shot examples, prompt context

### Context Budget Management

```python
class ContextBudgetManager:
    def allocate(
        self,
        problem_complexity: int,  # 1–5
        available_tokens: int
    ) -> dict[str, int]:
        """Allocate token budget per phase"""
        
        base_budgets = {
            "enhancement": 500,
            "decomposition": 1000,
            "generation": 8000,
            "critique": 4000,
            "synthesis": 3000
        }
        
        # Adjust for complexity
        if complexity >= 4:
            base_budgets["generation"] *= 1.5
            base_budgets["critique"] *= 1.3
        
        # Scale to available tokens
        total_base = sum(base_budgets.values())
        scale_factor = available_tokens / total_base
        
        return {
            phase: int(budget * scale_factor)
            for phase, budget in base_budgets.items()
        }
```

### Compression Strategies

**Prompt Compression** (mid-pipeline):
- Summarize Phase 3 candidates before Phase 4: "Phase 3 generated 4 candidates. Candidate 1 (Constructive): [summary]. Candidate 2 (Destructive): [summary]..."
- Reduces Phase 4 prompt size without losing information

**Neuro Compression** (at learn time):
- Extract top insights from synthesis
- Embed as semantic summary for L2/L3
- Discard verbose intermediate steps

**Aggressive Compression** (premium tier, cost optimization):
- Keep only final synthesis + claims
- Discard candidate details
- Usable for follow-up runs

### Session Persistence

```python
class ConversationState:
    conversation_id: str
    turn_number: int
    turns: Turn[] = [
        Turn(
            turn_number=1,
            query="...",
            synthesis="...",
            cost_usd=0.80,
            timestamp=...
        ),
        Turn(
            turn_number=2,
            query="Follow-up question",
            previous_synthesis="(from turn 1)",
            synthesis="...",
            cost_usd=0.60,
            timestamp=...
        )
    ]
    
    total_cost_usd: float = 1.40
    total_tokens: int = 15000
```

**Resume Semantics**:
- `--resume` loads prior PipelineState + ConversationState
- Previous synthesis injected into Phase 5 as context
- Cost accumulates across turns
- Neuro learns from multi-turn trajectory

---

## 10. KEY INVARIANTS & SAFETY GUARANTEES

### Immutability Invariant

**Rule**: No mutation of PipelineState except via PhaseOutput reducers

**Enforcement**:
- State marked as `frozen=True` (Pydantic)
- Phase results use `.copy(deep=True)` before modification
- Event log tracks all state transitions

**Benefit**:
- Deterministic replay
- Enables async phase execution
- Prevents hidden side effects

### Validation Layers

**Input Validation**:

```python
def sanitize_for_prompt(text: str) -> str:
    """Multi-layer sanitization"""
    # 1. Strip URLs (prevent injection)
    text = re.sub(r'https?://\S+', '[URL]', text)
    
    # 2. Strip emails (privacy)
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)
    
    # 3. Remove null bytes (buffer overflow)
    text = text.replace('\0', '')
    
    # 4. Detect prompt injection patterns
    injection_patterns = [
        r'ignore previous instructions',
        r'you are now',
        r'override',
        r'system prompt'
    ]
    for pattern in injection_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            logger.warn(f"Potential injection detected: {pattern}")
    
    # 5. Normalize Unicode (NFKC)
    text = unicodedata.normalize('NFKC', text)
    
    return text
```

**Output Parsing**:

```python
def extract_json(response: str) -> dict:
    """Graceful JSON extraction"""
    # Try direct parse
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    
    # Try markdown code block
    match = re.search(r'```(?:json)?\s*({.*?})\s*```', response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try to find JSON-like object
    match = re.search(r'\{.*\}', response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    
    # Fallback to empty dict
    logger.error(f"Could not extract JSON from: {response}")
    return {}
```

### Claim Labeling System

**ClaimLabel Enum**:

```python
class ClaimLabel(Enum):
    VERIFIED = "verified"      # Cross-validated, cited
    HYPOTHESIS = "hypothesis"  # Plausible, untested
    UNKNOWN = "unknown"        # Insufficient evidence
```

**Labeling Guideline**:

| Label | Criteria | Example |
|-------|----------|---------|
| VERIFIED | Independent confirmation, multiple sources, cited evidence | "The Earth orbits the Sun (Copernican model, confirmed by Newton's laws, satellite data)" |
| HYPOTHESIS | Logically sound, untested or single source | "Dark matter comprises 85% of matter (inferred from galaxy rotation curves, but direct detection missing)" |
| UNKNOWN | Insufficient information, expert disagreement | "The origin of consciousness (philosophy + neuroscience, no consensus)" |

**Consumer-Side Filtering**:

```python
# Application can filter synthesis by claim label
high_confidence_claims = [
    claim for claim in final_solution.claims
    if claim.label == ClaimLabel.VERIFIED
]
```

### Cost & Spend Caps

```python
class CostConstraint:
    SPEND_CAP_PER_RUN_USD = 5.00
    SPEND_CAP_PER_USER_DAILY = 50.00
    
    @staticmethod
    def check_preflight(preset: PipelinePreset, user_id: str):
        if preset.cost_usd > SPEND_CAP_PER_RUN_USD:
            raise BudgetExceededError(
                f"Preset costs ${preset.cost_usd}, exceeds cap ${SPEND_CAP_PER_RUN_USD}"
            )
        
        daily_cost = get_user_daily_cost(user_id)
        if daily_cost + preset.cost_usd > SPEND_CAP_PER_USER_DAILY:
            raise BudgetExceededError(
                f"Daily budget ${SPEND_CAP_PER_USER_DAILY} exhausted"
            )
```

### Token Budgets per Phase

```python
PHASE_TOKEN_BUDGETS = {
    "enhancement": 500,
    "decomposition": 1000,
    "generation": 8000,
    "critique": 4000,
    "synthesis": 3000
}

# Phase enforces early termination if exceeded
async def run_phase(phase_id: int, budget: int) -> PhaseOutput:
    tokens_used = 0
    while tokens_used < budget:
        # ... run sub-agents
        tokens_used += tokens_from_last_call()
    
    if tokens_used >= budget:
        logger.warn(f"Phase {phase_id} hit token budget, truncating")
```

### Timeout Enforcement

```python
ROLE_TIMEOUTS = {
    "generation_perspective_*": 60,      # seconds
    "critique_*": 30,
    "synthesis": 45,
    "search_query": 10
}

HYPERGATE_TIMEOUT_SECONDS = 5
GATE_TIMEOUT_SECONDS = 2

async def call_llm_with_timeout(role: str, prompt: str) -> str:
    timeout = ROLE_TIMEOUTS.get(role, 30)
    try:
        return await asyncio.wait_for(
            call_llm(role, prompt),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.error(f"LLM call {role} timed out after {timeout}s")
        # Trigger fallback routing
```

### Bloc Diversity Validation

```python
class PresetValidator:
    @staticmethod
    def validate(preset: PipelinePreset) -> list[str]:
        """Validate preset routing satisfies bloc constraints"""
        errors = []
        
        synthesis_bloc = preset.bloc_tags[preset.routing["synthesis"]]
        scoring_bloc = preset.bloc_tags[preset.routing["critique_factuality"]]
        
        # Check synthesis ≠ scoring
        if synthesis_bloc == scoring_bloc:
            errors.append(
                f"Synthesis bloc ({synthesis_bloc}) == Scoring bloc ({scoring_bloc})"
            )
        
        # Check perspective diversity
        perspective_models = [
            preset.routing[f"generation_perspective_{p}"]
            for p in ["constructive", "destructive", "systemic", "minimalist"]
        ]
        perspective_blocs = [preset.bloc_tags[m] for m in perspective_models]
        
        if len(set(perspective_blocs)) < 2:
            errors.append(
                f"Perspectives span only {len(set(perspective_blocs))} bloc(s), need ≥2"
            )
        
        bloc_counts = {}
        for bloc in perspective_blocs:
            bloc_counts[bloc] = bloc_counts.get(bloc, 0) + 1
        
        for bloc, count in bloc_counts.items():
            if count > 2:
                errors.append(f"Bloc {bloc} has {count} models, max 2 allowed")
        
        return errors

# At preset construction time:
errors = PresetValidator.validate(preset)
if errors:
    raise ValueError(f"Preset validation failed: {errors}")
```

### Backward Compatibility

**Resume Support**:

```python
class PipelineState:
    def __init__(self, **kwargs):
        # Accept both old flat and new nested field names
        if "problem" in kwargs and "core" not in kwargs:
            # Old format: flatten to nested
            kwargs["core"] = CorePhaseData(
                problem=kwargs.pop("problem"),
                task_type=kwargs.pop("task_type", "unknown"),
                # ... migrate other fields
            )
        
        super().__init__(**kwargs)
    
    def _ensure_fields_initialized(self):
        """Auto-initialize missing fields from old state files"""
        if self.method_state is None:
            self.method_state = {}
        if self.captured_events is None:
            self.captured_events = []
        # ... ensure all fields exist
```

**Testing Backward Compatibility**:

```python
def test_resume_from_v2_0_state():
    """Verify --resume works with older state files"""
    old_state_dict = load_json("fixtures/state_v2.0.json")
    state = PipelineState(**old_state_dict)
    
    # Verify all fields initialized
    assert state.core is not None
    assert state.method_state is not None
    assert state.captured_events is not None
```

---

## CONCLUSION

**The Reasoner System** is a production-grade, composable multi-method LLM reasoning orchestrator built on:

1. **Multi-perspective ensemble** for echo-chamber resistance
2. **Cross-bloc model diversity** for geopolitical bias mitigation
3. **Event-sourced, immutable state** for auditability and replay
4. **Graceful degradation** via cascading fallback routing
5. **19+ specialized reasoning methods** for diverse problem types
6. **Rigorous validation** via sanitization, parsing, claim labeling, and safety gates
7. **Memory hierarchy** (L1/L2/L3 cache) for few-shot learning and cost efficiency
8. **Composable workflows** via strategy pattern for maintainability

The system prioritizes **safety** (validation, immutability, audit trails), **diversity** (cross-bloc routing), and **efficiency** (token budgets, cost caps, tiered caching) while enabling users to solve complex problems through structured, multi-phase reasoning pipelines.

---

**Document Generated**: 2026-07-18  
**Reasoner Version**: 2.2  
**Python**: 3.12+  
**Frontend**: Next.js 16 / React 19  

