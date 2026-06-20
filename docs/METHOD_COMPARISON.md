# Μέθοδοι Συλλογιστικού — Αναλυτικός Οδηγός (ARA Pipeline v2.2)

> Αναλυτική περιγραφή κάθε μεθόδου: τι κάνει, σε ποιες περιπτώσεις επιλέγεται από το HyperGate,
> για ποια προβλήματα είναι βέλτιστη, και ποια η εσωτερική δομή φάσεων.

---

## Πίνακας Γρήγορης Αναφοράς

| Μέθοδος | HyperGate | Φάσεις | Παράλληλη Εκτέλεση | Βέλτιστη για |
|---------|-----------|--------|-------------------|--------------|
| Multi-Perspective | E | 3 | Φάση 2 (4 οπτικές) | Ανοιχτά ερωτήματα, γενική ανάλυση |
| Debate | B | 3 | Φάση 2 (2 πλευρές) | Απόφαση μεταξύ δύο αποκλειστικών επιλογών |
| Jury | F | 3 | Φάσεις 2+3 (experts+critics) | Ranking ανταγωνιστικών λύσεων |
| Research | G | 4 | Φάση 3 (perspectives) | Τεκμηριωμένες απαντήσεις με web sources |
| Scientific | C | 3 | — | Επιστημονικά ερωτήματα, έλεγχος υποθέσεων |
| Socratic | D | 2 | — | Αποκάλυψη κρυφών παραδοχών |
| Pre-Mortem | H | 4 | — | Risk analysis, project planning |
| Bayesian | I | 4 | — | Πιθανότητες, ποσοτική αβεβαιότητα |
| Dialectical | J | 4 | — | Σύνθεση δύο αντιθέτων που και οι δύο έχουν αξία |
| Analogical | K | 4 | — | Cross-domain μεταφορά λύσεων |
| Delphi | L | 5 | Φάσεις 2+4 (experts) | Consensus forecasting, εκτιμήσεις |
| CoVE | M | 4 | — | Επαλήθευση ισχυρισμών, fact-checking |
| SoT | N | 3 | Φάση 3 (parallel solve) | Προβλήματα με ανεξάρτητα υπο-έργα |
| ToT | O | 4 | — | Sequential decisions με backtracking |
| PoT | P | 3 | — | Μαθηματικά / υπολογιστικά προβλήματα |
| Self-Discover | Q | 3 | — | Άγνωστη δομή προβλήματος |
| Writing | R | 8 | Φάση 4 (SoT sections) | Άρθρα, essays, long-form περιεχόμενο |
| Coding | S | 5 | Φάση 3 (parallel files) | Παραγωγή production-grade κώδικα |

---

## Αναλυτική Περιγραφή Μεθόδων

---

### 1. Multi-Perspective (E)

**Τι κάνει:**
Αναλύει το πρόβλημα από 4 εντελώς διαφορετικές, ανεξάρτητες οπτικές γωνίες που τρέχουν παράλληλα, στη συνέχεια κάνει ανεξάρτητη κριτική αξιολόγηση και stress testing.

**Φάσεις:**
1. **Perspectives** *(παράλληλη — 4 LLM calls ταυτόχρονα)*
   - **Constructive**: "Χτίσε την ισχυρότερη δυνατή λύση από πρώτες αρχές"
   - **Destructive**: "Βρες κάθε αδυναμία, κάθε υπόθεση που μπορεί να αποτύχει"
   - **Systemic**: "Ανάλυσε τις 2ης και 3ης τάξης επιπτώσεις στο σύστημα"
   - **Minimalist**: "Εφάρμοσε Occam's Razor — ποια είναι η απλούστερη επαρκής λύση;"
2. **Critique & Pruning** *(critical=True)* — Ανεξάρτητος scorer βαθμολογεί όλες τις οπτικές (0–10), ποινή για confident hallucinations
3. **Stress Testing** — Προσομοίωση adversarial αποτυχιών σε real-world σενάρια

**Πότε επιλέγεται:** Γενικά ερωτήματα ανοιχτής ανάλυσης που δεν εμπίπτουν σαφώς σε άλλη κατηγορία. Default fallback του HyperGate.

**Βέλτιστο για:**
- "Ποια είναι τα πλεονεκτήματα/μειονεκτήματα του X;"
- "Πώς να προσεγγίσω το πρόβλημα Y;"
- Ανοιχτά στρατηγικά ερωτήματα χωρίς ένα σαφές σωστό/λάθος

**Output:** `core_analysis`, `key_insights`, `scores[]`, `stress_tests[]` με `survival_rate` και `failure_mode`

---

### 2. Debate (B)

**Τι κάνει:**
Δύο πλευρές αντιμάχονται σε δομημένους γύρους (opening → rebuttal → cross-examination) για να αναδείξουν τη νικήτρια θέση. Ο judge βαθμολογεί και αποφαίνεται.

