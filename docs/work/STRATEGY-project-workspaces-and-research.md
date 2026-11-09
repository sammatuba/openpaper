# Project workspaces, research enrichment, and fork architecture

Date: 2026-11-04. Phase: strategy completed; implementation packages proposed.
Request: use remaining Codex allowance productively, consider a local directory
per OpenPaper project, and inspect the personal fork for gaps and opportunities.
The operator selected all three priorities: research outputs, project workspaces,
and reliability. This record adds to the earlier ecosystem strategy.

## Recommended direction

Connect the existing reading application to versioned research workspaces.
Use the remaining allowance to produce a complete small example: a bound local
project, reproducible evidence records, a prior-work comparison, and a runnable
offline experiment specification. Fix the concrete reliability defects that
would undermine that example. Expand after this loop works.

Keep the current Cloud Run, Neon, GCS, Cloud Tasks, and Cloudflare architecture.
It already supports this personal workload. Inspection did not establish a
need for another database, a graph service, a vector service, or an agent
orchestration platform. Semantic retrieval becomes a candidate after measuring
lexical retrieval misses on actual research questions.

Suggested effort allocation across subsequent implementation: 40% research,
30% workspace integration, 30% reliability and verification. These are priorities,
not predictions of remaining messages, tokens, or completion time. Actual limits
and reset times must come from the account usage dashboard or CLI `/status`.
Codex/Work allowance does not pay for this fork's Vertex AI, Exa, storage, or
Cloud Build operations. No new paid inference, search batch, cloud job, or import
was started in this strategy pass.

## What was actually inspected

- Local `master` remains at `40e390800668`, with the earlier implementation
  changes uncommitted. The recorded latest server deployment is revision
  `openpaper-00009-fb9`; the PDF-viewer SSR correction remains local/undeployed.
  This pass did not independently query the live Cloud Run revision.
- The connector available in this conversation exposes seven older tools.
  An authenticated `list_projects` call succeeded and returned one project:
  `a5cf0e26-f8dd-424c-a452-dbcf6ebba946`, “Did They Collude or Just Agree?
  What Counts as Evidence of Collusion Among AI Reviewers,” with an empty
  description. The current source registers 15 tools. A browser being signed
  out does not establish failure of this separately authenticated connector.
- Read-only inspection of `../ai-safety` found four dated project directories,
  48 dossiers, and 48 generated paper cards. Dossier frontmatter labels 43
  `stub` and five `pass1`; this measures recorded status, not an independent
  assessment of how much each paper has been read. For example T17 records
  full-text extraction while retaining `pass1`.
- Current landscape exports contain 3,598 sources, 4,405 search hits, 583
  snapshot records, 13 relations, and zero claim rows. Zero claim rows does
  **not** mean that the written dossiers or report contain no evidence.
- The corpus manifest contains 50 entries: three completed and 47 awaiting
  selection. All three completed entries currently have `project_id: null`.
  That manifest field does not prove their present live project membership.
  Existing pilot entries and the stale duplicate were left untouched.
- Read the deployment templates, backup script, queue configuration, CI,
  MCP/retrieval/upload code, database models, passage backfill, research tools,
  evaluation README, and the adjacent research repository's routing rules,
  current proposals, roadmap, extraction rules, and landscape documentation.

These are source/local-record findings unless explicitly described as a live
connector result. No production database, cloud IAM, billing, bucket policy,
backup inventory, or attachment handoff was audited in this pass.

## Local directory per OpenPaper project

Adopt the idea with one qualification: `ai-safety` is already a research program
with a shared literature library and several deliverables. Preserve that layout.
Bind an OpenPaper project UUID to an existing project subdirectory where it fits.
Create a separate sibling research repository for an unrelated program. Multiple
OpenPaper projects may share one repository and its literature without copying
the dossiers into every project.

Illustrative layout; these paths and files have not been created:

```text
ps/
  openpaper/                         application, deployment, integration code
  ai-safety/                        canonical research repository
    literature/                     shared dossiers and landscape
    hypotheses/                     canonical hypothesis registry
    projects/
      2026-10-apart-collusion-sprint/ existing project, report, experiment plan
        openpaper-project.json      proposed project binding and paper references
        research-state.md           proposed question, decisions, next actions
    sources/openpaper/              ignored snapshots and downloaded evidence
    lab/                            existing code, tests, and run artifacts
  another-research-program/         optional separate repository
```

