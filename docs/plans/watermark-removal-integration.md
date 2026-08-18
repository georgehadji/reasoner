# AI Provenance-Mark Removal in Reasoner — Research & Implementation Plan

**Status:** Draft for review · **Date:** 2026-08-18 · **Branch target:** feature branch off `review-rebase`
**Source studied:** `guillaumemeyer/watermarks-remover` v0.5.0 (MIT), ~7,900 LOC of stdlib Python + agent skill
**Scope:** text (Layer A + Layer B) and image (container metadata) mark removal, integrated into Reasoner's hexagonal DDD architecture

---

## 0. TL;DR

The reference repo splits "AI watermark" into **five distinct mark classes** and treats each with a different mechanism, honesty level, and verifiability guarantee. Only two of the five are deterministic and verifiable; the rest are best-effort and the repo says so loudly.

Reasoner already ships a **naive, buggy Layer A** at `core/sanitization.py:202` (`clean_llm_artifacts`), called from exactly one place (`application/flows/synthesis_phase.py:82`). It:

- **corrupts multilingual output** — strips U+200D (ZWJ) and U+2066–U+2069 (RTL isolates) unconditionally, breaking emoji ZWJ sequences (👨‍👩‍👧, ❤️‍🔥), Persian/Urdu ZWNJ orthography (می‌روم → میروم), and mixed RTL/LTR prose — in a product whose `PipelineState` carries `language`, `output_language`, and `pivot_active`;
- **misses the security-relevant carriers entirely** — Unicode tag characters (U+E0001–U+E007F), private-use planes, and supplementary variation selectors, which are the classes used to smuggle instructions past human review;
- **reports nothing** — silent mutation, no counts, no verification, no way for a user or an auditor to know what changed.

The plan below replaces it with a **pure, context-aware, self-reporting Layer A domain engine**, adds an **image metadata scrubber** for the data-URL image path, and adds an **opt-in, credit-metered, cross-bloc Layer B rewrite phase** — all inside the existing layered contract, **adding zero new `.importlinter` exceptions**.

**Recommended default posture:** Layer A egress hygiene **on** (it is a bug fix and a prompt-injection defense). Layer B statistical rewrite **off**, opt-in, audited. Image metadata strip **on for user uploads** (privacy — EXIF GPS), **opt-in for Reasoner-generated images** (see §10.3).

---

# Part I — Research: how `watermarks-remover` actually removes marks

## 1.1 The mark taxonomy (the load-bearing idea)

The repo's central insight is that "AI watermark" is four or five unrelated technologies wearing one word. Each needs its own removal mechanism and its own honesty caveat.

| # | Class | Where the signal lives | Removal mechanism | Verifiable? |
|---|-------|------------------------|-------------------|-------------|
| 1 | **Edit-based text** | Invisible/format Unicode codepoints inserted into the string | Deterministic per-character classifier | **Yes** — exact counts, re-inspect proves clean |
| 2 | **Generative / statistical text** | *Which tokens were chosen* — biased sampling (Kirchenbauer green-list, SynthID-Text tournament sampling) | LLM rewrite (paraphrase / back-translate / structural regen) | **No** — best-effort; needs vendor detector + key to prove |
| 3 | **Data-driven / backdoor** | Model weights (trigger phrases → identifiable behavior) | — | Out of scope (model-side) |
| 4 | **File provenance metadata** | C2PA/JUMBF manifests, EXIF, XMP, OOXML doc props — *hard-bound* to the container | Structural container rewrite (drop chunks/segments/boxes) | **Yes** — re-inspect proves clean |
| 5 | **Pixel/waveform-domain** | The image/audio signal itself (SynthID-media, Tree-Ring, StegaStamp, StableSignature) and C2PA **soft binding** | Diffusion regeneration (CtrlRegen / DiffusionPurification) | **No** — heavy, drifts the content, no local oracle |

Classes 1 and 4 are engineering. Classes 2 and 5 are an arms race the repo explicitly refuses to claim it wins. Class 3 is out of scope everywhere.

## 1.2 Layer A — edit-based Unicode (`service/scripts/text_unicode.py`, 655 LOC)

The single most transferable component, and the one whose difficulty is entirely counter-intuitive: **stripping invisible characters is trivial; not destroying the ones that are load-bearing is the whole problem.**

### Carrier sets

- `STRIP_CODEPOINTS` — 60+ explicit codepoints: soft hyphen, CGJ, Arabic letter mark, Hangul fillers, Khmer inherent vowels, Mongolian FVS/vowel separator, the full zero-width family (ZWSP/ZWNJ/ZWJ/WJ/BOM), all bidi controls, invisible math operators (U+2061–U+2064), format controls U+206A–U+206F, VS1–VS16, interlinear annotation marks.
- Range-based: **tag characters U+E0001–U+E007F** (the classic stego channel), **variation selectors supplement U+E0100–U+E01EF**, **all three private-use planes** (U+E000–F8FF, U+F0000–FFFFD, U+100000–10FFFD).
- `SPACE_HOMOGLYPHS` — 16 space lookalikes (NBSP, en/em quad, thin, hair, figure, ideographic…) → normalized to U+0020, *not* deleted.
- `LATIN_CONFUSABLES` — Cyrillic + fullwidth Latin lookalikes → ASCII. **Aggressive mode only**, off by default.
- Catch-all: any remaining `unicodedata.category(ch) == "Cf"`.

### Preservation rules — the actual engineering

A naive strip corrupts real text. The repo encodes six context-sensitive exemptions, each keyed on *neighbouring* characters:

| Rule | Preserves | Condition |
|------|-----------|-----------|
| Emoji glue | ZWJ, VS15/VS16 | previous kept char is an emoji base, and (for ZWJ) the next char is too |
| Script joiners | ZWNJ/ZWJ | previous **and** next char are letters/marks of the *same* joining script (Arabic, Indic, South-Asian, Khmer, Mongolian) |
| Flag tag sequences | U+E0020–U+E007F | inside a complete `U+1F3F4 … U+E007F` subdivision-flag run (pre-scanned) |
| Same-script fillers | Mongolian FVS, Khmer inherent vowels, Hangul jamo fillers | directly after a base letter of that same script |
| Bidi | LRM/RLM/ALM/isolates, and complete LRE/RLE…PDF **embedding** pairs | always by default; **overrides** (LRO/RLO) stay destructive because they can reorder unrelated spans |
| Orthographic `Cf` | U+0600–0605, U+06DD, U+070F, U+08E2, U+110BD, U+110CD | always — these are normal Arabic/Syriac/Kaithi orthography |

Two O(n) pre-passes build index sets before classification: `_valid_flag_tag_indices()` and `_valid_bidi_embedding_indices()`. The classifier consults them by index.

A subtle detail worth copying verbatim: **glue characters do not advance `prev_kept`.** Without this, a ZWJ chain like `👨‍👩‍👧` breaks after the first join because the ZWJ itself becomes the "previous character."

### Shape