**Φάσεις:**
1. **Opening Statements** *(παράλληλη — Side A και Side B ταυτόχρονα)* — Κάθε πλευρά παρουσιάζει την ισχυρότερη θέση της, χωρίς να απαντά ακόμα
2. **Rebuttals** *(παράλληλη)* — Κάθε πλευρά επιτίθεται στη λογική της άλλης και υπερασπίζεται τη δική της
3. **Cross-Examination** — Κάθε πλευρά αμφισβητεί συγκεκριμένους ισχυρισμούς με αντεπιχειρήματα· verdict ανά ισχυρισμό: `REFUTED | WEAKENED | STANDS`

**Πότε επιλέγεται:** HyperGate κωδικός **B** — "δύο αντίπαλες θέσεις όπου μία πρέπει να κερδίσει".

**Βέλτιστο για:**
- "Πρέπει να χρησιμοποιήσουμε microservices ή monolith;"
- "PostgreSQL ή MongoDB για αυτή την εφαρμογή;"
- "Σωστό ή λάθος να κάνουμε X;" — ερωτήματα με ένα από τα δύο

**Διαφορά από Dialectical:** Το Debate αναδεικνύει **νικητή**. Το Dialectical συνθέτει και τις δύο πλευρές σε κάτι ανώτερο.

**Output:** `key_claims[]`, `target_flaws[]`, `challenges[]` με `verdict` ανά claim

---

### 3. Jury (F)

**Τι κάνει:**
Πολλαπλοί ανεξάρτητοι "generators" παράγουν λύσεις παράλληλα, ανεξάρτητοι "critics" τις βαθμολογούν με explicit ποινή για overconfident hallucinations, και ένας verifier ελέγχει τις αξιώσεις.

**Φάσεις:**
1. **Generation Pool** *(παράλληλη — N generators ταυτόχρονα)* — Κάθε generator παράγει ανεξάρτητα τη λύση του
2. **Critic Pool** *(παράλληλη, critical=True)* — Κάθε critic βαθμολογεί όλες τις λύσεις: factuality, reasoning, completeness, helpfulness. **Ρητή ποινή:** "Καλύτερα να πεις UNKNOWN παρά να μαντέψεις με ψεύτικη σιγουριά"
3. **Verification & Meta-Eval** — Ελέγχει τις ισχυρισμούς κάθε λύσης και αξιολογεί την αξιοπιστία κάθε critic

**Πότε επιλέγεται:** HyperGate κωδικός **F** — "ανταγωνιστικές λύσεις που χρειάζονται ranking".

**Βέλτιστο για:**
- "Ποια είναι η καλύτερη αρχιτεκτονική για X από αυτές τις επιλογές;"
- "Αξιολόγησε αυτές τις 3 προτάσεις"
- Ερωτήματα όπου υπάρχουν πολλαπλές βιώσιμες λύσεις και θέλουμε την καλύτερη

**Διαφορά από Multi-Perspective:** Η Multi-Perspective δημιουργεί οπτικές για ένα πρόβλημα. Η Jury δημιουργεί **ανταγωνιστικές λύσεις** και τις βαθμολογεί.

**Output:** `solution`, `key_claims[]`, `candidate_scores[]`, `confidence_vs_accuracy_penalty`, `verifications[]`, `critic_reliability[]`

---

### 4. Research (G)

**Τι κάνει:**
Ψάχνει ενεργά το web μέσω SearXNG για πραγματικές πηγές, συνεχίζει μέχρι να μαζέψει ≥5 αξιόπιστες πηγές, και μετά εκτελεί ανάλυση Multi-Perspective πάνω στα ευρήματα.

**Φάσεις:**
1. **Deep Research** *(iterative loop)* — Δημιουργεί queries → αναζητά → διαβάζει αποτελέσματα → αποφασίζει: `search` ή `done`. Δεν σταματά πριν από 5+ πηγές ή max iterations
2. **Perspectives** — Ίδιο με Multi-Perspective αλλά με context από τις πηγές
3. **Critique & Pruning** *(critical=True)* — Ίδιο με Multi-Perspective
4. **Stress Testing** — Ίδιο με Multi-Perspective

**Πότε επιλέγεται:** HyperGate κωδικός **G** — "απαιτεί σύνθεση από live web sources".

**Βέλτιστο για:**
- Ερωτήματα που αλλάζουν γρήγορα (τιμές, events, τεχνολογίες)
- "Ποια είναι τα τελευταία νέα για X;"
- Ερωτήματα που απαιτούν τεκμηρίωση από εξωτερικές πηγές

**Απαίτηση:** Ενεργό SearXNG instance. Χωρίς αυτό, επιστρέφει empty search results.

**Output:** `queries[]`, ευρήματα από πηγές, + ό,τι παράγει η Multi-Perspective pipeline

---

### 5. Scientific (C)

