# Research ecosystem verification

Date: 2026-11-03. Implementation and live checks tracked separately.

## MCP direct paper uploads (2026-11-04)

Added public PDF URL import, ChatGPT attachment input and owner-only upload
status. Attachment schema exposes all four official file fields and declares
openai/fileParams. Both paths reuse PDF validation and existing job dispatch.
A content/user/project UUID claim is committed before storage/dispatch; retries
and concurrent same-content submissions reuse the job. This does not dedup
uploads created through older UI/corpus paths or across different destinations.
Failed/interrupted/uncertain claims are never automatically resubmitted.

Downloader uses HTTPS on443, validates all DNS addresses, pins a public address
through verified TLS/SNI, checks each redirect, ignores ambient proxies and
credentials, and caps download bytes/time. Signed URLs are not persisted.

Tests: downloader/protocol/upload-routing5 passed, including file schema/meta
and15 tools. Isolated PostgreSQL7 passed with three concurrent requests/one
dispatch, invalid PDF/quota, viewer rejection, status isolation and completed
paper link. Interrupted-claim regression passed in the final7 rerun (8.971s).
A read-only live arXiv pilot PDF download via the pinned downloader returned
5,355,095 bytes and passed existing PDF validation; nothing was imported.
Real MCP URL/attachment/status wire regression passed in the final PostgreSQL7
run (8.448s), exercising both write tools over actual transport with mocked
download/dispatch, cross-tool content deduplication, and owner status polling.
Initial review `.meos/reviews/20261104T022128Z.md` requested a hard deadline,
stronger integration evidence, and exact verification commands. The downloader
now runs in an isolated subprocess; subprocess.run(timeout=60) kills and reaps
it across DNS/TLS/stream stalls. A real sleeping-child test verifies timeout
termination at0.2s. URL is supplied on stdin, not command-line arguments; stderr
is discarded and failures return generic text to avoid signed-URL disclosure.
Both real MCP write calls now use the repository's14-page PDF, actual validation
and upload_raw_file_microservice; only downloader, quota, telemetry and external
JobsClient submission boundary are isolated. It verifies PDF bytes/identity passed
to processing, a single dispatch across URL/file calls and running status.

Executed from server/ (dummy OAuth/provider environment, dotenv disabled):
`rtk proxy .venv/bin/python -m unittest tests.test_mcp_upload_download tests.test_mcp_protocol tests.test_mcp_routing -q`
passed6 tests in2.937s (including the actual-child timeout). For the isolated
PostgreSQL7 suite, execute from /tmp with PYTHONPATH set to server/,
OPENPAPER_ISOLATED_PG_TEST=1, PYTHON_DOTENV_DISABLED=1 and
DATABASE_URL=postgresql://sammatuba@/postgres?host=/tmp&port=55439:
`rtk proxy /home/sammatuba/projects/ps/openpaper/server/.venv/bin/python -m unittest tests.test_mcp_postgres -q`.
The final real-validation/dispatch-boundary PostgreSQL7 execution passed in12.019s.
Automatic approval review timed out once for this database test command; the
permitted retry started successfully. No production paper was imported.
Focused follow-up `.meos/reviews/20261104T031839Z.md` accepted the hard-deadline
fix and independently passed downloader/protocol/routing6. It requested a
standalone attachment dispatch test and explicit account-side acceptance notes.
The standalone different-content attachment wire case now passes actual PDF
validation and upload_raw_file_microservice, asserts its supplied download_url,
PDF bytes and owner at the JobsClient boundary, and retains cross-tool dedup.
The fixture path is now relative to the test file. The complete PostgreSQL7
suite including the final URL assertion and portable fixture passed in8.162s.

Pending after rollout: refresh ChatGPT to expose15 tools, import a user-selected
public PDF URL, upload a real conversation attachment, and poll each to its
completed paper link without browser automation. No account-side attachment or
new-paper processing acceptance is claimed yet. Final focused review `.meos/reviews/20261104T032017Z.md` accepted with no
findings; reviewer reran downloader/protocol/routing6 and diff checks, accepted
recorded PostgreSQL7 evidence without a read-only database rerun. Corrected
build `a735fa15-6a90-4d6d-8667-46cef54ea304` succeeded; image digest
`sha256:f42646d3721dc785f15e2abe782dd24cc931d32a164b2a265813edd2451e8e3f`.
Initial image16c578bd was superseded before deployment. Revision
`openpaper-00009-fb9` serves100% traffic. Both hosts pass live upload redirect/auth,
health200, discovery200/no-store and MCP POST401/no-store checks. A final public
pilot PDF download through the actual isolated-process wrapper returned
5,355,095 bytes and passed PDF validation; no paper was imported. Source remains
uncommitted. ChatGPT tool refresh/URL/attachment/completion acceptance remains
pending as described above.

