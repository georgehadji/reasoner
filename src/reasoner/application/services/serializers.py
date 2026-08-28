from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState

# `_event` is defined in sse_utils to avoid duplication across
# serializers.py and streaming.py.  Imported here for backward
# compatibility so consumers of api.serializers still find it.


def _is_orchestrated(preset: str) -> bool:
    return preset in ("jury", "jury-budget", "jury-premium", "orchestrated")

def _is_debate(preset: str) -> bool:
    return "debate" in preset

def _is_scientific(preset: str) -> bool:
    return "scientific" in preset

def _is_socratic(preset: str) -> bool:
    return "socratic" in preset

def _get_v(obj, key, default=None):
    if obj is None: return default
    if isinstance(obj, dict):
        val = obj.get(key, default)
        return default if val is None else val
    val = getattr(obj, key, default)
    return default if val is None else val

def _ser_0(state: PipelineState) -> dict:
    tt = _get_v(state, 'task_type')
    return {
        "task_type": tt.value if hasattr(tt, 'value') else str(tt or "unknown"),
        "rationale": _get_v(state, 'task_type_rationale', ''),
        "language": _get_v(state, 'language', 'English'),
        "tokens": state.phase_tokens.get("Phase 0: Classification", {"input": 0, "output": 0}),
    }

def _ser_1(state: PipelineState) -> dict:
    dec = _get_v(state, 'decomposition')
    if dec is None: return {}

    # Handle both object and dict formats
    sub_problems = _get_v(dec, 'sub_problems', [])
    assumptions = _get_v(dec, 'assumptions', [])

    return {
        "sub_problems": [
            {
                "id": _get_v(sp, 'id', ''),
                "description": _get_v(sp, 'description', ''),
                "constraints": _get_v(sp, 'constraints', [])
            } for sp in sub_problems
        ],
        "assumptions": [
            {
                "text": _get_v(a, 'text', ''),
                "label": (lambda x: x.value if hasattr(x, 'value') else str(x))(_get_v(a, 'label', 'UNKNOWN')),
                "rationale": _get_v(a, 'rationale', ''),
                # W2 premise audit (docs/plans/sycophancy-mitigation.md)
                "origin": _get_v(a, 'origin', 'analyst'),
                "load_bearing": _get_v(a, 'load_bearing', False),
                "falsifier": _get_v(a, 'falsifier', ''),
                "resolvable_by": _get_v(a, 'resolvable_by', ''),
            } for a in assumptions
        ],
        "failure_modes": _get_v(dec, 'failure_modes', []),
        "tokens": state.phase_tokens.get("Phase 1: Decomposition", {"input": 0, "output": 0}),
    }

def _ser_1_5(state: PipelineState) -> dict:
    """Deep Read serializer."""
    # Fallback to web_discovery_results if vetted_context is empty
    raw = _get_v(state, "vetted_context", [])
    if not raw:
        raw = _get_v(state, "web_discovery_results", [])

    # Return vetted results that contain deep read extractions
    clean = []
    for r in raw:
        item = {
            "url": r.get("url"),
            "title": r.get("title"),
            "date": r.get("date") or r.get("published"),
            "summary": r.get("summary", ""),
            "key_facts": r.get("key_facts", []),
            "relevant_quotes": r.get("relevant_quotes", []),
            "extraction_success": r.get("extraction_success", False),
        }
        if item["url"] and item["title"] and item.get("extraction_success"):
            clean.append(item)

    return {
        "vetted_context": clean,
        "tokens": state.phase_tokens.get(
            "Phase 1.5: Deep Read", {"input": 0, "output": 0}
        ),
    }