**Τι κάνει:**
Εφαρμόζει επιστημονική μέθοδο: δημιουργεί 3 ανταγωνιστικές υποθέσεις, σχεδιάζει mental experiments για να τις διαψεύσει, και αξιολογεί ποιες επιβιώνουν.

**Φάσεις:**
1. **Hypotheses** — Δημιουργεί 3 falsifiable υποθέσεις που εξηγούν το φαινόμενο, με explicit falsifiability criteria
2. **Falsification Tests** — Σχεδιάζει πείραμα ανά υπόθεση: αν το αποτέλεσμα είναι X, τότε H είναι `SUPPORTED | WEAKENED | FALSIFIED`
3. **Stress Testing** — Adversarial testing της υπόθεσης που επιβίωσε

**Πότε επιλέγεται:** HyperGate κωδικός **C** — "επιστημονική υπόθεση ή falsification testing".

**Βέλτιστο για:**
- "Γιατί συμβαίνει το φαινόμενο X;"
- "Ποια εξήγηση είναι πιο πιθανή: Α, Β, ή Γ;"
- Debugging "ποια αιτία προκαλεί αυτό το bug;"
- Ερωτήματα που απαιτούν έλεγχο παραδοχών με evidence

**Output:** `hypotheses[]` με `falsifiability`, `test_results[]` με `result` (SUPPORTED/WEAKENED/FALSIFIED)

---

### 6. Socratic (D)

**Τι κάνει:**
Εφαρμόζει τη σωκρατική ελεγκτική μέθοδο: θέτει 3-4 probing ερωτήσεις που αποκαλύπτουν αντιφάσεις στις παραδοχές, απαντά ειλικρινά, και εντοπίζει την aporia — το σημείο όπου η λογική σπάει.

**Φάσεις:**
1. **Maieutic Questions** — Δημιουργεί 3-4 ερωτήσεις που στοχεύουν κρυφές παραδοχές. Κάθε ερώτηση συνοδεύεται από `target_assumption`
2. **Dialectic Answers** — Απαντά ειλικρινά, εντοπίζει αντιφάσεις (`contradiction_found`), φτάνει στην aporia

**Πότε επιλέγεται:** HyperGate κωδικός **D** — "ωφελείται από βαθιές ερωτήσεις για κρυφές παραδοχές".

**Βέλτιστο για:**
- "Είναι σωστή αυτή η προσέγγιση;" — όταν θέλεις να αμφισβητηθούν οι παραδοχές σου
- Φιλοσοφικά / ηθικά ερωτήματα
- Όταν το ερώτημα περιέχει κρυφές παραδοχές που πρέπει να εξεταστούν
- "Έχω δίκιο που θεωρώ ότι X;" — debugging σκέψης

**Output:** `questions[]` με `target_assumption`, `answers[]` με `contradiction_found`

---

### 7. Pre-Mortem (H)

**Τι κάνει:**
Αντιστρέφει τη σκέψη: ξεκινά με την παραδοχή ότι το project **ήδη απέτυχε** (1 χρόνο μετά), ψάχνει πίσω για την κρίσιμη απόφαση που οδήγησε στην αποτυχία, εντοπίζει early warning signals, και redesigns με safeguards.

**Φάσεις:**
1. **Failure Narrative** — "Γράψε vivid post-mortem 1 χρόνο αργότερα. Τι ακριβώς πήγε στραβά; Ποιοι επηρεάστηκαν και πώς;"
2. **Root Cause Analysis** — "Ποια ήταν η μία pivot απόφαση που έβαλε σε κίνηση την αποτυχία; Γιατί φαινόταν λογική εκείνη τη στιγμή;"
3. **Early Warning Signals** — "Ποια observable σήματα στις πρώτες 30 μέρες προέβλεπαν την αποτυχία; Πώς να τα μετρήσεις;"
4. **Hardened Redesign** — "Redesign με safeguards, checkpoints, και rollback plan ενάντια σε αυτές τις failure modes"

**Πότε επιλέγεται:** HyperGate κωδικός **H** — "risk assessment — φαντάσου την αποτυχία και δούλεψε αντίστροφα".

**Βέλτιστο για:**
- "Τι μπορεί να πάει στραβά με αυτό το plan;"
- Project planning πριν από execution
- "Ποιοι είναι οι κίνδυνοι αυτής της στρατηγικής;"
- Αξιολόγηση σχεδίων πριν δεσμευτείς σε πόρους

**Output:** `what_happened`, `immediate_triggers[]`, `pivot_decision`, `why_it_seemed_reasonable`, `early_signals[]` με `day` και `how_to_detect`, `hardened_solution`, `safeguards[]`, `rollback_plan`

---

### 8. Bayesian (I)

