# Context: Src

## Directory: `sdk/typescript/src`

## Description
Source code for the TypeScript client SDK, containing core interfaces and fetch wrappers.

## Files
- **`client.ts`**: The Reasoner API client.  Scoped to running pipelines and the metadata needed to run them well:
- **`errors.ts`**: Error types for the Reasoner API.  Every non-2xx response becomes a subclass of {@link ReasonerError}, chosen by
- **`events.ts`**: Event shapes streamed by `POST /api/run` and `POST /api/run-followup`.  The event set is open.** The API adds new `type` values without a version
- **`http.ts`**: HTTP transport: authentication, retries, and abort plumbing.  Uses the global `fetch`, so the SDK runs unmodified on Node 20+, Bun, Deno,
- **`index.ts`**: `@reasoner/sdk` — TypeScript client for the Reasoner API.  ```ts
- **`sse.ts`**: Server-Sent Events parsing.  Implements the framing rules from the SSE spec rather than scanning for
- **`types.ts`**: Request and response shapes for the Reasoner API.  Wire shapes keep the API's `snake_case` naming so payloads map 1:1 onto the

## Subfolders
*No subfolders in this directory.*