## MCP research first release (2026-11-04)

Implemented standard search/fetch, indexed project evidence search, paginated
project context and highlights with caller-private annotation context. Fetch
reauthorizes, verifies content hashes and checks indexed lines against current
extracted text; it never assigns PDF page numbers to extracted-text lines.
Existing note append remains owner-only and retry-safe, now returns a readback
ETag. No migration or new note store.

Isolated PostgreSQL suite tests title-independent indexed matches, exact source
fetch, empty project scope, unauthorized/revoked access, member private-context
isolation, owner-only writes, fresh-session note readback and deduplication.
Actual MCP HTTP protocol tests exercise standard structured search/fetch and
append retry/readback with fake verified OAuth against the real test database.
Initial wire assertion incorrectly treated isError:false as failure; corrected
to assert its boolean value. Existing routing/discovery/init tests passed2/2.
Six-test PostgreSQL suite passed, including positive MCP wire search/fetch and
retry-safe save/readback; independent review is in progress. Added note pagination
so long appended notes remain retrievable with a shared full-note ETag.
No live owner-token or production note mutation performed.
Initial review `.meos/reviews/20261104T014431Z.md` requested accessible member
citation URLs and additional regression evidence. Shared citations now link to
an authorized project (whose existing reader opens the member paper); owned
citations link directly to the paper. Tests cover project navigation permission,
unchanged-index/changed-source rejection, invalid line bounds, oversized fetch,
author-string caps and two-page project context. Focused follow-up `.meos/reviews/20261104T014941Z.md` accepted with no findings;
reviewer reran protocol/routing2 but could not rerun PostgreSQL in read-only
sandbox. Final expanded six-test PostgreSQL suite passed in6.500s externally.
Final build `5d5ca13d-39b0-4145-956b-51340d2a22da` succeeded with digest
`sha256:8062f28a8ac53ea5a6c34bac6e128bda89abe43e4b82027eb5d4cbbbfc8fd0a9`.
Earlier intermediate builds were superseded before rollout. No schema migration.
Existing ChatGPT OpenPaper list_projects succeeded through the connected plugin;
new tool-list refresh and user-side full workflow acceptance remain pending.
Server-only revision `openpaper-00008-lxc` serves100% traffic. Both-host live
upload redirect/auth, health200, discovery200/no-store and MCP POST401/no-store
checks pass. The existing connected OpenPaper plugin get_paper_note successfully
returned the unchanged T17 note with ETag and pagination metadata (2829 chars).
No live note mutation or paper import was performed. This proves live OAuth
readback of the new response contract, not live write acceptance or refresh of
new tool definitions. Source changes remain uncommitted.

## Upload 404 correction (2026-11-04)

Production logs showed 16 slashless POST /api/paper/upload failures around
00:30–00:31 UTC. Empty unauthenticated POST probes reproduce on both public
hosts: slashless path404 plain Not Found, canonical trailing-slash path401.
The FastMCP catch-all root mount prevented Starlette's trailing-slash redirect.

`MCPRouteMount` delegates only paths registered by the wrapped MCP application,
keeping its middleware and lifespan intact. No frontend or proxy change is
needed. From server/, unittest tests.test_mcp_routing tests.test_mcp_protocol
passed (2 tests) with dummy provider/OAuth settings and SQLite configuration,
no live credentials. Coverage: multipart payload/project query across307,
canonical upload, URL JSON body across307, MCP middleware and405, unknown404,
real FastMCP discovery, unauthenticated401 and fake-bearer initialization200.
Diff whitespace checks pass. Independent review
`.meos/reviews/20261104T004919Z.md` accepted with no findings, independently
rerunning both tests and checking all registered MCP/OAuth route methods.
Server-only Cloud Build `d27fb2b8-c26d-442f-a123-24c84029f279` succeeded;
server image digest `sha256:8ee17f67cc4eb81f6af91526e294ed7ae54551fee99724555c63255aeab53fc8`
deployed as `openpaper-00007-gvn`, serving 100% of traffic. Only the server
container image was updated; the local PDF viewer fix remains undeployed.