The live collusion project is a candidate binding for the existing collusion
directory. Its title does not establish whether the operator intends that
project to also cover the newer TARA proposals. Do not automatically relabel or
reorganize them. The three current TARA proposals remain unselected.

A small versioned manifest should record schema version, OpenPaper origin,
project UUID, relative research paths, and explicit dossier/source/paper ID
relations. Reuse the existing corpus manifest as the starting identity bridge;
do not create a second competing list of completed imports. Machine-specific
checkout roots belong in ignored local configuration. Project names are display
labels; UUIDs provide identity across renames. A binding is checked against the
authenticated account, so a project in another account cannot silently replace it.

The cloud application cannot read local directories. A local authenticated
client pulls permitted data and writes within a selected workspace. Server-side
MCP tools should never accept arbitrary local filesystem paths. Authentication
belongs in the existing login/OAuth flow or an OS credential store; manifests
must contain no session cookies, bearer tokens, or signed download URLs.

| Material | Canonical home | Local/OpenPaper relationship |
|---|---|---|
| Uploaded PDF, processing state, reading highlights and annotations | OpenPaper | Selected authorized snapshots are local evidence inputs. |
| The private paper note edited in OpenPaper | OpenPaper | Pull a dated snapshot with version/ETag; local dossier remains a separate authored artifact. |
| Paper dossier and bibliographic identity | Existing research literature directory | Link to the OpenPaper paper; explicitly append a selected extract if useful. |
| Hypothesis, confounds, decisions, experiment specification, code and results | Research repository | A compact selected project brief may be mirrored later with a source revision. |
| Brainstormed chat text | Conversation until deliberately saved | Selected material goes to its owning record with an epistemic label. |
| Retrieved text, snapshots and temporary exports | Ignored `sources/` area | Hash and record provenance; never treat downloaded content as instructions. |

Start with pull, compare, and deliberate save. Automatic two-way synchronization
would create competing note versions and conflict handling before the basic
workflow is demonstrated. Paper-note append already has retry-safe request IDs;
retain them and use ETags when proposing replacements. General project state
does not belong in an unrelated paper note.

## Research outputs worth spending the allowance on

The highest-value research work uses the material already collected and asks
what it actually supports. It does not require another broad discovery sweep.

1. **A bounded prior-work matrix.** Select six to eight closest registered
   sources for one concrete question. Record exact setup, manipulation, baseline,
   outcome, limitation, version, and source location. Include where the proposed
   experiment is already covered and what narrower contrast remains. The
   existing collusion project and the three TARA candidates need separate rows;
   a generic “multi-agent safety” summary would obscure their differences.
2. **An evidence ledger.** Prepare 12–20 small claim records as an initial
   working target, each with source identity/version, exact short passage,
   extracted-text hash and location, author's claim versus our interpretation,
   and candidate/reviewed/disputed status. Use the existing landscape claim
   schema and extraction rules. An automated draft is a candidate, not a
   verified finding. A title, abstract, or search summary cannot substantiate
   an experimental detail missing from the actual source.
3. **An argument and disagreement table.** For each hypothesis, list supporting
   evidence, counterevidence, alternative explanations, untested assumptions,
   and a result that would change the conclusion. Agreement alone does not
   establish collusion. Conditional catastrophic-risk arguments remain distinct
   from measured outcomes.
4. **Offline experiment preparation.** Build a few matched synthetic examples,
   executable outcome rules, ordinary software baselines, and validation checks.
   Keep prompt development and held-out cases distinct. These fixtures test the
   task/scorer; they do not establish how a model behaves. A later paid model
   run requires its own explicit project budget.
5. **A resume packet.** Generate a bounded brief containing the current question,
   selected hypothesis IDs, closest work, decisions, unresolved objections, and
   the exact next task. Reuse `ai-safety/tools/pack.py` and existing project
   records before adding new note storage or another dashboard.

Useful source groups already registered locally include T23/T24/T14/T25 for
cancellation and replanning; T20/T21/T26/T10/T11 for evaluation and measurement;
and T22/T17/T27 for interacting responsibilities. These are candidate reading
sets based on existing dossiers, not newly verified scientific conclusions.
The collusion project's R-series sources provide a separate comparison set.
The user's selected MT-Bench paper remains an import/registration candidate;
this strategy pass did not verify its text or add it to the bibliography.

