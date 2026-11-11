# Investigation workspace — implementation and release report

The investigation workspace is implemented, independently accepted, and deployed
at https://papers.sammatuba.workers.dev on web revision `openpaper-00014-vjm`
with 100% traffic. The reviewed source commit is
`c757bbf00d6d1223eb1e1c489086a24d3de9512a` on
`feat/native-investigation-workspace`. The thumbnail repair is included. Authenticated current-account production UI acceptance remains open.

The work preserves the existing project library, discussions, PDF reader, legacy
briefs and the separately reviewed thumbnail repair. No live paid inference,
real research edits/imports, bulk maintenance or sibling repository changes were
used to demonstrate the feature.

**What changed.** Projects now have Case, Evidence and Draft views sharing one
explicitly saved investigation. Case records the research question, provisional
answer, unresolved tension, proposed discriminating experiment and ordered
claims. Existing imported briefs or descriptions can explicitly initialize an
unsaved case without manufacturing findings or rewriting the original brief.

Evidence attaches exact extracted-text line ranges and hashes from current
project sources. Findings separate observed results, authors’ interpretation,
our interpretation, setup and limitations; a finding can support, challenge or
qualify different claims. The comparison presents source setup/quotations and
records a candidate reconciliation without declaring a causal conclusion or
novelty from source counts.

Draft supports editable/reorderable sections, manual paragraphs, captured source
quotations and evidence gaps without model credits. Citations return to the
finding and existing PDF pane. Dependency pins flag changed source wording,
claims, interpretations, setup, relationships or archives. Ordinary Save retains
old pins; explicit review updates them. Quotation blocks retain their insertion
snapshot through source rebinding until reviewed. Unavailable captures redact
from subsequent reads and exports while authored prose remains intact.

Assistant drafting is explicit. A review shows chosen and omitted evidence,
instructions and configured provider. Generate creates one durable request
identity and uses the existing chat quota/message accounting. Duplicate/replayed
or uncertain requests never silently start another provider call. Empty/error,
invalid markers, cancellation and timeout preserve the manuscript. Proposals
remain separate until Insert; Discard does not change it. Source inspection can
open the PDF without losing the proposal. AI attribution and human-edit markers
remain visible after acceptance and ordinary editing.

Folded preview uses the actual pinned upstream Textfold pieces/layout/zoom/map
engine in scoped native DOM. It supports five levels, keyboard, wheel/pinch,
local expansion and map links, retaining source links and per-block attribution.
It has isolated theme/scroll/events and tracked cleanup. Original vendor inputs,
license and notice are unchanged. Local annotations export explicitly under
user/project/document/version namespaces; they are not automatically shared.

Saved bundle/Markdown/BibTeX exports recheck source access and show evidence,
provenance and missing/uncited limitations. Bundle import previews remap IDs,
mark provenance imported and leave all sources unbound. Offline recovery retains
authored work but removes captured source snapshots/bibliography. Conditional
ETag saves preserve local work on conflict/failure; leave/reload cancellation
keeps unsaved text. Viewer reading controls work independently of edit permission.

Usage guide: [INVESTIGATION-WORKSPACES.md](../INVESTIGATION-WORKSPACES.md).
Detailed acceptance matrix and commands:
[VERIFICATION-investigation-workspace.md](VERIFICATION-investigation-workspace.md).

**Milestones.** M0 preserved the dirty thumbnail baseline and recorded the review
base09bf3bae. M1 completed native extraction/lifecycle. M2 completed state/API/
source authorization and migration. M3 completed Case/Evidence/comparison.
M4 completed manual manuscripts and dependency review. M5 completed the durable
assistant flow with fake providers. M6 completed export/import/compatibility.
M7 passed implementation review and automated release/public checks; authenticated current-account production UI acceptance remains open.

**Verification.**

| Check | Executed result |
| --- | --- |
| Required isolated PostgreSQL |100 tests, zero skips; actual HTTP/DB persistence, roles, sources, concurrency, atomic rollback, ledger and disposable migration |
| Full server |484 tests OK;60 guarded integration skips covered separately above |
| Jobs |21 tests OK |
| Cloudflare Worker |2 pass |
| Local research tools |36 OK |
| CI tools |5 OK |
| Client TypeScript/production build |Pass; existing image/unused-directive/metadataBase warnings only |
| Parser/vendor/native generation/client schema |Pass, including exact source fidelity, license/notice, graph/UTF-8 bounds and offline capture redaction |
| Native browser |Two instances, actual five-level wording, keyboard/finder, map, wheel/pinch, local expansion, scrolled overlays, source version replacement, theme isolation and 20-cycle cleanup accounting |
| Production investigation browser |1440/390; canonical two-source journey, comparison, manual/source-quote/AI insertion and discard, source PDF, viewer read controls, brief-only initialization, reload/conflict/failure/cancel, native attribution/source callback, theme and reduced motion |
| Legacy production browsers |Research-overview and project-workflow suites pass at 1440/390 |