`_decide(ch, prev_kept, prev_input, next_input, *, valid_flag_tag, valid_bidi_embedding, normalize_spaces, treat_confusables, strip_emoji_glue, strip_bidi) -> (action, out_char, kind)` where `action ∈ {keep, strip, replace}`.

**One function, two callers** — `inspect_text()` and `clean_text()` both drive `_decide()`, so inspection provably predicts cleaning. This is the design's best structural property and non-negotiable to preserve. (The repo's own changelog documents the bug that appears when the two drift: container inspect reported `suspicious: false` on markdown whose body `clean_container` then scrubbed.)

**Weakness to fix on port:** `_decide()` is a 68-line if-ladder threading six boolean flags. It violates Reasoner's `<50 lines` / no-deep-nesting standard and is hard to extend. See §5.1 for the Specification-pattern refactor.

### Output

`TextInspectReport{length, suspicious_total, hits[CharHit], notes}` where `CharHit{codepoint, char, label, count, kind, samples[:10]}`. `kind ∈ {strip, bidi, tag_chars, variation_selector, zwj_family, private_use, space, confusable, other_cf}`. Every hit carries a **confidence**: `space` → `informational`, everything else → `probable`.

Clean returns `(text, stats)` with per-label removed/replaced counters and an `nfkc_changed` flag whose changed-character count is derived by `difflib.SequenceMatcher` opcodes.

## 1.3 Layer B — statistical / sampling watermarks (`rewrite_text.py`, 622 LOC)

Attacks class 2 by regenerating the wording. Five prompt strategies:

| Strength | Attack |
|----------|--------|
| `paraphrase` (default) | Explicit token-level churn: clause order, connectors, transition words, sentence boundaries, content **and** function words. Preserve facts/numbers/names/identifiers. |
| `humanize` | Zero-shot "write as if a human wrote it from scratch"; targets formulaic AI transitions. |
| `code` | Rewrites comments/docstrings/string literals + renames *local* identifiers; preserves behavior and public API names. |
| `backtranslate` | Round-trip through a pivot language. |
| `structural` | Extract bullet outline (no full sentences) → regenerate document from outline. |

### Candidate selection

`--candidates N` generates N rewrites and picks the winner by **bigram Jaccard distance** from the original (`1 - |A∩B|/|A∪B|`), with a **length-drift penalty** of −0.15 when the rewrite is >2× or <0.5× the original length. Pure function, trivially testable.

### Model hygiene (the rule that matters)

> Prefer a **non-origin** model for Layer B — do not rewrite Claude text with Claude if you are trying to avoid re-stamping.

Rewriting with the origin model re-applies the origin model's sampling bias. This maps *exactly* onto machinery Reasoner already has (§3, ADR-5).

### Verification harness

`--markllm-scheme kgw|synthid` runs THU-BPM/MarkLLM detection before and after the rewrite and reports a `cleared` boolean. The repo is emphatic that this is **same-scheme-config-only** — it proves a KGW mark you yourself embedded disappeared; it certifies nothing about a vendor detector.

### The disclaimer (a product decision, not a footnote)

The README argues against Layer B for most users:

1. Removal means **rewording, not restructuring** — the signal is spread across nearly every token, so shuffling paragraphs does nothing.
2. Rewording **degrades the copy** — output is capped by the rewriting model's ceiling.
3. Therefore: *"If the plan is to rewrite the text with a cheaper model anyway, why pay for a premium model in the first place?"*

For Reasoner — whose entire value proposition is premium multi-model synthesis — this is the single most important finding in the repo. It dictates the design in §5.5.

## 1.4 Stylometry scorer (`score_stylometry.py`, 404 LOC) — not a watermark detector

Zero-LLM, stdlib-only heuristic for "does this read as AI-written":

- **24 weighted regex markers** ("delve into" 1.2, "rich tapestry" 1.3, "in today's fast-paced world" 1.4, "as an AI" 1.5, …) → weighted density per 100 words.
- **Burstiness** — coefficient of variation of sentence word-length. CV < 0.25 → 0.95 AI-score; CV > 0.55 → 0.05. LLM prose is unnaturally uniform.
- **MATTR** — moving-average type-token ratio over 50-word sliding windows; LLMs cluster at 0.68–0.76.
- Composite: `0.45·burstiness + 0.45·ngram + 0.10·diversity`, **dampened** linearly from ×0.4 at 30 words to ×1.0 at 100 words, with an `insufficient_length` status below 30 words.

This is not watermark detection — it is a **quality/telltale signal**. For Reasoner it is more valuable as a *writing-quality metric* than as a removal tool (§5.4).

## 1.5 File/container metadata (`image_meta.py` 1,110 LOC, `container_meta.py` 1,277 LOC)

Pure structural rewrites, one strategy per format:

| Format | Mechanism |
|--------|-----------|
| **PNG** | Walk `length/type/payload/CRC` chunks; drop `caBX`/`juMB`/`c2*` (C2PA/JUMBF) and `tEXt`/`zTXt`/`iTXt`/`eXIf` containing AI markers; rebuild. |
| **JPEG** | Walk markers; drop **APP11** (JUMBF/C2PA) always, other APPn on marker-hit or full-strip, `COM` always. Keep APP0 (JFIF) for compatibility. Copy `SOS`→EOF verbatim to preserve entropy-coded scan. |
| **WebP** | Parse RIFF chunks; drop `C2PA`, `EXIF`, `XMP `, `ICCP`; **critically, clear the corresponding feature bits in the `VP8X` header** — otherwise the file declares metadata it no longer has and decoders choke. |
| **AVIF/HEIC** | Recursive ISOBMFF box walk; drop `jumb`/`c2pa`/`c2*` top-level boxes and `meta` sub-boxes, plus `uuid` boxes matching the XMP UUID. |
| **SVG / HTML / MD / DOCX / ODT / PDF** | XML/text-level: `<metadata>` blocks, `meta[name=generator]`, JSON-LD, `data-ai*` attributes, YAML frontmatter AI keys, `docProps`+`customXml`, `meta.xml`. |

Marker vocabulary: `C2PA_MARKERS` (c2pa, jumb, c2ma, contentcredentials, contentauth, cai:) and `AI_META_HINTS` (digitalSourceType, trainedAlgorithmicMedia, compositeWithTrainedAlgorithmicMedia, AIGC, SynthID, Claude, Anthropic, OpenAI, dcterms:provenance).

**PDF is the cautionary tale.** `exiftool -all=` writes PDFs *incrementally*: it appends an update block that frees the Info object, but **the original metadata bytes remain in the file verbatim** and exiftool can undo the edit. Exit code 0, viewers show nothing, file gets *larger* — a silent leak. The repo follows with `qpdf --linearize` to re-serialize from the object graph, and emits an explicit warning when qpdf is absent. **Lesson: "the tool exited 0" is not evidence of removal. Verify by re-inspection.**

## 1.6 Pixel domain — deliberately externalized

Never bundled. Runtime-loaded from an external checkout, capability-gated:

- **CtrlRegen** (ICLR 2025) via `mertizci/noai-watermark` — ControlNet + DINOv2 IP-Adapter controllable regeneration from clean noise. 512×512 native, auto-tiled with 192px overlap and cosine-blended seams for larger inputs. Conservative default strength **0.25** (backend default is 0.5) because *"removal can still leave forensic traces."* ~10 GB of model downloads, GPU strongly recommended.
- **MarkDiffusion DiffusionPurification** — blind regeneration, drifts content more than CtrlRegen; treated as fallback.
- **reverse-SynthID** — scoring only, non-commercial Research License, explicitly *not* an official Google detector.

## 1.7 Cross-cutting design principles worth carrying over

1. **Inspect → clean → re-inspect.** Every clean re-runs inspection on its own output and reports residual findings. Exit code 1 when anything survives.
2. **Verifiable vs best-effort, always separated.** Reports never blend "we removed 47 ZWSP" with "we paraphrased and hope."
3. **Four-tier finding confidence** — `confirmed` (recognized provenance structure) / `probable` (AI marker inside a recognized metadata structure) / `informational` (context notes, CMS generators) / `likely_false_positive` (raw whole-file byte scans that collide with compressed data).
4. **One decision function, two consumers.** Inspect and clean cannot drift.
5. **Capability gating.** `GET /capabilities` reports which optional tools/backends exist; the client is instructed to drive advice from it and never promise absent capabilities.
6. **Default-deny on binary.** Text tools refuse ZIP/PDF/image magic bytes plus a control-byte-ratio heuristic, and name the correct tool. (This was a real data-destruction bug: decoding a DOCX as text and writing it back destroyed the file.)
7. **Atomic, symlink-refusing writes.** temp-file + `os.replace`, refuse symlinked destinations.
8. **Never claim certification.** *"Until vendors ship public detectors and keys, no tool can honestly certify 'this fails the official check.'"*

## 1.8 What it explicitly cannot do

- Certify that any vendor detector will fail.
- Remove **C2PA soft binding** — an in-content watermark that re-links to a *remote* manifest after metadata is stripped. Stripping hard-bound C2PA does not clear it.
- Remove audio/video watermarks.
- Touch training-data backdoors.
- Guarantee that pixel removal leaves no forensic trace (arXiv:2605.09203 — removal itself is detectable).

---

# Part II — Reasoner today

## 2.1 The existing Layer A and why it must be replaced

`src/reasoner/core/sanitization.py:202` — `clean_llm_artifacts(text) -> str`. Imported at `application/pipeline.py:68` (unused there — dead import) and called once, at `application/flows/synthesis_phase.py:82`, on `core_solution` only.

| Defect | Evidence | Consequence |
|--------|----------|-------------|
| Unconditional ZWJ strip | `_STRIP_CODEPOINTS` contains U+200D; applied via `str.translate` with no context | Emoji ZWJ sequences collapse (👨‍👩‍👧 → 👨👩👧, ❤️‍🔥 breaks). Persian/Urdu/Devanagari ZWNJ orthography destroyed (می‌روم → میروم). |
| Unconditional bidi strip | `_BIDI_STRIP = re.compile(r"[‪-‮⁦-⁩]")` | RTL isolates removed from legitimate mixed RTL/LTR prose — and Reasoner's `PipelineState` carries `language` / `output_language` / `pivot_active`, so multilingual output is a first-class feature. |
| **No tag characters** | U+E0001–U+E007F absent from the strip set | The primary invisible-instruction smuggling channel passes straight through. This is the security-relevant gap. |
| No private-use planes | absent | Second stego channel passes through. |
| No supplementary variation selectors | U+E0100–U+E01EF absent | Third channel passes through. |
| No confusables handling | absent | Cyrillic/fullwidth homoglyph substitution undetected. |
| Silent | returns `str`, no counts | No report, no verification, no audit trail, no way to prove idempotence. |
| Single call site | `core_solution` only | `critical_insights`, `action_blueprint`, `open_questions`, writing/article output, direct answers, and follow-ups are never scrubbed. |

Rating: it removes the easy 40% of class 1, corrupts non-English text while doing so, and misses the class that matters for security.

## 2.2 Surfaces that need coverage

**Text — egress (Reasoner → user)**
- `FinalSolution.core_solution`, `.critical_insights`, `.action_blueprint`, `.open_questions` (`domain/core_types.py`, built in `flows/synthesis_phase.py:149`)
- Writing/article method output (`flows/writing_phases.py`, `flows/article_phases.py`)
- Direct answers (HyperGate `DIRECT` fast path) and follow-up streams (`api/streaming.py`)
- Renderer exports (`application/services/renderers/`, `export_to_json` at `_shared.py:300`)

**Text — ingress (user → Reasoner)**
- `problem` text via `sanitize_for_prompt` (`core/sanitization.py:182`)
- Uploaded document text (`api/routes/uploads.py` → `uploader.get_file_text`)
- Retrieved web/search context (`vetted_context`, `web_discovery_results`)

**Images**
- Generated: `api/routes/images.py:187` → `infrastructure/llm/image_generation.py` → **base64 data URLs, in memory, never files**. Gemini and OpenAI both attach provenance metadata.
- Uploaded: `api/routes/uploads.py` (bytes in memory, size-capped, streamed in 1 MB chunks).

**Architectural constraint this implies:** every scrubber must be **`bytes → bytes`**, not `path → path`. The reference repo is path-oriented throughout (`clean_image(path, dest)`); the port must invert that. Paths become an adapter concern, not a domain one.

## 2.3 Existing machinery to reuse (do not rebuild)

| Need | Existing Reasoner component |
|------|----------------------------|
| Non-origin rewrite model | `bloc_of()` in `infrastructure/llm/registry.py` + cross-bloc preset invariants (`domain/preset_registry.py:8-14`) |
| Capability gating | `core/ports/capability_registry_port.py` pattern; `/capabilities`-style reporting |
| Absent-backend fallback | `NoopExecutor` precedent (`infrastructure/execution/noop_executor.py`, selected in `flows/services.py:39`) |
| Cost metering / credits | `application/services/run_metering.py`, `api/run_observability.py` (`CreditSink`), `estimate_service` |
| Circuit breaking + fallback chain | `infrastructure/llm/router.py` (`ProviderRouter`) |
| Phase orchestration, SSE, retries | `application/flows/runner.py`, `api/serializers.py`, `api/streaming.py` |
| Audit trail | `application/services/audit_service.py` |
| Spend caps | `application/services/spend_limit_service.py`, `infrastructure/llm/spend_tracker.py` |
| Settings | `core/settings.py` (sole env reader) |

---

# Part III — Architecture decisions

Numbered so review can accept/reject individually.

### ADR-1 — Layer A lives in `domain/`, as a pure function core

`reasoner.domain` is the **bottom** layer of the `.importlinter` contract (`layers` list ends `… core, security, domain`). A pure Unicode classifier has zero outward dependencies, so it belongs there and can be imported by every layer above without a single new contract exception.

**Consequence:** the domain engine may import *nothing* from `core`, `application`, or `infrastructure` — only `unicodedata`, `dataclasses`, `re`. This is a feature: it forces the engine to be a total function and makes it exhaustively unit-testable with no fixtures.