## Architecture gaps and opportunities

Priority means order of attention for this personal research workflow. It is
not a published vulnerability rating. Existing protections and previous review
acceptances remain useful; the findings below do not invalidate all prior work.

| ID / priority | Finding and evidence | Proposed response and observable check |
|---|---|---|
| A01 / first | **Backfill dry run mutates state and can repeat forever.** `server/app/scripts/backfill_paper_passages.py:50` disables a global text-index trigger and commits before checking `dry_run` at line 85. The dry-run loop does not advance the selected batch. Trigger restoration is on the success path, not in `finally`. | Make dry run SELECT-only and finite; avoid globally disabling the trigger for the normal maintenance path. Check zero mutation/commit calls, multi-batch termination, interruption behavior, and unchanged trigger state on an isolated database. Do not use the current dry-run command as a production diagnostic. |
| A02 / first | **PDF URL policies differ by entry path.** MCP downloads pin public DNS addresses, validate each redirect and enforce a process deadline. Browser URL import calls `server/app/helpers/parser.py:117`, which uses ordinary redirect-following Requests HEAD/GET without equivalent public-address or total-deadline checks. | Extract a neutral shared download service and reuse it for browser and MCP imports. Check private/reserved addresses, redirected targets, DNS rebinding, invalid PDFs, and slow responses through both entry points. This is a confirmed code-policy difference; no live private-network request or exploit was attempted. |
| A03 / first | **Production/source traceability is incomplete.** The latest server rollout includes uncommitted source; the accepted frontend correction remains undeployed. Some handoff sections retain superseded next steps. | Review and checkpoint the current tree in coherent changes; record source tree/commit, build digest, migration and smoke evidence per release. Align the client rollout when authorized. A clean checkout should reproduce the intended release. Keep historical deployment evidence labelled as historical. |
| A04 / first | **Critical tests are not routinely exercised by CI.** `.github/workflows/test.yml` runs server unittest discovery only. PostgreSQL transaction/recovery suites require an opt-in variable and a specific local cluster, so default CI skips them. Jobs tests, Worker tests, research-tool tests and client checks are absent from this workflow. A migration test also contains a developer-specific absolute path. | Add bounded CI lanes with an explicitly disposable PostgreSQL instance and no live credentials; make expected integration checks fail rather than skip silently in that lane. Run jobs, Worker/research tests and client type/build checks as appropriate. Remove machine-specific paths. Do not weaken production-DB refusal guards to make CI green. |
| A05 / first | **Deployed capability and account capability diverge.** Current source advertises 15 tools, but this conversation has seven. Project listing works with connector OAuth; direct URL/attachment upload acceptance is still open. | Add a versioned capability manifest/diagnostic that can be compared across server protocol tests and the selected ChatGPT connection. Refresh/toggle tools in app settings; verify search/fetch, fresh project context, selected note save/readback, URL import and a real attachment separately. Protocol success is not attachment handoff acceptance. |
| A06 / next | **Import completion is not evidence-index readiness.** Paper text processing and subsequent passage indexing have distinct paths in `server/app/api/webhook_api.py`; MCP searches passages and rejects stale text on fetch. There is no project coverage report in the current MCP interface. | Expose read-only text/index readiness and coverage counts: papers with text, indexed text, stale/failed indexing, missing page maps. Persist/reconcile indexing work across request loss as needed. A completed import should explain when it is searchable; zero matches must not imply absence. Fix A01 before attempting maintenance backfills. |
| A07 / next | **Identity and deduplication are fragmented.** `mcp/uploads.py` claims are byte/user/destination-specific; UI, Zotero and the corpus tool use other identities. The Paper model has DOI/provenance but no common durable source-version/content-hash identity across these paths. | Extend the existing identity bridge and add a common owner-scoped identity service. Preserve work identity, exact version and byte hash separately. When a known paper is selected for another project, associate the existing paper rather than repeat inference. Version differences, mirrors and ambiguous DOI matches require explicit reconciliation; titles alone are insufficient. |
| A08 / next | **Project context is not a complete export.** `mcp/research.py:137` paginates papers, but embeds five highlights/annotations per paper. Highlight results report `has_more` without a cursor; legacy annotation listing discards that flag. Note content has proper offset/version metadata. | Add stable pagination and explicit completeness/version information before offering lossless snapshots. Reuse an authorized export service for local CLI and MCP. Test a project exceeding every page limit, interrupted pull, revoked membership, private notes, changed notes and deleted papers. Snapshots must identify omissions. |
| A09 / next | **Uncertain uploads require difficult manual recovery.** Durable MCP claims intentionally avoid blind re-enqueue; a crash after claiming can leave a pending job. Persisted outcome replay protects processing already checkpointed, but does not resolve every pre-dispatch or pre-checkpoint failure. Queue retry duration is configured at 24 hours. | Build a read-only reconciliation report joining job/task/paper/outcome state, age and possible next action. Add explicit reviewed recovery operations only after the report is useful. Never present stuck-job retry as guaranteed inference-once execution. Preserve the existing stale duplicate until inspected. |
| A10 / next | **Backup creation is proven more strongly than restoration.** The work record documents dump/upload/prune. `deploy/backup/backup.sh` backs up Postgres into the same storage bucket; source templates use a shared runtime service account. A full restore drill and current object-retention settings were not established here. | Restore a selected backup into a disposable database, verify notes/IDs/memberships and referenced PDF availability, then destroy the test. Record recovery time and missing dependencies. Inspect live bucket versioning/outcome lifecycle and secret recovery separately. Consider separating backup retention and runtime permissions so an application deletion cannot also remove all recovery copies. |
| A11 / next | **Research answer quality is not measured for this corpus.** Existing ResearchQA evaluates a broader paper-chat pipeline and includes model grading. It is not a demonstrated acceptance set for this MCP/local-workspace workflow. | Create roughly 20 hand-checkable project queries with expected sources and explicit no-evidence cases. Score retrieval, exact text identity, citation location, unsupported claims, pagination and access. Use independently reviewed anchors before an LLM judge; correlated judges are especially relevant to this research topic. No paid benchmark run is implicit. |
| A12 / measure first | **Long imports and project context may contend for a small service.** Templates allow 20 web requests and a 15-connection server pool. MCP imports open a session before an external download. Project context performs repeated per-paper note/highlight/annotation lookups. No pool-saturation failure was reproduced. | Measure query count, cold/warm latency, connection checkout duration and bounded concurrent imports. Release transactions around network work and batch reads where measurements justify it. Keep single-user scale-to-zero defaults until latency/cost evidence warrants a change. |
| A13 / next | **Operational visibility remains mostly logs and manual observations.** Queue retries and health checks exist; the inspected deploy scripts do not provision stuck-job, indexing, backup-age or billing alerts. One-week cost/idle-login checks remain open. | Add a compact read-only doctor/status report and minimal alerts for actionable failures. Distinguish expected idle cold starts from failures. Verify actual cloud settings before asserting alerts are absent or quoting costs. Max instances/concurrency constrain load, not total inference spend. |
| A14 / later | **Research state is not directly available to ChatGPT.** The local hypothesis/idea/map records and project decisions do not appear in paper-only MCP context; the live project description is empty. | First generate a concise local resume packet and allow an explicitly selected versioned brief to be published to project context. Consider read-only hypothesis/evidence/landscape queries later. Any cloud access to local records requires an explicit export/publish step; a local directory alone does not expose it. |