def _ser_2(state: PipelineState) -> dict:
    # ── Method-specific Phase 2 data ──
    scientific = _get_v(state, 'scientific_state', {})
    if scientific and scientific.get("hypotheses"):
        return {
            "scientific_state": {"hypotheses": scientific["hypotheses"]},
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")), {"input": 0, "output": 0}),
        }

    socratic = _get_v(state, 'socratic_state', {})
    if socratic and socratic.get("questions"):
        return {
            "socratic_state": {"questions": socratic["questions"]},
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")), {"input": 0, "output": 0}),
        }

    pre_mortem = _get_v(state, 'pre_mortem_state', {})
    if pre_mortem and pre_mortem.get("failure_narrative"):
        return {
            "pre_mortem_state": {"failure_narrative": pre_mortem["failure_narrative"]},
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")), {"input": 0, "output": 0}),
        }

    bayesian = _get_v(state, 'bayesian_state', {})
    if bayesian and bayesian.get("hypotheses_with_priors"):
        return {
            "bayesian_state": {"hypotheses_with_priors": bayesian["hypotheses_with_priors"]},
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")), {"input": 0, "output": 0}),
        }

    dialectical = _get_v(state, 'dialectical_state', {})
    if dialectical and dialectical.get("thesis"):
        return {
            "dialectical_state": {
                "thesis": dialectical["thesis"],
                "key_commitments": dialectical.get("key_commitments", []),
                "thesis_assumptions": dialectical.get("thesis_assumptions", []),
            },
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")), {"input": 0, "output": 0}),
        }

    analogical = _get_v(state, 'analogical_state', {})
    if analogical and analogical.get("abstract_structure"):
        return {
            "analogical_state": {
                "abstract_structure": analogical["abstract_structure"],
                "constraints": analogical.get("constraints", []),
                "objectives": analogical.get("objectives", []),
                "actors": analogical.get("actors", []),
                "core_dynamics": analogical.get("core_dynamics", []),
                "structural_type": analogical.get("structural_type", ""),
            },
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")), {"input": 0, "output": 0}),
        }

    debate = _get_v(state, 'debate_rounds', [])
    if debate:
        return {
            "debate_rounds": debate,
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")), {"input": 0, "output": 0}),
        }

    cove = _get_v(state, 'cove_state', {})
    if cove and cove.get("draft_answer"):
        return {
            "cove_state": {
                "draft_answer": cove["draft_answer"],
                "claims": cove.get("claims", []),
            },
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")), {"input": 0, "output": 0}),
        }

    sot = _get_v(state, 'sot_state', {})
    if sot and sot.get("sub_problems"):
        return {
            "sot_state": {"sub_problems": sot["sub_problems"]},
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")), {"input": 0, "output": 0}),
        }

    tot = _get_v(state, 'tot_state', {})
    if tot and tot.get("decision_points"):
        return {
            "tot_state": {"decision_points": tot["decision_points"]},
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")), {"input": 0, "output": 0}),
        }

    pot = _get_v(state, 'pot_state', {})
    if pot and pot.get("code"):
        return {
            "pot_state": {
                "code": pot["code"],
                "explanation": pot.get("explanation", ""),
                "expected_output_type": pot.get("expected_output_type", ""),
            },
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")), {"input": 0, "output": 0}),
        }

    sd = _get_v(state, 'self_discover_state', {})
    if sd and sd.get("selected_modules"):
        return {
            "self_discover_state": {
                "selected_modules": sd["selected_modules"],
                "composition_strategy": sd.get("composition_strategy", ""),
            },
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")), {"input": 0, "output": 0}),
        }

    delphi = _get_v(state, 'delphi_state', {})
    if delphi and delphi.get("round1_estimates"):
        return {
            "delphi_state": {"round1_estimates": delphi["round1_estimates"]},
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")), {"input": 0, "output": 0}),
        }

    # ── Research Phase 2: deep web search results ────────────────────────────
    research_results = _get_v(state, 'web_discovery_results', [])
    if research_results and getattr(state, 'method', None) == "research":
        clean = [r for r in research_results if r.get("url") and r.get("title")][:20]
        return {
            "web_discovery_results": clean,
            "tokens": next(
                (v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")),
                {"input": 0, "output": 0},
            ),
        }

    # ── Brainstorming Phase 2: raw VS idea pool ───────────────────────────────
    bs = _get_v(state, 'brainstorming_state', {})
    if bs and bs.get("raw_ideas"):
        return {
            "brainstorming_state": {
                "raw_ideas": bs["raw_ideas"],
                "raw_idea_count": bs.get("raw_idea_count", 0),
            },
            "tokens": next(
                (v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")),
                {"input": 0, "output": 0},
            ),
        }

    coding = _get_v(state, 'coding_state', {})
    if coding and coding.get("spec"):
        return {
            "coding_state": {
                "spec": coding["spec"],
                "language": coding.get("language", ""),
                "framework": coding.get("framework", ""),
                "files_to_generate": coding.get("files_to_generate", []),
            },
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")), {"input": 0, "output": 0}),
        }

    writing = _get_v(state, 'writing_state', {})
    if writing and "retrieved_sources" in writing:
        # "Retrieve Sources" phase completed — show sources, not subquestions
        return {
            "writing_state": {
                "retrieved_sources": [
                    {
                        "title": s.get("title", ""),
                        "url": s.get("url", ""),
                        "date": s.get("date", ""),
                        "excerpt": s.get("excerpt", "")[:300],
                        "authority_score": s.get("authority_score", 0.0),
                        "source_type": s.get("source_type", "website"),
                    }
                    for s in writing["retrieved_sources"][:20]
                ],
            },
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2.5:")), {"input": 0, "output": 0}),
        }
    if writing and writing.get("subquestions"):
        return {
            "writing_state": {
                "subquestions": writing["subquestions"],
                "topic": writing.get("topic", ""),
                "definitions_required": writing.get("definitions_required", []),
                "unknowns": writing.get("unknowns", []),
            },
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")), {"input": 0, "output": 0}),
        }
    if writing and writing.get("outline"):
        return {
            "writing_state": {
                "outline": writing["outline"],
                "suggested_title": writing.get("suggested_title", ""),
                "total_word_count": writing.get("total_word_count", 0),
            },
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")), {"input": 0, "output": 0}),
        }

    # ── Default (Multi-Perspective / Jury / etc.) ──
    candidates = _get_v(state, 'candidates', [])
    gen_candidates = _get_v(state, 'generation_candidates', [])

    result = {
        "candidates": [
            {
                "perspective": (lambda x: x.value if hasattr(x, 'value') else str(x))(_get_v(c, 'perspective', '')),
                "content": _get_v(c, 'content', ''),
                "key_insights": _get_v(c, 'key_insights', []),
                "model_used": _get_v(c, 'model_used', ''),
            } for c in candidates
        ],
        "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 2:")), {"input": 0, "output": 0}),
    }

    if gen_candidates:
        result["generation_candidates"] = [
            {
                "generator_id": _get_v(gc, 'generator_id', ''),
                "model_used": _get_v(gc, 'model_used', ''),
                "solution": _get_v(gc, 'solution', ''),
                "confidence": _get_v(gc, 'confidence', 0),
                "key_claims": _get_v(gc, 'key_claims', []),
                "approach_summary": _get_v(gc, 'approach_summary', ''),
            } for gc in gen_candidates
        ]

    # Include web discovery results for research method phases
    web_discovery = _get_v(state, 'web_discovery_results', [])
    if web_discovery:
        result["web_discovery_results"] = web_discovery

    return result