**Τι κάνει:**
Εφαρμόζει αυστηρά τον κανόνα Bayes: δημιουργεί 2-4 ανταγωνιστικές υποθέσεις με prior probabilities, αξιολογεί P(E|H) για κάθε παρατήρηση, υπολογίζει posteriors, και ελέγχει ευαισθησία παραδοχών.

**Φάσεις:**
1. **Priors** — Ορίζει 2-4 υποθέσεις. Κάθε μία παίρνει P(H) που αθροίζουν σε ~1.0
2. **Likelihoods** — Για 3-5 βασικές παρατηρήσεις: "Πόσο πιθανό είναι να δούμε αυτή την παρατήρηση αν H ισχύει; Αν H δεν ισχύει;"
3. **Posteriors** — P(H|E) ∝ P(E|H) × P(H). Normalization. Αναδεικνύει την most probable υπόθεση
4. **Sensitivity Analysis** — "Αν η σημαντικότερη παραδοχή είναι λάθος, πόσο αλλάζει το posterior;"

**Πότε επιλέγεται:** HyperGate κωδικός **I** — "εμπλέκει explicit probability estimation ή Bayesian belief updates".

**Βέλτιστο για:**
- "Ποια είναι η πιθανότητα X να ισχύει δοθέντων αυτών των στοιχείων;"
- Medical diagnosis: "Ποιο είναι το πιο πιθανό πρόβλημα;"
- "Πόσο πρέπει να αλλάξω τη γνώμη μου μετά από αυτό το νέο στοιχείο;"
- Ερωτήματα με ποσοτική αβεβαιότητα

**Output:** `hypotheses[]` με `prior_probability`, `likelihoods[]` με `p_e_given_h` + `p_e_given_not_h`, `posteriors[]` με `posterior_probability`, `sensitivity_analysis[]` με `posterior_shift`

---

### 9. Dialectical (J)

**Τι κάνει:**
Εφαρμόζει Hegelian διαλεκτική: Thesis → Antithesis → **Aufhebung** (όχι compromise — ποιοτική υπέρβαση που διατηρεί τις αλήθειες και των δύο πλευρών σε ανώτερο επίπεδο).

**Φάσεις:**
1. **Thesis** — Η ισχυρότερη δυνατή καταφατική θέση, fully committed
2. **Antithesis** — Αποκαλύπτει τις εσωτερικές αντιφάσεις της thesis, αρνείται κάθε commitment
3. **Contradictions** — Ταξινομεί: **irreconcilable** (πραγματικά αντίθετα) vs **compatible** (μπορούν να συγκατοικήσουν σε ανώτερο επίπεδο). Εντοπίζει synthesis candidates
4. **Aufhebung** — "ΌΧΙ compromise. Εύρεσε ποιοτικά ανώτερη θέση που διατηρεί τις αλήθειες και των δύο και τις υπερβαίνει"

**Πότε επιλέγεται:** HyperGate κωδικός **J** — "δύο αντίθετες θέσεις που και οι δύο έχουν αξία — synthesis, όχι νικητής".

**Βέλτιστο για:**
- "Πώς να ισορροπήσω ταχύτητα με ποιότητα;"
- "Πώς να συνδυάσω innovation με stability;"
- Παράδοξα που δεν λύνονται με απλή επιλογή
- Θέματα όπου ΚΑΙ οι δύο πλευρές μιας αντιπαράθεσης έχουν βαθιά δίκιο

**Διαφορά από Debate:** Το Debate επιλέγει νικητή. Η Dialectical βρίσκει **νέα αλήθεια** που υπερβαίνει και τις δύο.

**Output:** `thesis`, `antithesis`, `irreconcilable[]`, `compatible[]`, `synthesis_candidates[]`, `aufhebung`, `preserved_from_thesis[]`, `preserved_from_antithesis[]`, `new_insights[]`

---

### 10. Analogical (K)

**Τι κάνει:**
Αφαιρεί τη δομή του προβλήματος (αγνοεί επιφανειακά χαρακτηριστικά), ψάχνει σε άλλους τομείς για ισόμορφα προβλήματα που έχουν ήδη λυθεί, και μεταφέρει τον μηχανισμό λύσης.

**Φάσεις:**
1. **Abstraction** — Εξάγει `abstract_structure`: constraints, objectives, actors, core dynamics. "Τι τύπος προβλήματος είναι αυτό, αφηρημένα;"
2. **Domain Search** — Ψάχνει σε: biology, physics, engineering, military, economics, CS, history, social systems για isomorphic προβλήματα. Ranked by `structural_fit`
3. **Mapping** — Αντιστοιχεί source elements σε target elements. Κατηγοριοποιεί: object/relational/higher-order mapping. Σημειώνει unmapped elements
4. **Transfer** — Προσαρμόζει τον source μηχανισμό στο target. Εξηγεί **πού σπάει** η αναλογία και γιατί

**Πότε επιλέγεται:** HyperGate κωδικός **K** — "cross-domain analogical reasoning για μεταφορά λύσεων".

