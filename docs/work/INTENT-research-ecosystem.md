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

## Continuation: PDF viewer server rendering (2026-11-04)

Resolve the handoff's browser-global errors before further citation/project-chat
acceptance. Place the shared PDF viewer behind a client-only dynamic import so
all paper, share, project preview and audio consumers retain their existing API.
Keep highlight conversion helpers safe to import on the server. Do not change
PDF search, citations, annotation behavior, authentication or the corpus.

Checks: frontend typecheck and production build; production paper/share/project
routes must not log window/document errors; browser checks must load a real PDF
and retain desktop/mobile Notes behavior. Local mocked checks do not establish
live pilot rendering, idle-login, billing or project-chat model correctness.

## Upload 404 correction (2026-11-04)

The operator reports Library PDF uploads fail with API error 404. Production
logs confirm repeated POST /api/paper/upload 404; empty unauthenticated probes
on both hosts reproduce 404 at the slashless path and 401 at the canonical
trailing-slash path. The MCP root mount consumes unmatched application paths
before Starlette's slash redirect pass. Restrict that mount to registered MCP
routes while retaining its authentication middleware and lifespan. Preserve
application routing, multipart bodies, project query strings and MCP/OAuth
discovery/protocol behavior. No corpus expansion or duplicate mutation.

Check multipart and URL-upload slash redirects, body/query preservation,
MCP middleware/authentication and protocol initialization, and unknown-path
behavior. Independently review before a server-only rollout; verify public
slashless upload redirects and canonical authentication after rollout without
creating an owner session or importing additional papers.

## MCP research first release — approved 2026-11-04

Operator approved evidence search, project context and verified note saving.
Add standard search/fetch over existing indexed passages with stable IDs, exact
text and line provenance; project-scoped evidence search; paginated project
context with member papers and only the caller's private notes/highlights/
annotations. Paper text access through projects requires current membership;
private writes remain owner-only. Retain existing tools and OAuth middleware.
Fetch must reauthorize, reject stale citations and expose bounded full passage
items rather than silently truncate. Explicit append remains retry-safe and
returns a readback version; no automatic saving or new project-note store.
No discovery/import expansion, graph changes or embeddings in this release.
Verify actual PostgreSQL search, outsider/member/revoked permissions, exact
passage fetch, fresh-context note readback and retry deduplication, protocol
schemas/auth and upload regression; independent review before server rollout.
Live ChatGPT tool refresh/usage is a separate operator acceptance check.

## MCP paper uploads — approved 2026-11-04

Operator requests direct ChatGPT uploads and confirms both public URLs and chat
PDF attachments. Expose import_paper_from_url, upload_paper_file with official
openai/fileParams, and read-only get_paper_upload_status. Reuse PDF validation,
limits, storage and processing. Enforce project editor/admin permission before
download; status is owner-only and does not mutate jobs. Use a deterministic
content/user/project job ID to prevent retry/concurrent duplicate dispatch.
A claimed job is never resubmitted automatically after interruption, failure
or ambiguous enqueue; return explicit status requiring reconciliation. No schema
migration. Dedup covers this MCP path only, not existing UI/import corpus.
Fetch HTTPS PDFs with public-address validation and IP-pinned TLS connections
on every redirect, capped bytes/time, no ambient credentials or proxies. Never
store/log signed download URLs. Test attachment metadata/schema, retries/races,
limits, permissions, PDF/download failures and asynchronous processing status;
independent review then server-only rollout. No new live paper without selected
operator input; ChatGPT attachment acceptance remains account-side.