Live `/tmp/openpaper-upload-live-check.py` passed on both workers.dev and
deterministic run.app hosts: slashless file and URL POST307 to the same-origin
canonical path with query preserved; canonical POST401 without authentication;
health200; OAuth resource discovery200/no-store; MCP POST401/no-store. The
initial smoke expected401 for MCP GET but received the legitimate405; corrected
the probe method to POST and all checks passed. No owner session or test paper
was created; operator subsequently confirmed actual Library upload works.

The initial build submission was stopped
during local archive preparation; a minimal Dockerfile allowlist source bundle
was staged without the local virtualenv or dotenv files.

## PDF viewer continuation (2026-11-04)

- The shared `PdfHighlighterViewer` now uses `next/dynamic` with `ssr: false`.
  The previous implementation is in `PdfHighlighterViewerClient.tsx`; its only
  internal change is exporting the props interface. Conversion helpers are
  re-exported directly from `pdf-viewer/types`, avoiding the browser-only barrel.
- From `client/`, `rtk proxy node node_modules/typescript/bin/tsc --noEmit`
  and `rtk proxy npm run build` passed. The build generated all 46 static pages;
  existing image and unused-eslint-disable warnings remain.
- Started that production build with `rtk proxy npm run start -- --port 3000`.
  Requests to `/paper/p`, `/paper/share/p`, `/projects/p`,
  `/projects/p/conversations/c`, `/projects/p/audio/a` and `/understand` all
  returned 200. Server output remained only Next startup/ready messages after
  HTTP and browser checks: no window/document errors or unhandled rejections.
- `rtk proxy node /tmp/openpaper-pdf-boundary-check.cjs` passed in Chromium at
  1440×900 and 390×844 against the production server. Auth and API were mocked;
  the repository's real 14-page `publicusegeneralhealthchatbots.pdf` fixture
  rendered into a visible PDF.js canvas at both sizes. Notes creation, ETag
  editing, draft retention after 412, and Cancel refreshing the remote note
  passed at both sizes. No page errors were emitted. This is local evidence,
  not verification of live model responses or pilot PDFs.
- Sandbox networking/browser launch and reviewer runtime initially failed;
  the same commands succeeded with approved escalation.
- Independent review `.meos/reviews/20261104T002450Z.md` found no implementation
  defect and independently passed typecheck, helper server-safety/round-trip and
  diff checks. Its rework finding requested the runtime evidence now recorded
  above. Focused follow-up `.meos/reviews/20261104T002648Z.md` accepted with
  no findings. It independently passed typecheck, diff/JSON checks and exact
  viewer-move comparison; read-only sandbox prevented browser/build reruns.
  A local transcription of the parent runtime results is saved at
  `.meos/reviews/pdf-viewer-runtime-evidence.txt`.
- Operator confirmed the library lists Catastrophic AI Risks, Systematic
  Failures in Collective Reasoning, and AI Control, and that login works. This
  does not explicitly establish PDF/Notes rendering or 30-minute idle timing.
- Changes are local and uncommitted. No deployment, import, corpus expansion,
  stale-duplicate mutation, temporary owner session or billing check was run.

## Publication (2026-11-04 Manila)

Implementation commit `0a1cffe77bf844691f08897fd18361f2016b8a08` was pushed to
the feature branch and fast-forward merged/pushed to `origin/master`.
The final portable handoff is [HANDOFF-research-ecosystem.md](HANDOFF-research-ecosystem.md).
Earlier references to uncommitted changes describe the state before publication.

## MEOS wrapup (2026-11-04 Manila)

The live pointer and local checkpoint now describe the deployed stack and completed
three-item import pilot. Obsolete review-scope and account-readiness fields were
reconciled in `current.json`. Existing review and executed verification evidence
was retained; no implementation changed during wrapup. JSON validation and
`git diff --check` passed. The implementation remains uncommitted.

Exact continuation: collect the operator's pending browser check for the two new
PDFs and Notes; verify a second login after 30 minutes of application inactivity;
review GCP and Neon billing after a full week against the original P3 targets.
Before corpus expansion, validate citations and project chat. Preserve the stale
duplicate paper/job until separately reconciled. The PDF-viewer background SSR
errors remain a documented follow-up, with no separate baseline rebuild performed.

## Resumed session outcome (2026-11-04 Manila)