def _ser_3(state: PipelineState) -> dict:
    # ── Method-specific Phase 3 data ──
    scientific = _get_v(state, 'scientific_state', {})
    if scientific and scientific.get("test_results"):
        return {
            "scientific_state": {"test_results": scientific["test_results"]},
            "tokens": state.phase_tokens.get("Phase 3: Falsification Tests", {"input": 0, "output": 0}),
        }

    socratic = _get_v(state, 'socratic_state', {})
    if socratic and socratic.get("answers"):
        return {
            "socratic_state": {"answers": socratic["answers"]},
            "tokens": state.phase_tokens.get("Phase 3: Dialectic Answers", {"input": 0, "output": 0}),
        }

    pre_mortem = _get_v(state, 'pre_mortem_state', {})
    if pre_mortem and pre_mortem.get("root_cause"):
        return {
            "pre_mortem_state": {"root_cause": pre_mortem["root_cause"]},
            "tokens": state.phase_tokens.get("Phase 3: Root Cause Analysis", {"input": 0, "output": 0}),
        }

    bayesian = _get_v(state, 'bayesian_state', {})
    if bayesian and bayesian.get("evidence_likelihoods"):
        return {
            "bayesian_state": {
                "evidence_likelihoods": bayesian["evidence_likelihoods"],
                "observations": bayesian.get("observations", []),
            },
            "tokens": state.phase_tokens.get("Phase 3: Likelihood Update", {"input": 0, "output": 0}),
        }

    dialectical = _get_v(state, 'dialectical_state', {})
    if dialectical and dialectical.get("antithesis"):
        return {
            "dialectical_state": {
                "antithesis": dialectical["antithesis"],
                "contradictions_exposed": dialectical.get("contradictions_exposed", []),
                "negated_commitments": dialectical.get("negated_commitments", []),
            },
            "tokens": state.phase_tokens.get("Phase 3: Antithesis", {"input": 0, "output": 0}),
        }

    analogical = _get_v(state, 'analogical_state', {})
    if analogical and analogical.get("source_domains"):
        return {
            "analogical_state": {"source_domains": analogical["source_domains"]},
            "tokens": state.phase_tokens.get("Phase 3: Domain Search", {"input": 0, "output": 0}),
        }

    debate = _get_v(state, 'debate_rounds', [])
    if debate and len(debate) > 1:
        return {
            "debate_rounds": debate,
            "tokens": state.phase_tokens.get("Phase 3: Rebuttals", {"input": 0, "output": 0}),
        }

    cove = _get_v(state, 'cove_state', {})
    if cove and cove.get("verification_questions"):
        return {
            "cove_state": {"verification_questions": cove["verification_questions"]},
            "tokens": state.phase_tokens.get("Phase 3: Verification", {"input": 0, "output": 0}),
        }

    sot = _get_v(state, 'sot_state', {})
    if sot and sot.get("solutions"):
        return {
            "sot_state": {"solutions": sot["solutions"]},
            "tokens": state.phase_tokens.get("Phase 3: Solve", {"input": 0, "output": 0}),
        }

    critic_scores = _get_v(state, 'critic_scores', [])
    if critic_scores:
        serialized_scores = []
        for cs in critic_scores:
            candidate_scores = _get_v(cs, 'candidate_scores', {})
            serialized_candidates = {}

            # Extract items from candidate_scores safely
            items = candidate_scores.items() if hasattr(candidate_scores, 'items') else []
            for gid, ds in items:
                serialized_candidates[gid] = {
                    "factuality": _get_v(ds, 'factuality'),
                    "reasoning": _get_v(ds, 'reasoning'),
                    "completeness": _get_v(ds, 'completeness'),
                    "helpfulness": _get_v(ds, 'helpfulness'),
                    "total": _get_v(ds, 'total'),
                }

            serialized_scores.append({
                "critic_id": _get_v(cs, 'critic_id'),
                "critic_model": _get_v(cs, 'critic_model'),
                "candidate_scores": serialized_candidates,
                "ranking": _get_v(cs, 'ranking'),
                "dissenting_note": _get_v(cs, 'dissenting_note'),
            })

        return {
            "critic_scores": serialized_scores,
            "tokens": state.phase_tokens.get("Phase 3: Critic Pool", {"input": 0, "output": 0}),
        }

    tot = _get_v(state, 'tot_state', {})
    if tot and tot.get("current_candidates"):
        return {
            "tot_state": {
                "current_candidates": tot["current_candidates"],
                "current_path": tot.get("current_path", []),
            },
            "tokens": state.phase_tokens.get("Phase 3: Generate", {"input": 0, "output": 0}),
        }

    pot = _get_v(state, 'pot_state', {})
    if pot and pot.get("execution_output") is not None:
        return {
            "pot_state": {
                "execution_output": pot["execution_output"],
                "execution_success": pot.get("execution_success", False),
                "execution_error": pot.get("execution_error", ""),
                "intermediate_steps": pot.get("intermediate_steps", []),
            },
            "tokens": state.phase_tokens.get("Phase 3: Execute", {"input": 0, "output": 0}),
        }

    sd = _get_v(state, 'self_discover_state', {})
    if sd and sd.get("adapted_modules"):
        return {
            "self_discover_state": {"adapted_modules": sd["adapted_modules"]},
            "tokens": state.phase_tokens.get("Phase 3: Adapt Modules", {"input": 0, "output": 0}),
        }

    delphi = _get_v(state, 'delphi_state', {})
    if delphi and delphi.get("aggregated"):
        return {
            "delphi_state": {"aggregated": delphi["aggregated"]},
            "tokens": state.phase_tokens.get("Phase 3: Aggregation", {"input": 0, "output": 0}),
        }

    # ── Brainstorming Phase 3: clusters + scoring ─────────────────────────────
    bs = _get_v(state, 'brainstorming_state', {})
    if bs and bs.get("clusters"):
        return {
            "brainstorming_state": {
                "clusters": bs["clusters"],
                "top_ideas": bs.get("top_ideas", []),
                "deduplicated_count": bs.get("deduplicated_count", 0),
            },
            "tokens": next(
                (v for k, v in state.phase_tokens.items() if k.startswith("Phase 3:")),
                {"input": 0, "output": 0},
            ),
        }

    coding = _get_v(state, 'coding_state', {})
    if coding and coding.get("generated_files"):
        return {
            "coding_state": {
                "generated_files": [
                    {"path": f.get("path", ""), "language": f.get("language", ""), "key_decisions": f.get("key_decisions", [])}
                    for f in coding["generated_files"]
                ],
                "review": coding.get("review", {}),
            },
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 3:")), {"input": 0, "output": 0}),
        }

    writing = _get_v(state, 'writing_state', {})
    if writing and "cove_draft_claims" in writing:
        return {
            "writing_state": {
                "cove_draft_claims": writing.get("cove_draft_claims", []),
                "cove_verification_questions": writing.get("cove_verification_questions", []),
                "cove_verification_answers": writing.get("cove_verification_answers", []),
                "claims": writing.get("claims", []),
                "cove_changes_made": writing.get("cove_changes_made", []),
                "cove_remaining_uncertainties": writing.get("cove_remaining_uncertainties", []),
            },
            "tokens": state.phase_tokens.get("Phase 3: Extract Claims (CoVE)", {"input": 0, "output": 0}),
        }
    if writing and "claims" in writing:
        return {
            "writing_state": {
                "claims": writing.get("claims", []),
                "verifications": writing.get("verifications", []),
                "metrics": writing.get("metrics", {}),
            },
            "tokens": state.phase_tokens.get("Phase 3: Extract Claims", {"input": 0, "output": 0}),
        }
    if writing and writing.get("article"):
        return {
            "writing_state": {
                "article": writing["article"],
                "abstract": writing.get("abstract", ""),
                "draft_word_count": writing.get("draft_word_count", 0),
                "sections_written": writing.get("sections_written", []),
            },
            "tokens": state.phase_tokens.get("Phase 3: Draft Writing", {"input": 0, "output": 0}),
        }

    # ── Default (Critique & Pruning) ──
    scores = _get_v(state, 'scores', [])
    top_candidates = _get_v(state, 'top_candidates', [])
    top_perspectives = {(_get_v(c, 'perspective').value if hasattr(_get_v(c, 'perspective'), 'value') else str(_get_v(c, 'perspective'))) for c in top_candidates}

    result = {
        "scores": [
            {
                "perspective": (lambda x: x.value if hasattr(x, 'value') else str(x))(_get_v(s, 'perspective', '')),
                "logical_consistency": _get_v(s, 'logical_consistency', 0),
                "evidence_support": _get_v(s, 'evidence_support', 0),
                "failure_resilience": _get_v(s, 'failure_resilience', 0),
                "feasibility": _get_v(s, 'feasibility', 0),
                "total": round(_get_v(s, 'total', 0), 2),
                "bias_flags": _get_v(s, 'bias_flags', []),
                "steel_man": _get_v(s, 'steel_man', ''),
                "is_top": (lambda x: x.value if hasattr(x, 'value') else str(x))(_get_v(s, 'perspective')) in top_perspectives,
            } for s in sorted(scores, key=lambda x: _get_v(x, 'total', 0), reverse=True)
        ],
        "tokens": state.phase_tokens.get("Phase 3: Critique & Pruning", {"input": 0, "output": 0}),
    }

    return result

