# Vision: The Truth-Engine Optimization
**Objective:** Zero-Hallucination Reasoning through Forensic Auditing and Epistemic Rigor.

> Design vision, not shipped behaviour. The status table at the bottom is a
> snapshot dated 2026-09-08; nothing re-checks it, so verify against the code
> before relying on any row.

---

## 1. Strict Provenance (Taint Tracking)
To eliminate "pure" hallucinations (confabulations), the Reasoner must move from soft-RAG to **Strict Provenance**.
- **Mechanism:** Implement "Taint Records" for every claim. A claim is only valid if it can be mapped to a specific byte-range in the source context.
- **Rule:** If the `Synthesis` phase generates a fact without a verified `Context-ID`, the claim is automatically flagged as a `HYPOTHESIS` or deleted.

## 2. Source Reliability Weighting (The Authority Matrix)
The Reasoner must not treat all context as equally "true."
- **Mechanism:** Assign a **Reliability Score (0.0 - 1.0)** to every source fetched during `Context Vetting`.
- **Criteria:** Peer-reviewed data (1.0), official documentation (0.9), news (0.7), social media/unverified (0.3).
- **Optimization:** The final "Truth Score" of an answer is the weighted average of its supporting sources' reliability.

## 3. Cross-Lab Forensic Audit
Hallucinations are often artifacts of specific training data. They are rarely identical across different model families.
- **Mechanism:** Execute the `Forensic Search` loop when two models (e.g., Claude and DeepSeek) disagree.
- **Action:** Instead of "averaging" their disagreement, trigger a targeted search to find a third-party "tie-breaker" source. Disagreement is treated as a trigger for more compute, not a signal for compromise.

## 4. Adversarial Red-Teaming (Destructive Critique)
Standard critique suffers from "Affirmation Bias." 
- **Mechanism:** The `Critique` phase is replaced by **Adversarial Red-Teaming**. 
- **Prompting Strategy:** The model is explicitly tasked to "Prove this answer is false." It is rewarded for finding logic gaps, dates that don't align, or citations that don't support the claim. 
- **Survival Logic:** Only claims that survive the "Destructive Phase" are promoted to the final `Synthesis`.

## 5. Formal Logical Verification (NLI)
Language is fluid, but logic is formal.
- **Mechanism:** Integrate specialized **Natural Language Inference (NLI)** checks between the "Source" and the "Claim."
- **Test:** Does the Source *entail* the Claim, or does it merely *mention* the keywords? Any claim that is only "Neutral" or "Contradictory" relative to the source is purged.

## 6. Inference-Time Compute Scaling
Hallucinations often happen when a model is "rushed" to a conclusion.
- **Mechanism:** Scale the **Chain-of-Thought (CoT)** length based on the complexity of the verification.
- **Optimization:** For high-stakes queries, the Reasoner executes multiple internal paths. If the paths diverge (high variance), the system continues "thinking" (sampling) until the distribution of internal answers converges to a single mode.

## 7. The "Unknown" Victory (Epistemic Refusal)
The ultimate defense against hallucinations is the courage to be silent.
- **Vision:** Re-align the system's success metrics. A declaration of `UNKNOWN` with a detailed explanation of *why* the information is missing is considered a **higher-order success** than a "best-guess" answer.
- **User UX:** Present the user with a "Knowledge Map" showing what is `VERIFIED`, what is `PROBABLE`, and where the `VOID` of information exists.

---

### Implementation Status: Forensic Architecture
| Component | Implementation Priority | Status |
| :--- | :--- | :--- |
| **Provenance Tracking** | CRITICAL | In Progress |
| **NLI Logic Gates** | HIGH | Research |
| **Source Weighting** | MEDIUM | Planned |
| **Adversarial Critique** | HIGH | Active |
| **Inference Scaling** | EXPERIMENTAL | Conceptual |
