# Article Workflow — Πλήρης Τεχνική Περιγραφή

Το **ArticleFlow** είναι το πιο εξελιγμένο workflow του Reasoner. Πρόκειται για μια
**10-φασική εκδοτική pipeline** που παράγει άρθρα επιπέδου δημοσίευσης (publication-grade),
με ενσωματωμένο pre-processing (augmentation), adversarial review, editorial auditing,
και πλήρη retry μηχανισμό σε περίπτωση αποτυχίας.

---

## Φάση -1: Preflight (HyperGate + Neuro)

Πριν ξεκινήσει το pipeline, ο HyperGate αναλύει το ερώτημα του χρήστη:

1. **Fast-path checks:**
   - Αν το ερώτημα μοιάζει με απλή δημιουργική γραφή ("γράψε ένα ποίημα") → `direct` απάντηση
   - Αν το ερώτημα απαιτεί real-time δεδομένα ("τιμή Bitcoin τώρα") → `web_search`
   - Αν το ερώτημα είναι factual lookup ("ποια είναι η πρωτεύουσα της Γαλλίας;") → `direct`

2. **Deep concept guard:** Αν το ερώτημα περιέχει αφηρημένες έννοιες (τέχνη, δικαιοσύνη,
   συνείδηση, αλήθεια, ύπαρξη κ.ά.), **δεν** επιτρέπεται το factual fast-path. Π.χ. το
   "Τι είναι τέχνη;" περνάει ΠΑΝΤΑ από το πλήρες pipeline, ποτέ ως direct answer.

3. **5 sub-agents σε parallel:** LanguageDetector, ComplexityEstimator, DirectDetector,
   WebSearchDetector, MethodClassifier τρέχουν ταυτόχρονα.

4. **TieBreaker:** Αν τα σήματα είναι αντικρουόμενα, ένα 6ο sub-agent παίρνει την
   τελική απόφαση.

5. **Neuro recall:** Ανακτά σχετικές προηγούμενες συνομιλίες από τη μνήμη.

6. **Preset resolution:** Αποφασίζει ποια μοντέλα θα χρησιμοποιηθούν ανά ρόλο
   (budget → φθηνά μοντέλα, premium → frontier models).

---

## Φάση 0: Augmentation (Pre-processing για βαθιά ερωτήματα)

Πριν τις κυρίως φάσεις, αν το ερώτημα ανιχνευθεί ως "deep question" μέσω regex:

```
is_deep_question("What is art?") → True
is_deep_question("How to make coffee?") → False
```

Εκτελούνται **parallel** LLM calls που εμπλουτίζουν το pipeline με insights:

| Επίπεδο | Μέθοδοι | Extra calls |
|---------|---------|-------------|
| Budget | Κανένα | 0 |
| Standard | `debate` (pro/con analysis) | 1 |
| Premium | `debate` + `iterative_critique` + `jury` + `socratic` | 4 |

Το αποτέλεσμα αποθηκεύεται στο `state.writing_state["pre_research_summary"]` και
εγχέεται σε τρία σημεία του pipeline:
- **Retrieval planning:** οι search queries γίνονται πιο στοχευμένες
- **Outline generation:** ο argument map εμπλουτίζεται με debate/critique findings
- **Draft composition:** το draft ενσωματώνει τα pre-research insights

**Graceful degradation:** Αν ένα augmentation method αποτύχει, τα υπόλοιπα συνεχίζουν.
Αν όλα αποτύχουν, το pipeline συνεχίζει κανονικά χωρίς augmentation.

**Caching:** Αποτελέσματα augmentation cache-άρονται (L1 LRU, 128 entries, 24h TTL)
για να αποφεύγονται duplicate LLM calls σε επαναλαμβανόμενα deep questions.

---

## Φάση 1: Evidence Collection (Συλλογή Πηγών)

Το σύστημα παράγει 3-5 στοχευμένα search queries και ανακτά πηγές:

**Path A — Sonar/Perplexity native search:**
Αν ο router έχει αναθέσει το ρόλο `primary` σε μοντέλο Perplexity Sonar, το μοντέλο
κάνει native web search και επιστρέφει απευθείας citations με inline [Title](URL) links.
Αυτό είναι το γρηγορότερο μονοπάτι — ένα LLM call αντί για 3-5 ξεχωριστά searches.

