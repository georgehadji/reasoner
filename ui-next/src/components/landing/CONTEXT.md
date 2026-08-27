# Context: Landing

## Directory: `ui-next/src/components/landing`

## Description
The public marketing surface: the home page, the `/capabilities` and `/developers` pages split off from it, the chrome they share, and the mechanism visuals they draw on.

## Files
- **`LandingPage.tsx`**: The home page. States the claim once, frames it with the four-stage rail, then shows the product's own output — a real article run (§1), the ideation tiers (§2, anchor `#brainstorming`), the code note (§3), and the agent section (§4, anchor `#agents`), whose exhibit is three real labelled claims lifted out of the captured run by `CLAIM_SPECIMENS` — derived, never transcribed — followed by the three doors and a link to `/docs/mcp`. The rest of the mechanism argument that used to run down this page now lives in `CapabilitiesPage.tsx`.
- **`CapabilitiesPage.tsx`**: The mechanism argument in eight sections (§1 Hallucination through §8 Methods), served at `/capabilities`. Anchors are unchanged from when these ran on the home page, so inbound links still land — but the §n markers are not: Ideation (`#brainstorming`) moved back to the home page and the numbering closed up over it. Link against ids, never against markers. Every claim maps to code; §5 Sycophancy is additionally gated by `SYCOPHANCY_CONTROLS` and guarded by `tests/test_site_capabilities_sync.py`.
- **`DevelopersPage.tsx`**: The programmatic surface in seven sections (§1 MCP, §2 HTTP, §3 Command line, §4 Discovery, §5 Preview, §6 Metering, §7 Keys), served at `/developers`. Argues that MCP, HTTP, and the CLI are three doors onto one pipeline; the instructions themselves live in `lib/docs.ts` (`/docs/mcp`, `/docs/agent-integration`, `/docs/api-reference`) and this page links out to them rather than restating them. Tool names, endpoints, and status codes must be checked against `src/reasoner/api/` before editing.
- **`prose.tsx`**: `Section` / `Heading` / `Lede` / `Body` / `Aside` — the editorial chrome both pages share. It lives apart from either because a divergence between the two would read as two sites rather than one argument split across two URLs.
- **`DisagreementField.tsx`**: `'use client'` canvas behind the hero — four point groups orbit one attractor and never reach it.
- **`MechanismDiagram.tsx`**: The four failure modes as stops on a rail, HTML not SVG so labels keep the page's point scale and reflow on a phone. Each stage links into its section on `/capabilities`.
- **`PipelineRail.tsx`**: `'use client'` canvas over that rail — packets cross the four stages in lanes that never merge.
- **`CollagePlate.tsx`**: Server-rendered SVG, one square plate per failure mode, seeded PRNG at module load so the markup is deterministic and costs no runtime JS.
- **`Testimonial.tsx`**: No entries yet. Renders nothing rather than a placeholder — a landing page with no testimonials reliably outperforms one with an invented or generic one, and a fabricated quote is exactly the class of claim removed from this page.

## Subfolders
*No subfolders in this directory.*
