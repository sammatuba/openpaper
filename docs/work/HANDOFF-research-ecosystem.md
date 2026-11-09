# Research ecosystem handoff — 2026-11-04

Resume on `master`, tracking `origin/master`. Implementation commit:
`0a1cffe77bf844691f08897fd18361f2016b8a08`, also pushed to
`origin/feat/cloud-run-personal` and fast-forward merged into `origin/master`.
This handoff is committed separately after the implementation. The live pointer
is [current.json](current.json); run `rtk proxy bash ./meos start --runtime codex`
when starting a new session.

## Latest strategy: research workspaces and architecture (2026-11-04)

**Latest implementation/wrapup supersedes the strategy-only state below:**
Read [first-slice verification and continuation](VERIFICATION-project-workspaces-and-research.md).
Maintenance, shared downloads, CI, workspace CLI and staged research packet are
implemented locally with executed checks. Required review report is
`.meos/reviews/20261104T054504Z.md`; check its final verdict. Actual ai-safety
binding/promotion is deferred at the user's request to close this session soon.
All source remains uncommitted; this slice has not been deployed.

Live connector now exposes15 tools. Project context and evidence search work.
MT-Bench paper `bcd665b8-c545-4586-8dee-baf54d4ccfa1` is already in the live
collusion project alongside the report; do not reupload. Earlier seven-tool
observations are historical. Hash-verified primary inputs are preserved under
ignored `.meos/artifacts/collusion-r1-sources` for next-session verification.

The operator invoked meos-strategy and selected all three priorities: research
outputs, local project workspaces, and reliability. Read
[the current assessment and work packages](STRATEGY-project-workspaces-and-research.md).
It records source evidence, research opportunities, directory ownership,
14 architecture findings, acceptance checks, and the proposed sequence.

Source remains uncommitted; recorded deployment remains revision9 and the
frontend correction is still local. In this strategy pass, authenticated
connector project listing worked, but this conversation exposed seven older
tools. Refresh/discovery and real URL/attachment acceptance remain open; earlier
12-tool confirmation below is historical, not this conversation's capability.

Research inspection found 48 dossiers and a landscape with3,598 sources but zero
exported claim rows. This is an opportunity to structure evidence, not evidence
that the existing written research has no support. The proposed workspace bridge
reuses ai-safety's existing project/literature layout and corpus IDs.

First proposed implementation: W0, fix the passage backfill's mutating/nonterminating
dry run and unify browser/MCP PDF URL protections; add reproducible isolated CI
checks and release/source traceability. Then W1, a small local project-binding
contract, paired with a bounded prior-work comparison. The strategy pass only
changed work records. A fake-database reproduction confirmed the dry-run defect;
no real maintenance/import, sibling write, paid research run, or deployment ran.
No independent implementation review is claimed for this authored assessment.
Independent strategy review `.meos/reviews/20261104T042621Z.md` accepted with
no material findings; source inspection and JSON/link/diff checks passed.

## Direct ChatGPT uploads deployed (2026-11-04)

Operator requested public PDF URLs and chat attachments. Added
import_paper_from_url, upload_paper_file (official openai/fileParams), and
get_paper_upload_status:15 tools after refresh. Existing PDF pipeline/limits,
project editor permission, owner-only status, content/user/project dedup with
no blind re-enqueue. Isolated HTTPS downloader enforces a hard60s process deadline.

Final review `.meos/reviews/20261104T032017Z.md` accepts all findings. Tests:
PostgreSQL7 (8.162s), downloader/protocol/routing6 independently pass, real
public PDF subprocess download/validation pass. Corrected build
`a735fa15-6a90-4d6d-8667-46cef54ea304` succeeded; revision
`openpaper-00009-fb9` serves100%. Both-host live smoke passes. No migration or
production paper import. Source remains uncommitted; previous frontend SSR fix
still undeployed.

Next: refresh Open Paper tools to15, then import a user-selected URL and an
actual ChatGPT attachment and poll to completed paper links without browser UI.
See [the guide](CHATGPT-research-workflow.md). Tool-side wire tests pass;
account-side attachment handoff/full processing acceptance remains pending.
Do not reupload completed pilot entries or mutate the stale duplicate.

## MCP research first release deployed (2026-11-04)

Added search/fetch, indexed project evidence search, paginated project context
and private highlights; enriched annotations and note readback/version metadata.
Independent review follow-up `.meos/reviews/20261104T014941Z.md` accepted both
initial findings after member citation and regression fixes. PostgreSQL6 and
protocol/routing2 pass. Final build `5d5ca13d-39b0-4145-956b-51340d2a22da`
succeeded; revision `openpaper-00008-lxc` now serves100% traffic. Both-host
smoke passes and connected ChatGPT note readback returns new ETag/pagination
fields without mutation. Source changes remain uncommitted.

