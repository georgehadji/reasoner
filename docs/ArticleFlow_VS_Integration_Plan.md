# Integration Plan: Verbalized Sampling (VS) in ArticleFlow

## Objective

Integrate Verbalized Sampling (VS) into ArticleFlow so that exploratory
stages operate on distributions of plausible solutions while
verification stages remain deterministic.

Design principle:

-   Exploration → maximize diversity.
-   Convergence → maximize correctness.
-   Verification → maximize determinism.

This follows the findings of the Verbalized Sampling paper that
distribution-level prompting is most beneficial when multiple valid
outputs exist, while factual verification should remain conservative.

------------------------------------------------------------------------

# Architectural Principle

Split the pipeline into two regimes.

## Exploration

-   Phase -1 Preflight
-   Phase 0 Augmentation
-   Phase 1 Retrieval Planning
-   Phase 2 Argument Map
-   NEW Phase 2.5 Concept Exploration

VS is enabled.

## Convergence

-   Phase 3 Draft
-   Phase 4 Fact Check
-   Phase 4.5 Structural Review
-   Phase 5 Development Edit
-   Phase 6 Style + Copy Edit
-   Phase 7 Audit
-   Phase 8 Synthesis

VS is disabled except for optional controlled experiments.

------------------------------------------------------------------------

# Phase-by-phase Plan

## Phase -1 Preflight

No VS.

Add a classifier:

exploration_required = True/False

Outputs:

-   exploration_budget
-   candidate_count
-   probability_threshold

------------------------------------------------------------------------

## Phase 0 Augmentation

Replace single debate generation with VS.

Each augmentation agent produces:

-   multiple alternatives
-   estimated relative probabilities
-   novelty notes

Merge outputs into a unified augmentation summary.

------------------------------------------------------------------------

## Phase 1 Retrieval Planning

Instead of generating only 3--5 queries:

Generate 12--20 candidate queries.

Cluster.

Remove duplicates.

Select representative queries using

-   diversity
-   expected evidence coverage
-   probability ranking.

Only representative queries are executed.

------------------------------------------------------------------------

## Phase 2 Argument Mapping

Generate 5--8 complete argument maps.

Each contains

-   thesis
-   antithesis
-   synthesis
-   key claims
-   evidence mapping
-   counterarguments

Cluster similar maps.

Construct a fused outline.

This becomes the canonical outline.

------------------------------------------------------------------------

## Phase 2.5 (NEW)

Latent Concept Exploration

Generate distributions for

-   titles
-   narrative strategies
-   framing
-   analogies
-   reader personas
-   section ordering

Cluster.

Rank.

Inject only selected concepts into drafting.

------------------------------------------------------------------------

## Phase 3 Draft

Default production mode:

Single draft from locked outline.

Experimental mode:

Generate three drafts from different outline variants.

Use structural comparison.

Merge before fact checking.

------------------------------------------------------------------------

## Phase 4 Fact Checking

No VS.

Deterministic verification only.

------------------------------------------------------------------------

## Phase 4.5 Structural Review

Optional VS.

Generate multiple independent critiques covering

-   logic
-   assumptions
-   evidence
-   flow
-   bias
-   missing literature

Merge critiques into one review.

------------------------------------------------------------------------

## Phase 5 Development Edit

Default:

Single revision.

Experimental:

Generate several revision strategies.

Select one before rewriting.

Avoid merging conflicting revisions.

------------------------------------------------------------------------

## Phase 6

No VS.

------------------------------------------------------------------------

## Phase 7

No VS.

------------------------------------------------------------------------

## Phase 8

Optional:

Generate several executive summaries for different audiences.

Keep one publication version.

------------------------------------------------------------------------

# New Components

## Distribution Manager

Responsibilities

-   clustering
-   duplicate removal
-   representative selection
-   novelty estimation
-   entropy estimation

## Selection Engine

Inputs

-   probability
-   novelty
-   evidence coverage
-   diversity

Outputs

-   selected representatives

------------------------------------------------------------------------

# Configuration

``` yaml
vs:
  enabled: true
  exploration_only: true
  candidate_count: 8
  probability_threshold: 0.10
  clustering: semantic
  merge_strategy: representative
```

------------------------------------------------------------------------

# Rollout

Stage 1

VS only in

-   augmentation
-   retrieval planning
-   argument mapping

Stage 2

Add

-   concept exploration
-   critique generation

Stage 3

A/B test optional draft diversification.

------------------------------------------------------------------------

# Success Metrics

-   Retrieval coverage
-   Outline diversity
-   Evidence coverage
-   Critique completeness
-   Audit pass rate
-   Human quality score
-   Token cost
-   Latency
-   Cost per accepted article

------------------------------------------------------------------------

# Risks

-   Increased token usage
-   Near-duplicate candidates
-   Poor probability calibration
-   Longer latency
-   Over-diversification

Mitigations

-   semantic clustering
-   entropy thresholds
-   representative selection
-   exploration budget
-   deterministic convergence

------------------------------------------------------------------------

# Recommendation

Adopt VS only during exploration. Freeze the search space after the
outline is finalized. Maintain deterministic drafting, verification,
editing, and auditing unless experimental evidence demonstrates
measurable gains from broader deployment.
