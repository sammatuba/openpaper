# Research ecosystem verification

Date: 2026-11-03. Implementation and live checks tracked separately.

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