- Full Terra review `.meos/reviews/20261103T160931Z.md` returned rework. All three findings were resolved locally and independently accepted in `.meos/reviews/terra-focused-recovery-cors.md`; the later importer User-Agent fix was independently accepted there too.
- Frontend TypeScript, production build and mocked desktop/mobile Notes checks passed. Locked Cloud Build `01c4c5da-c4d8-4ed9-abb9-9584aa1bd2a4` passed all five image builds and publication (14m13s), resolving the local dependency-repair caveat. Recovery/CORS focused tests, actual isolated PostgreSQL PDF crash/replay, corpus/operator14, Worker, shell and diff checks passed.
- Worker version `984b0013-26c3-458a-a190-563b65b62872` is live at https://papers.jansammat26.workers.dev. Bootstrap/CORS/queue updates and MCP key initialization completed; migration `openpaper-migrate-wbpvx` succeeded; web revision `openpaper-00006-gfh` and jobs deployed; schedules updated.
- Live homepage/API health and MCP metadata return200; unauthorized MCP returns401 with no-store; anonymous jobs returns403. Operator confirmed real Google login, existing55-page PDF rendering, Notes, ChatGPT OAuth connection and paper search. A temporary verification job using the deployed server image/runtime returned one Exa result and was deleted.
- Three-item pilot completed: existing local PDF linked without reupload; T17 and R11 imported with dossier notes created once. Authenticated readbacks verify PDF magic, extracted text, verbatim dossiers, ETags and credentialed CORS exposure. First attempts were blocked by Cloudflare1010 before origin; no jobs were created, then manual reconciliation and the reviewed User-Agent fix permitted retry. All temporary owner sessions were cleaned; temporary Cloudflare config copy removed and original preserved. See corpus-import.md for paper IDs.
- Remaining observations: operator browser rendering check for new pilot PDFs/Notes, idle-login, week-long costs, and citations/project chat before expansion. Existing stale duplicate paper/job preserved. Existing unchanged PDF-viewer import logs background SSR window/document errors; route HTTP200 and mocked UI pass, baseline runtime not rebuilt.
- Changes remain uncommitted. No corpus expansion beyond the pilot ran. Historical sections below preserve prior-session evidence.

## Executed

- Routine local checks (2026-11-03): `rtk node --test deploy/cloudflare/worker.test.mjs`
  passed (1/1); `rtk bash -n deploy/deploy.sh` passed;
  `rtk python3 -m unittest test_corpus test_operator_pilot` from
  `scripts/research/` passed (14 tests); `rtk git diff --check` passed;
  `UV_CACHE_DIR=/tmp/openpaper-uv-cache rtk uv lock --check` from `server/`
  passed (171 packages resolved). The temporary UV cache path was needed
  because the default cache is read-only in this sandbox.

- Cloudflare connected account verified as the personal account, workers.dev
  subdomain `jansammat26`. Only `blackglass` existed before this work.
- GCP `personal` configuration active account verified; work account was not
  selected. Existing Exa secret absent (names only inspected).
- Live disposable GCS JSON conditional-write check: initial write HTTP 200,
  conflicting write HTTP 412, first value preserved. Test object removed. This
  validates GCS generation preconditions, not the deployed jobs revision.
- Terra hostname package: Node Worker tests, bash syntax and optional Exa
  manifest rendering passed; no live proxy/origin migration performed yet.
- Corpus package: eight stdlib tests passed per execution agent; parent initially
  ran the first four before follow-up improvements. No corpus uploaded.
- Reliability package: seven outcome delivery/replay tests and four table webhook
  mock tests passed per execution agent; six existing webhook tests passed.
  Existing TestClient runner suite passed 4/4 outside the sandbox; a bounded
  faulthandler diagnostic identified an AnyIO wakeup stall inside the sandbox.
- Real PostgreSQL integration: three tests passed against isolated local
  PostgreSQL 18 (TCP disabled, /tmp socket, disposable random schemas). Confirmed
  duplicate handler waits on a row lock via pg_stat_activity, exactly one result
  and row persist, late failure cannot downgrade success, foreign-key failure
  rolls the whole result transaction back, and wrong task ID is rejected.
- Operator confirmed EXA_API_KEY stored securely and the new browser OAuth
  redirect registered; exact key contents were not requested or displayed.
- Live one-result Exa search through the existing application helper passed for
  AI Control: returned the matching arXiv resource. Key read from Secret Manager
  into process memory only. This does not yet verify deployed service wiring.