def _ser_4(state: PipelineState) -> dict:
    # ── Method-specific Phase 4 data ──
    cove = _get_v(state, 'cove_state', {})
    if cove and cove.get("verification_answers"):
        return {
            "cove_state": {"verification_answers": cove["verification_answers"]},
            "tokens": state.phase_tokens.get("Phase 4: Revised Answer", {"input": 0, "output": 0}),
        }

    pre_mortem = _get_v(state, 'pre_mortem_state', {})
    if pre_mortem and pre_mortem.get("early_signals"):
        return {
            "pre_mortem_state": {
                "early_signals": pre_mortem["early_signals"],
                "monitoring_cadence": pre_mortem.get("monitoring_cadence", ""),
            },
            "tokens": state.phase_tokens.get("Phase 4: Early Warning Signals", {"input": 0, "output": 0}),
        }

    bayesian = _get_v(state, 'bayesian_state', {})
    if bayesian and bayesian.get("posteriors"):
        return {
            "bayesian_state": {
                "posteriors": bayesian["posteriors"],
                "most_probable": bayesian.get("most_probable", ""),
            },
            "tokens": state.phase_tokens.get("Phase 4: Posterior Analysis", {"input": 0, "output": 0}),
        }

    dialectical = _get_v(state, 'dialectical_state', {})
    if dialectical and (dialectical.get("irreconcilable") or dialectical.get("compatible") or dialectical.get("synthesis_candidates")):
        return {
            "dialectical_state": {
                "irreconcilable": dialectical.get("irreconcilable", []),
                "compatible": dialectical.get("compatible", []),
                "synthesis_candidates": dialectical.get("synthesis_candidates", []),
            },
            "tokens": state.phase_tokens.get("Phase 4: Contradictions", {"input": 0, "output": 0}),
        }

    analogical = _get_v(state, 'analogical_state', {})
    if analogical and analogical.get("analogy_mappings"):
        return {
            "analogical_state": {
                "analogy_mappings": analogical["analogy_mappings"],
                "unmapped_elements": analogical.get("unmapped_elements", []),
                "mapping_quality": analogical.get("mapping_quality", ""),
            },
            "tokens": state.phase_tokens.get("Phase 4: Mapping", {"input": 0, "output": 0}),
        }

    sot = _get_v(state, 'sot_state', {})
    if sot and sot.get("assembled_answer"):
        return {
            "sot_state": {
                "assembled_answer": sot["assembled_answer"],
                "transitions": sot.get("transitions", []),
                "resolved_conflicts": sot.get("resolved_conflicts", []),
            },
            "tokens": state.phase_tokens.get("Phase 4: Assemble", {"input": 0, "output": 0}),
        }

    tot = _get_v(state, 'tot_state', {})
    if tot and tot.get("evaluations"):
        return {
            "tot_state": {
                "evaluations": tot["evaluations"],
                "best_candidate": tot.get("best_candidate", ""),
                "current_path": tot.get("current_path", []),
            },
            "tokens": state.phase_tokens.get("Phase 4: Evaluate", {"input": 0, "output": 0}),
        }

    pot = _get_v(state, 'pot_state', {})
    if pot and pot.get("interpretation"):
        return {
            "pot_state": {
                "interpretation": pot["interpretation"],
                "computed_answer": pot.get("computed_answer", ""),
                "caveats": pot.get("caveats", []),
            },
            "tokens": state.phase_tokens.get("Phase 4: Interpret", {"input": 0, "output": 0}),
        }

    sd = _get_v(state, 'self_discover_state', {})
    if sd and sd.get("module_outputs"):
        return {
            "self_discover_state": {
                "module_outputs": sd["module_outputs"],
                "final_answer": sd.get("final_answer", ""),
            },
            "tokens": state.phase_tokens.get("Phase 4: Implement", {"input": 0, "output": 0}),
        }

    delphi = _get_v(state, 'delphi_state', {})
    if delphi and delphi.get("round2_estimates"):
        return {
            "delphi_state": {"round2_estimates": delphi["round2_estimates"]},
            "tokens": state.phase_tokens.get("Phase 4: Round 2 Estimates", {"input": 0, "output": 0}),
        }

    # ── Brainstorming Phase 4: full developments ──────────────────────────────
    bs = _get_v(state, 'brainstorming_state', {})
    if bs and bs.get("developments"):
        return {
            "brainstorming_state": {
                "developments": bs.get("developments", []),
                "top_ideas": bs.get("top_ideas", []),
            },
            "tokens": next(
                (v for k, v in state.phase_tokens.items() if k.startswith("Phase 4:") or k.startswith("Phase 7:")),
                {"input": 0, "output": 0},
            ),
        }

    coding = _get_v(state, 'coding_state', {})
    if coding and coding.get("tests"):
        return {
            "coding_state": {
                "tests": {
                    "test_files": [
                        {"path": tf.get("path", ""), "covers": tf.get("covers", [])}
                        for tf in coding["tests"].get("test_files", [])
                    ],
                    "coverage_estimate": coding["tests"].get("coverage_estimate", ""),
                    "missing_coverage": coding["tests"].get("missing_coverage", []),
                },
                "review": coding.get("review", {}),
            },
            "tokens": next((v for k, v in state.phase_tokens.items() if k.startswith("Phase 4:")), {"input": 0, "output": 0}),
        }

    # Writing flow — SoT synthesis (check before pre_mortem/critic since article persists)
    writing = _get_v(state, 'writing_state', {})
    if writing and (writing.get("article") or writing.get("sot_sections") or writing.get("sections")):
        return {
            "writing_state": {
                "article": writing.get("article", ""),
                "title": writing.get("title", ""),
                "abstract": writing.get("abstract", ""),
                "sections": writing.get("sections", []),
                "sot_skeleton": writing.get("sot_skeleton", []),
                "sot_sections": writing.get("sot_sections", []),
                "gaps_noted": writing.get("gaps_noted", []),
            },
            "tokens": state.phase_tokens.get("Phase 4: Synthesize (SoT)", {"input": 0, "output": 0}),
        }

    # Writing flow — Journal Review (checked before pre_mortem since both may exist)
    if writing and writing.get("critic_corrections"):
        return {
            "writing_state": {
                "critic_corrections": writing["critic_corrections"],
                "critic_score": writing.get("critic_score", 0),
                "must_revise": writing.get("must_revise", False),
            },
            "tokens": state.phase_tokens.get("Phase 4.5: Journal Review", {"input": 0, "output": 0}),
        }

    # Writing flow — Pre-Mortem
    if writing and writing.get("pre_mortem"):
        pm = writing["pre_mortem"]
        return {
            "writing_state": {
                "pre_mortem": {
                    "failure_narrative": pm.get("failure_narrative", ""),
                    "root_causes": pm.get("root_causes", []),
                    "weak_sections": pm.get("weak_sections", []),
                    "challenged_claims": pm.get("challenged_claims", []),
                },
            },
            "tokens": state.phase_tokens.get("Phase 4.25: Pre-Mortem", {"input": 0, "output": 0}),
        }

    if writing and writing.get("factcheck_reviews"):
        return {
            "writing_state": {
                "factcheck_reviews": writing["factcheck_reviews"],
                "overall_confidence": writing.get("overall_confidence", 0.0),
                "hallucination_risk": writing.get("hallucination_risk", "unknown"),
                "needs_rewrite": writing.get("needs_rewrite", False),
            },
            "tokens": state.phase_tokens.get("Phase 4: Fact-Check", {"input": 0, "output": 0}),
        }

    # ── Default (Stress Testing) ──
    stress = _get_v(state, 'stress_results', [])
    verif = _get_v(state, 'verification_results', [])
    meta = _get_v(state, 'meta_evaluation')
    scores = _get_v(state, 'scores', [])

    result = {
        "tests": [
            {
                "scenario": (lambda x: x.value if hasattr(x, 'value') else str(x))(_get_v(sr, 'scenario', '')),
                "survival_rate": _get_v(sr, 'survival_rate', 0),
                "failure_mode": _get_v(sr, 'failure_mode', ''),
                "recovery_path": _get_v(sr, 'recovery_path', ''),
            } for sr in stress
        ],
        "tokens": state.phase_tokens.get("Phase 4: Stress Testing", {"input": 0, "output": 0}),
    }

    if verif:
        result["verification_results"] = [
            {
                "claim": _get_v(vr, 'claim', ''),
                "source_generator": _get_v(vr, 'source_generator', ''),
                "verdict": (lambda x: x.value if hasattr(x, 'value') else str(x))(_get_v(vr, 'verdict', '')),
                "evidence": _get_v(vr, 'evidence', ''),
                "confidence": _get_v(vr, 'confidence', 0),
            } for vr in verif
        ]

    if meta:
        result["meta_evaluation"] = {
            "critic_reliability": _get_v(meta, 'critic_reliability', {}),
            "bias_analysis": _get_v(meta, 'bias_analysis', {}),
            "agreement_rate": _get_v(meta, 'agreement_rate', 0),
            "most_reliable_critic": _get_v(meta, 'most_reliable_critic', ''),
            "least_reliable_critic": _get_v(meta, 'least_reliable_critic', ''),
            "meta_insight": _get_v(meta, 'meta_insight', ''),
        }

    return result