At that release, the operator confirmed all12 tools visible,1 accessible project and13 AI metadata
search matches after refresh. The later upload release requires another tool refresh.
Use [the workflow guide](CHATGPT-research-workflow.md) for search/fetch,
selected-note save/readback and fresh conversation project context. Account-side
new-tool/live-write acceptance is pending. Earlier local frontend SSR fix is
still undeployed. No corpus expansion or stale-duplicate changes occurred.

## Upload404 correction deployed (2026-11-04)

Operator Library uploads returned404 because MCP's catch-all root mount consumed
slashless application paths before Starlette could redirect. A route-aware MCP
mount fixes this while retaining its middleware/lifespan. Two focused tests and
independent review `.meos/reviews/20261104T004919Z.md` passed. Server-only build
`d27fb2b8-c26d-442f-a123-24c84029f279` succeeded and revision
`openpaper-00007-gvn` serves100% of traffic. Both hosts now pass file/URL-upload
redirect/auth checks plus health and MCP discovery/auth smoke. Operator confirmed actual Library upload works after the fix. Source changes remain uncommitted. No new paper was
imported, no temporary owner session created, and stale duplicate preserved.

## Local continuation (2026-11-04)

A shared browser-only PDF viewer boundary is implemented locally and uncommitted.
Typecheck, production build, six HTTP routes without browser-global server errors,
and desktop/mobile Chromium rendering of a real PDF plus Notes concurrency UI
checks passed. See the current verification document and pointer. Initial review
found no code defect but requested runtime evidence, which has now been recorded;
focused follow-up `.meos/reviews/20261104T002648Z.md` accepted with no findings.
This change has not been deployed.

The operator confirms the three expected pilot titles are visible in the library
and login works. Explicit new-PDF/Notes rendering and 30-minute idle timing remain
unconfirmed. No imports or stale-duplicate mutations occurred.

## Delivered and verified

- Live URL: https://papers.jansammat26.workers.dev.
- Durable outcome recovery, notes with ETags, authenticated OAuth MCP, Exa
  wiring, short hostname and corpus tooling are deployed. Full review findings
  and the importer User-Agent fix received independent Terra follow-up acceptance.
- Locked five-image Cloud Build `01c4c5da-c4d8-4ed9-abb9-9584aa1bd2a4`
  succeeded; migration `openpaper-migrate-wbpvx` succeeded; web revision
  `openpaper-00006-gfh` and jobs deployed; schedules updated.
- Frontend typecheck/build and mocked desktop/mobile notes checks passed.
  Recovery/CORS tests and isolated PostgreSQL crash/replay checks passed.
  [Verification](VERIFICATION-research-ecosystem.md) records the executed evidence
  and limitations; local independent reports remain under ignored `.meos/reviews/`.
- Operator confirmed Google login, existing 55-page PDF rendering, Notes, ChatGPT
  OAuth connection and paper search. A bounded one-result Exa check passed using
  the deployed image/runtime; its temporary job was deleted.
- Pilot completed: existing local PDF reconciled without reupload; T17 and R11
  imported with dossier notes created once. Authenticated readbacks verified
  PDFs, extracted text, exact source notes, ETags and credentialed CORS.
  IDs and state are in [the manifest](corpus-manifest.json) and
  [pilot evidence](corpus-import.md). Do not resubmit completed entries.
- Initial Python requests were rejected by Cloudflare before origin. Database
  reconciliation verified no new jobs before the reviewed User-Agent fix and
  successful retry. Temporary owner sessions and temporary Cloudflare config
  copy were cleaned up; the original authentication config was preserved.

## Next actions

1. Collect the operator's pending browser rendering confirmation for the two new
   pilot PDFs and their Notes. The previous session requested it but received no
   result before this handoff.
2. Verify a second login after 30 minutes without application activity.
3. After a full week, review GCP and Neon billing against the original P3 targets
   in [the deployment intent](INTENT-personal-cloud-run-deploy.md).
4. Validate citations and project chat before any corpus expansion. No expansion
   beyond this pilot was performed or authorized.
5. Separately reconcile the stale duplicate placeholder paper and running job;
   preserve them until resolved. Do not automatically delete or reupload them.

An unchanged PDF-viewer import produced background SSR `window`/`document`
errors in the local server. The route returned HTTP 200 and the mocked UI passed;
the existing PDF also rendered live. A separate baseline runtime was not rebuilt.
Concurrent database-pool saturation and live MCP note append were not verified;
do not describe paper search confirmation as proof of every MCP write path.
