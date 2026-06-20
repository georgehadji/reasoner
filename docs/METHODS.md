# ARA Pipeline — Methods Documentation

Αναλυτική τεκμηρίωση όλων των μεθόδων συλλογιστικής του ARA Pipeline v2.0.

---

## Πίνακας Περιεχομένων

1. [Επισκόπηση Αρχιτεκτονικής](#1-επισκόπηση-αρχιτεκτονικής)
2. [Καθολικές Φάσεις](#2-καθολικές-φάσεις)
3. [Τυπικές Μέθοδοι](#3-τυπικές-μέθοδοι)
   - [Multi-Perspective](#multi-perspective)
   - [Iterative](#iterative)
   - [Debate](#debate)
   - [Research](#research)
   - [Jury](#jury)
   - [Scientific](#scientific)
   - [Socratic](#socratic)
4. [Εξειδικευμένες Μέθοδοι](#4-εξειδικευμένες-μέθοδοι)
   - [Pre-Mortem](#pre-mortem)
   - [Bayesian](#bayesian)
   - [Dialectical](#dialectical)
   - [Analogical](#analogical)
   - [Delphi](#delphi)
5. [Οδηγός Επιλογής Μεθόδου](#5-οδηγός-επιλογής-μεθόδου)

---

## 1. Επισκόπηση Αρχιτεκτονικής

### Pipeline Flow

```
Problem → Phase 0 (Classification) → Phase 1 (Decomposition) → 
Context Vetting → [Method-Specific Pipeline] → Phase 5 (Synthesis)
```

### Βασικά Στοιχεία

| Στοιχείο | Περιγραφή |
|----------|-----------|
| **ProviderRouter** | Δρομολογεί κλήσεις σε διαφορετικά μοντέλα ανάλογα με το role |
| **PipelineState** | Κεντρικό state object που κρατά όλα τα ενδιάμεσα αποτελέσματα |
| **PhaseConfig** | Ρυθμίσεις ανά φάση (role, temperature, max_tokens) |
| **extract_json** | Parser που εξάγει JSON από τις απαντήσεις των LLM |

---

## 2. Καθολικές Φάσεις

### Phase 0: Classification
```python
async def _phase_0_classify(self, state: PipelineState):
    # 1. Detect language (Greek, Russian, Arabic, Chinese, Japanese, Korean, Spanish, German, Turkish, English)
    lang = detect_language(state.problem)
    
    # 2. Call LLM με role="classification"
    raw, _ = await self.router.call(
        role="classification",
        system_prompt=phases.CLASSIFICATION_SYSTEM,
        user_prompt=phases.classification_prompt(state.problem, lang)
    )
    
    # 3. Parse JSON response
    data = extract_json(raw)
    state.task_type = data.get("task_type")  # analytical, strategic, creative, technical, hybrid
    state.language = data.get("language")
```

**Output:** `{task_type, rationale, language}`

### Phase 1: Decomposition
```python
async def _phase_1_decompose(self, state: PipelineState):
    # 1. Build context with web discovery results if available
    web_context = f"\nWEB DISCOVERY RESULTS:\n{json.dumps(state.web_discovery_results)}"
    
    # 2. Call LLM με role="decomposition"
    raw, _ = await self.router.call(
        role="decomposition",
        system_prompt=phases.DECOMPOSITION_SYSTEM,
        user_prompt=phases.decomposition_prompt(state)
    )
    
    # 3. Parse causal chain, assumptions, failure_modes
    data = extract_json(raw)
    state.decomposition = data
```

**Output:** `{causal_chain[], assumptions[], failure_modes[], jury_guidelines?}`

### Context Vetting (Iterative RAG)
```python
async def _phase_context_vetting(self, state, source_type="general"):
    # 1. Initialize discovery client (Perplexity/Tavily)
    client, _ = await get_discovery_client(source_type=source_type)
    
    # 2. Iterative loop (max 3 iterations)
    for i in range(1, max_iterations + 1):
        # 2a. Ask LLM if more searches are needed
        decision_data = extract_json(await self.router.call(
            role="primary",
            system_prompt=phases.ITERATIVE_CONTEXT_SYSTEM,
            user_prompt=phases.iterative_context_prompt(state, current_results, i)
        ))
        
        action = decision_data.get("action")  # "search" or "done"
        if action == "done" or i == max_iterations:
            break
            
        # 2b. Execute searches
        queries = decision_data.get("queries", [])[:3]
        results = await asyncio.gather(*[client.search(q) for q in queries])
        
    # 3. Apply CoT vetting to all results
    for result in results:
        flags_data = extract_json(await self.router.call(
            role="context_vetting",
            system_prompt=phases.COT_DETECTION_SYSTEM,
            user_prompt=phases.cot_detection_prompt(state, result.get("snippet"))
        ))
        result["vetting_flags"] = flags_data.get("flags", [])
    
    state.vetted_context = results
```

### Phase 5: Synthesis
```python
async def _phase_synthesis(self, state: PipelineState):
    raw, _ = await self.router.call(
        role="synthesis",
        system_prompt=phases.SYNTHESIS_SYSTEM,
        user_prompt=phases.synthesis_prompt(state)
    )
    
    # Parse with citation handling
    json_data = extract_json(raw) or {}
    state.final_solution = FinalSolution(
        core_solution=extract_solution_prose(raw),
        critical_insights=json_data.get("critical_insights", []),
        action_blueprint=json_data.get("action_blueprint", []),
        claim_labels={k: ClaimLabel(v) for k, v in json_data.get("claim_labels", {}).items()},
        meta_audit=MetaCognitiveAudit(...),
        sources=json_data.get("sources", [])
    )
```

---

## 3. Τυπικές Μέθοδοι

### Multi-Perspective

**Περιγραφή:**
Η προεπιλεγμένη μέθοδος. Τέσσερις ανεξάρτητες οπτικές (Constructive, Destructive, Systemic, Minimalist) αναλύουν το πρόβλημα παράλληλα.

**Φάσεις:**
```python
async def _run_multi_perspective_pipeline(self, state):
    # Phase 2: 4 parallel perspective calls
    await self._phase_2_perspectives(state)
    
    # Phase 3: Single critique pass
    await self._phase_3_critique(state)
    
    # Phase 4: Stress test top-k
    await self._phase_4_stress_test(state)
```

**Phase 2 Implementation:**
```python
async def _phase_2_perspectives(self, state, use_reflexion=False):
    # Define perspective prompts
    PERSPECTIVE_SYSTEMS = {
        "constructive": "Find the strongest possible solution",
        "destructive": "Find every flaw, do NOT propose solutions",
        "systemic": "Identify second and third-order effects",
        "minimalist": "Find the simplest 80% solution"
    }
    
    # Run all 4 perspectives concurrently
    tasks = [
        self.router.call(role=p.name, system_prompt=PERSPECTIVE_SYSTEMS[p.name])
        for p in self.perspectives  # [CONSTRUCTIVE, DESTRUCTIVE, SYSTEMIC, MINIMALIST]
    ]
    results = await asyncio.gather(*tasks)
    
    # Parse and store candidates
    for raw, _ in results:
        data = extract_json(raw)
        state.candidates.append(SolutionCandidate(
            perspective=PerspectiveType(data["perspective"]),
            content=data.get("core_analysis", ""),
            key_insights=data.get("key_insights", [])
        ))
```

**Phase 3 Implementation:**
```python
async def _phase_3_critique(self, state):
    # Score all candidates 0-10 on multiple criteria
    raw, _ = await self.router.call(
        role="scoring",
        system_prompt=phases.CRITIQUE_SYSTEM,
        user_prompt=phases.critique_prompt(state)
    )
    
    data = extract_json(raw)
    state.scores = _parse_critique_scores(data.get("scores", []))
    
    # Pruning: keep top-k by total score
    scored = {s.perspective: s.total for s in state.scores}
    top_p = sorted(scored, key=scored.get, reverse=True)[:self.top_k]
    state.top_candidates = [c for c in state.candidates if c.perspective in top_p]
```

**Βέλτιστο Για:** Γενική ανάλυση προβλημάτων

---

### Iterative

**Περιγραφή:**
Εξελικτική προσέγγιση με επαναληπτική βελτίωση. Μέγιστο 3 γύροι με early exit όταν mean_score ≥ 8.5.

**Φάσεις:**
```python
async def _run_iterative_pipeline(self, state):
    MAX_ROUNDS = 3
    CONVERGENCE_THRESHOLD = 8.5
    
    for i in range(MAX_ROUNDS):
        # Generate candidates with reflexion memory
        await self._phase_2_perspectives(state, use_reflexion=True)
        
        # Critique
        await self._phase_3_critique(state)
        
        # Store insights for next round
        new_memories = [s.steel_man for s in state.scores if s.steel_man]
        state.reflexion_memory.extend(new_memories)
        
        # Early convergence check
        if state.scores:
            mean_score = sum(s.logical_consistency for s in state.scores) / len(state.scores)
            if mean_score >= CONVERGENCE_THRESHOLD:
                break  # Exit early
        
        # Clear for next round (except last)
        if i < MAX_ROUNDS - 1:
            state.candidates, state.scores, state.top_candidates = [], [], []
```

**Reflexion Memory:**
```python
# Passed to perspective prompt for context
context = {
    "problem": state.problem,
    "causal_chain": state.decomposition.get("causal_chain", []),
    "reflexion_memory": state.reflexion_memory  # Previous steel-man arguments
}
```

**Βέλτιστο Για:** Προβλήματα βελτιστοποίησης, σχεδιασμού

---

### Debate

**Περιγραφή:**
Πολυ-πρακτορικό σύστημα όπου δύο μοντέλα (Model A vs Model B) ανταγωνίζονται και ένα τρίτο (Judge) αξιολογεί.

**Φάσεις:**
```python
async def _run_debate_pipeline(self, state):
    await self._phase_debate_opening(state)      # Round 1
    await self._phase_debate_rebuttal(state)     # Round 2
    await self._phase_debate_cross_examine(state) # Round 3 (A5)
    await self._phase_debate_judge(state)        # Final judgment
```

**Phase 1 - Opening:**
```python
async def _phase_debate_opening(self, state):
    # Two parallel opening statements
    results = await asyncio.gather(
        self.router.call(role="constructive", ...)  # Side A
        self.router.call(role="destructive", ...)   # Side B
    )
    
    statements = [extract_json(r[0]) for r in results]
    state.debate_rounds.append({
        "round": 1, 
        "type": "opening", 
        "statements": statements
    })
```

**Phase 2 - Rebuttal:**
```python
async def _phase_debate_rebuttal(self, state):
    statement_a = state.debate_rounds[0]['statements'][0]['content']
    statement_b = state.debate_rounds[0]['statements'][1]['content']
    
    # Each side rebuts the other
    results = await asyncio.gather(
        self.router.call(role="constructive", prompt=rebuttal_prompt("A", statement_b)),
        self.router.call(role="destructive", prompt=rebuttal_prompt("B", statement_a))
    )
```

**Phase 3 - Cross-Examination:**
```python
async def _phase_debate_cross_examine(self, state):
    # Judge asks probing questions to both sides
    for side in ["A", "B"]:
        raw, _ = await self.router.call(
            role="systemic",
            system_prompt=phases.DEBATE_CROSS_SYSTEM,
            user_prompt=phases.debate_cross_examine_prompt(state, side, opponent_claims)
        )
```

**Phase 4 - Judge:**
```python
async def _phase_debate_judge(self, state):
    raw, _ = await self.router.call(
        role="systemic",
        system_prompt=phases.DEBATE_JUDGE_SYSTEM,
        user_prompt=phases.debate_judge_prompt(state)
    )
    
    data = extract_json(raw)
    state.scores = _parse_critique_scores(data.get("scores", []))
```

**Βέλτιστο Για:** Στρατηγικές αποφάσεις με αντισταθμίσεις

---

### Research

**Περιγραφή:**
Προσέγγιση βασισμένη σε αποδείξεις με χρήση Perplexity Sonar για αναζήτηση στο web.

**Φάσεις:**
```python
async def _run_research_pipeline(self, state):
    await self._phase_research_web_search(state)  # Deep iterative research
    await self._phase_2_perspectives(state)        # Analyze with web context
    await self._phase_3_critique(state)            # Fact-checked critique
```

**Deep Research Implementation:**
```python
async def _phase_research_web_search(self, state):
    max_iterations = 3
    current_knowledge = []
    
    for i in range(1, max_iterations + 1):
        # LLM decides if more searches needed
        data = extract_json(await self.router.call(
            role="primary",
            system_prompt=phases.DEEP_RESEARCH_SYSTEM,
            user_prompt=phases.deep_research_prompt(state, current_knowledge, i)
        ))
        
        if data.get("action") == "done":
            break
            
        # Execute searches
        queries = data.get("queries", [])[:3]
        for q in queries:
            results = await client.search(q, num_results=5)
            current_knowledge.extend(results)
    
    state.web_discovery_results = current_knowledge
```

**Βέλτιστο Για:** Εμπειρικές ερωτήσεις, τρέχοντα γεγονότα

---

### Jury

**Περιγραφή:**
Παράλληλο σύστημα πολλαπλών πρακτόρων με meta-evaluation.

**Φάσεις:**
```python
async def _run_jury_pipeline(self, state):
    await self._phase_jury_generate(state)              # 4 generators
    await self._phase_jury_critique(state)              # 3 critics
    await self._phase_jury_verify_and_meta_eval(state)  # Verifier + Meta-Evaluator
    await self._phase_jury_weighted_ranking(state)      # Weighted ranking
```

**Generation:**
```python
async def _phase_jury_generate(self, state):
    gen_roles = ["generator_1", "generator_2", "generator_3", "generator_4"]
    
    tasks = [
        self.router.call(
            role=role,
            system_prompt=phases.JURY_GENERATOR_SYSTEM,
            user_prompt=phases.jury_generator_prompt(state, role)
        )
        for role in gen_roles
    ]
    
    results = await asyncio.gather(*tasks)
    state.generation_candidates = [
        GenerationCandidate(**extract_json(r[0])) for r in results
    ]
```

**Critique:**
```python
async def _phase_jury_critique(self, state):
    critic_roles = ["critic_1", "critic_2", "critic_3"]
    
    tasks = [
        self.router.call(
            role=role,
            system_prompt=phases.JURY_CRITIC_SYSTEM,
            user_prompt=phases.jury_critic_prompt(state),
            temperature=0.1
        )
        for role in critic_roles
    ]
    
    results = await asyncio.gather(*tasks)
    state.critic_scores = [CriticScore(**extract_json(r[0])) for r in results]
```

**Meta-Evaluation:**
```python
async def _phase_jury_verify_and_meta_eval(self, state):
    # 1. Verify claims
    v_data = extract_json(await self.router.call(
        role="verifier",
        system_prompt=phases.JURY_VERIFIER_SYSTEM,
        user_prompt=phases.jury_verifier_prompt(state)
    ))
    state.verification_results = [VerificationResult(**v) for v in v_data.get("verifications")]
    
    # 2. Evaluate critic quality
    m_data = extract_json(await self.router.call(
        role="meta_evaluator",
        system_prompt=phases.JURY_META_EVAL_SYSTEM,
        user_prompt=phases.jury_meta_eval_prompt(state)
    ))
    state.meta_evaluation = MetaEvaluation(**m_data)
```

**Βέλτιστο Για:** Αποφάσεις υψηλού ρίσκου με πολλαπλά stakeholders

---

### Scientific

**Περιγραφή:**
Υποθετική-πειραματική προσέγγιση βασισμένη στην επιστημονική μέθοδο.

**Φάσεις:**
```python
async def _run_scientific_pipeline(self, state):
    await self._phase_scientific_hypothesize(state)  # Generate hypotheses
    await self._phase_scientific_test(state)          # Design tests
    await self._phase_4_stress_test(state)            # Evaluate evidence
```

**Βέλτιστο Για:** Ερευνητικές ερωτήσεις, τεχνικές αποφάσεις

---

### Socratic

**Περιγραφή:**
Ερωτηματική προσέγγιση με επαναληπτικές ερωτήσεις για διερεύνηση.

**Φάσεις:**
```python
async def _run_socratic_pipeline(self, state):
    await self._phase_socratic_question(state)  # Initial question
    await self._phase_socratic_answer(state)     # Follow-up loop
```

**Βέλτιστο Για:** Διευκρίνιση ασαφών προβλημάτων

---

## 4. Εξειδικευμένες Μέθοδοι

### Pre-Mortem

**Μεθοδολογία (Gary Klein, 1989):**
```
Failure Narrative → Root Cause → Early Signals → Hardened Redesign
```

**Pipeline:**
```python
async def _run_pre_mortem_pipeline(self, state):
    await self._phase_pre_mortem_failure(state)    # Imagine failure
    await self._phase_pre_mortem_backtrack(state)  # Find root cause
    await self._phase_pre_mortem_signals(state)    # Early warning signals
    await self._phase_pre_mortem_redesign(state)   # Hardened solution
```

**Phase 1 - Failure Narrative:**
```python
async def _phase_pre_mortem_failure(self, state):
    raw, _ = await self.router.call(
        role="destructive",
        system_prompt=phases.PRE_MORTEM_FAILURE_SYSTEM,
        user_prompt=phases.pre_mortem_failure_prompt(state)
    )
    # Output: {failure_narrative, timeline, key_events}
    state.pre_mortem_state["failure_narrative"] = extract_json(raw)
```

**Phase 2 - Root Cause:**
```python
async def _phase_pre_mortem_backtrack(self, state):
    raw, _ = await self.router.call(
        role="scoring",
        system_prompt=phases.PRE_MORTEM_BACKTRACK_SYSTEM,
        user_prompt=phases.pre_mortem_backtrack_prompt(state)
    )
    # Output: {root_cause, pivot_point, decision_chain}
    state.pre_mortem_state["root_cause"] = extract_json(raw)
```

**Phase 3 - Early Signals:**
```python
async def _phase_pre_mortem_signals(self, state):
    raw, _ = await self.router.call(
        role="scoring",
        system_prompt=phases.PRE_MORTEM_SIGNALS_SYSTEM,
        user_prompt=phases.pre_mortem_signals_prompt(state)
    )
    # Output: {early_signals[], monitoring_cadence}
    data = extract_json(raw)
    state.pre_mortem_state["early_signals"] = data.get("early_signals", [])
```

**Phase 4 - Redesign:**
```python
async def _phase_pre_mortem_redesign(self, state):
    raw, _ = await self.router.call(
        role="synthesis",
        system_prompt=phases.PRE_MORTEM_REDESIGN_SYSTEM,
        user_prompt=phases.pre_mortem_redesign_prompt(state)
    )
    # Output: {hardened_solution, safeguards[], checkpoints[], rollback_plan}
    data = extract_json(raw)
    state.pre_mortem_state["hardened_solution"] = data.get("hardened_solution")
```

**Presets:** `pre-mortem-budget`, `pre-mortem-premium`

**Βέλτιστο Για:** Αξιολόγηση κινδύνου, σχεδιασμός έργων

---

### Bayesian

**Μεθοδολογία (Jaynes, 2003):**
```
Priors → Likelihoods → Posteriors → Sensitivity Analysis
```

**Pipeline:**
```python
async def _run_bayesian_pipeline(self, state):
    await self._phase_bayesian_priors(state)       # Prior elicitation
    await self._phase_bayesian_likelihood(state)   # Likelihood assessment
    await self._phase_bayesian_posterior(state)     # Posterior update
    await self._phase_bayesian_sensitivity(state)   # Sensitivity analysis
```

**Phase 1 - Priors:**
```python
async def _phase_bayesian_priors(self, state):
    raw, _ = await self.router.call(
        role="constructive",
        system_prompt=phases.BAYESIAN_PRIOR_SYSTEM,
        user_prompt=phases.bayesian_prior_prompt(state)
    )
    # Output: {hypotheses: [{name, prior_probability, rationale}]}
    data = extract_json(raw)
    state.bayesian_state["hypotheses_with_priors"] = data.get("hypotheses", [])
```

**Phase 2 - Likelihoods:**
```python
async def _phase_bayesian_likelihood(self, state):
    raw, _ = await self.router.call(
        role="destructive",
        system_prompt=phases.BAYESIAN_LIKELIHOOD_SYSTEM,
        user_prompt=phases.bayesian_likelihood_prompt(state)
    )
    # Output: {likelihoods: [{hypothesis, observation, likelihood}], observations}
    data = extract_json(raw)
    state.bayesian_state["evidence_likelihoods"] = data.get("likelihoods", [])
```

**Phase 3 - Posteriors:**
```python
async def _phase_bayesian_posterior(self, state):
    raw, _ = await self.router.call(
        role="scoring",
        system_prompt=phases.BAYESIAN_POSTERIOR_SYSTEM,
        user_prompt=phases.bayesian_posterior_prompt(state)
    )
    # Output: {posteriors: [{hypothesis, posterior_probability}], most_probable}
    data = extract_json(raw)
    state.bayesian_state["posteriors"] = data.get("posteriors", [])
```

**Phase 4 - Sensitivity:**
```python
async def _phase_bayesian_sensitivity(self, state):
    raw, _ = await self.router.call(
        role="synthesis",
        system_prompt=phases.BAYESIAN_SENSITIVITY_SYSTEM,
        user_prompt=phases.bayesian_sensitivity_prompt(state)
    )
    # Output: {sensitivity_analysis: [{assumption, impact}], most_sensitive_assumption}
    data = extract_json(raw)
    state.bayesian_state["sensitivity_results"] = data.get("sensitivity_analysis", [])
```

**Presets:** `bayesian-budget`, `bayesian-premium`

**Βέλτιστο Για:** Αποφάσεις υπό αβεβαιότητα, ποσοτικοποίηση ρίσκου

---

### Dialectical

**Μεθοδολογία (Hegelian):**
```
Thesis → Antithesis → Contradictions → Aufhebung (Transcendence)
```

**Pipeline:**
```python
async def _run_dialectical_pipeline(self, state):
    await self._phase_dialectical_thesis(state)           # Primary position
    await self._phase_dialectical_antithesis(state)        # Opposing position
    await self._phase_dialectical_contradictions(state)   # Analyze conflicts
    await self._phase_dialectical_aufhebung(state)        # Transcend
```

**Phase 1 - Thesis:**
```python
async def _phase_dialectical_thesis(self, state):
    raw, _ = await self.router.call(
        role="constructive",
        system_prompt=phases.DIALECTICAL_THESIS_SYSTEM,
        user_prompt=phases.dialectical_thesis_prompt(state)
    )
    # Output: {thesis, key_commitments[], assumptions[]}
    data = extract_json(raw)
    state.dialectical_state["thesis"] = data.get("thesis", "")
    state.dialectical_state["key_commitments"] = data.get("key_commitments", [])
```

**Phase 2 - Antithesis:**
```python
async def _phase_dialectical_antithesis(self, state):
    raw, _ = await self.router.call(
        role="destructive",
        system_prompt=phases.DIALECTICAL_ANTITHESIS_SYSTEM,
        user_prompt=phases.dialectical_antithesis_prompt(state)
    )
    # Output: {antithesis, contradictions_exposed[], negated_commitments[]}
    data = extract_json(raw)
    state.dialectical_state["antithesis"] = data.get("antithesis", "")
    state.dialectical_state["contradictions_exposed"] = data.get("contradictions_exposed", [])
```

**Phase 3 - Contradictions:**
```python
async def _phase_dialectical_contradictions(self, state):
    raw, _ = await self.router.call(
        role="scoring",
        system_prompt=phases.DIALECTICAL_CONTRADICTIONS_SYSTEM,
        user_prompt=phases.dialectical_contradictions_prompt(state)
    )
    # Output: {irreconcilable[], compatible[]}
    data = extract_json(raw)
    state.dialectical_state["irreconcilable"] = data.get("irreconcilable", [])
    state.dialectical_state["compatible"] = data.get("compatible", [])
```

**Phase 4 - Aufhebung:**
```python
async def _phase_dialectical_aufhebung(self, state):
    raw, _ = await self.router.call(
        role="synthesis",
        system_prompt=phases.DIALECTICAL_AUFHEBUNG_SYSTEM,
        user_prompt=phases.dialectical_aufhebung_prompt(state)
    )
    # Output: {synthesis, preserved_truths[], new_concepts[]}
    # NOT compromise - qualitative transcendence
    data = extract_json(raw)
    state.dialectical_state["synthesis"] = data.get("synthesis", "")
```

**Presets:** `dialectical-budget`, `dialectical-premium`

**Βέλτιστο Για:** Φιλοσοφικά προβλήματα, πολιτικές debates

---

### Analogical

**Μεθοδολογία (Gentner, 1983 - Structure-Mapping):**
```
Abstraction → Domain Search → Mapping → Transfer & Adaptation
```

**Pipeline:**
```python
async def _run_analogical_pipeline(self, state):
    await self._phase_analogical_abstraction(state)     # Extract structure
    await self._phase_analogical_domain_search(state)   # Find source domains
    if state.analogical_state.get("source_domains"):
        await self._phase_analogical_mapping(state)      # Map elements
        await self._phase_analogical_transfer(state)      # Transfer solution
```

**Phase 1 - Abstraction:**
```python
async def _phase_analogical_abstraction(self, state):
    raw, _ = await self.router.call(
        role="systemic",
        system_prompt=phases.ANALOGICAL_ABSTRACTION_SYSTEM,
        user_prompt=phases.analogical_abstraction_prompt(state)
    )
    # Output: {abstract_structure, constraints[], objectives[], actors[], core_dynamics[]}
    data = extract_json(raw)
    state.analogical_state["abstract_structure"] = data.get("abstract_structure", "")
    state.analogical_state["constraints"] = data.get("constraints", [])
```

**Phase 2 - Domain Search:**
```python
async def _phase_analogical_domain_search(self, state):
    raw, _ = await self.router.call(
        role="systemic",
        system_prompt=phases.ANALOGICAL_DOMAIN_SEARCH_SYSTEM,
        user_prompt=phases.analogical_domain_search_prompt(state)
    )
    # Output: {source_domains: [{domain, relevance, solution}]}
    data = extract_json(raw)
    state.analogical_state["source_domains"] = data.get("source_domains", [])
```

**Phase 3 - Mapping:**
```python
async def _phase_analogical_mapping(self, state):
    raw, _ = await self.router.call(
        role="systemic",
        system_prompt=phases.ANALOGICAL_MAPPING_SYSTEM,
        user_prompt=phases.analogical_mapping_prompt(state)
    )
    # Output: {analogy_mappings[], unmapped_elements[], mapping_quality}
    data = extract_json(raw)
    state.analogical_state["analogy_mappings"] = data.get("analogy_mappings", [])
```

**Phase 4 - Transfer:**
```python
async def _phase_analogical_transfer(self, state):
    raw, _ = await self.router.call(
        role="synthesis",
        system_prompt=phases.ANALOGICAL_TRANSFER_SYSTEM,
        user_prompt=phases.analogical_transfer_prompt(state)
    )
    # Output: {transferred_solution, transfer_steps[], adaptations_required[], confidence}
    data = extract_json(raw)
    state.analogical_state["transferred_solution"] = data.get("transferred_solution", "")
```

**Presets:** `analogical-budget`, `analogical-premium`

**Βέλτιστο Για:** Καινοτομία μέσω cross-domain transfer

---

### Delphi

**Μεθοδολογία (RAND Corporation, Dalkey & Helmer, 1963):**
```
Round 1 (Independent) → Aggregation → Round 2 (Revision) → Convergence → Dissent
```

**Pipeline:**
```python
async def _run_delphi_pipeline(self, state):
    await self._phase_delphi_round1(state)        # 4 independent experts
    await self._phase_delphi_aggregation(state)    # Compute median, IQR
    await self._phase_delphi_round2(state)        # Revision with feedback
    await self._phase_delphi_convergence(state)   # Check convergence
    await self._phase_delphi_dissent(state)       # Analyze disagreements
```

**Round 1:**
```python
async def _phase_delphi_round1(self, state):
    tasks = [
        self.router.call(
            role=f"expert_{i+1}",
            system_prompt=phases.DELPHI_EXPERT_SYSTEM,
            user_prompt=phases.delphi_round1_prompt(state, expert_num=i+1)
        )
        for i in range(4)
    ]
    
    results = await asyncio.gather(*tasks)
    estimates = []
    for raw, _ in results:
        data = extract_json(raw)
        data["expert_id"] = f"expert_{i+1}"
        estimates.append(data)
    
    state.delphi_state["round_1_estimates"] = estimates
```

**Aggregation:**
```python
async def _phase_delphi_aggregation(self, state):
    values = [e.get("estimate_value") for e in estimates if isinstance(e.get("estimate_value"), (int, float))]
    
    # Compute statistics
    values_sorted = sorted(values)
    median = ...
    q1, q3 = ...
    iqr = q3 - q1
    
    # Identify outlier
    outlier_id = max(estimates, key=lambda e: abs(e.get("estimate_value", 0) - median))
    
    state.delphi_state["aggregated_stats"] = {
        "median": median,
        "q1": q1, "q3": q3, "iqr": iqr,
        "outlier_expert": outlier_id,
        "n_estimates": len(values)
    }
```

**Round 2 - Revision:**
```python
async def _phase_delphi_round2(self, state):
    stats = state.delphi_state["aggregated_stats"]
    
    for expert_id in ["expert_1", "expert_2", "expert_3", "expert_4"]:
        # Provide feedback: your estimate, median, outlier info
        raw, _ = await self.router.call(
            role=expert_id,
            system_prompt=phases.DELPHI_REVISION_SYSTEM,
            user_prompt=phases.delphi_round2_prompt(state, expert_id)
        )
        
        data = extract_json(raw)
        data["expert_id"] = expert_id
        round2_estimates.append(data)
    
    state.delphi_state["round_2_estimates"] = round2_estimates
```

**Convergence:**
```python
async def _phase_delphi_convergence(self, state):
    raw, _ = await self.router.call(
        role="synthesis",
        system_prompt=phases.DELPHI_CONVERGENCE_SYSTEM,
        user_prompt=phases.delphi_convergence_prompt(state)
    )
    
    data = extract_json(raw)
    state.delphi_state["consensus"] = data.get("consensus", {})
    state.delphi_state["convergence_achieved"] = data.get("convergence_achieved", False)
```

**Dissent Analysis:**
```python
async def _phase_delphi_dissent(self, state):
    raw, _ = await self.router.call(
        role="synthesis",
        system_prompt=phases.DELPHI_DISSENT_SYSTEM,
        user_prompt=phases.delphi_dissent_prompt(state)
    )
    
    data = extract_json(raw)
    state.delphi_state["dissent_analysis"] = data.get("dissent_analysis", {})
```

**Presets:** `delphi-budget`, `delphi-premium`

**Βέλτιστο Για:** Προβλέψεις, expert consensus

---

## 5. Οδηγός Επιλογής Μεθόδου

| Πρόβλημα | Μέθοδος |
|----------|---------|
| Γενική ανάλυση | Multi-Perspective |
| Βελτιστοποίηση | Iterative |
| Στρατηγικές αποφάσεις | Debate |
| Έρευνα/Γεγονότα | Research |
| Υψηλό ρίσκο | Jury |
| Επιστημονική μέθοδος | Scientific |
| Διευκρίνιση | Socratic |
| Αξιολόγηση κινδύνου | Pre-Mortem |
| Αβεβαιότητα | Bayesian |
| Φιλοσοφικό | Dialectical |
| Καινοτομία | Analogical |
| Πρόβλεψη | Delphi |

---

## Σύνοψη

Το ARA Pipeline παρέχει 7 τυπικές και 5 εξειδικευμένες μεθόδους συλλογιστικής. Κάθε μέθοδος υλοποιεί διαφορετική στρατηγική συλλογισμού, βελτιστοποιημένη για συγκεκριμένους τύπους προβλημάτων και περιορισμούς κόστους.