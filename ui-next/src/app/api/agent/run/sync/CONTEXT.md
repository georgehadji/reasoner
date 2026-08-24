# Context: Sync

## Directory: `ui-next/src/app/api/agent/run/sync`

## Description
Exposes routing, templates, or integrations for Agent Run Sync within the 'ui-next/src/app/api' ecosystem.

## Files
- **`route.ts`**: Proxies POST /api/agent/run/sync — blocks until the pipeline finishes and returns one JSON RunResult. A run can legitimately take up to the pipeline's own cap (currently 600s); this route holds the connection open

## Subfolders
*No subfolders in this directory.*
