Drop 3–5 screenshots or URLs here, each with a one-line note saying what you want from
it (proportions, type treatment, density, restraint).

A reference is a constraint. "Premium" is an adjective the model resolves to its median.
Skills read this directory; an empty directory means the design brief is under-specified.

https://www.anthropic.com/
https://www.perplexity.ai/
https://www.blackbox.ai/#build
https://antigravity.google/
https://claude.ai/new


---

## Two rules, specific to this project

**1. Nothing from an AI company.** No Anthropic, OpenAI, Perplexity, Mistral, Cursor,
Linear. The current UI was built with Anthropic's site as its single reference, and
`globals.css` documents the result in its own comments: `--bg: #FAF9F5` is Anthropic
ivory, `--accent: #96401F` is annotated "Anthropic coral" and derived from `#D97757`.
That is a verbatim hit on the second entry of `spec/banlist.md`.

A reference taken from inside your own market does not read as *polished like them*. It
reads as *derivative of them*, because the audience knows the original. From inside the
category you may take patterns and information architecture — never identity.

**2. Reach for adjacent categories with the same underlying problem.** Reasoner displays
contested, multi-source output where every claim carries a VERIFIED / HYPOTHESIS /
UNKNOWN label. Look at fields where showing disagreement and uncertainty *is* the job:

- scientific instrumentation and lab equipment interfaces
- financial and market terminals
- election and forecast graphics (uncertainty bands, not point estimates)
- archival, cartographic and bibliographic work
- court records, citation apparatus, provenance and chain-of-custody documents

Editorial and print sources count. So do physical objects. A reference does not have to
be a website.

## Both surfaces are in scope

This project weights the marketing surface (`/`, `/landing`, `/pricing`, `/capabilities`,
`/developers`, `/how-it-works`, `/docs`) and the application surface (`/chat`,
`/dashboard`, `/settings`) EQUALLY. A reference that only informs a hero is half a
reference. Where possible, note what it implies for dense, long-lived screens too.

## What is already locked and needs no reference

The token architecture survives the redesign unchanged: per-token computed contrast
ratios, borders as alpha of the opposite ground (WCAG 1.4.11), the separate `--sidebar-*`
ramp, the doubled dark block, and the `--ok` / `--warn` / `--unknown` epistemic tokens.
References are wanted for HUE FAMILY, TYPEFACES, DENSITY and SIGNATURE — not for
structure.

---

## What is actually saved here (2026-08-28)

All four are AI companies — the exact thing rule 1 warns against, chosen deliberately by
the user after the warning. That is a valid call, but it changes what these files are for.

Each note is therefore split into **TAKE** and **DO NOT TAKE**. From inside your own
category you may take structure, proportion, density, typographic system and information
design. You may not take hue family, typeface or signature — those are the parts the
audience already recognises as belonging to someone else.

Three of the four are near-black grounds with a single accent, which `spec/banlist.md`
bans outright. Not one of them is a palette source. Read the DO NOT TAKE sections before
proposing any colour.

**Still missing: an out-of-category reference.** Nothing here comes from scientific
instrumentation, financial terminals, forecast graphics, archival or provenance work. The
palette and the signature have to come from somewhere, and right now there is no source
in this directory that is allowed to supply them.