**Path B — External search:**
Αν το primary model ΔΕΝ είναι Sonar, το σύστημα:
1. Ζητά από το LLM να παράγει JSON `{"queries": ["...", "...", "..."]}`
2. Τρέχει 3-5 parallel searches μέσω SearXNG / Brave / Tavily
3. Deduplicate-άρει τα αποτελέσματα (βάσει URL)
4. Αποθηκεύει τις πηγές στο `state.writing_state["retrieved_sources"]`

**Fallback:** Αν όλα αποτύχουν, ενεργοποιείται το `insufficient_evidence` gate και το
pipeline συνεχίζει με γενική γνώση, μαρκάροντας claims ως `[UNVERIFIED]`.

**Pre-research injection:** Αν υπάρχουν augmentation insights, εγχέονται στο prompt
ώστε τα queries να στοχεύουν συγκεκριμένα claims και αντεπιχειρήματα.

---

## Φάση 2: Argument Map & Outline (Δομικός Σχεδιασμός)

Πριν τη συγγραφή, το σύστημα χτίζει έναν **argument map** — όχι απλά μια λίστα
ενοτήτων, αλλά μια δομημένη αναπαράσταση της επιχειρηματολογίας:

Το μοντέλο `article_sot_skeleton` παράγει JSON:
```json
{
  "suggested_title": "...",
  "argument_map": {
    "thesis": "...",
    "antithesis": "...",
    "synthesis": "...",
    "key_claims": ["...", "..."],
    "counterarguments": ["...", "..."],
    "evidence_mapping": {"claim_1": ["source_1", "source_2"], ...}
  },
  "outline": [
    {"section": "Εισαγωγή", "purpose": "...", "estimated_words": 200},
    {"section": "Ιστορικό Πλαίσιο", "purpose": "...", "estimated_words": 400},
    ...
  ],
  "total_word_count": 2500
}
```

**Γιατί πριν το draft:** Ο διαχωρισμός structure → content επιτρέπει:
- Ανεξάρτητο quality check της δομής πριν επενδυθούν tokens στο draft
- Επαναχρησιμοποίηση του outline για multiple drafts
- Καλύτερη συνοχή — το draft ακολουθεί προκαθορισμένη δομή

---

## Φάση 3: First Draft (Πρώτη Συγγραφή)

Το μοντέλο `writing_draft` γράφει το πλήρες άρθρο:

- **Budget tier:** Claude Sonnet (Anthropic 🇺🇸) — $2/$10 per M tokens
- **Premium tier:** Claude Sonnet — $2/$10 per M (ήταν GPT-5.5, μειώθηκε για κόστος)

Το prompt περιλαμβάνει:
- Τις πηγές (truncated στα top-N για token efficiency)
- Το argument map και το outline από τη Φάση 2
- Το style brief (author/publication style, αν έχει ζητηθεί)
- **Pre-research insights** από το augmentation
- Οδηγίες για narrative depth, citation format, και audience level

Το αποτέλεσμα αποθηκεύεται στο `state.writing_state["final_article"]`.

---

## Φάση 4: Fact Check & Claim Ledger (Adversarial Verification)

**Δεν είναι απλό fact-checking.** Είναι adversarial verification:

Το μοντέλο `writing_factcheck` (συνήθως Perplexity Sonar/Sonar Pro):
1. Εξάγει όλα τα factual claims από το draft
2. Για κάθε claim, ελέγχει αν υποστηρίζεται από τις πηγές
3. Δημιουργεί ένα **claim ledger** — έναν πίνακα με:
   - `claim_id`, `claim_text`, `source_url`, `support_level` (SUPPORTS/PARTIAL/CONTRADICTS/UNVERIFIED)
   - `verification_notes`
4. Υπολογίζει metrics: `claim_support_ratio`, `unverified_claims_count`

**Gate:** Αν το `claim_support_ratio < ARTICLE_MIN_CLAIM_SUPPORT_RATIO` (0.6), το
σύστημα σημειώνει gaps και συνεχίζει — δεν μπλοκάρει, αλλά επισημαίνει.