- Operator also registered the dedicated MCP Google callback URI.

## Pending

- Initial independent Sol 6.1 high review: rework, report
  `.meos/reviews/20261103T153948Z.md`. Sole blocker: failed PDF status writes
  could be acknowledged after CRUD returned None. A late implementation fix
  checks that return value; regression and bounded re-review pending. Minor
  account-state documentation mismatch reconciled in current.json.
- MCP protocol/authentication and ETag verification/review. Dependencies are
  installed; isolated PostgreSQL note concurrency and encrypted store restart
  tests passed per execution agent.
- Deployments, live hostname login/PDF/streaming, deployed Exa wiring,
  three-item corpus pilot, ChatGPT registration. OAuth redirect registration,
  Exa secure key input and a bounded helper search are complete; Business
  owner/admin rights confirmed.
- Prior P3 idle-login and week-long billing checks remain open.

## Known recovery limits

An outcome is replayable once persistence succeeds. If storage is unavailable
after inference, a dispatch retry may repeat inference because the result never
became durable. Queue retries are bounded (100 attempts and 24 hours, stopping
after both conditions); stored outcomes are kept until a lifecycle rule or an
explicit retention process removes them. Review must assess these limits
against the intent without claiming indefinite recovery.

## Handoff 2026-11-03

User requested immediate stop due to usage limits. Terra independent follow-up review
was interrupted (exit 130); it has no verdict. The initial full review remains
rework; its reported PDF blocker was subsequently fixed and five regression tests
passed. Luna follow-up was narrower and is not a full review. Frontend dependency
installation and typecheck/build were interrupted. No production deployment,
import, or new operator session was performed. Local changes are uncommitted.

## Review fixes: PDF replay and CORS

- PDF enrichment and upload completion now share one externally managed
  SQLAlchemy transaction; failed highlight or annotation writes raise. From
  `server/`, `env OPENAI_API_KEY=dummy ANTHROPIC_API_KEY=dummy
  GEMINI_API_KEY=dummy DATABASE_URL=sqlite:///dummy.db .venv/bin/python -m
  unittest tests.test_pdf_webhook_recovery -q` passed six tests. The replay
  regression uses SQLite and simulated CRUD commits to check rollback and
  duplicate delivery. A separate isolated PostgreSQL 18 integration test
  (`tests.test_pdf_webhook_postgres`) also passed with real CRUD calls: a
  crash rolls back highlight, annotation, conversation and message writes;
  replay creates one of each and completes the job. The test verified its
  dedicated socket-only cluster and used a disposable schema.
- CORS explicitly exposes ETag for credentialed requests. From `server/`,
  `.venv/bin/python -m unittest tests.test_cors_etag -q` passed one configuration
  test. A full cross-origin browser edit remains unverified; attempted
  TestClient request hung in this environment.
- `git diff --check` passed. Independent follow-up review is pending.

## Frontend local verification

- Yarn 1.22.22 frozen-lockfile installation succeeded with optional packages
  skipped after the Windows SWC download stalled. Standalone `tsc --noEmit`
  passed. Matching Linux native packages were installed locally without saving;
  npm also changed four locally installed packages, so the subsequent successful
  production build did not verify an exact frozen-lockfile dependency tree.
  The build generated 46 static pages and reported lint warnings.
- Headless Chromium against the local production frontend, with authentication
  and API responses mocked, passed at 1440×900 and 390×844. Both viewport checks
  navigated to Paper notes, created a note with POST, edited with PUT and the
  returned ETag in If-Match, preserved the draft after a simulated 412 conflict,
  and loaded the remote version after Cancel. These checks do not verify a live
  cross-origin server or authentication.
- The local production paper route returned HTTP 200 and rendered the mocked
  browser flow, but its server logged background `window`/`document` undefined
  rejections. The compiled failing module is `pdfjs-dist/web/pdf_viewer.mjs`,
  imported at module scope by `react-pdf-highlighter-extended`; the paper page’s
  `PdfHighlighterViewer` import already exists at HEAD. This indicates a
  pre-existing import path, though a separate baseline runtime was not built.

## Operator ChatGPT refresh confirmation

Operator reports all12 OpenPaper tools are visible after refresh. The connection
returns1 accessible project and13 papers matching AI in title/abstract search.
This confirms tool discovery and read-only project/metadata lookup. It does not
establish exact search/fetch citation verification, live note append/readback
or fresh-conversation context recovery; those acceptance checks remain open.