def _ser_writing_premortem(state: PipelineState) -> dict:
    """Serializer dedicated to the article Pre-Mortem phase (4.25)."""
    writing = _get_v(state, 'writing_state', {})
    pm = writing.get("pre_mortem", {}) if writing else {}
    # Prefer the revised article if corrections were applied, else show original
    # We check for 'article_original' first (set by C2 fix), falling back to 'article'
    article_original = (writing.get("article_original") or writing.get("article", "")) if writing else ""
    article_revised = writing.get("article_revised", "") if writing else ""
    return {
        "writing_state": {
            "pre_mortem": {
                "failure_narrative": pm.get("failure_narrative", ""),
                "root_causes": pm.get("root_causes", []),
                "weak_sections": pm.get("weak_sections", []),
                "challenged_claims": pm.get("challenged_claims", []),
                "missing_counterarguments": pm.get("missing_counterarguments", []),
                "overgeneralizations": pm.get("overgeneralizations", []),
                "early_warnings": pm.get("early_warnings", []),
            },
            # surface the current article draft alongside so the UI can show both
            "article": article_revised if article_revised else article_original,
            "article_original": article_original if article_revised else "",
        },
        "tokens": state.phase_tokens.get("Phase 4.25: Pre-Mortem", {"input": 0, "output": 0}),
    }