### ADR-2 — Ports in `core/ports/`, adapters in `infrastructure/`

Outward-facing capabilities (image format scrubbing, statistical rewriting, optional pixel backends) get `Protocol` ports in `core/ports/watermark_port.py`, implemented in `infrastructure/watermark/`. Matches `code_executor.py` → `infrastructure/execution/` exactly.

### ADR-3 — Bytes in, bytes out; no filesystem in the domain or ports

Reasoner's images are in-memory data URLs. Path handling is an adapter/CLI concern. This also sidesteps the reference repo's entire class of symlink/atomic-write hazards — Reasoner never writes the artifacts to disk on this path.

### ADR-4 — Layer B is a **phase**, not a post-processing hook

Registering `egress_rewrite` as an optional terminal phase in the flow registry gets SSE events, retry/backoff, token budgets, cost metering, circuit-breaking, and `--resume` state persistence for free. A bolt-on hook gets none of them and bypasses metering — a billing hole.

### ADR-5 — Non-origin rewrite = cross-bloc reuse

The reference repo's "prefer a non-origin model" rule and Reasoner's existing cross-bloc diversity invariant are the same constraint. `NonOriginModelSelector` reuses `bloc_of()`: pick a **peer-tier** model whose bloc **and** vendor differ from the synthesis model. Peer-tier (not cheapest) is what answers the README's quality-collapse objection — the rewrite is not allowed to be a downgrade.

### ADR-6 — Protected spans

Reasoner output contains URLs, citations, evidence bundles, code fences, and technical identifiers. NFKC and confusable normalization must **never** run inside them. The reference repo applies NFKC globally and has no such concept; this is an addition, not a port. Layer A carrier stripping still runs everywhere (invisible characters inside a URL are a carrier by definition, and inside a code fence they are a bug).

### ADR-7 — Inspect and clean share one decision function

Non-negotiable. Enforced by a property test (§8.3): for all inputs, `inspect(t).suspicious_total == clean(t).stats.total_changed`.

### ADR-8 — Pixel-domain removal: port + Noop, no implementation

CtrlRegen needs ~10 GB of weights and a GPU. That does not belong in Reasoner's runtime or its container image. Ship `PixelScrubberPort` with `NoopPixelScrubber` as the bound default and an HTTP adapter stub for an external service. Capability reporting tells the UI to hide the option. Honest and cheap.

### ADR-9 — Zero new `.importlinter` exceptions

Current gate: 58 exceptions, MAX 65, pinned `grimp` 3.14. The design above is contract-clean by construction. **Any PR in this plan that needs a new exception has a design bug — fix the design, not the contract.**

### ADR-10 — Report, never mutate silently

Every operation returns a report value object alongside the transformed content. Reports flow into `PipelineState.meta` and out through SSE, so the user can always see what was changed.

---

# Part IV — Module map and paradigm per module

The paradigm is chosen per module from what the module actually is, not applied uniformly.

| Module | Layer | Paradigm | Patterns | Rationale |
|--------|-------|----------|----------|-----------|
| `domain/watermark/marks.py` | domain | **Pure functional / algebraic data types** | Value Object, frozen dataclass | Carrier taxonomy is data. Immutable, hashable, comparable, no behavior. |
| `domain/watermark/rules.py` | domain | **Declarative rule set** | **Specification**, Composite | Preservation rules are composable predicates over a context. Replaces the 68-line if-ladder; each rule independently testable and extensible without touching the classifier. |
| `domain/watermark/layer_a.py` | domain | **Pure functional** | Strategy (via rule tuple), Interpreter | Total function `str → Report`/`str → (str, Stats)`. No I/O, no async, no state. |
| `domain/watermark/spans.py` | domain | **Pure functional** | Value Object | Protected-span detection (code fences, URLs, identifiers) as an immutable interval set. |
| `domain/watermark/stylometry.py` | domain | **Pure functional / statistical** | Value Object | Deterministic scoring; no dependencies beyond `re`/`math`. |
| `domain/watermark/report.py` | domain | **Data-oriented** | Value Object, Builder | Frozen report aggregate with `to_dict()` for SSE. |
| `core/ports/watermark_port.py` | core | **Interface-oriented** | **Hexagonal Port** (`Protocol`, `runtime_checkable`) | Mirrors `code_executor.py`. Structural typing → adapters need no inheritance. |
| `infrastructure/watermark/image/*.py` | infra | **Pure functions + thin adapter** | **Strategy per format** + **Registry** + Abstract Factory | Each format is an independent `bytes → ScrubOutcome`; dispatch by magic bytes. Adding HEIC touches one file and one registry line. |
| `infrastructure/watermark/pixel/noop.py` | infra | Object-oriented | **Null Object** | Exact `NoopExecutor` precedent: fail-closed, never silently simulate. |
| `infrastructure/watermark/rewriter.py` | infra | **Async OO + functional core** | **Strategy** (prompt), **Template Method** (shared contract), pure scorer | I/O shell around a pure selection function. |
| `application/services/watermark_service.py` | app | **Async orchestration** | **Facade**, **Chain of Responsibility** (inspect→clean→verify), Policy | One entry point; stages composable and individually skippable. |
| `application/services/egress_policy.py` | app | **Declarative policy** | **Strategy**, Specification | What gets scrubbed at which surface, resolved from settings + preset + request. |
| `application/flows/egress_rewrite_phase.py` | app | Async coroutine (existing flow convention) | Template Method (phase contract) | Matches every other `*_phase.py`. |
| `api/routes/provenance.py` | api | Declarative FastAPI | **DTO / Adapter**, Dependency Injection | Thin; no logic. |
| `ui-next/.../provenance/*` | ui | Declarative React + hooks | Presentational/Container, Zustand slice | Matches existing UI conventions. |

---

# Part V — Module specifications

## 5.1 `domain/watermark/` — the pure core

```
src/reasoner/domain/watermark/
├── __init__.py          # public surface: inspect_text, scrub_text, score_stylometry
├── marks.py             # carrier tables + MarkKind enum          (~220 LOC)
├── rules.py             # PreservationRule specifications          (~180 LOC)
├── spans.py             # protected-span detection                 (~120 LOC)
├── layer_a.py           # classifier + inspect/scrub               (~200 LOC)
├── stylometry.py        # zero-LLM AI-cadence scorer               (~230 LOC)
└── report.py            # frozen report value objects              (~150 LOC)
```

### `marks.py` — carrier taxonomy as data

Port the reference tables verbatim (they are the researched artifact), as `frozenset[int]` / `Mapping[int, str]` module constants. Add `MarkKind(StrEnum)`: `ZWJ_FAMILY, BIDI, TAG_CHARS, VARIATION_SELECTOR, PRIVATE_USE, SPACE_HOMOGLYPH, CONFUSABLE, OTHER_CF`. Add `MarkConfidence(StrEnum)`: `CONFIRMED, PROBABLE, INFORMATIONAL, LIKELY_FALSE_POSITIVE`.

### `rules.py` — Specification pattern (the key refactor)