All provider tests used instrumented fakes. Local API mocks mutate saved backing
state, enforce ETags and reject unexpected calls; separate PostgreSQL HTTP tests
cover real persistence and security. Screenshots and logs are retained under
`.meos/artifacts/investigation-workspace/`; persistent results and exact commands
are in the verification document. The pre-existing socket-only PostgreSQL
cluster was inspected before deliberate `--run-existing` use and left running.
Only this session’s managed frontend process was stopped after browser checks.

**Independent review.** Final report
[REVIEW-investigation-workspace.md](REVIEW-investigation-workspace.md), source
`.meos/reviews/20261111T012737Z.md`: **accept, no findings**. Earlier important
findings led to actual fixes/regressions for source snapshots, native provenance/
links, viewer controls, brief-only initialization, AI provenance/staleness,
long quotations, local coordinates/overlays/cleanup and navigation recovery.
A missing native-preview assertion was corrected and rerun before final acceptance.

The reviewer independently passed TypeScript, parser/vendor/native reproduction,
client validation, 19 focused Python tests, Worker and diff checks. It assessed
full DB/build/browser/job evidence from author logs; its read-only sandbox refused
existing PostgreSQL and blocked temp writes or timed out other suites. Those
checks are author-executed evidence, not independently rerun results.

**Executed release.** GCP project `openpaper-sammatuba`, region
`asia-southeast1`, canonical origin `https://papers.sammatuba.workers.dev`.

| Item | Exact result |
| --- | --- |
| Source |`c757bbf00d6d1223eb1e1c489086a24d3de9512a` |
| Cloud Build |`d954bd84-bcb0-47a5-9f23-0bd68205989e` SUCCESS; all five locked images published |
| Build tag |`investigation-c757bbf00d6d` |
| Migration |`openpaper-migrate-dl2kh` succeeded; head `project_investigation_01` |
| Web |`openpaper-00014-vjm` Ready, 100% traffic |
| Client digest |`sha256:6fd6c133e197cdd194fd0dffaf239f87baaede9db2a36f807ef328885437aac6` |
| Server digest |`sha256:8b1338998c474295c800b1a03cc690b50c25bec1c269e2bc4a88492cde7de5ea` |
| Jobs |Unchanged `openpaper-jobs-00009-fdw`; anonymous403 |
| Staged/public smoke |57 HTTP/asset checks each; 45 served JS entry bundles each |
| Temporary stage tag |Removed after public acceptance |

The build used an exact git archive with runtime environment files excluded.
Migration used the resolved server digest before web rollout. New web was staged
with prior revision100%, inspected and smoke-tested before traffic. Actual
container digests match the build; old/new revision specs excluding images are
identical. Existing Caddy image, runtime identity, secrets, queue, jobs service,
backup and schedules were preserved. Only server/client were replaced.

Public checks cover homepage/health, Evidence/Draft routes, new API auth
boundaries, OAuth/MCP discovery and no-store401, credentialed CORS/If-Match,
native asset and compiled new-client/canonical-origin bundles. They passed again
through the canonical Worker hostname after switching traffic. Readiness, exact
images and 100% traffic were verified once more after removing the stage tag.

Two rollout probe issues were corrected: exported namespace caused a CLI
project-lookup error (removed without enabling another API), and the initial
OAuth metadata probe used the wrong path (corrected to the advertised resource
path). Neither changed application data or exposed traffic to an unready revision.

Rollback restores `openpaper-00013-7qj` at 100% traffic:

```bash
rtk proxy gcloud --configuration=personal --project=openpaper-sammatuba run services update-traffic openpaper --to-revisions=openpaper-00013-7qj=100 --region=asia-southeast1
```

Keep the additive schema and authored records; do not downgrade/drop them as
application rollback. Fresh original images/status are retained in
`live-before.json` and `revisions-before.json`. Source is committed locally on
the feature branch; no push or merge was performed. Final report/evidence updates
are a separate documentation commit.

**Limits and account acceptance.** The feature organizes evidence and authorship;
it does not verify scientific truth, establish novelty or perform experiments.
PDF page mapping remains unknown when it cannot be proved. Imported sources need
explicit current project binding. Old brief annotations remain browser-local.
No current operator browser/session is exposed to this execution environment;
authenticated production UI/Google account acceptance has not been exercised.
Old temporary pilot authorization is not reused to manufacture an owner session.
Live paid AI acceptance remains a separate explicit user action.