def _ser_writing_critic(state: PipelineState) -> dict:
    """Serializer dedicated to the article Journal Review phase (4.5)."""
    writing = _get_v(state, 'writing_state', {})
    return {
        "writing_state": {
            "critic_corrections": writing.get("critic_corrections", []) if writing else [],
            "critic_score": writing.get("critic_score", 0) if writing else 0,
            "must_revise": writing.get("must_revise", False) if writing else False,
            "article_revised": writing.get("article_revised", "") if writing else "",
            "article": writing.get("article", "") if writing else "",
        },
        "tokens": state.phase_tokens.get("Phase 4.5: Journal Review", {"input": 0, "output": 0}),
    }


def _ser_citations(state: PipelineState) -> list[dict]:
    prism = state.method_state.get("prism") if state.method_state else {}
    return prism.get("citations", [])


def _ser_5(state: PipelineState) -> dict:
    # ── Writing flow — Humanize (check first: most recent state wins) ──
    writing = _get_v(state, 'writing_state', {})
    if writing and writing.get("humanized_article"):
        return {
            "writing_state": {
                "humanized_article": writing["humanized_article"],
                "ai_tells_found": writing.get("ai_tells_found", []),
                "humanize_skipped": writing.get("humanize_skipped", False),
                "humanize_skip_reason": writing.get("humanize_skip_reason", ""),
                # This branch returns before the Final Assembly branch below, and
                # it serves article phases 6, 7 and 8 as well as the writing
                # flow. Without this line the bibliography disappears from the
                # payload of every phase after the humanize pass has run.
                "sources_cited": writing.get("sources_cited", []),
            },
            "tokens": state.phase_tokens.get("Phase 5.5: Humanize", {"input": 0, "output": 0}),
        }

    # ── Writing flow — Final Assembly ──
    if writing and writing.get("final_article"):
        return {
            "writing_state": {
                "final_article": writing["final_article"],
                "title": writing.get("title", ""),
                "sources_cited": writing.get("sources_cited", []),
                "claim_traceability": writing.get("claim_traceability", []),
                "metrics": writing.get("metrics", {}),
                "humanize_skipped": writing.get("humanize_skipped", False),
                "humanize_skip_reason": writing.get("humanize_skip_reason", ""),
            },
            "tokens": state.phase_tokens.get("Phase 5: Final Assembly", {"input": 0, "output": 0}),
        }

    # ── Method-specific Phase 5 data ──
    cove = _get_v(state, 'cove_state', {})
    if cove and cove.get("revised_answer"):
        return {
            "cove_state": {
                "revised_answer": cove["revised_answer"],
                "changes_made": cove.get("changes_made", []),
                "remaining_uncertainties": cove.get("remaining_uncertainties", []),
            },
            "tokens": state.phase_tokens.get("Phase 5: Final Revision", {"input": 0, "output": 0}),
        }

    pre_mortem = _get_v(state, 'pre_mortem_state', {})
    if pre_mortem and pre_mortem.get("hardened_solution"):
        return {
            "pre_mortem_state": {
                "hardened_solution": pre_mortem["hardened_solution"],
                "safeguards": pre_mortem.get("safeguards", []),
                "checkpoints": pre_mortem.get("checkpoints", []),
                "rollback_plan": pre_mortem.get("rollback_plan", ""),
            },
            "tokens": state.phase_tokens.get("Phase 5: Hardened Redesign", {"input": 0, "output": 0}),
        }

    bayesian = _get_v(state, 'bayesian_state', {})
    if bayesian and bayesian.get("sensitivity_results"):
        return {
            "bayesian_state": {
                "sensitivity_results": bayesian["sensitivity_results"],
                "most_sensitive_assumption": bayesian.get("most_sensitive_assumption", ""),
            },
            "tokens": state.phase_tokens.get("Phase 5: Sensitivity Analysis", {"input": 0, "output": 0}),
        }

    dialectical = _get_v(state, 'dialectical_state', {})
    if dialectical and dialectical.get("aufhebung"):
        return {
            "dialectical_state": {
                "aufhebung": dialectical["aufhebung"],
                "preserved_from_thesis": dialectical.get("preserved_from_thesis", []),
                "preserved_from_antithesis": dialectical.get("preserved_from_antithesis", []),
                "transcended": dialectical.get("transcended", ""),
                "new_insights": dialectical.get("new_insights", []),
            },
            "tokens": state.phase_tokens.get("Phase 5: Aufhebung", {"input": 0, "output": 0}),
        }

    analogical = _get_v(state, 'analogical_state', {})
    if analogical and analogical.get("transferred_solution"):
        return {
            "analogical_state": {
                "transferred_solution": analogical["transferred_solution"],
                "transfer_steps": analogical.get("transfer_steps", []),
                "adaptations_required": analogical.get("adaptations_required", []),
                "broken_analogies": analogical.get("broken_analogies", []),
                "transfer_confidence": analogical.get("transfer_confidence", ""),
                "caveats": analogical.get("caveats", []),
            },
            "tokens": state.phase_tokens.get("Phase 5: Transfer", {"input": 0, "output": 0}),
        }

    tot = _get_v(state, 'tot_state', {})
    if tot and tot.get("backtrack_decision"):
        return {
            "tot_state": {
                "backtrack_decision": tot["backtrack_decision"],
                "final_path": tot.get("final_path", []),
                "tot_confidence": tot.get("tot_confidence", 0.0),
            },
            "tokens": state.phase_tokens.get("Phase 5: Backtrack", {"input": 0, "output": 0}),
        }

    delphi = _get_v(state, 'delphi_state', {})
    if delphi and (delphi.get("convergence") or delphi.get("dissent_report")):
        result = {}
        if delphi.get("convergence"):
            result["delphi_state"] = {"convergence": delphi["convergence"]}
        if delphi.get("dissent_report"):
            result.setdefault("delphi_state", {})["dissent_report"] = delphi["dissent_report"]
        result["tokens"] = state.phase_tokens.get("Phase 5: Convergence", {"input": 0, "output": 0})
        return result

    coding = _get_v(state, 'coding_state', {})
    if coding and coding.get("final_files"):
        return {
            "coding_state": {
                "final_files": [
                    {"path": f.get("path", ""), "changed": f.get("changed", False)}
                    for f in coding["final_files"]
                ],
                "readme": coding.get("readme", ""),
                "fixes_applied": coding.get("fixes_applied", []),
                "known_limitations": coding.get("known_limitations", []),
                "language": coding.get("language", ""),
                "framework": coding.get("framework", ""),
            },
            "tokens": state.phase_tokens.get("Phase 5: Final Assembly", {"input": 0, "output": 0}),
        }

    base = {}
    citations = _ser_citations(state)
    if citations:
        base["citations"] = citations
    cross_lang = _ser_cross_language(state)
    if cross_lang:
        base["cross_language"] = cross_lang
    return base


