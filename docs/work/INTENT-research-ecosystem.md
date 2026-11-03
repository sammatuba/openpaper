# Intent: connect the personal research ecosystem

Opened: 2026-11-03. Operator authorized the strategy with “proceed accordingly”.
Strategy: [research ecosystem](STRATEGY-research-ecosystem.md).

## Outcome

Keep the current Cloud Run reading flow and Vertex AI provider while adding a
short free hostname, Exa discovery, a resumable curated corpus import, and an
authenticated ChatGPT tool connection. Preserve the existing landscape/map and
research provenance. Sol 6.1 high handles intent and review coordination; Terra
6.1 handles implementation, with delegation explicitly authorized by the operator.

## Boundaries

- Retain upstream defaults behind environment/config switches. Preserve the
  single browser origin, private storage, allow-listed sign-in and personal GCP
  configuration. No local secret files or credential output.
- Existing 48 dossiers are the curated import scope. The 3,598 landscape sources
  are not a bulk-processing target. Preserve authored notes and epistemic labels.
- Infrastructure deployment and pilot work follow the approved strategy; perform
  local verification before live changes. Obtain missing credentials through
  secure sign-in/input, never chat or a committed file. Account/workspace UI
  actions may require the operator; continue independent work while pending.
- General idea records remain in ai-safety. Do not invent paper annotations or
  fake literature to hold them. Keep graph schemas and existing visualization.

## Work packages and observable checks

1. **Reliable outcomes:** persist PDF and data-table success/failure outcomes in
   private durable storage before acknowledging them. An outage longer than a
   minute must trigger delivery retries without rerunning successful inference.
   Replay must not create duplicate papers/table rows or replace success with
   failure. Persistence/enqueue failures must not produce false acknowledgement.
   Test outage/recovery, duplicate delivery, failed outcomes, storage/queue
   failures and unchanged default Celery behavior. Retention/retry limits must
   be documented; this is not a promise of recovery after indefinite outages.
2. **Hostname and Exa:** a fixed-upstream streaming Cloudflare proxy, configurable
   browser origin separate from internal Cloud Run origin; auth/API/MCP uncached.
   Configure OAuth redirects, cookies and storage CORS consistently. Optional
   EXA_API_KEY secret wiring must preserve keyless deployment. Verify scripts,
   proxy forwarding and existing app tests, then login, PDF, streaming and bounded
   Exa search live when credentials/registration permit.
3. **Import and landscape bridge:** dry-run manifest for every dossier plus
   distinct local PDFs, stable IDs/identities/hash and persistent job outcomes.
   Resume must avoid duplicate upload or note replacement. Map existing sources
   to papers without flattening graph relation semantics. Pilot local/arXiv/
   non-arXiv inputs before expanding; record explicit unavailable/skipped items.
4. **ChatGPT MCP:** established MCP/OAuth components, authenticated per-user
   retrieval over existing services, then explicit retry-safe paper-note append.
   No destructive write tools. Verify access isolation, concurrent note safety,
   retry deduplication, protocol initialization and real account connection when
   workspace rights are available. Keep project-wide idea storage unchanged.

## Completion evidence

Run relevant checks and independent MEOS review before claiming implementation
complete. Track local implementation separately from deployed/live verification.
Retain pending P3 idle-login and week-long cost checks until actually observed.
Record exact outstanding account actions and next steps in current.json.