**Sonar-aware prompts:** Αν ο factchecker είναι Sonar, το prompt προσαρμόζεται
για live web verification αντί για source-only verification.

---

## Φάση 4.5: Structural Adversarial Review (Δομική Κριτική)

**Δεν είναι grammar check.** Είναι structural/logical critique:

Το μοντέλο `article_critic` αξιολογεί:
- **Λογικά κενά:** Πού η επιχειρηματολογία είναι ελλιπής;
- **Αγνοημένα αντεπιχειρήματα:** Ποιες αντίθετες απόψεις δεν αναφέρθηκαν;
- **Υποθέσεις:** Ποιες προκείμενες είναι ατεκμηρίωτες;
- **Δομική συνοχή:** Ρέει σωστά η αφήγηση;
- **Rigor score:** 0.0-1.0 αξιολόγηση της επιχειρηματολογικής αυστηρότητας

**Μοντέλα:**
- Budget: Hermes 4 70B (Nous Research 🇺🇸) — critic-specialized
- Premium: Grok 4.3 (xAI 🇺🇸) — τ²-Bench 97.7% adversarial reasoning

---

## Φάση 5: Developmental Edit (Ουσιαστική Διόρθωση)

Το μοντέλο `article_revise` ξαναγράφει το άρθρο λαμβάνοντας υπόψη:
- To structural critique από τη Φάση 4.5
- Το claim ledger από τη Φάση 4
- Τις αρχικές πηγές

**Δεν κάνει grammar/spelling fixes.** Διορθώνει:
- Επιχειρηματολογικές αδυναμίες
- Ελλιπή evidence
- Narrative flow προβλήματα
- Αντιφατικά claims

**Μοντέλα:**
- Budget: DeepSeek V4 Flash (🇨🇳) — $0.09/$0.18 per M
- Premium: DeepSeek V4 Pro (🇨🇳) — $0.435/$0.87 per M, 1.6T MoE

---

## Φάση 6: Style + Copy Edit (Διπλή Διόρθωση)

**Δύο sequential περάσματα σε μία φάση:**

### 6α: Style Edit
Το μοντέλο `article_humanize` (ίδιο με το draft — Claude Sonnet):
- Προσαρμόζει τον τόνο και το ύφος
- Διατηρεί τη "φωνή" του συγγραφέα (author voice preservation)
- Βελτιώνει readability χωρίς να αλλάζει το περιεχόμενο

### 6β: Copy Edit
Το μοντέλο `writing_assemble` (GPT-4o Mini):
- Γραμματική, ορθογραφία, στίξη
- Συνέπεια στη μορφοποίηση
- Τελική συναρμολόγηση (assembly)

**Graceful degradation:** Αν το style edit αποτύχει, το copy edit τρέχει πάνω στο
pre-style draft — δεν χάνεται η πρόοδος.

---

## Φάση 7: Final Editorial Audit (Τελικός Έλεγχος)

Το μοντέλο `article_verifier` εκτελεί ένα structured checklist audit:

```json
{
  "passes_audit": true/false,
  "audit_score": 0.85,
  "checks": {
    "factual_accuracy": "pass",
    "argument_coherence": "pass",
    "source_attribution": "partial",
    "tone_consistency": "pass",
    "length_target": "pass",
    "bias_assessment": "neutral"
  },
  "recommendations": ["..."],
  "critical_issues": []
}
```

**Retry μηχανισμός:** Αν `passes_audit == false`, το pipeline **αυτόματα**:
1. Ξανατρέχει Developmental Edit (Φάση 5)
2. Ξανατρέχει Style + Copy Edit (Φάση 6)
3. Ξανατρέχει Final Audit (Φάση 7)

Αυτό γίνεται **μία μόνο φορά** (`audit_retried` flag) — όχι infinite loop.

**Cache hits:** Στο retry, τα LLM calls για edit/audit γίνονται cache hit (ίδιο prompt,
ίδιο state) — οπότε το retry είναι σχεδόν instant και δεν κοστίζει tokens.

---

## Φάση 8: Synthesis (Τελική Σύνθεση)

