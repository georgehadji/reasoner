# Converting regulated buyers — research and page plan

**Date:** 2026-11-13 · **Scope:** `ui-next/` marketing and trust pages · **Status:** research, nothing built

Labels: VERIFIED (checked in this repo or a primary source), INFERENCE (reasoned from
sources), HYPOTHESIS (worth testing), UNKNOWN (needs an owner answer).

---

## 1. Bottom line

For these buyers the landing page does not close the sale. A security, legal or procurement
reviewer does, usually before anyone talks to us. Visual polish and messaging matter less
than **whether that reviewer can find what they need on their own**, and whether it is
consistent.

Three things follow:

1. **The trust surface is the conversion surface.** `/security`, `/subprocessors`,
   `/privacy` and a downloadable evidence pack do more for these buyers than the hero does.
   (INFERENCE, from §2.1 and §2.2.)
2. **One false claim ends the review.** `/security` currently makes claims that the
   architecture almost certainly cannot support (§5). Fix them before driving any regulated
   traffic. (VERIFIED that the claims are on the page; UNKNOWN whether any is true.)
3. **Each sector has one gating question.** A sector page that answers it in the first
   screen, or says honestly that we can't yet, beats six briefs on one page. (INFERENCE.)

---

## 2. What the evidence says

Most sources on trust centers are vendors selling trust-center software. Their uplift
figures (e.g. "42% higher win rates", "70–90% shorter review") have no published method and
are **not used here**. The direction is consistent across them; the numbers are not
reliable.

### 2.1 Buyers self-serve before engaging

- NN/g: prospects want to find information themselves, not through a salesperson. Price is
  their first need, including on B2B sites. Don't assume they will contact you for it.
  (VERIFIED, NN/g primary.)
- Regulated reviewers expect a public trust page they can read *before* deciding to engage.
  Static pages with outdated PDFs don't help. (Vendor sources, consistent; INFERENCE.)
- ISO 27001 / SOC 2 often decide eligibility before commercial talks begin, especially in
  EU and APAC procurement portals. (Vendor source; INFERENCE.)

**Implication:** keep pricing public (we do). Put evidence in front of the contact form, not
behind it.

### 2.2 Sector gates

| Sector | The gating question | Source quality |
|---|---|---|
| **Healthcare (UK NHS)** | Does it pass DTAC? NHS England refreshed DTAC (in force 6 April 2026). Five areas: clinical safety, data protection, technical security, interoperability, usability. ISO/IEC 42001 is cited as evidence of responsible AI development. Each buying organisation decides; there is no pass mark. | NHS / law firm; partly primary |
| **Healthcare (US)** | Is there a BAA covering every hop, PHI included? | Already `[INPUT REQUIRED]` on landing |
| **Defence** | Where does it run? A vendor blog reports that DoW Instruction 8430.01 (Sept 2026) bars non-public information from any GenAI service not on department systems. IL4/IL5 workloads are reported to need air-gapped deployment. France awarded a defence GenAI framework to Mistral in Jan 2026. | Mostly vendor blogs; **not** primary-verified |
| **Aerospace / engineering** | Does controlled technical data (ITAR/EAR) touch infrastructure that non-US persons can access? Access control decides compliance, not labels. | Practitioner guides; get counsel before relying on it |
| **Academia** | Will the university's IT security review approve it for confidential or research data? USNH, UChicago and Utah all require a security review or intake form, even for free tools. The user stays responsible for checking output accuracy. | Primary university policies |
| **Legal** | Is confidentiality kept tightly enough that privilege survives? *US v. Heppner* (SDNY, Feb 2026) reportedly found no privilege where the tool disclaimed confidentiality. Hallucinated citations: 60+ UK and 1,000+ global incidents reported. Reviewers ask about training on data, deletion, keys and auditable logs. | Commentary; primary opinions not retrieved |
| **Government / policy (UK)** | Can the supplier fill an ATRS record? PPN 02/24 asks suppliers about AI use. ATRS-scope bodies must publish transparency records, and suppliers have to supply the information. | Secondary; check GOV.UK |
| **EU (all sectors)** | AI Act Art. 50 transparency duties applied from 2 Aug 2026. The Digital Omnibus may move some dates. Buyers can already ask model providers for GPAI documentation. | Law-firm sources |

**The product's natural strength (VERIFIED in repo):** it already *produces* the artefacts
these reviewers ask for: the record of each run, per-claim epistemic labels, routing by lab
and bloc (`western_only`), and a sub-processor list generated from the live registry. In most
of the gates above, "explain how the output was reached" is a named requirement. Few
competitors can show it. That is the wedge.

**The product's gaps against the gates (UNKNOWN unless stated):** no SOC 2 or ISO 27001
(VERIFIED: `/security` says SOC 2 is not yet certified). No SSO (VERIFIED, planned).
Self-hosted / on-prem is offered on `/pricing` as an enterprise item (VERIFIED it is
claimed; UNKNOWN whether it exists). No zero-retention mode (VERIFIED, `/privacy`). No BAA or
DPA chain (UNKNOWN). No DTAC, DCB0129 or ISO 42001 (UNKNOWN; assume none).