**Βέλτιστο για:**
- "Πώς λύνουν άλλοι τομείς αυτό το είδος προβλήματος;"
- Δημιουργικές λύσεις σε stuck προβλήματα
- "Υπάρχει ένα παράδειγμα από τη φύση/ιστορία που εφαρμόζεται εδώ;"

**Output:** `abstract_structure`, `source_domains[]` με `relevance_score`, `analogy_mappings[]` με `mapping_type`, `transferred_solution`, `broken_analogies[]`

---

### 11. Delphi (L)

**Τι κάνει:**
Εφαρμόζει τη μέθοδο Delphi για structured expert consensus: 4 ανεξάρτητοι experts κάνουν εκτίμηση χωρίς να ξέρουν τι λένε οι άλλοι, βλέπουν ανώνυμα aggregate στατιστικά, αναθεωρούν ή υπερασπίζονται, και ο outlier γράφει minority report.

**Φάσεις:**
1. **Round 1** *(παράλληλη — 4 experts ταυτόχρονα)* — Κάθε expert: ανεξάρτητη εκτίμηση με `estimate_value` (numeric αν δυνατό), `confidence`, `key_assumptions[]`
2. **Aggregation** — Υπολογίζει median, IQR, εντοπίζει outlier. **Ανωνυμία**: δεν αποκαλύπτεται ποιος expert είπε τι
3. **Round 2** *(παράλληλη — 4 experts)* — Βλέπουν aggregate. Αναθεωρούν ή υπερασπίζονται. `position: revised | maintained`
4. **Convergence** — Αξιολογεί: `converged: true/false`. IQR analysis. Consensus recommendation αν converged
5. **Dissent Report** — Ο outlier γράφει `minority_report`: τι χάνει η πλειοψηφία, ποια evidence υποστηρίζει την άλλη άποψη

**Πότε επιλέγεται:** HyperGate κωδικός **L** — "structured rounds εκτίμησης για ποσοτικό consensus — forecasting, sizing, probability".

**Βέλτιστο για:**
- "Πόσο θα κοστίσει αυτό το project;"
- "Πότε θα είναι έτοιμο το feature X;"
- "Ποια είναι η πιθανότητα αυτής της στρατηγικής να πετύχει;"
- Εκτιμήσεις όπου διαφωνία ανάμεσα σε experts είναι σημαντική πληροφορία

**Διαφορά από Jury:** Η Jury κάνει ranking λύσεων. Η Delphi κάνει **ποσοτική εκτίμηση** με μέτρηση διαφωνίας.

**Output:** `estimate_value`, `confidence`, `median`, `iqr`, `outlier_expert`, `converged`, `consensus_label`, `minority_report`

---

### 12. CoVE — Chain-of-Verification (M)

**Τι κάνει:**
Δημιουργεί αρχική απάντηση, σπάει την σε atomic ισχυρισμούς, δημιουργεί ανεξάρτητες ερωτήσεις επαλήθευσης για κάθε ισχυρισμό, απαντά ΧΩΡΙΣ να κοιτά την αρχική απάντηση, και αναθεωρεί.

**Φάσεις:**
1. **Draft** — Ολοκληρωμένη απάντηση με explicit claims και `confidence` (0.0–1.0) ανά claim
2. **Verification Questions** — 1-2 ερωτήσεις ανά claim που μπορούν να απαντηθούν **χωρίς να κοιτάξεις το draft**
3. **Independent Answers** — Απαντά τις ερωτήσεις ΑΝΕΞΑΡΤΗΤΑ. Verdict ανά claim: `supports | contradicts | insufficient`
4. **Revision** — Διορθώνει contradicted claims, προσθέτει caveats για insufficient, ενισχύει supported. `retracted_claims[]`, `upgraded_claims[]`

**Πότε επιλέγεται:** HyperGate κωδικός **M** — "απαιτεί structured fact-checking και επαλήθευση ισχυρισμών".

**Βέλτιστο για:**
- Ερωτήματα που περιέχουν πολλά συγκεκριμένα facts
- "Είναι αληθές ότι X, Y, και Z;"
- Technical ερωτήματα που τείνουν σε hallucination
- Όταν η ακρίβεια είναι κρίσιμη και θέλεις επαλήθευση

**Διαφορά από Scientific:** Η CoVE επαληθεύει **υπάρχοντες ισχυρισμούς**. Η Scientific δημιουργεί και **ελέγχει υποθέσεις**.

**Output:** `draft_answer`, `claims[]` με `confidence`, `verification_questions[]`, `answers[]` με `verdict`, `revised_answer`, `retracted_claims[]`

---

### 13. SoT — Skeleton-of-Thought (N)

**Τι κάνει:**
Σπάει το πρόβλημα σε 3-5 **ανεξάρτητα** υπο-προβλήματα, τα λύνει **παράλληλα** (asyncio semaphore με 4 concurrent solvers), και τα συναρμολογεί σε μία συνεκτική απάντηση.