Το μοντέλο `synthesis` παράγει το τελικό output:
- Το πλήρες άρθρο (core_solution)
- Critical insights (βασικά συμπεράσματα)
- Open questions (αναπάντητα ερωτήματα)
- Action blueprint (προτεινόμενες ενέργειες)
- Epistemic labels: VERIFIED / HYPOTHESIS / UNKNOWN

Ακολουθεί **post-synthesis verification** από cross-model reviewer για validation.

---

## Post-flight

Μετά την ολοκλήρωση:
1. **Neuro learn:** Το αποτέλεσμα αποθηκεύεται στη μνήμη για μελλοντική ανάκληση
2. **Telemetry:** Metrics (κόστος, διάρκεια, quality scores, models) καταγράφονται
3. **Event persistence:** Όλα τα events αποθηκεύονται στο event store

---

## Συνοπτικό Διάγραμμα

```
User Question
    │
    ▼
HyperGate (5 sub-agents parallel + deep concept guard)
    │
    ▼
Augmentation (debate + critique + jury + socratic — μόνο για deep questions)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│ Φάση 1:  Evidence Collection (3-5 parallel searches) │
│ Φάση 2:  Argument Map + Outline                      │
│ Φάση 3:  First Draft                                 │
│ Φάση 4:  Fact Check + Claim Ledger                   │
│ Φάση 4.5: Structural Adversarial Review              │
│ Φάση 5:  Developmental Edit                          │
│ Φάση 6:  Style + Copy Edit (2 passes)                │
│ Φάση 7:  Final Editorial Audit ───┐                  │
│ Φάση 8:  Synthesis                 │                  │
└────────────────────────────────────│──────────────────┘
                                     │
                          ┌──────────┘
                          │ (αν fails)
                          ▼
                    Retry: Φάση 5 → 6 → 7
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│ Cross-model post-synthesis verification              │
│ Neuro learn + Telemetry + Event persistence          │
└─────────────────────────────────────────────────────┘
```

## Μοντέλα ανά ρόλο

| # | Φάση | Budget Model | Premium Model |
|---|------|-------------|---------------|
| 1 | Retrieval | Perplexity Sonar | Perplexity Sonar Pro |
| 2 | Outline | GPT-4o Mini | Claude Sonnet |
| 3 | Draft | Claude Sonnet | Claude Sonnet |
| 4 | Fact Check | Perplexity Sonar | Perplexity Sonar Pro |
| 4.5 | Structural Review | Hermes 4 70B | Grok 4.3 |
| 5 | Dev Edit | DeepSeek V4 Flash | DeepSeek V4 Pro |
| 6α | Style Edit | Claude Sonnet | Claude Sonnet |
| 6β | Copy Edit | GPT-4o Mini | GPT-4o Mini |
| 7 | Final Audit | Qwen 3.5 Flash | Qwen 3.7 Max |
| 8 | Synthesis | Qwen 3.7 Plus | Qwen 3.7 Max |
| - | Post-verify | Perplexity Sonar | Perplexity Sonar Pro |
| - | Fusion | DeepSeek V4 Flash | DeepSeek V4 Pro |

**Cross-lab diversity:** Budget χρησιμοποιεί 6 διαφορετικά labs,
Premium χρησιμοποιεί 5 διαφορετικά labs (Anthropic, Perplexity, xAI, DeepSeek, Qwen).

## Ρυθμίσεις & Toggles

```bash
# Απενεργοποίηση augmentation (default: on)
AUGMENTATION_ENABLED=false

# LLM depth confirmation για μείωση false positives (default: off)
AUGMENTATION_LLM_CONFIRM=true

# Caching αποτελεσμάτων augmentation (default: on, 128 entries, 24h TTL)
AUGMENTATION_CACHE_ENABLED=false

# A/B testing augmented vs baseline ποιότητας (default: off)
AUGMENTATION_AB_TEST=true
```

## Running

```bash
# Budget (~$0.05/run)
python -m reasoner.main --problem "What is art?" --preset article-budget

# Premium (~$0.07/run, ήταν ~$0.25 πριν τις βελτιστοποιήσεις)
python -m reasoner.main --problem "What is art?" --preset article-premium
```