---

## 3. Recommended structure

### 3.1 Funnel per buyer role

```
Champion (analyst, researcher, counsel)      Reviewer (security, DPO, procurement)
  landing → sector page → sample run           sector page → /trust → evidence pack
            │                                              │
            └──────────── /contact?topic=pilot ◄───────────┘
```

Two readers, two paths. The page today serves only the champion.

### 3.2 Page plan

| Page | Change | Why |
|---|---|---|
| **`/` landing** | Keep the current structure. Replace the six sector cards with links to sector pages. Add a "For your security review" strip linking `/trust`, `/subprocessors` and the evidence pack. | The reviewer needs a way in from the first screen. (INFERENCE) |
| **New: `/for/healthcare`, `/for/defence`, `/for/research`, `/for/legal`, `/for/engineering`, `/for/public-sector`** | One template. First screen: the gating question from §2.2, answered as **Yes / Not yet / No** with a date or `[INPUT REQUIRED]`. Then: two worked use cases, the methods that fit, a sample run, what not to use it for, and a pilot CTA with the topic prefilled (`/contact?topic=pilot&sector=…`). | Specific answers beat broad claims. "Not yet" is credible; silence reads as "no". (HYPOTHESIS: test against one combined page) |
| **`/security` → `/trust`** | Make it a trust center: controls table with status and evidence link per row; a data-flow diagram (browser → API → OpenRouter → lab, and what each hop retains); retention; incident contact; certifications with honest status. Fix the claims in §5 first. | It's the most-read page for reviewers. (INFERENCE, §2.1) |
| **`/subprocessors`** | Add a column for country / jurisdiction and one for data-training policy. List **OpenRouter as a sub-processor in its own row**: today it appears only in a footnote, and it is the primary route. Mark which ones Western-only excludes. | Reviewers map data flows hop by hop. (VERIFIED that OpenRouter is a footnote) |
| **New: evidence pack** (`/trust/pack`, gated by nothing) | Pre-filled answers to a standard questionnaire (CAIQ-lite or SIG-lite), a sample run export, the architecture diagram, and a DTAC/ATRS crosswalk *once true*. PDF and HTML. | Turns the 3-week questionnaire into a pre-read. (INFERENCE) |
| **`/how-it-works`** | Make the complete sample run the centrepiece, downloadable as the same export a customer gets. Add "How a reviewer reads this record". | The audit record *is* the proof. (INFERENCE) |
| **`/pricing`** | Keep public prices. Add a "Pilot" row: what's included, how long it runs, what you get at the end. Replace "self-hosted deployment" with its real status. | NN/g: show price. Don't promise what doesn't exist. |
| **`/contact`** | Add a sector field (prefilled from the sector page) and an optional "What does your review need?" checklist (DPA, BAA, SOC 2 report, on-prem, data residency). | Qualifies the lead and tells us which gaps are losing deals. (HYPOTHESIS) |
| **Nav** | Add **Trust** and a **Sectors** menu. Drop **Developers** into the footer or under Docs for this audience. | Reviewers look for "Trust" or "Security" in the header. (INFERENCE) |

### 3.3 Visual direction

Keep Overprint for persuasion surfaces (landing, sector heroes). Run trust surfaces in a
quieter **document mode**:

- no misregistered plates, grain off or halved;
- the record's §0–§5 rule system for structure;
- tables over cards, and dates on every status;
- print stylesheet, because reviewers print or PDF these pages for the file.

That's a deliberate shift from persuasion to reading. (Impeccable "Read" mode; INFERENCE.)

---

## 4. Copy rules for these pages

- Every capability claim carries a status (Available / Pilot / Planned / Not offered) and a
  date. Banned: "enterprise-grade", "military-grade", "HIPAA-ready", "secure by design".
- Say what it is **not for** on every sector page (already done for clinical use on landing).
- No accuracy or hallucination-rate numbers until measured (`[INPUT REQUIRED: real results]`).
- Name the jurisdictions. Defence and public-sector readers will check where DeepSeek and
  Qwen sit before reading anything else.

---

## 5. Fix before sending regulated traffic

On `/security` today (VERIFIED, `app/security/page.tsx:102`):

> "We do not train on your data, we encrypt it end to end, and we log every access."