def _ser_egress_rewrite(state: PipelineState) -> dict:
    """Serialize the Layer B rewrite outcome, or {} when the phase didn't run."""
    provenance = _get_v(_get_v(state, "meta", None), "provenance_report", {})
    if not isinstance(provenance, dict):
        return {}
    return provenance.get("egress_rewrite", {})


def _ser_cross_language(state: PipelineState) -> dict:
    """Serialize the cross-language pivot metadata, or {} when no pivot ran.

    Keys mirror what _phase_cross_language_translate_in/out actually write to
    cross_language_state. The previous inline version in _ser_synthesis asked
    for target_language/back_translated, which the pipeline never sets, so it
    emitted two constant-empty fields and dropped original_problem -- leaving
    the client unable to show what the user originally typed.
    """
    cross_lang = _get_v(state, "cross_language_state", {})
    if not cross_lang or not cross_lang.get("source_language"):
        return {}
    return {
        "source_language": cross_lang["source_language"],
        "original_problem": cross_lang.get("original_problem", ""),
        "direction": cross_lang.get("direction", ""),
        "translated": bool(
            cross_lang.get("translated_problem") or cross_lang.get("translated_synthesis")
        )
        or cross_lang.get("direction") == "out",
    }


def _ser_synthesis(state: PipelineState) -> dict:
    """Universal Synthesis serializer."""
    # ── Default (Synthesis) ──
    # Check final_solution first so the Synthesis phase shows the clean synthesized
    # output.  writing_state.final_article is the fallback for Final Assembly.
    fs = _get_v(state, "final_solution")
    if fs is not None:
        meta = _get_v(fs, "meta_audit", {})

        # Action blueprint handling
        raw_bp = _get_v(fs, "action_blueprint", [])
        clean_bp = []
        for step in (raw_bp if isinstance(raw_bp, list) else []):
            if isinstance(step, dict):
                # Only accept dicts that have at least one expected key or a non-empty action
                if not any(
                    k in step
                    for k in (
                        "step",
                        "action",
                        "time_horizon",
                        "go_criteria",
                        "fallback",
                    )
                ):
                    continue
                entry = {
                    "step": _get_v(step, "step", ""),
                    "action": _get_v(step, "action", ""),
                    "time_horizon": _get_v(step, "time_horizon", ""),
                    "go_criteria": _get_v(step, "go_criteria", ""),
                    "fallback": _get_v(step, "fallback", ""),
                }
                if entry["step"] or entry["action"]:
                    clean_bp.append(entry)
            elif step is not None and str(step).strip():
                clean_bp.append(
                    {
                        "step": "",
                        "action": str(step).strip(),
                        "time_horizon": "",
                        "go_criteria": "",
                        "fallback": "",
                    }
                )

        # Claim labels handling
        raw_labels = _get_v(fs, "claim_labels", {})
        clean_labels = {
            k: (v.value if hasattr(v, "value") else str(v))
            for k, v in (
                raw_labels.items() if isinstance(raw_labels, dict) else {}
            )
        }

        # Aggregate tokens across all phases
        total_input = sum(t.get("input", 0) for t in state.phase_tokens.values())
        total_output = sum(t.get("output", 0) for t in state.phase_tokens.values())

        # Build meta_audit only when source data exists
        meta_audit: dict[str, Any] = {}
        if meta:
            meta_audit = {
                "most_dangerous_assumption": _get_v(
                    meta, "most_dangerous_assumption", ""
                ),
                "dominant_bias": _get_v(meta, "dominant_bias", ""),
                "remaining_uncertainty": _get_v(meta, "remaining_uncertainty", ""),
                "assumption_failure_impact": _get_v(
                    meta, "assumption_failure_impact", ""
                ),
                "non_obvious_insight": _get_v(meta, "non_obvious_insight", ""),
            }

        # W2 premise audit (docs/plans/sycophancy-mitigation.md §2d) — the
        # load-bearing, user-origin premises the synthesis was built on, so an
        # API/MCP consumer sees what was taken on trust alongside the answer.
        dec = _get_v(state, 'decomposition')
        raw_assumptions = _get_v(dec, 'assumptions', []) if dec is not None else []
        premises: list[dict[str, Any]] = []
        if raw_assumptions:
            from reasoner.core.parsing import _parse_premises
            premises = [
                {
                    "text": p.text,
                    "origin": p.origin,
                    "label": p.label.value,
                    "load_bearing": p.load_bearing,
                    "falsifier": p.falsifier,
                    "resolvable_by": p.resolvable_by,
                }
                for p in _parse_premises(raw_assumptions)
                if p.origin in ("user_stated", "user_implied")
            ]

        result = {
            "core_solution": _get_v(fs, "core_solution", ""),
            "critical_insights": _get_v(fs, "critical_insights", []),
            "action_blueprint": clean_bp,
            "open_questions": _get_v(fs, "open_questions", []),
            "claim_labels": clean_labels,
            "premises": premises,
            "evidence": _get_v(fs, "evidence", {}),
            "meta_audit": meta_audit,
            "layout_hints": _get_v(fs, "layout_hints", {}),
            "tokens": {"input": total_input, "output": total_output},
        }

        # Cross-language metadata
        cross_lang = _ser_cross_language(state)
        if cross_lang:
            result["cross_language"] = cross_lang

        # Provenance/watermark scrub report (domain.watermark, set in synthesis_phase.py) --
        # written onto state.meta but otherwise never left it; the frontend has
        # nothing to show a ProvenanceBadge for without this.
        provenance_report = _get_v(_get_v(state, "meta", None), "provenance_report", {})
        if provenance_report:
            result["provenance_report"] = provenance_report

        return result

    writing = _get_v(state, "writing_state", {})
    if writing and writing.get("humanized_article"):
        return {
            "writing_state": {
                "final_article": writing["humanized_article"],
                "ai_tells_found": writing.get("ai_tells_found", []),
                "metrics": writing.get("metrics", {}),
                "cove_changes_made": writing.get("cove_changes_made", []),
            },
            "tokens": state.phase_tokens.get(
                "Phase 5.5: Humanize", {"input": 0, "output": 0}
            ),
        }
    if writing and writing.get("final_article"):
        return {
            "writing_state": {
                "final_article": writing["final_article"],
                "final_abstract": writing.get("final_abstract", ""),
                "sources_cited": writing.get("sources_cited", []),
                "confidence_notice": writing.get("confidence_notice", ""),
                "final_word_count": writing.get("final_word_count", 0),
                "metrics": writing.get("metrics", {}),
                "claim_traceability": writing.get("claim_traceability", []),
                "gaps_noted": writing.get("gaps_noted", []),
                "sot_skeleton": writing.get("sot_skeleton", []),
                "sot_sections": writing.get("sot_sections", []),
                "pre_mortem": writing.get("pre_mortem", {}),
                "cove_changes_made": writing.get("cove_changes_made", []),
            },
            "tokens": state.phase_tokens.get(
                "Phase 5: Final Assembly", {"input": 0, "output": 0}
            ),
        }

    return {}


# _event is re-exported from sse_utils (imported at top of file).