## A small vertical implementation sequence

Each package should finish with a usable artifact and verification record. A
quota interruption should leave the next package unstarted, rather than leave
all three tracks half-built. The names below are proposed work packages, not
already available CLI commands or MCP tools.

| Package | Concrete deliverable | Done when |
|---|---|---|
| W0: stabilize the baseline | Fix A01/A02, make the core recovery/database checks reproducible in CI, reconcile current release/source records. | Dry run is finite/read-only; both URL entry paths share protections; isolated integration checks run deliberately; deployment provenance and remaining account acceptance are explicit. |
| W1: bind and inspect one workspace | Versioned project manifest plus local `bind`/`doctor` functions. Reuse the existing `ai-safety` layout and corpus IDs. Implement the client code in the OpenPaper integration area. | UUID survives rename; account/project access is checked; wrong workspace/path traversal is rejected; repeat bind is harmless; no credentials or machine roots enter versioned data. Initial binding target is confirmed before writing into the research repository. |
| W2: pull and resume | Complete paginated project snapshot and a bounded context packet from selected local records. Immutable raw input goes under ignored sources; authored files receive a proposed diff. | A second unchanged pull makes no authored diff; interrupted pulls leave no partial promoted snapshot; changed ETags and revocation are detected; omitted/truncated data is disclosed; existing dossiers/notes are preserved. |
| R1: deepen the selected question | Six-to-eight-paper prior-work matrix, candidate evidence ledger and disagreement table. | Every research claim has an inspected source/version/location; unsupported comparisons are marked; novel contribution is a proposed delta against the closest work, not asserted by default. |
| R2: prepare the experiment | Matched synthetic cases, deterministic scorer/control tests, and a budget-ready run plan. | Cases and scoring run locally without provider calls; confounds and stopping rules are recorded; code fixtures are distinguished from model results. |
| W3: verify the complete loop | Project retrieval acceptance set, account-side direct import/save checks, read-only reconciliation report, selected backup restore drill. | One selected source can be read, linked to a local claim, used in a bounded comparison and resumed in a fresh context, with provenance and no duplicate expensive processing. Account-only failures remain explicit rather than being counted as passes. |