**Φάσεις:**
1. **Skeleton** — Decompose σε 3-5 sub-problems. Κριτήριο: "ανεξάρτητα και παράλληλα επιλύσιμα". Κάθε sub-problem: `description`, `inputs[]`, `expected_output`, `rationale`
2. **Solve** *(παράλληλη — έως 4 ταυτόχρονα)* — Κάθε solver επιλύει ένα sub-problem ανεξάρτητα
3. **Assemble** — Συνδυάζει τις λύσεις, εξασφαλίζει smooth transitions, επιλύει τυχόν contradictions

**Πότε επιλέγεται:** HyperGate κωδικός **N** — "ΑΝΕΞΑΡΤΗΤΑ υπο-έργα που τρέχουν παράλληλα".

**Βέλτιστο για:**
- "Γράψε ένα business plan" → chapters που δεν εξαρτώνται μεταξύ τους
- "Σχεδίασε ένα σύστημα" → API design, DB schema, frontend, deployment — ανεξάρτητα
- Μεγάλα προβλήματα που φυσικά χωρίζονται σε workstreams

**Διαφορά από ToT:** Η SoT: παράλληλα **ανεξάρτητα** sub-tasks. Η ToT: σειριακές **εξαρτημένες** αποφάσεις.

**Output:** `sub_problems[]`, `solutions[]` ανά sub-problem, `assembled_answer`, `resolved_conflicts[]`

---

### 14. ToT — Tree-of-Thoughts (O)

**Τι κάνει:**
Εντοπίζει 2-3 κρίσιμα sequential decision points, για κάθε ένα δημιουργεί 2-3 candidate actions, τα αξιολογεί πολυδιάστατα, και αποφασίζει: CONTINUE (συνέχισε αυτό το μονοπάτι), BACKTRACK (δοκίμασε άλλο), ή TERMINATE.

**Φάσεις:**
1. **Decompose** — Εντοπίζει max 3 sequential decision points. Κάθε decision point: 2-3 candidate actions
2. **Generate** — Για το τρέχον decision point: 2-3 diverse candidates. Κάθε candidate: `expected_outcome`, `risks[]`, `prerequisites[]`
3. **Evaluate** — Scores 0-10: `feasibility`, `expected_value`, `risk_level`, `alignment_with_goal`. Best candidate recommendation
4. **Backtrack** — Decision: `continue | backtrack | terminate`. Αν backtrack, επιστρέφει σε προηγούμενο decision point

**Πότε επιλέγεται:** HyperGate κωδικός **O** — "ΕΞΑΡΤΗΜΕΝΕΣ sequential αποφάσεις όπου η κάθε επιλογή περιορίζει ή ανοίγει τις επόμενες".

**Βέλτιστο για:**
- Στρατηγικές αποφάσεις με cascading effects
- "Ποιο είναι το βέλτιστο μονοπάτι για να φτάσω από A σε Z;"
- Business strategy: market entry → pricing → go-to-market (κάθε βήμα εξαρτάται από το προηγούμενο)
- Game-like scenarios με sequential choices

**Διαφορά από SoT:** Η ToT κάνει backtracking και ασχολείται με **εξαρτημένες** αποφάσεις. Η SoT δεν κάνει backtrack γιατί τα sub-tasks είναι ανεξάρτητα.

**Output:** `decision_points[]`, `candidates[]`, `evaluations[]` με multi-dimensional scores, `decision` (continue/backtrack/terminate), `final_path[]`

---

### 15. PoT — Program-of-Thought (P)

**Τι κάνει:**
Εκφράζει τη συλλογιστική ως εκτελέσιμο Python κώδικα, προσομοιώνει / tracing την εκτέλεση, και ερμηνεύει τα αποτελέσματα στο context του αρχικού ερωτήματος.

**Φάσεις:**
1. **Generate Code** — Self-contained Python (stdlib only), με print statements, edge case handling
2. **Execute** — Προσομοιώνει ή tracing λογικά. Αν υπάρχει πραγματικό execution environment, εκτελεί. Αποτέλεσμα: `output`, `success`, `error`, `intermediate_steps[]`
3. **Interpret** — "Τι σημαίνουν αυτά τα αποτελέσματα για το αρχικό ερώτημα; Ποιοι οι περιορισμοί;"

**Πότε επιλέγεται:** HyperGate κωδικός **P** — "ο κώδικας IS η συλλογιστική — μαθηματικά/υπολογιστικά".

**Βέλτιστο για:**
- "Υπολόγισε το Lyapunov exponent του standard map"
- Αριθμητικές προσομοιώσεις
- "Απόδειξε αυτή την ιδιότητα υπολογιστικά"
- Ερωτήματα όπου ο κώδικας είναι πιο ακριβής από λόγια

