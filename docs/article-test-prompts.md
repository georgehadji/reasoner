# Article Preset Test Prompts

10 prompts designed to stress-test each phase of the 10-phase editorial pipeline.

---

## 1. Claim-heavy — tests Fact Check + Claim Ledger

```
Write an article about how microplastics affect human fertility rates, citing recent scientific studies. Target publication: The Atlantic.
```

**Tests:** Claim ledger extraction, source verification, citation accuracy scoring.

---

## 2. Counterargument-rich — tests Structural Review

```
Write an article arguing that remote work has been a net negative for innovation. Address the strongest counterarguments directly. Target publication: The Economist.
```

**Tests:** Implicit assumption detection, counterargument identification, logical gap analysis.

---

## 3. Assumption-dense — tests implicit assumption detection

```
Write an article explaining why the 4-day work week is inevitable for knowledge workers by 2030.
```

**Tests:** Unstated premise identification, speculative leap detection, rigor scoring.

---

## 4. Speculation-prone — tests speculative leap detection

```
Write an article predicting how quantum computing will transform drug discovery within the next five years.
```

**Tests:** Evidence support ratio, verification status classification (verified vs speculative), claim ledger accuracy.

---

## 5. Style-matching — tests Style Edit + publication conventions

```
Write an article in the style of Paul Graham about why startups should ignore competitor funding rounds.
```

**Tests:** Voice preservation through dev edit and style edit, publication convention matching, tone consistency.

---

## 6. Data-interpretation — tests evidence support scoring

```
Write an article analyzing whether the global decline in insect populations is reversible, using recent entomology research.
```

**Tests:** Source-to-claim mapping, evidence density scoring, synthesis quality with scientific sources.

---

## 7. Opinion-broad — tests argument map structure

```
Write an article about whether AI regulation helps or hurts innovation.
```

**Tests:** Argument blueprint construction (all 9 fields), outline section completeness, draft adherence to blueprint.

---

## 8. Narrow-technical — tests outline depth

```
Write an article explaining CRISPR-Cas12a's advantages over Cas9 for therapeutic gene editing.
```

**Tests:** Technical accuracy in outline and draft, domain-expert-level critique in structural review, citation precision.

---

## 9. Short-edge — tests word budget adherence

```
Write a 500-word op-ed about why cities should eliminate parking minimums.
```

**Tests:** Conciseness enforcement, redundancy removal in dev edit, word count tracking.

---

## 10. Meta / abstract — tests new-insight articulation

```
Write an article about why most published research findings are false, and what should change about academic publishing.
```

**Tests:** New-insight articulation in argument map, developmental edit quality for complex reasoning, final audit thesis-advancement scoring.

---

## Quickest high-signal test

```
Write an article about whether AI regulation helps or hurts innovation.
```

Broad enough to need argument mapping, has obvious counterarguments, invites speculation, and has verifiable claims from both sides. Hits every phase in a single prompt.