If only one implementation cycle fits, target **W0 plus a minimal W1 and one R1
comparison**. This produces infrastructure improvement, a real project binding,
and research output. Defer advanced synchronization, dashboard work and broad
collection. If more allowance remains, complete W2/R2 and expand the acceptance
set. Selection of a TARA research question remains an operator decision, and
inspection in this repository does not move its dated submission or experiment
records forward.

## Alternatives and what would change the choice

- **Everything inside OpenPaper:** convenient single interface, but needs new
  general project-note, experiment and version-history semantics. Reconsider
  after local packets prove materially awkward, with conflict handling designed.
- **Every OpenPaper project gets an independent Git repository:** useful for
  separate collaborators/programs; duplicates shared AI-safety literature and
  policy if applied mechanically. Prefer project subdirectories for this program.
- **Automatic two-way sync:** convenient only after artifact ownership, complete
  pagination and conflict handling are proven. Start with deliberate pulls/saves.
- **Vector/graph infrastructure:** justified by measured unanswered queries or
  relation operations beyond existing PostgreSQL/SQLite and generated maps.
  Current counts alone do not demonstrate that need.
- **Autonomous research agents:** consider bounded source tasks after source
  fidelity and output validation work. Multiple model opinions do not constitute
  independent empirical evidence. This strategy did not launch worker agents.

Material unknowns: exact remaining allowance/reset; account-side file handoff;
chosen mapping of the collusion project versus newer TARA work; project membership
of the existing pilot papers; live index coverage; current cloud costs, alerts,
IAM and backup retention; citation accuracy on actual selected research questions.

## Verification and handoff

Executed in this strategy pass:

- MEOS startup under Codex; read-only source and adjacent-repository inspection.
- Authenticated connector project listing; tool metadata inspection.
- Python counts of current local exports, dossier frontmatter and corpus states.
- A fake-database execution of the actual AST-extracted `backfill` function,
  with no application imports or real database access. With `dry_run=True`
  and zero unindexed papers, it issued ALTER/UPDATE/ALTER and three commits.
  With one unindexed paper, the same batch was selected repeatedly; the harness
  deliberately stopped on the third selection. The exception path closed the
  session without issuing the trigger-enable statement. This establishes A01's
  control-flow defect without changing a database.
- Documentation JSON/link/diff validation, recorded with the work pointer.

Independent strategy review `.meos/reviews/20261104T042621Z.md` accepted the
assessment with no material findings. The reviewer checked source evidence,
JSON, local links and diff whitespace; it did not rerun the fake-database
reproduction or application integration suites. This is strategy acceptance,
not implementation acceptance. No application code was changed, no production
import or database maintenance ran, and no sibling research files were edited.
Proposed fixes still need bounded intent, implementation checks and independent
MEOS review. Include this currently untracked document in any later commit.

Official OpenAI documentation opened on 2026-11-04:

- [Work/Codex pricing and usage](https://learn.chatgpt.com/docs/pricing): account
  dashboard/CLI status for actual limits; API-key usage has separate API pricing.
- [Custom MCP management](https://developers.openai.com/api/docs/guides/custom-mcp-server):
  app details support refreshing tools, descriptions and instructions.

Next implementation intent: W0, beginning with a truly read-only, terminating
passage-maintenance dry run and a shared PDF-download policy, then W1's small
project-binding contract. Carry R1 alongside the workspace example once the
research target is fixed. Preserve the outstanding live connector acceptance
and the uncommitted earlier implementation throughout.