**Διαφορά από Coding:** Η PoT χρησιμοποιεί κώδικα **ως εργαλείο συλλογιστικής**. Η Coding παράγει **production software** (πολλά αρχεία, tests, security review, documentation).

**Output:** `code` (complete Python), `output`, `success`, `intermediate_steps[]`, `interpretation`, `caveats[]`

---

### 16. Self-Discover (Q)

**Τι κάνει:**
Meta-reasoning: δεν εφαρμόζει ένα fixed pipeline αλλά **επιλέγει δυναμικά** ποια reasoning modules χρειάζεται το πρόβλημα, τα προσαρμόζει στο συγκεκριμένο context, και τα εκτελεί σε sequence.

**Φάσεις:**
1. **Select Modules** — Επιλέγει 3-5 από το inventory: `decomposition`, `verification`, `analogy`, `causal_analysis`, `counterfactual`, `abstraction`, `constraint_satisfaction`, `optimization`. Καθορίζει `order` και `composition_strategy`
2. **Adapt** — Κάθε module γίνεται concrete actionable instruction για **αυτό** το πρόβλημα. Ορίζει inputs/outputs
3. **Implement** — Εκτελεί τα modules in sequence, passing outputs forward. Synthesizes σε final answer με `module_attribution`

**Πότε επιλέγεται:** HyperGate κωδικός **Q** — "απαιτεί dynamic composition reasoning modules για αυτή την συγκεκριμένη δομή".

**Βέλτιστο για:**
- Ερωτήματα που δεν ταιριάζουν σαφώς σε καμία άλλη κατηγορία
- "Πώς να σκεφτώ αυτό το πρόβλημα;" — meta-level
- Σύνθετα προβλήματα που χρειάζονται custom combination methods
- Όταν η δομή του προβλήματος είναι unclear

**Output:** `selected_modules[]`, `adapted_modules[]` με concrete instructions, `module_outputs[]`, `final_answer`, `module_attribution{}`

---

### 17. Writing (R)

**Τι κάνει:**
Composite pipeline για research-backed long-form writing: συνδυάζει CoVE (claim verification), SoT (parallel section writing), Pre-Mortem (quality check), και adversarial journal review σε 8 φάσεις.

**Φάσεις:**
1. **Decompose Topic** — Δομή άρθρου, βασικές ενότητες
2. **Retrieve Sources** — Web search για πηγές (SearXNG)
3. **Extract Claims** *(CoVE draft, critical=True)* — Atomic claims από πηγές με `source_url` και `confidence`
4. **Adversarial Verify** — Fact-check κάθε claim ανεξάρτητα
5. **Synthesize** *(SoT parallel)* — Γράφει κάθε ενότητα παράλληλα βασισμένη σε verified claims
6. **Pre-Mortem** — "Γιατί θα απέρριπτε αυτό το άρθρο ένας journal reviewer;"
7. **Journal Review** — Adversarial critic feedback
8. **Final Assembly** — Polished article με sources section, `confidence_notice`, `word_count`

**Πότε επιλέγεται:** HyperGate κωδικός **R** — fast-path regex για "write article/essay/blog post/report". Επίσης οποιοδήποτε ερώτημα με research writing intent.

**Βέλτιστο για:**
- "Γράψε ένα άρθρο για X"
- "Δημιούργησε ένα informative essay"
- Long-form explainers, technical reports, whitepapers

**ΔΕΝ είναι βέλτιστο για:** Δημιουργική γραφή (ποιήματα, ιστορίες) — αυτά πάνε direct answer.

**Output:** `claims[]` με `confidence`, `sections[]`, `final_article`, `abstract`, `sources_cited[]`, `confidence_notice`

---

### 18. Coding (S)

**Τι κάνει:**
5-φάσιο pipeline για παραγωγή production-grade κώδικα: spec analysis → parallel file generation → adversarial security review → TDD test generation → final assembly με applied fixes.

**Φάσεις:**
1. **Spec Analysis** — Technical specification: language, framework, αρχεία, public interfaces, error strategy, security boundaries, testability
2. **Code Generation** *(παράλληλη — ένα αρχείο ανά call)* — Full production code ανά αρχείο: type annotations, specific exceptions, input validation, no hardcoded secrets, structured logging, no stubs
3. **Security Review** *(critical=True)* — Principal security engineer adversarial review: injections, SSRF, path traversal, hardcoded secrets, silent error swallows, race conditions, incomplete implementations
4. **Test Generation** — TDD test suite: normal cases, boundaries, invalid inputs, error paths, security issues. Runnable χωρίς modification
5. **Final Assembly** — Principal engineer: applies critical+high fixes, ensures imports match exports, types compatible. Παράγει `files[]`, `readme`, `fixes_applied[]`

**Πότε επιλέγεται:** HyperGate κωδικός **S** — "παραγωγή production software, implementation, αρχιτεκτονική".

