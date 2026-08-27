# Context: App

## Directory: `ui-next/src/app`

## Description
The visual page views, routes, layouts, and API routes of the Next.js 16 app router.

## Files
- **`error.tsx`**: React error boundary component rendering failure states.
- **`fonts.ts`**: Typography — three variable families, self-hosted by next/font.  Roles are deliberately split. Sans carries UI chrome (nav, buttons,
- **`global-error.tsx`**: Code or resource asset facilitating system functionality.
- **`globals.css`**: Code or resource asset facilitating system functionality.
- **`globals.css.test.ts`**: Code or resource asset facilitating system functionality.
- **`layout.tsx`**: Without metadataBase, relative OpenGraph and canonical URLs resolve against
- **`not-found.tsx`**: The App Router's reserved handler for unmatched routes and for any `notFound()` call. Next.js serves it with a real 404 status, which is what keeps a mistyped URL out of the index in the first place; `noindex` here is
- **`page.tsx`**: React page view component rendering the primary route content.
- **`providers.tsx`**: Register listener BEFORE any async calls so we don't miss the INITIAL_SESSION
- **`robots.ts`**: robots.txt.  AI answer engines are given an explicit allow rule rather than being left to
- **`sitemap.ts`**: XML sitemap, served at /sitemap.xml.  Only public, indexable pages belong here. Authenticated surfaces are

## Subfolders
- **`about`**: Static pages and component layouts describing the Reasoner platform mission.
- **`api`**: Backend-for-frontend (BFF) HTTP endpoints exposing server functionality to client web states.
- **`changelog`**: Exposes routing, templates, or integrations for Changelog within the 'ui-next/src/app' ecosystem.
- **`chat`**: The primary chat application screen supporting live SSE streams of Reasoning steps.
- **`contact`**: Exposes routing, templates, or integrations for Contact within the 'ui-next/src/app' ecosystem.
- **`cookies`**: Exposes routing, templates, or integrations for Cookies within the 'ui-next/src/app' ecosystem.
- **`dashboard`**: User analytical dashboards tracking credits, token limits, history, and active pipelines.
- **`capabilities`**: The nine mechanism sections (§1–§9) that used to run down the home page — re-exports `components/landing/CapabilitiesPage`.
- **`docs`**: Browsers-friendly system documentation renderer and page views.
- **`faq`**: Exposes routing, templates, or integrations for Faq within the 'ui-next/src/app' ecosystem.
- **`forgot-password`**: Exposes routing, templates, or integrations for Forgot-password within the 'ui-next/src/app' ecosystem.
- **`help`**: Exposes routing, templates, or integrations for Help within the 'ui-next/src/app' ecosystem.
- **`developers`**: The programmatic-surface marketing page — re-exports `components/landing/DevelopersPage` and adds the `WebAPI`, `HowTo`, and breadcrumb JSON-LD that let an answer engine quote the MCP setup steps and cite `/docs/mcp`.
- **`how-it-works`**: Exposes routing, templates, or integrations for How-it-works within the 'ui-next/src/app' ecosystem.
- **`landing`**: Exposes routing, templates, or integrations for Landing within the 'ui-next/src/app' ecosystem.
- **`llms-full.txt`**: Exposes routing, templates, or integrations for Llms-full.txt within the 'ui-next/src/app' ecosystem.
- **`llms.txt`**: Exposes routing, templates, or integrations for Llms.txt within the 'ui-next/src/app' ecosystem.
- **`login`**: Exposes routing, templates, or integrations for Login within the 'ui-next/src/app' ecosystem.
- **`pricing`**: Product tier pricing, feature comparisons, and gateway subscriptions page.
- **`privacy`**: Exposes routing, templates, or integrations for Privacy within the 'ui-next/src/app' ecosystem.
- **`reset-password`**: Exposes routing, templates, or integrations for Reset-password within the 'ui-next/src/app' ecosystem.
- **`security`**: Exposes routing, templates, or integrations for Security within the 'ui-next/src/app' ecosystem.
- **`settings`**: Exposes routing, templates, or integrations for Settings within the 'ui-next/src/app' ecosystem.
- **`signup`**: Exposes routing, templates, or integrations for Signup within the 'ui-next/src/app' ecosystem.
- **`status`**: Exposes routing, templates, or integrations for Status within the 'ui-next/src/app' ecosystem.
- **`subprocessors`**: Exposes routing, templates, or integrations for Subprocessors within the 'ui-next/src/app' ecosystem.
- **`terms`**: Exposes routing, templates, or integrations for Terms within the 'ui-next/src/app' ecosystem.
