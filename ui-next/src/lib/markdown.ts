/* eslint-disable @typescript-eslint/no-explicit-any */

export function buildMarkdownFromPhase(
  index: number,
  phaseNum: number,
  name: string,
  data: unknown,
  options?: {
    omitSections?: Array<'critical_insights' | 'action_blueprint' | 'open_questions' | 'sources' | 'vetted_context'>;
    /** Drop the `### Phase N · name` heading and its rule. Set when the output
     *  is rendered inside a phase card, whose own <h2> already carries both —
     *  otherwise every phase is announced twice and the card contributes an
     *  h3 that outranks nothing. Left off for exports, where the heading is
     *  the only thing separating one phase from the next. */
    omitHeading?: boolean;
  }
): string {
  let md = '';
  if (!options?.omitHeading) {
    if (index > 0) {
      md += '---\n\n';
    }
    md += `### Phase ${index + 1} · ${name}\n\n`;
  }
  if (!data || typeof data !== 'object') {
    md += String(data) + '\n\n';
    return md;
  }

  const d = data as Record<string, unknown>;
  let rendered = false;

  const append = (text: string) => {
    md += text;
    rendered = true;
  };

  // ── Models & Agents metadata ──
  if (Array.isArray(d.models) && d.models.length) {
    append(`*Models: ${(d.models as string[]).map(m => m.split('/').pop() || m).join(', ')}*\n\n`);
  }
  if (Array.isArray(d.subagents) && d.subagents.length) {
    append('*Agents:*\n');
    (d.subagents as Array<Record<string, any>>).forEach((s) => {
      const name = typeof s.name === 'string' ? s.name : 'unknown';
      const model = typeof s.model === 'string' ? s.model : 'unknown';
      append(`- ${name} → ${model.split('/').pop() || model}\n`);
    });
    append('\n');
  }

  // ── Direct answer ──
  if (typeof d.solution === 'string' && d.solution.trim()) {
    append(d.solution + '\n\n');
  }

  // ── Classification / Synthesis common ──
  if (typeof d.task_type === 'string') {
    append(`**Task Type:** ${d.task_type}\n\n`);
  }
  if (typeof d.rationale === 'string' && d.rationale.trim()) {
    append(`${d.rationale}\n\n`);
  }
  if (typeof d.language === 'string') {
    append(`**Language:** ${d.language}\n\n`);
  }

  // ── Decomposition ──
  if (Array.isArray(d.sub_problems) && d.sub_problems.length) {
    append('**Sub-Problems**\n');
    (d.sub_problems as Array<Record<string, any>>).forEach((sp, idx) => {
      const desc = typeof sp.description === 'string' ? sp.description : '';
      const constraints = Array.isArray(sp.constraints) ? (sp.constraints as string[]).join(', ') : '';
      append(`${idx + 1}. ${desc}${constraints ? ` *(constraints: ${constraints})*` : ''}\n`);
    });
    append('\n');
  }
  if (Array.isArray(d.assumptions) && d.assumptions.length) {
    append('**Assumptions**\n');
    (d.assumptions as Array<Record<string, string>>).forEach((a) => {
      append(`- **${a.label || 'UNKNOWN'}**: ${a.text || ''}${a.rationale ? ` — ${a.rationale}` : ''}\n`);
    });
    append('\n');
  }
  if (Array.isArray(d.failure_modes) && d.failure_modes.length) {
    append('**Failure Modes**\n');
    (d.failure_modes as string[]).forEach((fm) => append(`- ${fm}\n`));
    append('\n');
  }

  // ── Deep Read / Research ──
  if (Array.isArray(d.vetted_context) && d.vetted_context.length) {
    append('**Vetted Context**\n');
    (d.vetted_context as Array<Record<string, any>>).forEach((c) => {
      const summary = c.summary || c.content || c.snippet || '';
      const title = c.title || 'Source';
      const url = c.url || '';
      const date = c.date || c.published || '';
      if (url) {
        const attribution = date ? `${date} — [${title}](${url})` : `[${title}](${url})`;
        append(`- ${attribution}\n`);
      } else if (date) {
        append(`- ${date} — ${title}\n`);
      } else {
        append(`- ${title}\n`);
      }
      if (summary) {
        append(`  ${summary}\n`);
      }
      if (Array.isArray(c.key_facts) && c.key_facts.length) {
        c.key_facts.forEach((fact: string) => {
          append(`  - ${fact}\n`);
        });
      }
      if (Array.isArray(c.relevant_quotes) && c.relevant_quotes.length) {
        c.relevant_quotes.forEach((quote: string) => {
          append(`  > *"${quote}"*\n`);
        });
      }
      if (Array.isArray(c.vetting_flags) && c.vetting_flags.length) {
        append(`  ⚠️ Vetting flags: ${c.vetting_flags.length}\n`);
      }
    });
    append('\n');
  }
  if (Array.isArray(d.web_discovery_results) && d.web_discovery_results.length) {
    append('**Sources Discovered**\n');
    (d.web_discovery_results as Array<Record<string, any>>).forEach((r) => {
      const title = r.title || 'Source';
      const url = r.url || '';
      const snippet = r.snippet || r.content || '';
      if (url) {
        append(`- [${title}](${url})`);
      } else {
        append(`- ${title}`);
      }
      if (snippet) {
        append(` — ${snippet}`);
      }
      append('\n');
    });
    append('\n');
  }

  // ── Perspectives / Candidates ──
  if (Array.isArray(d.candidates) && d.candidates.length) {
    (d.candidates as Array<Record<string, any>>).forEach((c) => {
      const perspective = typeof c.perspective === 'string' ? c.perspective : 'Perspective';
      const modelUsed = typeof c.model_used === 'string' ? c.model_used : '';
      const modelLabel = modelUsed ? ` *(model: ${modelUsed.split('/').pop() || modelUsed})*` : '';
      append(`#### ${perspective}${modelLabel}\n\n`);
      if (typeof c.content === 'string' && c.content.trim()) {
        append(c.content + '\n\n');
      }
      if (Array.isArray(c.key_insights) && c.key_insights.length) {
        (c.key_insights as string[]).forEach((insight) => append(`- ${insight}\n`));
        append('\n');
      }
    });
  }
  if (Array.isArray(d.generation_candidates) && d.generation_candidates.length) {
    append('**Generation Candidates**\n');
    (d.generation_candidates as Array<Record<string, any>>).forEach((gc) => {
      const id = typeof gc.generator_id === 'string' ? gc.generator_id : 'Generator';
      append(`- **${id}** (confidence: ${gc.confidence ?? '?'})\n`);
      if (typeof gc.solution === 'string') append(`  ${gc.solution}\n`);
    });
    append('\n');
  }
  if (d.scientific_state && typeof d.scientific_state === 'object') {
    const ss = d.scientific_state as Record<string, unknown>;
    if (Array.isArray(ss.hypotheses) && ss.hypotheses.length) {
      append('**Hypotheses**\n');
      (ss.hypotheses as Array<Record<string, any>>).forEach((h, i) => {
        const id = typeof h.id === 'string' ? h.id : `H${i + 1}`;
        const statement = typeof h.statement === 'string' ? h.statement : typeof h.hypothesis === 'string' ? h.hypothesis : '';
        const falsifiability = typeof h.falsifiability === 'string' ? h.falsifiability : '';
        const posterior = typeof h.posterior_probability === 'number' ? `${Math.round(h.posterior_probability * 100)}%` : '';
        append(`${i + 1}. **${id}** — ${statement}`);
        if (posterior) append(` *(posterior: ${posterior})*`);
        append('\n');
        if (falsifiability) append(`   *Falsifiability:* ${falsifiability}\n`);
      });
      append('\n');
    }
    if (Array.isArray(ss.test_results) && ss.test_results.length) {
      append('**Falsification Tests**\n');
      (ss.test_results as Array<Record<string, any>>).forEach((t) => {
        const hid = typeof t.hypothesis_id === 'string' ? t.hypothesis_id : '';
        const experiment = typeof t.experiment === 'string' ? t.experiment : typeof t.test_name === 'string' ? t.test_name : '';
        const result = typeof t.result === 'string' ? t.result : '?';
        append(`- **${hid || 'Test'}** — ${experiment}`);
        if (result) append(` *[${result}]*`);
        append('\n');
        if (typeof t.observation === 'string' && t.observation.trim()) {
          append(`  *Observation:* ${t.observation}\n`);
        }
      });
      append('\n');
    }
  }
  if (d.socratic_state && typeof d.socratic_state === 'object') {
    const ss = d.socratic_state as Record<string, unknown>;
    if (Array.isArray(ss.questions) && ss.questions.length) {
      append('**Questions**\n');
      (ss.questions as Array<Record<string, any>>).forEach((q, i) => {
        const text = typeof q.text === 'string' ? q.text : typeof q.question === 'string' ? q.question : '';
        const target = typeof q.target_assumption === 'string' ? q.target_assumption : '';
        append(`${i + 1}. ${text}\n`);
        if (target) append(`   *Targets:* ${target}\n`);
      });
      append('\n');
    }
    if (Array.isArray(ss.answers) && ss.answers.length) {
      append('**Answers**\n');
      (ss.answers as Array<Record<string, any>>).forEach((a) => {
        const qid = typeof a.question_id === 'string' ? a.question_id : '';
        const answer = typeof a.answer === 'string' ? a.answer : '';
        const contradiction = typeof a.contradiction_found === 'string' ? a.contradiction_found : '';
        append(`- **${qid || 'Answer'}**: ${answer}\n`);
        if (contradiction) append(`  *Contradiction:* ${contradiction}\n`);
      });
      append('\n');
    }
  }
  // ── State Objects (dispatched via lookup) ──
  // OPTIMIZATION: Skip all 11 state blocks if none are present (common for Perspectives/Classification phases)
  const _STATE_KEYS = ['cove_state','pre_mortem_state','bayesian_state','dialectical_state','analogical_state','sot_state','tot_state','pot_state','self_discover_state','delphi_state','writing_state','debate_rounds'];
  if (_STATE_KEYS.some(k => (d as Record<string, unknown>)[k] !== undefined)) {

  // ── CoVE state ──
  if (d.cove_state && typeof d.cove_state === 'object') {
    const cs = d.cove_state as Record<string, unknown>;
    if (typeof cs.draft_answer === 'string' && cs.draft_answer.trim()) {
      append('**Draft Answer**\n');
      append(cs.draft_answer + '\n\n');
    }
    if (Array.isArray(cs.claims) && cs.claims.length) {
      append('**Claims**\n');
      (cs.claims as string[]).forEach((c) => append(`- ${c}\n`));
      append('\n');
    }
    if (Array.isArray(cs.verification_questions) && cs.verification_questions.length) {
      append('**Verification Questions**\n');
      (cs.verification_questions as Array<Record<string, any>>).forEach((q, i) => {
        const text = typeof q.question === 'string' ? q.question : typeof q.text === 'string' ? q.text : '';
        append(`${i + 1}. ${text}\n`);
      });
      append('\n');
    }
    if (Array.isArray(cs.verification_answers) && cs.verification_answers.length) {
      append('**Verification Answers**\n');
      (cs.verification_answers as Array<Record<string, any>>).forEach((a) => {
        const text = typeof a.answer === 'string' ? a.answer : typeof a.text === 'string' ? a.text : '';
        const question = typeof a.question === 'string' ? a.question : '';
        append(`- ${text}\n`);
        if (question) append(`  *Q:* ${question}\n`);
      });
      append('\n');
    }
    if (typeof cs.revised_answer === 'string' && cs.revised_answer.trim()) {
      append('**Revised Answer**\n');
      append(cs.revised_answer + '\n\n');
    }
    if (Array.isArray(cs.changes_made) && cs.changes_made.length) {
      append('**Changes Made**\n');
      (cs.changes_made as string[]).forEach((c) => append(`- ${c}\n`));
      append('\n');
    }
    if (Array.isArray(cs.remaining_uncertainties) && cs.remaining_uncertainties.length) {
      append('**Remaining Uncertainties**\n');
      (cs.remaining_uncertainties as string[]).forEach((u) => append(`- ${u}\n`));
      append('\n');
    }
  }
  // ── Vetted Context / Sources ──
  if (!options?.omitSections?.includes('vetted_context')) {
    if (Array.isArray(d.vetted_context) && d.vetted_context.length) {
      append('**Vetted Sources**\n');
      (d.vetted_context as any[]).forEach((item) => {
        const title = item.title || 'Source';
        const url = item.url || '';
        const summary = item.summary || item.snippet || '';
        append(`- [${title}](${url})${summary ? `: ${summary}` : ''}\n`);
        if (Array.isArray(item.key_facts) && item.key_facts.length) {
          item.key_facts.forEach((f: any) => append(`  - ${f}\n`));
        }
      });
      append('\n');
    }
  }

  // ── Pre-Mortem state ──
  if (d.pre_mortem_state && typeof d.pre_mortem_state === 'object') {
    const pm = d.pre_mortem_state as Record<string, unknown>;

    // Failure Narrative (handle string or object)
    if (pm.failure_narrative) {
      append('**Failure Narrative**\n');
      if (typeof pm.failure_narrative === 'string') {
        append(pm.failure_narrative + '\n\n');
      } else if (typeof pm.failure_narrative === 'object') {
        const fn = pm.failure_narrative as Record<string, any>;
        if (fn.scenario) append(`*Scenario:* ${fn.scenario}\n\n`);
        if (fn.what_happened) append(`${fn.what_happened}\n\n`);
        if (Array.isArray(fn.immediate_triggers) && fn.immediate_triggers.length) {
          append('Immediate Triggers:\n');
          fn.immediate_triggers.forEach((t: any) => append(`- ${t}\n`));
          append('\n');
        }
      }
    }

    if (pm.root_cause && typeof pm.root_cause === 'object') {
      append('**Root Cause**\n');
      const rc = pm.root_cause as Record<string, any>;
      if (rc.pivot_decision) append(`*Pivot Decision:* ${rc.pivot_decision}\n\n`);
      if (rc.cascade && Array.isArray(rc.cascade)) {
        rc.cascade.forEach((step: any) => append(`- ${step}\n`));
        append('\n');
      }
    }

    if (Array.isArray(pm.early_signals) && pm.early_signals.length) {
      append('**Early Warning Signals**\n');
      (pm.early_signals as any[]).forEach((s) => {
        if (typeof s === 'string') {
          append(`- ${s}\n`);
        } else if (typeof s === 'object' && s !== null) {
          const signal = s.signal || s.text || 'Unknown signal';
          const detect = s.how_to_detect || s.detection;
          append(`- ${signal}${detect ? ` (Detect: ${detect})` : ''}\n`);
        }
      });
      append('\n');
    }

    if (typeof pm.monitoring_cadence === 'string' && pm.monitoring_cadence.trim()) {
      append(`*Monitoring cadence:* ${pm.monitoring_cadence}\n\n`);
    }

    if (typeof pm.hardened_solution === 'string' && pm.hardened_solution.trim()) {
      append('**Hardened Solution**\n');
      append(pm.hardened_solution + '\n\n');
    }

    if (Array.isArray(pm.safeguards) && pm.safeguards.length) {
      append('**Safeguards**\n');
      (pm.safeguards as any[]).forEach((s) => {
        if (typeof s === 'string') {
          append(`- ${s}\n`);
        } else if (typeof s === 'object' && s !== null) {
          append(`- ${s.name || s.title || s.text || 'Safeguard'}${s.description ? `: ${s.description}` : ''}\n`);
        }
      });
      append('\n');
    }

    if (Array.isArray(pm.checkpoints) && pm.checkpoints.length) {
      append('**Checkpoints**\n');
      (pm.checkpoints as any[]).forEach((c) => {
        if (typeof c === 'string') {
          append(`- ${c}\n`);
        } else if (typeof c === 'object' && c !== null) {
          const cp = c.checkpoint || c.text || c.validation_metric || 'Checkpoint';
          append(`- ${cp}${c.target ? ` (Target: ${c.target})` : ''}\n`);
        }
      });
      append('\n');
    }

    if (typeof pm.rollback_plan === 'string' && pm.rollback_plan.trim()) {
      append(`*Rollback plan:* ${pm.rollback_plan}\n\n`);
    }
  }
  // ── Bayesian state ──
  if (d.bayesian_state && typeof d.bayesian_state === 'object') {
    const bs = d.bayesian_state as Record<string, unknown>;
    if (Array.isArray(bs.hypotheses_with_priors) && bs.hypotheses_with_priors.length) {
      append('**Hypotheses with Priors**\n');
      (bs.hypotheses_with_priors as Array<Record<string, any>>).forEach((h, i) => {
        const statement = typeof h.statement === 'string' ? h.statement : typeof h.hypothesis === 'string' ? h.hypothesis : '';
        const prior = typeof h.prior === 'number' ? h.prior : typeof h.prior_probability === 'number' ? h.prior_probability : undefined;
        append(`${i + 1}. ${statement}`);
        if (prior !== undefined) append(` *(prior: ${prior})*`);
        append('\n');
      });
      append('\n');
    }
    if (Array.isArray(bs.evidence_likelihoods) && bs.evidence_likelihoods.length) {
      append('**Evidence Likelihoods**\n');
      (bs.evidence_likelihoods as Array<Record<string, any>>).forEach((el) => {
        const evidence = typeof el.evidence === 'string' ? el.evidence : '';
        const likelihood = typeof el.likelihood === 'number' ? el.likelihood : typeof el.value === 'number' ? el.value : '?';
        append(`- ${evidence} — likelihood: ${likelihood}\n`);
      });
      append('\n');
    }
    if (Array.isArray(bs.observations) && bs.observations.length) {
      append('**Observations**\n');
      (bs.observations as string[]).forEach((o) => append(`- ${o}\n`));
      append('\n');
    }
    if (Array.isArray(bs.posteriors) && bs.posteriors.length) {
      append('**Posteriors**\n');
      (bs.posteriors as Array<Record<string, any>>).forEach((p) => {
        const id = typeof p.hypothesis_id === 'string' ? p.hypothesis_id : typeof p.id === 'string' ? p.id : '';
        const value = typeof p.posterior === 'number' ? p.posterior : typeof p.value === 'number' ? p.value : '?';
        append(`- **${id || 'H'}** — posterior: ${value}\n`);
      });
      append('\n');
    }
    if (typeof bs.most_probable === 'string' && bs.most_probable.trim()) {
      append(`*Most probable:* ${bs.most_probable}\n\n`);
    }
    if (Array.isArray(bs.sensitivity_results) && bs.sensitivity_results.length) {
      append('**Sensitivity Analysis**\n');
      (bs.sensitivity_results as Array<Record<string, any>>).forEach((sr) => {
        const assumption = typeof sr.assumption === 'string' ? sr.assumption : '';
        const impact = typeof sr.impact === 'string' ? sr.impact : '';
        append(`- ${assumption}${impact ? ` — impact: ${impact}` : ''}\n`);
      });
      append('\n');
    }
    if (typeof bs.most_sensitive_assumption === 'string' && bs.most_sensitive_assumption.trim()) {
      append(`*Most sensitive assumption:* ${bs.most_sensitive_assumption}\n\n`);
    }
  }
  // ── Dialectical state ──
  if (d.dialectical_state && typeof d.dialectical_state === 'object') {
    const ds = d.dialectical_state as Record<string, unknown>;
    if (typeof ds.thesis === 'string' && ds.thesis.trim()) {
      append('**Thesis**\n');
      append(ds.thesis + '\n\n');
    }
    if (Array.isArray(ds.key_commitments) && ds.key_commitments.length) {
      append('**Key Commitments**\n');
      (ds.key_commitments as string[]).forEach((c) => append(`- ${c}\n`));
      append('\n');
    }
    if (Array.isArray(ds.thesis_assumptions) && ds.thesis_assumptions.length) {
      append('**Thesis Assumptions**\n');
      (ds.thesis_assumptions as string[]).forEach((a) => append(`- ${a}\n`));
      append('\n');
    }
    if (typeof ds.antithesis === 'string' && ds.antithesis.trim()) {
      append('**Antithesis**\n');
      append(ds.antithesis + '\n\n');
    }
    if (Array.isArray(ds.contradictions_exposed) && ds.contradictions_exposed.length) {
      append('**Contradictions Exposed**\n');
      (ds.contradictions_exposed as string[]).forEach((c) => append(`- ${c}\n`));
      append('\n');
    }
    if (Array.isArray(ds.negated_commitments) && ds.negated_commitments.length) {
      append('**Negated Commitments**\n');
      (ds.negated_commitments as any[]).forEach((n) => {
        if (typeof n === 'string') {
          append(`- ${n}\n`);
        } else if (n && typeof n === 'object') {
          const comm = n.commitment || n.text || '';
          const neg = n.negation || n.counter || '';
          if (comm && neg) {
            append(`- **${comm}**: ${neg}\n`);
          } else {
            append(`- ${comm || neg}\n`);
          }
        }
      });
      append('\n');
    }
    if (Array.isArray(ds.irreconcilable) && ds.irreconcilable.length) {
      append('**Irreconcilable**\n');
      (ds.irreconcilable as string[]).forEach((x) => append(`- ${x}\n`));
      append('\n');
    }
    if (Array.isArray(ds.compatible) && ds.compatible.length) {
      append('**Compatible**\n');
      (ds.compatible as string[]).forEach((x) => append(`- ${x}\n`));
      append('\n');
    }
    if (Array.isArray(ds.synthesis_candidates) && ds.synthesis_candidates.length) {
      append('**Synthesis Candidates**\n');
      (ds.synthesis_candidates as string[]).forEach((s) => append(`- ${s}\n`));
      append('\n');
    }
    if (typeof ds.aufhebung === 'string' && ds.aufhebung.trim()) {
      append('**Aufhebung**\n');
      append(ds.aufhebung + '\n\n');
    }
    if (Array.isArray(ds.preserved_from_thesis) && ds.preserved_from_thesis.length) {
      append('*Preserved from thesis:* ' + (ds.preserved_from_thesis as string[]).join(', ') + '\n\n');
    }
    if (Array.isArray(ds.preserved_from_antithesis) && ds.preserved_from_antithesis.length) {
      append('*Preserved from antithesis:* ' + (ds.preserved_from_antithesis as string[]).join(', ') + '\n\n');
    }
    if (typeof ds.transcended === 'string' && ds.transcended.trim()) {
      append(`*Transcended:* ${ds.transcended}\n\n`);
    }
    if (Array.isArray(ds.new_insights) && ds.new_insights.length) {
      append('**New Insights**\n');
      (ds.new_insights as string[]).forEach((n) => append(`- ${n}\n`));
      append('\n');
    }
  }
  // ── Analogical state ──
  if (d.analogical_state && typeof d.analogical_state === 'object') {
    const as = d.analogical_state as Record<string, unknown>;
    if (typeof as.abstract_structure === 'string' && as.abstract_structure.trim()) {
      append('**Abstract Structure**\n');
      append(as.abstract_structure + '\n\n');
    }
    if (Array.isArray(as.constraints) && as.constraints.length) {
      append('**Constraints**\n');
      (as.constraints as string[]).forEach((c) => append(`- ${c}\n`));
      append('\n');
    }
    if (Array.isArray(as.objectives) && as.objectives.length) {
      append('**Objectives**\n');
      (as.objectives as string[]).forEach((o) => append(`- ${o}\n`));
      append('\n');
    }
    if (Array.isArray(as.actors) && as.actors.length) {
      append('**Actors**\n');
      (as.actors as string[]).forEach((a) => append(`- ${a}\n`));
      append('\n');
    }
    if (Array.isArray(as.core_dynamics) && as.core_dynamics.length) {
      append('**Core Dynamics**\n');
      (as.core_dynamics as string[]).forEach((cd) => append(`- ${cd}\n`));
      append('\n');
    }
    if (typeof as.structural_type === 'string' && as.structural_type.trim()) {
      append(`*Structural type:* ${as.structural_type}\n\n`);
    }
    if (Array.isArray(as.source_domains) && as.source_domains.length) {
      append('**Source Domains**\n');
      (as.source_domains as Array<Record<string, any>>).forEach((sd, i) => {
        const name = typeof sd.name === 'string' ? sd.name : typeof sd.domain === 'string' ? sd.domain : `Domain ${i + 1}`;
        append(`${i + 1}. ${name}\n`);
      });
      append('\n');
    }
    if (Array.isArray(as.analogy_mappings) && as.analogy_mappings.length) {
      append('**Analogy Mappings**\n');
      (as.analogy_mappings as Array<Record<string, any>>).forEach((am) => {
        const source = typeof am.source_element === 'string' ? am.source_element : '';
        const target = typeof am.target_element === 'string' ? am.target_element : '';
        append(`- ${source} → ${target}\n`);
      });
      append('\n');
    }
    if (Array.isArray(as.unmapped_elements) && as.unmapped_elements.length) {
      append('**Unmapped Elements**\n');
      (as.unmapped_elements as string[]).forEach((u) => append(`- ${u}\n`));
      append('\n');
    }
    if (typeof as.mapping_quality === 'string' && as.mapping_quality.trim()) {
      append(`*Mapping quality:* ${as.mapping_quality}\n\n`);
    }
    if (typeof as.transferred_solution === 'string' && as.transferred_solution.trim()) {
      append('**Transferred Solution**\n');
      append(as.transferred_solution + '\n\n');
    }
    if (Array.isArray(as.transfer_steps) && as.transfer_steps.length) {
      append('**Transfer Steps**\n');
      (as.transfer_steps as string[]).forEach((s) => append(`- ${s}\n`));
      append('\n');
    }
    if (Array.isArray(as.adaptations_required) && as.adaptations_required.length) {
      append('**Adaptations Required**\n');
      (as.adaptations_required as string[]).forEach((a) => append(`- ${a}\n`));
      append('\n');
    }
    if (Array.isArray(as.broken_analogies) && as.broken_analogies.length) {
      append('**Broken Analogies**\n');
      (as.broken_analogies as string[]).forEach((b) => append(`- ${b}\n`));
      append('\n');
    }
    if (typeof as.transfer_confidence === 'string' && as.transfer_confidence.trim()) {
      append(`*Transfer confidence:* ${as.transfer_confidence}\n\n`);
    }
    if (Array.isArray(as.caveats) && as.caveats.length) {
      append('**Caveats**\n');
      (as.caveats as string[]).forEach((c) => append(`- ${c}\n`));
      append('\n');
    }
  }
  // ── SoT state ──
  if (d.sot_state && typeof d.sot_state === 'object') {
    const sot = d.sot_state as Record<string, unknown>;
    if (Array.isArray(sot.sub_problems) && sot.sub_problems.length) {
      append('**Sub-Problems**\n');
      (sot.sub_problems as Array<Record<string, any>>).forEach((sp, i) => {
        const desc = typeof sp.description === 'string' ? sp.description : typeof sp.problem === 'string' ? sp.problem : '';
        append(`${i + 1}. ${desc}\n`);
      });
      append('\n');
    }
    if (Array.isArray(sot.solutions) && sot.solutions.length) {
      append('**Solutions**\n');
      (sot.solutions as Array<Record<string, any>>).forEach((sol) => {
        const id = typeof sol.sub_problem_id === 'string' ? sol.sub_problem_id : '';
        const text = typeof sol.solution === 'string' ? sol.solution : '';
        append(`- **${id || 'Solution'}**: ${text}\n`);
      });
      append('\n');
    }
    if (typeof sot.assembled_answer === 'string' && sot.assembled_answer.trim()) {
      append('**Assembled Answer**\n');
      append(sot.assembled_answer + '\n\n');
    }
    if (Array.isArray(sot.transitions) && sot.transitions.length) {
      append('**Transitions**\n');
      (sot.transitions as string[]).forEach((t) => append(`- ${t}\n`));
      append('\n');
    }
    if (Array.isArray(sot.resolved_conflicts) && sot.resolved_conflicts.length) {
      append('**Resolved Conflicts**\n');
      (sot.resolved_conflicts as string[]).forEach((c) => append(`- ${c}\n`));
      append('\n');
    }
  }
  // ── ToT state ──
  if (d.tot_state && typeof d.tot_state === 'object') {
    const tot = d.tot_state as Record<string, unknown>;
    if (Array.isArray(tot.decision_points) && tot.decision_points.length) {
      append('**Decision Points**\n');
      (tot.decision_points as Array<Record<string, any>>).forEach((dp, i) => {
        const desc = typeof dp.description === 'string' ? dp.description : typeof dp.question === 'string' ? dp.question : '';
        append(`${i + 1}. ${desc}\n`);
      });
      append('\n');
    }
    if (Array.isArray(tot.current_candidates) && tot.current_candidates.length) {
      append('**Candidates**\n');
      (tot.current_candidates as Array<Record<string, any>>).forEach((c) => {
        const text = typeof c.candidate === 'string' ? c.candidate : typeof c.action === 'string' ? c.action : '';
        append(`- ${text}\n`);
      });
      append('\n');
    }
    if (Array.isArray(tot.evaluations) && tot.evaluations.length) {
      append('**Evaluations**\n');
      (tot.evaluations as Array<Record<string, any>>).forEach((e) => {
        const candidate = typeof e.candidate === 'string' ? e.candidate : '';
        const score = typeof e.score === 'number' ? e.score : typeof e.rating === 'number' ? e.rating : '?';
        append(`- ${candidate} — score: ${score}\n`);
      });
      append('\n');
    }
    if (typeof tot.best_candidate === 'string' && tot.best_candidate.trim()) {
      append(`*Best candidate:* ${tot.best_candidate}\n\n`);
    }
    if (Array.isArray(tot.current_path) && tot.current_path.length) {
      append('**Path**\n');
      append(tot.current_path.join(' → ') + '\n\n');
    }
    if (typeof tot.backtrack_decision === 'string' && tot.backtrack_decision.trim()) {
      append(`*Backtrack decision:* ${tot.backtrack_decision}\n\n`);
    }
    if (Array.isArray(tot.final_path) && tot.final_path.length) {
      append('**Final Path**\n');
      append(tot.final_path.join(' → ') + '\n\n');
    }
    if (typeof tot.tot_confidence === 'number') {
      append(`*Confidence:* ${Math.round(tot.tot_confidence * 100)}%\n\n`);
    }
  }
  // ── PoT state ──
  if (d.pot_state && typeof d.pot_state === 'object') {
    const pot = d.pot_state as Record<string, unknown>;
    if (typeof pot.code === 'string' && pot.code.trim()) {
      append('**Code**\n```\n' + pot.code + '\n```\n\n');
    }
    if (typeof pot.explanation === 'string' && pot.explanation.trim()) {
      append('**Explanation**\n');
      append(pot.explanation + '\n\n');
    }
    if (typeof pot.execution_output === 'string' && pot.execution_output.trim()) {
      append('**Execution Output**\n');
      append(pot.execution_output + '\n\n');
    }
    if (typeof pot.execution_success === 'boolean') {
      append(`*Success:* ${pot.execution_success ? 'Yes' : 'No'}\n\n`);
    }
    if (typeof pot.execution_error === 'string' && pot.execution_error.trim()) {
      append(`*Error:* ${pot.execution_error}\n\n`);
    }
    if (Array.isArray(pot.intermediate_steps) && pot.intermediate_steps.length) {
      append('**Intermediate Steps**\n');
      (pot.intermediate_steps as string[]).forEach((s) => append(`- ${s}\n`));
      append('\n');
    }
    if (typeof pot.interpretation === 'string' && pot.interpretation.trim()) {
      append('**Interpretation**\n');
      append(pot.interpretation + '\n\n');
    }
    if (typeof pot.computed_answer === 'string' && pot.computed_answer.trim()) {
      append('**Computed Answer**\n');
      append(pot.computed_answer + '\n\n');
    }
    if (Array.isArray(pot.caveats) && pot.caveats.length) {
      append('**Caveats**\n');
      (pot.caveats as string[]).forEach((c) => append(`- ${c}\n`));
      append('\n');
    }
  }
  // ── Self-Discover state ──
  if (d.self_discover_state && typeof d.self_discover_state === 'object') {
    const sd = d.self_discover_state as Record<string, unknown>;
    if (Array.isArray(sd.selected_modules) && sd.selected_modules.length) {
      append('**Selected Modules**\n');
      (sd.selected_modules as Array<Record<string, any>>).forEach((m) => {
        const name = typeof m.name === 'string' ? m.name : typeof m.module === 'string' ? m.module : '';
        append(`- ${name}\n`);
      });
      append('\n');
    }
    if (typeof sd.composition_strategy === 'string' && sd.composition_strategy.trim()) {
      append(`*Composition strategy:* ${sd.composition_strategy}\n\n`);
    }
    if (Array.isArray(sd.adapted_modules) && sd.adapted_modules.length) {
      append('**Adapted Modules**\n');
      (sd.adapted_modules as Array<Record<string, any>>).forEach((m) => {
        const name = typeof m.name === 'string' ? m.name : typeof m.module === 'string' ? m.module : '';
        const adaptation = typeof m.adaptation === 'string' ? m.adaptation : '';
        append(`- ${name}${adaptation ? `: ${adaptation}` : ''}\n`);
      });
      append('\n');
    }
    if (Array.isArray(sd.module_outputs) && sd.module_outputs.length) {
      append('**Module Outputs**\n');
      (sd.module_outputs as Array<Record<string, any>>).forEach((mo) => {
        const name = typeof mo.module === 'string' ? mo.module : typeof mo.name === 'string' ? mo.name : '';
        const output = typeof mo.output === 'string' ? mo.output : '';
        append(`- **${name || 'Module'}**: ${output}\n`);
      });
      append('\n');
    }
    if (typeof sd.final_answer === 'string' && sd.final_answer.trim()) {
      append('**Final Answer**\n');
      append(sd.final_answer + '\n\n');
    }
  }
  // ── Delphi state ──
  if (d.delphi_state && typeof d.delphi_state === 'object') {
    const del = d.delphi_state as Record<string, unknown>;
    if (Array.isArray(del.round1_estimates) && del.round1_estimates.length) {
      append('**Round 1 Estimates**\n');
      (del.round1_estimates as Array<Record<string, any>>).forEach((e) => {
        const expert = typeof e.expert === 'string' ? e.expert : typeof e.expert_id === 'string' ? e.expert_id : '';
        const estimate = typeof e.estimate === 'string' ? e.estimate : typeof e.value === 'string' ? e.value : '';
        append(`- **${expert || 'Expert'}**: ${estimate}\n`);
      });
      append('\n');
    }
    if (del.aggregated && typeof del.aggregated === 'object') {
      append('**Aggregated**\n');
      append(JSON.stringify(del.aggregated, null, 2) + '\n\n');
    }
    if (Array.isArray(del.round2_estimates) && del.round2_estimates.length) {
      append('**Round 2 Estimates**\n');
      (del.round2_estimates as Array<Record<string, any>>).forEach((e) => {
        const expert = typeof e.expert === 'string' ? e.expert : typeof e.expert_id === 'string' ? e.expert_id : '';
        const estimate = typeof e.estimate === 'string' ? e.estimate : typeof e.value === 'string' ? e.value : '';
        append(`- **${expert || 'Expert'}**: ${estimate}\n`);
      });
      append('\n');
    }
    if (del.convergence && typeof del.convergence === 'object') {
      append('**Convergence**\n');
      append(JSON.stringify(del.convergence, null, 2) + '\n\n');
    }
    if (typeof del.dissent_report === 'string' && del.dissent_report.trim()) {
      append('**Dissent Report**\n');
      append(del.dissent_report + '\n\n');
    }
  }
  if (Array.isArray(d.debate_rounds) && d.debate_rounds.length) {
    append('**Debate Rounds**\n');
    (d.debate_rounds as Array<Record<string, any>>).forEach((r, i) => {
      const roundType = r.type || 'round';
      append(`${i + 1}. **${r.round || `Round ${i + 1}`}** (${roundType})\n`);
      if (roundType === 'opening' && Array.isArray(r.statements)) {
        r.statements.forEach((s: any) => {
          const side = s.side || 'Side';
          const content = s.content || s.statement || '';
          append(`   - **${side}**: ${content}\n`);
        });
      } else if (roundType === 'rebuttal' && Array.isArray(r.rebuttals)) {
        r.rebuttals.forEach((reb: any) => {
          const side = reb.side || reb.position || 'Rebuttal';
          const content = reb.content || reb.argument || reb.rebuttal || '';
          append(`   - **${side}**: ${content}\n`);
        });
      } else if (typeof r.summary === 'string' && r.summary.trim()) {
        append(`   ${r.summary}\n`);
      }
    });
    append('\n');
  }

  // ── Writing state ──
  if (d.writing_state && typeof d.writing_state === 'object') {
    const ws = d.writing_state as Record<string, unknown>;
    if (typeof ws.topic === 'string' && ws.topic.trim()) {
      append(`*Topic:* ${ws.topic}\n\n`);
    }
    if (Array.isArray(ws.subquestions) && ws.subquestions.length) {
      append('**Research Questions**\n');
      (ws.subquestions as Array<Record<string, any>>).forEach((sq, i) => {
        const q = typeof sq.question === 'string' ? sq.question : `Q${i + 1}`;
        const priority = typeof sq.priority === 'string' ? sq.priority : '';
        const risk = typeof sq.risk === 'string' ? sq.risk : '';
        append(`${i + 1}. **${q}**${priority ? ` *(priority: ${priority})*` : ''}${risk ? ` *(risk: ${risk})*` : ''}\n`);
      });
      append('\n');
    }
    if (Array.isArray(ws.retrieved_sources)) {
      if (ws.retrieved_sources.length) {
        append(`**Retrieved Sources:** ${ws.retrieved_sources.length}\n\n`);
      } else {
        append(`**Retrieved Sources:** 0\n\n`);
      }
    }
    // CoVE states
    if (Array.isArray(ws.cove_draft_claims)) {
      if (ws.cove_draft_claims.length) {
        append(`**CoVE Draft Claims:** ${ws.cove_draft_claims.length}\n`);
        (ws.cove_draft_claims as Array<Record<string, any>>).slice(0, 5).forEach((c, i) => {
          const text = typeof c.text === 'string' ? c.text : '';
          append(`  ${i + 1}. ${text}\n`);
        });
        if (ws.cove_draft_claims.length > 5) append(`  ... and ${ws.cove_draft_claims.length - 5} more\n`);
        append('\n');
      } else if ('cove_draft_claims' in ws) {
        append('*Skipped (no sources retrieved)*\n\n');
      }
    }
    if (Array.isArray(ws.cove_verification_questions) && ws.cove_verification_questions.length) {
      append('**CoVE Verification Questions**\n');
      (ws.cove_verification_questions as Array<Record<string, any>>).forEach((q, i) => {
        const text = typeof q.question === 'string' ? q.question : '';
        append(`${i + 1}. ${text}\n`);
      });
      append('\n');
    }
    if (Array.isArray(ws.cove_verification_answers) && ws.cove_verification_answers.length) {
      append('**CoVE Verification Answers**\n');
      (ws.cove_verification_answers as Array<Record<string, any>>).forEach((a) => {
        const verdict = typeof a.verdict === 'string' ? a.verdict : '?';
        const answer = typeof a.answer === 'string' ? a.answer : '';
        const icon = verdict === 'supports' ? '✅' : verdict === 'contradicts' ? '❌' : '⚠️';
        append(`- ${icon} ${answer}\n`);
      });
      append('\n');
    }
    if (Array.isArray(ws.cove_changes_made) && ws.cove_changes_made.length) {
      append('**CoVE Changes Made**\n');
      (ws.cove_changes_made as string[]).forEach((c) => append(`- ${c}\n`));
      append('\n');
    }
    if (Array.isArray(ws.claims)) {
      if (ws.claims.length) {
        append(`**Extracted Claims:** ${ws.claims.length}\n`);
        (ws.claims as Array<Record<string, any>>).slice(0, 5).forEach((c, i) => {
          const text = typeof c.text === 'string' ? c.text : '';
          const status = typeof c.status === 'string' ? c.status : '';
          const icon = status === 'verified' ? '✅' : status === 'weak' ? '⚠️' : status === 'rejected' ? '❌' : '';
          append(`  ${i + 1}. ${icon} ${text}\n`);
        });
        if (ws.claims.length > 5) append(`  ... and ${ws.claims.length - 5} more\n`);
        append('\n');
      } else if ('claims' in ws) {
        append('*Skipped (no claims to verify)*\n\n');
      }
    }
    if (Array.isArray(ws.verifications) && ws.verifications.length) {
      append('**Verification Results**\n');
      const byStatus: Record<string, number> = {};
      (ws.verifications as Array<Record<string, any>>).forEach((v) => {
        const st = typeof v.status === 'string' ? v.status : 'UNKNOWN';
        byStatus[st] = (byStatus[st] || 0) + 1;
      });
      Object.entries(byStatus).forEach(([st, count]) => append(`- ${st}: ${count}\n`));
      append('\n');
    }
    if (ws.metrics && typeof ws.metrics === 'object') {
      const m = ws.metrics as Record<string, unknown>;
      append('**Quality Metrics**\n');
      if (typeof m.claim_support_ratio === 'number') append(`- Claim Support Ratio: ${(m.claim_support_ratio * 100).toFixed(1)}%\n`);
      if (typeof m.citation_accuracy === 'number') append(`- Citation Accuracy: ${(m.citation_accuracy * 100).toFixed(1)}%\n`);
      if (typeof m.contradiction_rate === 'number') append(`- Contradiction Rate: ${(m.contradiction_rate * 100).toFixed(1)}%\n`);
      append('\n');
    }
    if (typeof ws.suggested_title === 'string' && ws.suggested_title.trim()) {
      append(`*Suggested Title:* ${ws.suggested_title}\n\n`);
    }
    if (Array.isArray(ws.outline) && ws.outline.length) {
      append('**Outline**\n');
      (ws.outline as Array<Record<string, any>>).forEach((sec, i) => {
        const title = typeof sec.title === 'string' ? sec.title : `Section ${i + 1}`;
        const wc = typeof sec.word_count === 'number' ? sec.word_count : 0;
        append(`${i + 1}. **${title}**${wc ? ` (~${wc} words)` : ''}\n`);
        if (Array.isArray(sec.key_points)) {
          (sec.key_points as string[]).forEach((kp) => append(`   - ${kp}\n`));
        }
      });
      append('\n');
    }
    if (typeof ws.article === 'string' && ws.article.trim()) {
      append('**Article Draft**\n');
      append(ws.article + '\n\n');
    } else if (Array.isArray(ws.sections) && ws.sections.length) {
      append('**Article Draft**\n');
      (ws.sections as Array<Record<string, any>>).forEach((sec) => {
        const heading = typeof sec.heading === 'string' ? sec.heading : '';
        const content = typeof sec.content === 'string' ? sec.content : '';
        if (heading) append(`### ${heading}\n\n`);
        if (content) append(`${content}\n\n`);
      });
    } else if (Array.isArray(ws.sot_sections) && ws.sot_sections.length) {
      append('**Article Draft (SoT)**\n');
      (ws.sot_sections as Array<Record<string, any>>).forEach((sec) => {
        const heading = typeof sec.heading === 'string' ? sec.heading : '';
        const content = typeof sec.content === 'string' ? sec.content : '';
        if (heading) append(`### ${heading}\n\n`);
        if (content) append(`${content}\n\n`);
      });
    }
    if (typeof ws.abstract === 'string' && ws.abstract.trim()) {
      append('**Abstract**\n');
      append(ws.abstract + '\n\n');
    }
    if (Array.isArray(ws.critic_corrections) && ws.critic_corrections.length) {
      append('**Critic Corrections**\n');
      (ws.critic_corrections as Array<Record<string, any>>).forEach((cc) => {
        const issue = typeof cc.issue === 'string' ? cc.issue : '';
        const action = typeof cc.action === 'string' ? cc.action : '';
        append(`- [${action.toUpperCase()}] ${issue}\n`);
      });
      append('\n');
    }
    if (typeof ws.critic_score === 'number') {
      append(`*Critic Score:* ${ws.critic_score}/10\n\n`);
    }
    if (Array.isArray(ws.factcheck_reviews) && ws.factcheck_reviews.length) {
      append('**Fact-Check Reviews**\n');
      (ws.factcheck_reviews as Array<Record<string, any>>).forEach((fr, i) => {
        const verified = fr.verified === true ? '✅' : '⚠️';
        const conf = typeof fr.confidence === 'number' ? `${Math.round(fr.confidence * 100)}%` : '?';
        append(`${i + 1}. ${verified} Paragraph ${fr.paragraph_num || i + 1} — confidence: ${conf}\n`);
        if (Array.isArray(fr.unverified_claims) && fr.unverified_claims.length) {
          (fr.unverified_claims as string[]).forEach((uc) => append(`   - *Unverified:* ${uc}\n`));
        }
      });
      append('\n');
    }
    if (typeof ws.overall_confidence === 'number') {
      append(`*Overall Confidence:* ${Math.round(ws.overall_confidence * 100)}%\n\n`);
    }
    if (typeof ws.hallucination_risk === 'string' && ws.hallucination_risk.trim()) {
      append(`*Hallucination Risk:* ${ws.hallucination_risk}\n\n`);
    }
    // Pre-Mortem state
    if (ws.pre_mortem && typeof ws.pre_mortem === 'object') {
      const pm = ws.pre_mortem as Record<string, unknown>;
      if (typeof pm.failure_narrative === 'string' && pm.failure_narrative.trim()) {
        append('**Pre-Mortem: Failure Narrative**\n');
        append(pm.failure_narrative + '\n\n');
      }
      if (Array.isArray(pm.root_causes) && pm.root_causes.length) {
        append('**Pre-Mortem Root Causes**\n');
        (pm.root_causes as string[]).forEach((rc) => append(`- ${rc}\n`));
        append('\n');
      }
      if (Array.isArray(pm.weak_sections) && pm.weak_sections.length) {
        append('**Pre-Mortem Weak Sections**\n');
        (pm.weak_sections as string[]).forEach((s) => append(`- ${s}\n`));
        append('\n');
      }
      if (Array.isArray(pm.challenged_claims) && pm.challenged_claims.length) {
        append('**Pre-Mortem Challenged Claims**\n');
        (pm.challenged_claims as string[]).forEach((c) => append(`- ${c}\n`));
        append('\n');
      }
    }
    // SoT state
    if (Array.isArray(ws.sot_skeleton) && ws.sot_skeleton.length) {
      append('**SoT Skeleton**\n');
      (ws.sot_skeleton as Array<Record<string, any>>).forEach((sec, i) => {
        const heading = typeof sec.heading === 'string' ? sec.heading : `Section ${i + 1}`;
        const deps = Array.isArray(sec.dependencies) && sec.dependencies.length ? ` (deps: ${(sec.dependencies as string[]).join(', ')})` : '';
        append(`${i + 1}. **${heading}**${deps}\n`);
      });
      append('\n');
    }
    if (Array.isArray(ws.sot_sections) && ws.sot_sections.length) {
      append('**SoT Written Sections**\n');
      (ws.sot_sections as Array<Record<string, any>>).forEach((sec) => {
        const heading = typeof sec.heading === 'string' ? sec.heading : '';
        const content = typeof sec.content === 'string' ? sec.content : '';
        if (content.trim()) {
          append(`### ${heading}\n${content}\n\n`);
        }
      });
    }
    if (typeof ws.final_article === 'string' && ws.final_article.trim()) {
      append('**Final Article**\n');
      append(ws.final_article + '\n\n');
    }
    if (typeof ws.final_abstract === 'string' && ws.final_abstract.trim()) {
      append('**Final Abstract**\n');
      append(ws.final_abstract + '\n\n');
    }
    if (typeof ws.confidence_notice === 'string' && ws.confidence_notice.trim()) {
      append(`> **Confidence Notice:** ${ws.confidence_notice}\n\n`);
    }
    if (Array.isArray(ws.sources_cited) && ws.sources_cited.length) {
      append('**Sources Cited**\n');
      (ws.sources_cited as string[]).forEach((s) => append(`- ${s}\n`));
      append('\n');
    }
    if (Array.isArray(ws.final_changes) && ws.final_changes.length) {
      append('**Changes Made**\n');
      (ws.final_changes as string[]).forEach((c) => append(`- ${c}\n`));
      append('\n');
    }
    if (Array.isArray(ws.gaps_noted) && ws.gaps_noted.length) {
      append('**Identified Gaps**\n');
      (ws.gaps_noted as string[]).forEach((g) => append(`- ${g}\n`));
      append('\n');
    }
    if (Array.isArray(ws.claim_traceability) && ws.claim_traceability.length) {
      append('**Claim Traceability**\n');
      (ws.claim_traceability as Array<Record<string, string>>).slice(0, 10).forEach((ct) => {
        append(`- ${ct.claim_id || ''} → ${ct.used_in_section || ''}\n`);
      });
      append('\n');
    }
  }

  }

  // ── Critique & Pruning ──
  if (Array.isArray(d.critic_scores) && d.critic_scores.length) {
    append('**Critic Scores Matrix**\n');
    (d.critic_scores as Array<Record<string, any>>).forEach((cs) => {
      const criticId = typeof cs.critic_id === 'string' ? cs.critic_id : '';
      const criticModel = typeof cs.critic_model === 'string' ? cs.critic_model : '';
      const modelLabel = criticModel ? ` *(model: ${criticModel.split('/').pop() || criticModel})*` : '';
      append(`#### ${criticId}${modelLabel}\n`);
      
      const candidateScores = cs.candidate_scores as Record<string, any>;
      if (candidateScores && typeof candidateScores === 'object') {
        Object.entries(candidateScores).forEach(([genId, scores]) => {
          const total = typeof scores.total === 'number' ? scores.total.toFixed(1) : '?';
          append(`- **${genId}** — total: ${total}\n`);
          if (typeof scores.steel_man === 'string' && scores.steel_man.trim()) {
            append(`  *Steel man:* ${scores.steel_man}\n`);
          }
        });
      }
      if (typeof cs.dissenting_note === 'string' && cs.dissenting_note.trim()) {
        append(`> *Dissenting Note:* ${cs.dissenting_note}\n`);
      }
      append('\n');
    });
  }
  if (Array.isArray(d.scores) && d.scores.length) {
    append('**Scores**\n');
    (d.scores as Array<Record<string, any>>).forEach((s) => {
      const perspective = typeof s.perspective === 'string' ? s.perspective : '';
      const total = typeof s.total === 'number' ? s.total : '?';
      const isTop = s.is_top ? ' ⭐' : '';
      append(`- **${perspective}${isTop}** — total: ${total}\n`);
      if (typeof s.steel_man === 'string' && s.steel_man.trim()) {
        append(`  *Steel man:* ${s.steel_man}\n`);
      }
    });
    append('\n');
  }

  // ── Stress Testing ──
  if (Array.isArray(d.tests) && d.tests.length) {
    append('**Stress Tests**\n');
    (d.tests as Array<Record<string, any>>).forEach((t) => {
      const scenario = typeof t.scenario === 'string' ? t.scenario : 'Scenario';
      const survival = typeof t.survival_rate === 'number' ? `${Math.round(t.survival_rate * 100)}%` : '?';
      append(`- **${scenario}** — survival: ${survival}\n`);
      if (typeof t.failure_mode === 'string' && t.failure_mode.trim()) {
        append(`  *Failure:* ${t.failure_mode}\n`);
      }
      if (typeof t.recovery_path === 'string' && t.recovery_path.trim()) {
        append(`  *Recovery:* ${t.recovery_path}\n`);
      }
    });
    append('\n');
  }
  if (Array.isArray(d.verification_results) && d.verification_results.length) {
    append('**Verification**\n');
    (d.verification_results as Array<Record<string, string>>).forEach((v) => {
      append(`- **${v.verdict || '?' }**: ${v.claim || ''}\n`);
    });
    append('\n');
  }
  if (d.meta_evaluation && typeof d.meta_evaluation === 'object') {
    const me = d.meta_evaluation as Record<string, unknown>;
    append('**Meta Evaluation**\n');
    if (typeof me.meta_insight === 'string') append(`${me.meta_insight}\n\n`);
  }

  // ── Synthesis ──
  if (typeof d.core_solution === 'string' && d.core_solution.trim()) {
    const cs = d.core_solution.trim();
    // Skip if core_solution is just a JSON dump of the structured fields
    const looksLikeJsonDump = cs.startsWith('```json') || (cs.startsWith('{') && cs.includes('"critical_insights"'));
    if (!looksLikeJsonDump) {
      append(d.core_solution + '\n\n');
    }
  }
  if (
    Array.isArray(d.critical_insights) &&
    d.critical_insights.length &&
    !options?.omitSections?.includes('critical_insights')
  ) {
    append('### Critical Insights\n');
    (d.critical_insights as string[]).forEach((i, idx) => {
      append(`${idx + 1}. ${i}\n`);
    });
    append('\n');
  }
  if (
    Array.isArray(d.action_blueprint) &&
    d.action_blueprint.length &&
    !options?.omitSections?.includes('action_blueprint')
  ) {
    append('### Action Blueprint\n');
    (d.action_blueprint as unknown[]).forEach((b) => {
      if (typeof b === 'string') {
        const action = b.trim();
        if (action) append(`- ${action}\n`);
      } else if (b && typeof b === 'object') {
        const action = ((b as Record<string, string>).action || '').trim();
        const step = (b as Record<string, string>).step || 'Step';
        if (action) append(`- **${step}**: ${action}\n`);
      }
    });
    append('\n');
  }
  if (
    Array.isArray(d.open_questions) &&
    d.open_questions.length &&
    !options?.omitSections?.includes('open_questions')
  ) {
    append('### Open Questions\n');
    (d.open_questions as string[]).forEach((q) => append(`- ${q}\n`));
    append('\n');
  }
  if (
    Array.isArray(d.sources) &&
    d.sources.length &&
    !options?.omitSections?.includes('sources')
  ) {
    append('### Sources\n');
    (d.sources as Array<Record<string, string>>).forEach((s) => {
      append(`- [${s.title || s.url || 'Source'}](${s.url || ''})\n`);
    });
    append('\n');
  }

  // A phase that recorded errors produced no content *because it failed*. Say so
  // rather than rendering an indistinguishable "No content for this phase."
  if (Array.isArray(d.errors) && d.errors.length) {
    append(`### Phase errors (${(d.errors as string[]).length})\n`);
    (d.errors as string[]).forEach((e) => append(`- ${e}\n`));
    append('\n');
  }

  if (!rendered) {
    md += '*No content for this phase.*\n\n';
  }

  return md;
}

export function buildMarkdownFromPhases(
  phases: Array<{ phase: number; name: string; data: unknown }>,
  options?: { omitSections?: Array<'critical_insights' | 'action_blueprint' | 'open_questions' | 'sources'> }
): string {
  return phases.map((p, idx) => buildMarkdownFromPhase(idx, p.phase, p.name, p.data, options)).join('');
}