**Βέλτιστο για:**
- "Φτιάξε ένα REST API για X"
- "Υλοποίησε αυτό το feature σε Python/TypeScript/Go"
- "Σχεδίασε και κώδικοποίησε αυτή την αρχιτεκτονική"
- Οποιοδήποτε ερώτημα που ζητά working, deployable code

**Διαφορά από PoT:** Η Coding φτιάχνει **software** (πολλά αρχεία, tests, documentation, security). Η PoT γράφει κώδικα **ως εργαλείο για να υπολογίσει κάτι**.

**Output:** `language`, `framework`, `files[]` με complete code, `critical_issues[]`, `high_issues[]`, `test_files[]`, `coverage_estimate`, `readme`, `fixes_applied[]`

---

## Disambiguation Guide — Πότε να χρησιμοποιήσεις τι

### B (Debate) vs J (Dialectical)

| Ερώτηση | Σωστή μέθοδος |
|---------|--------------|
| "SQL ή NoSQL για αυτή την εφαρμογή;" | **B** — ένα από τα δύο |
| "Microservices ή monolith;" | **B** — ένα από τα δύο |
| "Πώς να ισορροπήσω speed with quality;" | **J** — και τα δύο έχουν αξία |
| "Innovation vs stability — πώς να τα συνδυάσω;" | **J** — synthesis |

**Κανόνας:** B αν χρειάζεσαι **νικητή**. J αν χρειάζεσαι **σύνθεση**.

### E (Multi-Perspective) vs F (Jury)

| Ερώτηση | Σωστή μέθοδος |
|---------|--------------|
| "Πώς να αντιμετωπίσω την κλιματική αλλαγή;" | **E** — ανοιχτή ανάλυση |
| "Ποια από αυτές τις 3 αρχιτεκτονικές είναι καλύτερη;" | **F** — ranking λύσεων |

### E (Multi-Perspective) vs L (Delphi)

| Ερώτηση | Σωστή μέθοδος |
|---------|--------------|
| "Ποια είναι τα pros/cons του X;" | **E** — ανάλυση |
| "Πόσο θα κοστίσει αυτό το project;" | **L** — εκτίμηση με αριθμό |

### N (SoT) vs O (ToT)

| Ερώτηση | Σωστή μέθοδος |
|---------|--------------|
| "Γράψε business plan (sections ανεξάρτητα)" | **N** — parallel independent |
| "Ποια στρατηγική go-to-market να ακολουθήσω;" | **O** — sequential decisions |

### M (CoVE) vs C (Scientific)

| Ερώτηση | Σωστή μέθοδος |
|---------|--------------|
| "Είναι αληθείς αυτοί οι 5 ισχυρισμοί;" | **M** — verify existing claims |
| "Ποια εξήγηση εξηγεί καλύτερα αυτό το φαινόμενο;" | **C** — generate + test hypotheses |

### S (Coding) vs P (PoT)

| Ερώτηση | Σωστή μέθοδος |
|---------|--------------|
| "Υλοποίησε ένα authentication system" | **S** — production software |
| "Υπολόγισε το Lyapunov exponent αριθμητικά" | **P** — code as reasoning |

---

## Ομάδες Μεθόδων

### Adversarial / Αντιπαράθεση
**Debate (B), Dialectical (J)** — Και οι δύο χρησιμοποιούν σκόπιμη αντιπαράθεση. Η Debate αναδεικνύει νικητή, η Dialectical βρίσκει υπέρβαση.

### Panel / Consensus
**Jury (F), Delphi (L)** — Πολλαπλοί ανεξάρτητοι agents συγκλίνουν. Η Jury για ranking, η Delphi για ποσοτική εκτίμηση.

### Verification / Επαλήθευση
**CoVE (M), Scientific (C)** — Δοκιμάζουν claims. Η CoVE επαληθεύει γεγονότα, η Scientific ελέγχει υποθέσεις.

### Structured Decomposition
**SoT (N), ToT (O), Self-Discover (Q)** — Σπάνε το πρόβλημα. SoT παράλληλα, ToT σειριακά, Self-Discover δυναμικά.

### Computation
**PoT (P)** — Κώδικας ως λογική.

### Risk & Uncertainty
**Pre-Mortem (H), Bayesian (I)** — Αβεβαιότητα και κίνδυνος. Pre-Mortem: narrative failure analysis. Bayesian: numeric probability.

### Domain-Specific Production
**Writing (R), Coding (S)** — Long-form outputs: άρθρα και software αντίστοιχα.

### General Purpose
**Multi-Perspective (E), Research (G), Analogical (K), Socratic (D)** — Ευρεία εφαρμογή χωρίς συγκεκριμένη δομή προβλήματος.

---

<!-- Generated: 2026-04-27 | Methods: 18 | Token estimate: ~3200 -->