- **"End to end"**: requests are decrypted by our API, OpenRouter and the model lab. That is
  encryption in transit, not end to end. A security reviewer will spot this immediately.
  (INFERENCE from the architecture; UNKNOWN whether there's another meaning.)
- **"We do not train on your data"** / `/privacy` "Your data is never used for training":
  true for us, perhaps. But it depends on each provider's terms and on OpenRouter's settings
  (some routes allow provider training). `[INPUT REQUIRED: per-provider training policy, and is OpenRouter's "no training" setting enforced?]`
- **"Zero-Trust internal network", "Network Isolation", "Every access is logged"**: marked
  done, with no evidence link. `[INPUT REQUIRED: is each true, and what can we show?]`
- **`/pricing` "self-hosted deployment"**: `[INPUT REQUIRED: does a self-hosted build exist?]`

---

## 6. What to measure (no targets until there is a baseline)

- Landing → sector page → `/contact?topic=pilot` path, by sector.
- `/trust` and evidence-pack views per pilot enquiry. The question to answer: do reviewers
  read the page before engaging?
- The checklist answers on `/contact`, counted. This is the ranked list of gaps that are
  losing deals.
- Share of pilots that never sent a security questionnaire.

---

## 7. Owner inputs that unblock the most

1. Corrected answers for the claims in §5.
2. Certifications: SOC 2 / ISO 27001 / ISO 42001, with status and target dates if any.
3. Is on-prem or self-hosted real? Is any EU-only hosting option real?
4. DPA and BAA chain through OpenRouter and each provider.
5. Which two sectors to launch first. The sector template is cheap, but evidence per sector
   is not. Research and legal look closest to what exists today (no certification hard
   gate in the policies found); defence looks furthest (deployment model). (INFERENCE)

---

## Sources

- NN/g, [B2B websites topic](https://www.nngroup.com/topic/b2b-websites/), [Show price](https://www.nngroup.com/articles/show-price/), [B2B trust](https://www.nngroup.com/articles/b2b-trust-from-b2c/)
- Trust centers (vendor sources): [Responsive](https://www.responsive.io/blog/how-trust-center-reduce-cost-security-questionnaires), [Drata](https://drata.com/blog/how-to-build-a-trust-center-that-delivers-growth), [UpGuard](https://www.upguard.com/blog/what-is-sales-enablement), [SafeBase](https://safebase.io/blog/trust-center), [Orbiq](https://www.orbiqhq.com/trust-center/how-to-build-a-trust-center)
- NHS: [DTAC (NHS England)](https://transform.england.nhs.uk/key-tools-and-info/digital-technology-assessment-criteria-dtac), [Burges Salmon on the refresh](https://www.burges-salmon.com/articles/102mnjh/new-nhs-digital-technology-assessment-criteria-what-health-tech-suppliers-need-t), [HTN, Feb 2026](https://htn.co.uk/2026/02/25/digital-technology-assessment-criteria-refreshed-to-create-simpler-more-trusted-pathway-for-nhs-digital-innovation/), [NHS Innovation Service](https://innovation.nhs.uk/innovation-guides/regulation/digital-product-or-service/)
- Defence: [ibl.ai on DoWI 8430.01](https://ibl.ai/blog/dod-dowi-8430-01-software-defined-warfare-sovereign-ai.md), [Mistral framework](https://www.gend.co/blog/mistral-ai-french-defence-framework), [techUK](https://www.techuk.org/insights/guest-insights/the-uk-s-defence-ai-sovereignty-gap-is-assurance), [Coder](https://coder.com/blog/ai-agent-security-sovereignty-defense)
- Export control: [Kiteworks](https://www.kiteworks.com/regulatory-compliance/ai-compliance-manufacturers-requirements), [Visual Compliance](https://www.visualcompliance.com/blog/itar-or-ear-how-aerospace-firms-can-spot-and-fix-their-biggest-compliance-risks/), [Mondaq](https://www.mondaq.com/unitedstates/new-technology/1776516/itar-ai-enabled-defense-technologies-autonomous-systems-targeting-algorithms-and-the-new-export-control-frontier)
- Universities: [USNH](https://td.usnh.edu/TDClient/60/Portal/KB/ArticleDet?ID=5146), [UChicago](https://genai.uchicago.edu/about/generative-ai-guidance), [Utah](https://ai.utah.edu/_resources/documents/uofu-ai-research-guidance.pdf)
- Legal: [TransPerfect on Heppner/Munir](https://www.transperfectlegal.com/blog/ai-privilege-problem-control-not-code-lessons-munir-and-heppne), [Law Society of Ireland vendor tool](https://www.lawsociety.ie/globalassets/documents/practice-essentials/ai-vendor-assessment-tool.pdf), [Access Group](https://www.theaccessgroup.com/en-gb/legal/ai-in-legal/how-uk-law-firms-can-avoid-ai-hallucinations-and-build-ethical-ai-practices/)
- UK public sector: [Freeths on PPN 02/24](https://www.freeths.co.uk/insights-events/legal-articles/2024/ai-and-procurement-a-practical-approach/), [Trowers](https://www.trowers.com/-/media/files/thought-leadership/governance-of-ai-in-the-public-sector.pdf)
- EU AI Act: [Cooley](https://cooley.com/news/insight/2026/2026-08-03-eu-ai-act-transparency-obligations-take-effect-2-august-2026), [Morgan Lewis](https://www.morganlewis.com/blogs/sourcingatmorganlewis/2026/08/eu-ai-acts-transparency-rules-what-went-into-effect-on-2-august), [WSGR](https://www.wsgrdataadvisor.com/2026/08/eu-ai-act-enforcement-phase-begins/), [Houthoff](https://www.houthoff.com/insights/news/ai-act-transparency-obligations-and-the-ai-omnibus-regulation/)