```python
@dataclass(frozen=True, slots=True)
class CharContext:
    """Everything a preservation rule may look at. Immutable, index-free."""
    cp: int
    prev_kept: int | None      # last char that survived and is not glue
    prev_input: int | None
    next_input: int | None
    in_flag_sequence: bool     # from ScanIndex
    in_bidi_embedding: bool    # from ScanIndex

@runtime_checkable
class PreservationRule(Protocol):
    name: str
    def preserves(self, ctx: CharContext) -> bool: ...

# Each rule is a small frozen dataclass with one method:
#   EmojiGlueRule, ScriptJoinerRule, FlagTagRule, SameScriptFillerRule,
#   BidiDirectionalRule, OrthographicCfRule
PRESERVATION_RULES: tuple[PreservationRule, ...] = (...)
```

`ScrubOptions(frozen=True)`: `normalize_spaces=True`, `aggressive_confusables=False`, `strip_emoji_glue=False`, `strip_bidi=False`, `nfkc=False`. Each flag *disables* specific rules; the classifier receives a pre-filtered `active_rules` tuple, so it never re-checks flags per character.

**Result:** the classifier collapses from 68 lines to ~15:

```python
def classify(ctx: CharContext, rules: tuple[PreservationRule, ...],
             opts: ScrubOptions) -> Decision:
    if any(rule.preserves(ctx) for rule in rules):
        return Decision.keep(ctx.cp)
    if is_carrier(ctx.cp):
        return Decision.strip(ctx.cp, kind_of(ctx.cp))
    if opts.normalize_spaces and ctx.cp in SPACE_HOMOGLYPHS:
        return Decision.replace(SPACE_HOMOGLYPHS[ctx.cp], MarkKind.SPACE_HOMOGLYPH)
    if opts.aggressive_confusables and ctx.cp in LATIN_CONFUSABLES:
        return Decision.replace(LATIN_CONFUSABLES[ctx.cp], MarkKind.CONFUSABLE)
    if unicodedata.category(chr(ctx.cp)) == "Cf":
        return Decision.strip(ctx.cp, MarkKind.OTHER_CF)
    return Decision.keep(ctx.cp)
```

Every rule is independently unit-testable. Adding a script exemption is a new 8-line dataclass plus one tuple entry — no change to `classify`.

### `spans.py` — protected spans (ADR-6)

`ProtectedSpans(intervals: tuple[tuple[int,int], ...])` with `.covers(index) -> bool`, built by `detect_protected_spans(text)`: fenced code blocks (``` and ~~~), inline code, URLs (`https?://…`), and markdown link targets. Only **normalizing** decisions (confusable, NFKC) consult it; carrier stripping ignores it by design.

### `layer_a.py` — the two entry points

```python
def inspect_text(text: str, opts: ScrubOptions = DEFAULT) -> TextInspectReport: ...
def scrub_text(text: str, opts: ScrubOptions = DEFAULT) -> ScrubResult: ...
```

Both build one `ScanIndex` (the two O(n) pre-passes) and one `ProtectedSpans`, then drive `classify()` over the same iterator. `ScrubResult(text: str, report: TextInspectReport, stats: ScrubStats)`.

Guarantees, asserted by property tests:
- **Idempotent** — `scrub(scrub(t).text).stats.total_changed == 0`
- **Inspect predicts clean** — `inspect(t).suspicious_total == scrub(t).stats.total_changed`
- **ASCII-preserving** — text of only `[\x20-\x7E\n\t]` is returned byte-identical
- **Never lengthens** — `len(out) <= len(in)` (replacements are 1:1, strips are 1:0)

### `stylometry.py`

Direct port of the composite scorer, thresholds unchanged. Exposed as a **quality metric**, not a removal tool (§5.4).

## 5.2 `core/ports/watermark_port.py`

```python
@dataclass(frozen=True, slots=True)
class ScrubOutcome:
    data: bytes
    actions: tuple[str, ...]
    findings: tuple[MarkFinding, ...]
    residual: bool               # re-inspection found survivors
    degraded: bool = False       # a required tool was missing — mirrors TranslationResult
    degraded_reason: str = ""

@runtime_checkable
class ImageMarkScrubberPort(Protocol):
    def supports(self, data: bytes) -> bool: ...
    def inspect(self, data: bytes) -> ImageInspectReport: ...
    def scrub(self, data: bytes, *, strip_all_metadata: bool = True) -> ScrubOutcome: ...

@runtime_checkable
class StatisticalRewriterPort(Protocol):
    async def rewrite(self, text: str, *, strategy: RewriteStrategy,
                      candidates: int = 1) -> RewriteOutcome: ...

@runtime_checkable
class PixelScrubberPort(Protocol):
    async def available(self) -> bool: ...
    async def scrub(self, data: bytes, *, strength: float = 0.25) -> ScrubOutcome: ...
```

`degraded` / `degraded_reason` copy the `TranslationPort` convention deliberately (`core/ports/translation_port.py:14-18`) — the identity fallback must be distinguishable from real work. That is exactly the PDF/exiftool trap from §1.5.

## 5.3 `infrastructure/watermark/image/` — Strategy + Registry

```
infrastructure/watermark/
├── image/
│   ├── detect.py       # magic-byte format detection      (~60 LOC)
│   ├── png.py          # chunk walk/filter/rebuild        (~130 LOC)
│   ├── jpeg.py         # marker walk, APP11 + COM drop    (~150 LOC)
│   ├── webp.py         # RIFF chunks + VP8X flag fixup    (~120 LOC)
│   ├── isobmff.py      # AVIF/HEIC recursive box walk     (~160 LOC)
│   ├── markers.py      # C2PA_MARKERS + AI_META_HINTS     (~40 LOC)
│   └── registry.py     # format → strategy dispatch       (~50 LOC)
├── pixel/
│   ├── noop.py         # Null Object (bound default)      (~30 LOC)
│   └── http_backend.py # external-service adapter stub    (~90 LOC)
├── rewriter.py         # StatisticalRewriterPort impl     (~220 LOC)
└── scrubber.py         # ImageMarkScrubberPort facade     (~110 LOC)
```

Each format module exposes two pure functions — `inspect(data) -> ImageInspectReport` and `strip(data, *, strip_all_metadata) -> tuple[bytes, tuple[str, ...]]`. No classes, no I/O, no shared state. `registry.py` holds `dict[ImageFormat, FormatStrategy]`; `scrubber.py` is the single class implementing the port, doing detect → strip → **re-inspect** → assemble `ScrubOutcome`.

**Do not skip the WebP VP8X flag fixup** (§1.5) — dropping `EXIF`/`XMP `/`ICCP` chunks without clearing their bits in the VP8X header yields a file that declares metadata it no longer contains.

**`data_url.py` codec** at the adapter boundary: `parse_data_url(str) -> tuple[str, bytes]` / `to_data_url(mime, bytes) -> str`. The domain and ports never see base64.

## 5.4 `application/services/watermark_service.py` — Facade + Chain

```python
class WatermarkService:
    def __init__(self, image_scrubber: ImageMarkScrubberPort,
                 rewriter: StatisticalRewriterPort,
                 pixel: PixelScrubberPort) -> None: ...

    def inspect_text(self, text: str) -> TextInspectReport          # sync, pure delegate
    def scrub_text(self, text: str, policy: EgressPolicy) -> ScrubResult
    def scrub_image(self, data_url: str, policy: EgressPolicy) -> ImageScrubResult
    async def rewrite_text(self, text: str, *, strategy, model_hint) -> RewriteOutcome
    def capabilities(self) -> CapabilityReport
```

`capabilities()` mirrors the reference `/capabilities`: which image formats are supported, whether a pixel backend is bound (`not isinstance(pixel, NoopPixelScrubber)`), whether Layer B is enabled. **The UI drives affordances from this** — never offer what is not bound.

`egress_policy.py` resolves, in precedence order: request flag → preset config → `settings` default. Yields a frozen `EgressPolicy(layer_a: bool, layer_a_options: ScrubOptions, image_metadata: bool, layer_b: LayerBPolicy)`.

## 5.5 Layer B — `infrastructure/watermark/rewriter.py` + `flows/egress_rewrite_phase.py`

This is where the README's disclaimer (§1.3) becomes design.

**Model selection — `NonOriginModelSelector`:**

```python
def select_rewrite_model(synthesis_model: str, tier: str) -> str:
    """Peer-tier, cross-bloc, cross-vendor. Never a downgrade."""
    origin_bloc = bloc_of(synthesis_model)          # infrastructure/llm/registry.py
    # candidates: same price/capability tier, bloc != origin_bloc, vendor != origin vendor
```

Rewriting premium synthesis with a budget model is forbidden by construction. If no peer-tier cross-bloc candidate exists, the phase **skips and reports why** rather than silently downgrading.

**Strategies** (Strategy + Template Method): `PARAPHRASE` (default), `HUMANIZE`, `BACKTRANSLATE`, `STRUCTURAL`. Prompts ported verbatim — they are the researched artifact. Shared template contract: *preserve all facts, numbers, names, technical identifiers; do not add or remove claims; output only the rewritten text.*

**Candidate selection** — pure function in `domain/watermark/divergence.py`:

```python
def select_most_diverged(original: str, candidates: Sequence[str]) -> Selection:
    """Bigram Jaccard distance, −0.15 penalty for >2× or <0.5× length drift."""
```

**Post-conditions enforced by the phase, not the model** (the reference repo does not do this and it is where Reasoner can be materially better):

1. **Citation integrity** — every URL present before the rewrite must be present after. `synthesis_phase.py:85-91` already has this check; reuse it. Any dropped citation → **reject the rewrite, keep the original**, report the rejection.
2. **Number/identifier preservation** — extract `\b\d[\d.,]*\b` and backtick-quoted identifiers before and after; mismatch → reject.
3. **Length drift guard** — outside [0.6×, 1.6×] → reject.
4. **Evidence label integrity** — `VERIFIED`/`HYPOTHESIS`/`UNKNOWN` labels and `evidence` bundles are **never** rewritten. Layer B touches prose only.
5. **Layer A after** — always re-scrub the rewrite output (a non-origin model can introduce its own carriers).

**Phase registration** — `egress_rewrite`, optional terminal phase after `synthesis`, gated by `EgressPolicy.layer_b`. Emits its own SSE event with `{strategy, model, divergence_score, rejected_reason?, before_len, after_len}` so the replacement is **visible**, never silent.

**Cost** — the phase runs through `services.call_llm`, so `run_metering.metered()`, `CreditSink`, `spend_limit_service`, and the circuit breaker all apply automatically. **`estimate_service.estimate_cost()` must include it when the policy enables it** — otherwise users get surprise-billed. This is a required change, not optional.

## 5.6 API — `api/routes/provenance.py`

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/provenance/capabilities` | Which formats/backends are bound. Drives UI affordances. |
| `POST` | `/api/provenance/inspect` | `{content?: str, image?: dataURL}` → report. Read-only, no mutation. |
| `POST` | `/api/provenance/scrub` | Layer A + image metadata. Deterministic, cheap. |
| `POST` | `/api/provenance/rewrite` | Layer B. **Auth + CSRF + credits + audit required.** |

Follows the existing route conventions exactly: `Depends(require_csrf)`, `Depends(check_rate_limit)`, `Depends(check_quota_if_authenticated)`, `Depends(require_auth_if_legacy_disabled)`. Registered in `api/__init__.py` alongside `images_router`.

**Next.js proxy routes required** (per the per-constant rule): `ui-next/src/app/api/provenance/{capabilities,inspect,scrub,rewrite}/route.ts`. Missing one 404s silently.

## 5.7 Frontend — `ui-next/src/components/provenance/`

| Component | Role |
|-----------|------|
| `ProvenanceBadge.tsx` | Inline chip on results: "3 invisible characters removed" → opens detail |
| `ProvenanceReport.tsx` | Findings table: kind, count, confidence tier, sample offsets |
| `EgressSettings.tsx` | Per-run toggles; **Layer B rendered disabled with its cost + quality warning until explicitly enabled** |
| `RewriteDiff.tsx` | Before/after with divergence score, shown only when Layer B ran |

State: a `provenance` slice in `stores/app-store.ts`. Capabilities fetched once via SWR and cached; **every affordance is gated on it.**

**Copy discipline (enforced in review):** never "undetectable", never "proves human-written", never "bypasses AI detection". Use "removed N invisible characters", "stripped C2PA metadata", "best-effort statistical rewrite — cannot certify removal".

---

# Part VI — Integration points

Concrete, file-by-file.

| # | File | Change |
|---|------|--------|
| 1 | `core/sanitization.py:202` | `clean_llm_artifacts` → thin deprecated delegate to `domain.watermark.scrub_text(...).text`. Keeps the shim (`reasoner/sanitization.py`) and every existing caller working; behavior strictly improves. |
| 2 | `application/pipeline.py:68` | Drop the unused `clean_llm_artifacts` import. |
| 3 | `flows/synthesis_phase.py:82` | Replace with `WatermarkService.scrub_text`; store the report in `state.meta`. |
| 4 | `flows/synthesis_phase.py:149` | Scrub `critical_insights`, `action_blueprint`, `open_questions` too — not just `core_solution`. |
| 5 | `flows/writing_phases.py`, `flows/article_phases.py` | Same egress scrub on article/writing output. |
| 6 | `api/streaming.py` | Idempotent Layer A safety net on direct answers and follow-ups (safe: Layer A is idempotent by construction). |
| 7 | `flows/factory.py` + flow registry | Register the optional `egress_rewrite` terminal phase. |
| 8 | `api/routes/images.py:187` | Scrub generated-image metadata before returning, when policy allows (default **off** — see §10.3). |
| 9 | `api/routes/uploads.py:81` | Inspect uploaded images; scrub metadata by default (**privacy: EXIF GPS**). Inspect uploaded text for carriers and surface findings. |
| 10 | `core/sanitization.py:182` (`sanitize_for_prompt`) | Add carrier **inspection + stripping** on ingress. Tag characters in a prompt are an injection vector, not a curiosity. Report counts in warnings. |
| 11 | `domain/pipeline_state.py` (`PipelineMeta`) | Add `provenance_report: dict[str, Any] = field(default_factory=dict)`. **Dict, accessed via `.get()`** — per the project invariant this keeps `--resume` working with older state files. |
| 12 | `application/services/serializers.py` | Serialize the provenance report into the SSE payload. |
| 13 | `core/settings.py` | Add the `WATERMARK_*` block (§9). |
| 14 | `application/services/estimate_service.py` | Include Layer B in the estimate when policy enables it. |
| 15 | `api/__init__.py` | Mount `provenance_router`. |
| 16 | `.env.example` | Document the new settings. |

---

# Part VII — Phased rollout

Each phase is independently shippable, independently valuable, and independently revertible.

### Phase 1 — Domain core (no behavior change) · ~2 days
Build `domain/watermark/{marks,rules,spans,layer_a,report}.py` + full unit and property tests. Nothing wired. **Exit:** ≥95% coverage on the domain package; all four invariants (§5.1) hold under Hypothesis.

### Phase 2 — Replace the buggy Layer A · ~1 day
Rewire `clean_llm_artifacts` as a delegate; drop the dead import; extend scrubbing to all `FinalSolution` prose fields; land the report in `PipelineMeta`. **Exit:** existing suite green; new regression tests prove emoji ZWJ / Persian ZWNJ / RTL isolates survive and tag characters do not. This phase alone fixes a live multilingual-corruption bug and closes the invisible-instruction channel.

### Phase 3 — Ports + image metadata scrubbing · ~3 days
`core/ports/watermark_port.py`; `infrastructure/watermark/image/*`; `data_url.py`; wire into uploads (default on) and generated images (default off). **Exit:** round-trip tests on real PNG/JPEG/WebP/AVIF fixtures — cleaned images still decode, re-inspection is clean, WebP VP8X flags are consistent.

### Phase 4 — Service, API, capabilities · ~2 days
`WatermarkService`, `egress_policy.py`, `api/routes/provenance.py`, Next.js proxy routes, settings. **Exit:** `GET /api/provenance/capabilities` accurate; inspect/scrub endpoints pass integration tests with auth/CSRF/rate-limit.

### Phase 5 — Frontend · ~2 days
Badge, report drawer, settings panel; capability-gated. **Exit:** Playwright coverage; copy reviewed against the discipline rules in §5.7.

### Phase 6 — Layer B (opt-in, feature-flagged) · ~4 days
`NonOriginModelSelector`, strategies, divergence scorer, `egress_rewrite` phase, post-condition guards, estimate integration, audit logging, `RewriteDiff` UI. **Exit:** rewrite never ships when a post-condition fails; cost appears in the pre-run estimate; every invocation lands in the audit log. Ships behind `WATERMARK_LAYER_B_ENABLED=false`.

### Phase 7 (optional, deferred) — Stylometry as a quality metric · ~1 day
Surface the score as a **writing-quality signal** in the writing/article methods ("your draft reads formulaically: CV 0.22, 6 AI-cadence phrases"), not as a removal tool. This is the honest, defensible use of that scorer and arguably worth more to Reasoner than the removal use.

### Explicitly **not** planned
Pixel-domain removal (port + Noop only, ADR-8) · PDF/DOCX/ODT container cleaning (Reasoner does not emit them) · audio/video · MarkLLM/MarkDiffusion harnesses · directory/website audits.

---

# Part VIII — Testing

Project standard: 80% minimum, TDD (RED → GREEN → REFACTOR).

### 8.1 Unit — `tests/unit/test_watermark_layer_a.py`
One test per carrier class; one test **per preservation rule** (the Specification refactor makes this natural); the false-positive corpus that the reference repo's issue history produced — emoji ZWJ families, ❤️‍🔥, keycaps, subdivision flags 🏴󠁧󠁢󠁳󠁣󠁴󠁿, Persian می‌روم, Devanagari क्‍ष, Mongolian FVS, Khmer inherent vowels, Hangul partial syllables, Arabic U+0600-family, mixed RTL/LTR paragraphs.

### 8.2 Unit — `tests/unit/test_watermark_image.py`
Per format: real fixture in, decodes out, re-inspect clean. WebP VP8X flag consistency. JPEG entropy-coded scan byte-identical. Malformed/truncated inputs raise rather than emit corrupt bytes.

### 8.3 Property — `tests/unit/test_watermark_properties.py` (Hypothesis)
```
idempotence:        scrub(scrub(t).text).stats.total_changed == 0
inspect_predicts:   inspect(t).suspicious_total == scrub(t).stats.total_changed
ascii_identity:     t ∈ [\x20-\x7E\n\t]*  ⟹  scrub(t).text == t
never_lengthens:    len(scrub(t).text) <= len(t)
span_protection:    code fences and URLs are byte-identical under default options
```

### 8.4 Regression — `tests/unit/test_sanitization_regression.py`
Pin the exact corruption cases the old implementation caused (§2.1) so they can never return.

### 8.5 Integration — `tests/integration/test_provenance_api.py`
Endpoints under auth/CSRF/rate-limit; capabilities accuracy; 402 on insufficient credits for `/rewrite`.

### 8.6 Layer B — `tests/unit/test_layer_b_guards.py`
Every post-condition rejects with a mocked rewriter: dropped citation, mutated number, length drift, altered evidence label, and "no peer-tier cross-bloc candidate → skip, don't downgrade."

### 8.7 Architecture — extend `tests/architecture/`
Assert `domain.watermark` imports nothing outside `domain` + stdlib. Assert `.importlinter` exception count is unchanged (ADR-9).

---

# Part IX — Configuration

```python
# core/settings.py — new block
WATERMARK_EGRESS_LAYER_A: bool = env("WATERMARK_EGRESS_LAYER_A", "true")
WATERMARK_INGRESS_INSPECT: bool = env("WATERMARK_INGRESS_INSPECT", "true")
WATERMARK_AGGRESSIVE_CONFUSABLES: bool = env("WATERMARK_AGGRESSIVE_CONFUSABLES", "false")
WATERMARK_NFKC: bool = env("WATERMARK_NFKC", "false")
WATERMARK_IMAGE_STRIP_UPLOADS: bool = env("WATERMARK_IMAGE_STRIP_UPLOADS", "true")
WATERMARK_IMAGE_STRIP_GENERATED: bool = env("WATERMARK_IMAGE_STRIP_GENERATED", "false")
WATERMARK_LAYER_B_ENABLED: bool = env("WATERMARK_LAYER_B_ENABLED", "false")
WATERMARK_LAYER_B_DEFAULT_STRATEGY: str = env("WATERMARK_LAYER_B_DEFAULT_STRATEGY", "paraphrase")
WATERMARK_LAYER_B_CANDIDATES: int = env_int("WATERMARK_LAYER_B_CANDIDATES", "1")
WATERMARK_PIXEL_BACKEND_URL: str | None = env("WATERMARK_PIXEL_BACKEND_URL")  # unset → Noop
```

Defaults chosen so that a deployment that changes nothing gets: the multilingual bug fixed, the injection channel closed, upload EXIF privacy — and no new legal surface.

---

# Part X — Scope boundaries, risks, and posture

## 10.1 Honest capability statement (must appear in UI and API docs)

| Class | Reasoner coverage | Verifiable? |
|-------|-------------------|-------------|
| Edit-based Unicode | **Full** — carriers + preservation rules | **Yes** — counts + re-inspect |
| File metadata (PNG/JPEG/WebP/AVIF/HEIC) | **Full** for these formats | **Yes** — re-inspect |
| Statistical token-sampling | Best-effort rewrite, opt-in | **No** |
| Pixel-domain (SynthID-media, Tree-Ring…) | **Out of scope** — port + Noop | n/a |
| C2PA **soft binding** | **Out of scope** — survives metadata strip by design | n/a |
| Audio / video | Out of scope | n/a |
| Training backdoors | Out of scope | n/a |

Stripping hard-bound C2PA does **not** clear soft binding or pixel marks. Say so in the report, every time.

## 10.2 Technical risks

| Risk | Mitigation |
|------|-----------|
| Over-stripping corrupts multilingual output | Specification-pattern rules + the false-positive corpus in §8.1; aggressive modes default-off |
| Image scrubber emits undecodable files | Round-trip decode assertions per format; WebP VP8X fixup; malformed input raises rather than emits |
| Layer B degrades premium output | Peer-tier cross-bloc selection (ADR-5) + five post-condition guards + user-visible diff |
| Layer B billing surprise | Phase-level metering + estimate integration (Integration point 14) |
| Silent no-op mistaken for success | `degraded`/`degraded_reason` on every outcome (the PDF/exiftool lesson, §1.5) |
| Scope creep into PDF/DOCX | Explicitly out of scope; Reasoner does not emit those containers |
| Contract drift | ADR-9 + the architecture test in §8.7 |

## 10.3 Legal and ethical posture — a real decision, stated plainly

This is ordinary, legitimate engineering: Layer A hygiene fixes a bug and closes an injection channel; EXIF stripping is a privacy feature; users cleaning their own content is the reference repo's stated purpose and its MIT license permits the port. The plan proceeds on that basis.

Two points deserve an explicit decision from you rather than a default:

**1. Reasoner is a hosted service, not a local CLI.** The reference repo is a tool a user runs on their own machine against their own files. Reasoner would be a *provider* performing removal on behalf of third parties, at scale, for money. EU AI Act Art. 50 and California SB 942 place machine-readable-marking duties on generative-AI providers; a service whose marketed function is removing those marks sits in a materially different posture from a local utility. That does not make the feature unlawful — it makes the framing, defaults, and audit trail matter.

**2. Stripping C2PA from images Reasoner itself just generated** is the sharpest case: Reasoner requests an image from Gemini/OpenAI, the provider attaches provenance, and Reasoner removes it before delivery. That makes Reasoner the party that removed the mark, on content it generated. Hence `WATERMARK_IMAGE_STRIP_GENERATED=false` by default — opt-in, per-run, audit-logged. **Uploaded** images are the opposite case (the user's own file, EXIF GPS is a genuine privacy leak) and default to on.

Design consequences already built into this plan:

- Layer A hygiene + ingress injection defense are **on** — they are defensible on their own merits and need no watermark framing.
- Layer B and generated-image stripping are **off by default, opt-in per run, and written to `audit_service`** with user, timestamp, and content hash.
- Copy discipline (§5.7): never "undetectable", "bypasses detection", or "proves human-written". The reports state what was verifiably removed and what was best-effort — nothing more.
- Recommend a ToS attestation for Layer B ("content you own or are authorized to process"), following the reference repo's responsible-use language.

If you would rather ship the full capability on by default, that is your call — the code paths are identical and only the four settings defaults in §9 change.

---

## Appendix A — Mapping: reference repo → Reasoner

| `watermarks-remover` | Reasoner destination | Change on port |
|---|---|---|
| `text_unicode.py` `_decide()` | `domain/watermark/{rules,layer_a}.py` | if-ladder → Specification pattern |
| `text_unicode.py` tables | `domain/watermark/marks.py` | verbatim |
| `text_unicode.py` reports | `domain/watermark/report.py` | frozen dataclasses |
| `score_stylometry.py` | `domain/watermark/stylometry.py` | verbatim; repositioned as quality metric |
| `rewrite_text.py` prompts | `infrastructure/watermark/rewriter.py` | verbatim |
| `rewrite_text.py` divergence | `domain/watermark/divergence.py` | pure function, moved to domain |
| `rewrite_text.py` backends | — | dropped; use `ProviderRouter` |
| `rewrite_text.py` model hygiene | `NonOriginModelSelector` | reuse `bloc_of()`, add peer-tier constraint |
| `image_meta.py` strip_* | `infrastructure/watermark/image/*.py` | path→bytes; one module per format |
| `format_dispatch.py` | `infrastructure/watermark/image/detect.py` | image only |
| `container_meta.py` | — | out of scope |
| `server.py` HTTP API | `api/routes/provenance.py` | FastAPI + existing auth/CSRF/quota |
| `/capabilities` | `WatermarkService.capabilities()` | same idea |
| `common.py` safe writes | — | not needed; bytes never hit disk |
| `common.py` binary guard | `infrastructure/watermark/image/detect.py` | magic bytes only |
| `clean_ctrlregen.py`, `markdiffusion_harness.py`, `score_synthid.py` | `PixelScrubberPort` + `NoopPixelScrubber` | port only, no implementation |
| `audit_dir.py`, `audit_website.py` | — | out of scope |

## Appendix B — New-file manifest

**Backend (16 new files)**
```
src/reasoner/domain/watermark/{__init__,marks,rules,spans,layer_a,stylometry,divergence,report}.py
src/reasoner/core/ports/watermark_port.py
src/reasoner/infrastructure/watermark/{__init__,scrubber,rewriter,data_url}.py
src/reasoner/infrastructure/watermark/image/{__init__,detect,markers,png,jpeg,webp,isobmff,registry}.py
src/reasoner/infrastructure/watermark/pixel/{__init__,noop,http_backend}.py
src/reasoner/application/services/{watermark_service,egress_policy}.py
src/reasoner/application/flows/egress_rewrite_phase.py
src/reasoner/api/routes/provenance.py
```

**Frontend (8 new files)**
```
ui-next/src/components/provenance/{ProvenanceBadge,ProvenanceReport,EgressSettings,RewriteDiff}.tsx
ui-next/src/app/api/provenance/{capabilities,inspect,scrub,rewrite}/route.ts
```

**Tests (7 new files)**
```
tests/unit/{test_watermark_layer_a,test_watermark_rules,test_watermark_image,
            test_watermark_properties,test_sanitization_regression,test_layer_b_guards}.py
tests/integration/test_provenance_api.py
```

**Modified:** 16 files (Part VI) · **New `.importlinter` exceptions:** 0 (ADR-9)
