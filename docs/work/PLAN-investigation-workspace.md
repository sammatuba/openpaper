# Investigation workspace — execution plan

Contract: [INTENT-investigation-workspace.md](INTENT-investigation-workspace.md).
Checks: [ACCEPTANCE-investigation-workspace.md](ACCEPTANCE-investigation-workspace.md).
Resume: [HANDOFF-investigation-workspace.md](HANDOFF-investigation-workspace.md).

This document makes the implementation decisions for the first complete release.
File names for new modules are intended destinations; split private helpers when
useful while preserving these public contracts. Do not stop after a milestone
and describe the whole feature as complete.

## 1. Baseline and existing seams

Baseline HEAD is `09bf3bae02ed55a1537b0f4a71a01e536f17b0b3` on master.
The local thumbnail repair is reviewed, uncommitted and undeployed. It touches
server paper/project/search serialization, S3 preview signing, the project
metadata query, the isolated test runner and a new preview test. Preserve it.
The new work must be tested with that repair included.

| Existing seam | Use in this feature |
| --- | --- |
| `client/src/app/(main)/(protected)/projects/[projectId]/layout.tsx` | Keep the project shell, uploads, navigation and source reader. |
| `client/src/components/project/ProjectWorkspaceProvider.tsx` | Add investigation data/state; keep papers and conversations fetched once. |
| Project `page.tsx`, `ProjectRail.tsx`, `ProjectHeader.tsx` | Case entry and Case/Evidence/Draft links, including mobile navigation. |
| `ProjectResearchOverview.tsx`, `EditProjectDialog.tsx` | Preserve the legacy brief entry and its existing admin-only edit rule. |
| `components/textfold/TextFoldReader.tsx`, `lib/textfold-upstream.tsx` | Replace new-flow frame mounting with native mounting; retain tested format adapter and source fidelity. |
| `client/public/vendor/textfold/UPSTREAM.json` | Pinned upstream input, Apache license, notice and existing optional-takeaway patch. |
| `server/app/api/projects`, `database/crud/projects`, `database/models.py` | Project access, new persistence and API registration in `app/main.py`. |
| `server/app/mcp/research.py` | Reuse bounded project passage search; enforce project-paper association for every new source read. |
| `Paper.raw_content`, `Paper.page_offset_map`, `PaperPassage` | Canonical extracted wording, optional page mapping and existing search index. |
| `server/app/api/message_api.py`, `llm/base.py`, `database/crud/message_crud.py` | Existing stream protocol, configured providers, usage and saved messages for explicit drafting. |
| `client/scripts/check-project-*.cjs`, `scripts/ci/run_isolated_postgres.py` | Extend real browser and required isolated PostgreSQL checks. |

## 2. Interaction contract

Routes under `/projects/{projectId}`:

- `/` is **Case**: question, provisional answer, unresolved tension and next
  useful test first; below, an ordered outline of claims with finding links.
- `/evidence` is **Evidence**: findings filterable by claim, relationship and
  source status. Comparison shows two selected findings' result, setup,
  limitations and exact quotations beside each other on desktop, sequentially
  on mobile. It does not label every difference a contradiction.
- `/draft` is **Draft**: section outline, paragraph editor and linked evidence.
  Seed the outline only after an explicit Create draft action. Sections are
  editable/reorderable; defaults are Introduction, Related work, Evidence and
  reconciliation, Proposed experiment, Limitations, Conclusion. Experiments
  remain labelled proposed until a human supplies actual results.

Use an ordinary ordered list with explicit Move up/down controls for claims and
sections. Do not add a drag-and-drop library or a freeform graph. URLs can use
`?claim=<uuid>`, `?finding=<uuid>` and `?block=<uuid>` for stable selection; validate
IDs against the loaded project and never show another project's cached item.
Changing views, folding, filtering or choosing evidence causes no write or model
call. Tab selection and source inspection survive opening/closing the PDF pane.

Every editable view shows Saved / Unsaved changes / Saving / Save failed or
Conflict. One workspace-level explicit Save commits the investigation and
manuscript atomically. No silent debounce overwrite. Changing the selected item
keeps its local edits in the provider. A leave warning covers unsaved changes;
offer a local JSON download before discard/reload. No sensitive document copy
is persisted to localStorage as an implicit recovery mechanism. Fold/selection
preferences may be persisted under the signed-in user/project/version key.

At 1440px, use the existing shell with a readable central case/draft and the
on-demand inspector. At 390px, show one primary view at a time, with an accessible
inspector sheet and a Back action restoring selection/scroll. Do not stack the
navigation sheet, source reader and evidence inspector over each other. Keep
Artifacts opt-in and preserve saved rail/artifact preferences. Use OpenPaper's
theme and typography; surface provenance close to the relevant text.

## 3. Persistence and document schema

Add an additive Alembic revision `project_investigation_01`, whose parent is the
then-current single Alembic head (currently `project_research_brief_01`). Never
create a second head or modify an old deployed migration.

Add `ProjectInvestigation` / table `project_investigations`:

- `project_id`: UUID primary key, FK `project.id ON DELETE CASCADE`.
- `schema_version`: integer, exactly 1.
- `revision`: positive bigint; increments for every actual document save.
- `document`: non-null JSONB, strict Pydantic document below.
- `updated_by`: nullable user FK with SET NULL; standard created/updated times.

One bounded document gives atomic case/manuscript saves and avoids a partially
saved claim/evidence/draft graph. No append-only history/version browser in this
release; the dependency pins below preserve what a paragraph was based on.

The `openpaper/investigation` v1 document has these fields; unknown fields are
rejected. It is separate from the existing extensible `textfold/doc` v0 format.

| Field | Shape and purpose |
| --- | --- |
| `format`, `version` | Literal `openpaper/investigation`, strict integer 1. |
| `case` | Strings `question`, `why_it_matters`, `landscape`, `coverage_limits`, `provisional_answer`, `unresolved_tension`, `reconciliation`, `discriminating_experiment`, `update_criteria`. Optional ISO search date; blank stays blank. |
| `claims` | Ordered records `{id, statement, reasoning, caveats, archived}`. |
| `findings` | `{id, label, observed_result, author_interpretation, our_interpretation, setup, limitations, source, archived}`. Setup has strings `model`, `task`, `training`, `intervention`, `evaluation`, `other`; never manufacture absent values. |
| `relations` | `{id, claim_id, finding_id, relation, rationale}`; relation is `supports`, `challenges` or `qualifies`. The same finding may relate differently to different claims. |
| `manuscript` | `{title, sections}`; sections are ordered `{id, title, blocks}`. |
| Draft block | `{id, kind, text, claim_ids, finding_ids, provenance, dependency_pins, quote_snapshot}`. Kind is `paragraph`, `source_quote`, or `gap`. References are UUIDs in this document. Source quotes reference exactly one finding and retain a server-controlled insertion `quote_snapshot` (verified anchor or transport-redacted placeholder, nullable until binding). Rebinding the finding preserves that access-checked capture until explicit block review; user prose is a paragraph, never a fabricated source quote. |
| Provenance | `human`, `assembled`, `assistant` or `imported`; assistant provenance includes an authorized local request/message ID. Imported provenance retains an origin label and original IDs as untrusted origin metadata, never as local authorization. Record insertion time/actor on the server. Model-authored text remains AI-authored after ordinary human editing, with an edited marker. |
| Dependency pins | Server-computed SHA-256 digests of the claims, findings, relations and source versions used by that block when inserted or explicitly reviewed. |

All object IDs are UUIDs, unique across the document; duplicate relation triples
are rejected. Maximum 100 claims, 500 findings, 1000 relations, 30 manuscript
sections and 1000 total blocks. UTF-8 serialized document must fit 2,000,000
bytes; strict integers reject booleans. Case fields and reasoning/interpretation
fields are at most 20,000 characters each; labels/titles at most 500, claim
statement at most 2,000, draft block text at most 10,000. An exact quotation is
nonempty and at most 20,000 characters. Apply the byte bound to the canonical
server document too. Archive referenced claims/findings; do not silently remove
entities used by relations or paragraphs. Reject dangling IDs and duplicate IDs
with 422. Validate on both client and server; server is authoritative.

Add `ProjectDraftRequest` / table `project_draft_requests` for durable request
identity, not another model service:

- UUID `id` primary key supplied by the client for an explicit Generate action;
  project FK CASCADE and requester user FK, request hash and immutable bounded
  input snapshot, base workspace revision, target section UUID.
- `state`: pending/running/completed/failed/uncertain; timestamps, bounded error
  code; project conversation UUID and final assistant message UUID nullable
  SET NULL on deletion. Keep terminal request identities until project deletion.
- Snapshot holds chosen claim/finding/relationship digests and verified source
  excerpts, selected configured provider and user instructions. At most 20
  findings, 10 claims, 32,000 source-context characters and 128,000 UTF-8 bytes
  per request. Reject oversize selection before creating a conversation.

Implement schemas in `server/app/schemas/investigation.py` and client contracts
in `client/src/lib/investigation.ts`. Keep the existing description and
research_brief columns untouched. GET of a legacy project returns a virtual
empty investigation with revision 0; a legacy brief remains available beside
it. An explicit **Start from existing brief** copies only the human-reviewable
question/context/synthesis fields into an unsaved form. It creates no claims,
findings or citations automatically and never overwrites the original brief.

## 4. API, authorization and concurrency

New router: `server/app/api/projects/project_investigation_api.py`, mounted
under `/api/projects/{project_id}/investigation`. Use shared service/CRUD modules
for project access, document validation, anchors and drafting; do not import the
MCP server initialization path merely to reuse its retrieval helpers.

| Method and suffix | Contract |
| --- | --- |
| GET root | Return `{document, revision, validation}` and strong ETag `"investigation:<project UUID>:<revision>"`; no database write. Virtual empty state uses revision 0. |
| PUT root | Body `{document, reviewed_block_ids: [], reviewed_proposal_ids: []}` and required `If-Match`. Atomically validate and save; return canonical body + new ETag. Explicit reviewed IDs refresh pins only after current source checks; ordinary edits retain previous pins. |
| GET `/sources/search?q=&limit=` | Project-scoped indexed passage search, q 1–200 chars and limit 1–30. Reuse existing retrieval semantics and disclose indexed-only coverage. No search hit is a finding until explicitly attached. |
| GET `/sources/{paper_id}?start_line=&line_count=` | Project-associated paper only. Return exact numbered extracted-text lines, source SHA-256 and current bibliography. At most 200 lines and 20,000 chars; if the requested slice exceeds the bound, ask for a smaller range rather than silently truncating a quotation. |
| POST `/draft-requests` | Create/reuse pending request and its existing-format project discussion atomically, after source/permission/quota validation. Body includes request UUID, base workspace revision, section ID, selected claim/finding IDs, instructions (at most 2,000 chars), configured provider. No model call. Same UUID/hash returns same identity; different payload 409. |
| POST `/draft-requests/{id}/run` | Explicit, single-claim generation stream; see section 7. |
| GET `/draft-requests/{id}` | Request status, resumable discussion link and validated proposal if completed. No generation, no state-changing recovery on GET. |
| GET `/export?format=bundle\|markdown\|bibtex` | Authorized export built from current server state and current source checks. No enrichment/search/model call. |

Read: project owner or current project member. Edit/save: owner or current
admin/editor. Viewer writes/generation get 403; outsider/nonexistent project
gets 404; unauthenticated gets the existing 401. Export has the same read scope.
Draft generation is restricted to its requester with current edit access;
proposal readback additionally requires access to its existing discussion.
Recheck access on every request, including request replays and exports. Never
use an owned paper from outside this project just because the actor can read it.
Do not pull private paper notes/highlights into shared evidence automatically.

PUT without If-Match returns 428. Stale ETag returns 412 and the current ETag;
leave client edits intact with Reload latest / Download my draft / Cancel.
Malformed ETag gets 400; a well-formed ETag for a different project gets 412,
never an unconditional save. Invalid UUID/schema/references get 422; canonical
body or requested source-slice byte/character overflow gets 413. Source-version
conflicts get 409. Credit denial gets 429 before a model stream starts.
The initial revision-0 create must also be conditional: lock the project, check
current role, check/create workspace row, validate then commit. All saves use
the same project → role → workspace lock order. Concurrent first creates and
ordinary saves have one winner and one 412, never a lost update. Lock relevant
project-paper/source rows during new-anchor validation so removal cannot race
the attachment's authorization. DB errors roll back the entire document.

Content and export responses are `Cache-Control: private, no-store`. ETag must
be exposed through the existing credentialed CORS configuration. Keep generic
project listings light; do not add this document to `/api/projects` list output.

## 5. Exact source anchors and dependency changes

A finding's `source` is a discriminated union: `kind: anchored` for a verified
capture and `kind: unbound` for an imported locator awaiting explicit binding.
The redacted read representation is transport-only; clients cannot create a
canonical anchor by submitting `kind: redacted`. Unchanged redacted findings
are merged from the authorized server record on a conditional save.

An anchored finding's canonical `source` snapshot is server controlled:
`paper_id`, `start_line`, `end_line`, `quote`, `source_sha256`, `quote_sha256`,
title/authors/date/DOI snapshot and nullable verified `page_span`. Lines are
1-indexed inclusive in `Paper.raw_content.split('\n')`; quote is exactly
`'\n'.join(lines[start_line-1:end_line])`. Do not normalize whitespace or
line endings after capture. Hash exact UTF-8 text. If supporting imported
Textfold fold anchors, preserve their original sentence numbering separately.
Textfold evidence indexes are never substituted for PDF/extracted-text anchors.

On attach or re-anchor, the server checks current membership and project-paper
association, reads the current extracted text, verifies the selected line range
and whole source hash, and constructs this snapshot. A forged quote or a source
changed since selection returns 422/409 respectively without saving any part.
Resolve page_span only if the existing offset map can prove the page(s);
otherwise show “Extracted text lines …; PDF page not mapped.” No inferred pages.
The existing index may be absent; line-based source inspection still works
without running a backfill. Show index coverage limits for search.

On workspace load, source inspection, assistant request, acceptance and export,
validate referenced sources against current associations and extracted wording.
Batch unique paper reads, load only needed columns, and process raw text one
paper at a time. Do not introduce an N+1 heavy-column query per finding.
Return derived validation separately from stored authored content:

- `current`: whole-text version and selected quotation still match.
- `source_changed`: raw-text hash changed, including when the old quote still
  exists. Keep the captured quote clearly labelled as the old version; show
  current context for explicit review/re-anchor. Never silently move anchors.
- `unavailable`: paper deleted, unlinked from this project, missing extracted
  text, or access lost. Retain a tombstone reference and authored argument.

On a fresh read, unavailable sources expose no captured quote/bibliography to
an actor without current project-source access. Return a redacted placeholder;
PUT roundtrip of an unchanged placeholder preserves the server's canonical
snapshot, cannot replace it or reactivate access. Readback/export/assistant
context reapply redaction; data retained for referential integrity is not a new
grant. Existing authored prose remains authored prose, with missing-source
warnings. A `source_quote` block from an unavailable source is redacted too.

Compute dependency digests over canonical JSON excluding display-only labels
and timestamps but including claim statement/reasoning/caveats, finding results/
setup/interpretations/limitations/source version, and relation kind/rationale.
A mismatch marks the paragraph **Evidence changed — review needed**. Source
status problems take precedence over reviewed pins. Do not rewrite the text or
refresh pins in ordinary Save. **Reviewed changed evidence** is explicit and
only succeeds when selected dependencies are accessible/current; it refreshes
that block's pins in the same conditional save. Relation changes and archived
claims/findings also flag affected blocks. Distinguish missing citations from
an assertion that a claim is false.

## 6. Native Textfold: extraction, lifecycle and integration

Keep upstream commit `92ad625ab6887bf0060374c1fd86a558513baed2` and existing
license/notice. The checked-in reader is a document-global IIFE with window
scrolling, body popovers, root attributes and global events. Inserting that
script into a div unchanged is not a native integration.

Create a static ESM reader factory and React lifecycle wrapper:

```ts
mountTextfold({
  root, scrollElement, document, identity, theme,
  onSelectUnit, onOpenSource, onSelection,
}): {
  setDocument(next, identity): void;
  setLevel(level): void;
  setTheme(theme): void;
  focusUnit(id): void;
  exportLocalAnnotations(): unknown;
  destroy(): void;
}
```

The `document` argument is validated Textfold data, not a fake browser Document.
Use a scoped open ShadowRoot within the ordinary React workspace. A shadow root
is CSS/ID isolation, not a security sandbox. React owns the surrounding cards,
selection, inspector and authoring controls; the upstream engine owns its mounted
reading subtree. One active fold surface per selected item is sufficient for
the product; the adapter must nevertheless pass a two-instance isolation test.

Preserve and adapt actual upstream pieces/layout/FLIP/stage/zoom/map routines:

1. Replace the self-running/global data setup with instance arguments, and the
   global i18n/reader exports with module/instance state. No eval/new Function,
   document.write, hidden iframe or monkey-patching global document/window.
2. Scope ID/query lookups, root attributes, language/theme/type settings and
   popovers/ghosts to the instance. Route scroll, viewport size, hit testing and
   coordinate measurements through its scroll container/owner document, rather
   than window scrollY or the whole app body. Put instance overlays inside its
   own root and clamp them to visible workspace bounds.
3. Register events/observers with tracked cleanup or AbortController; cancel
   animation frames, timers, pending transitions and observers on destroy.
   Guard asynchronous work after unmount or document/user changes. Keyboard
   1–5 and zoom shortcuts work only when the reader has focus and the target is
   not an input/textarea/contenteditable, including inside the shadow root.
4. Scope CSS (`:root`/html → instance host, body → reader surface). Keep ordinary
   page scroll and theme untouched. Theme changes update the active instance
   without resetting reader selection, level or typed manuscript text.
5. Keep the existing local highlight/annotation semantics with user, project,
   document and source-version namespacing. No automatic migration of old
   browser-only annotations into shared findings. Retain an explicit legacy
   annotation export before replacing the old reader on legacy briefs.
6. Hide disconnected model/PDF conversion features. Use OpenPaper source-open
   callbacks and the existing PDF reader, not Textfold's standalone service.
7. Escape text and sanitize generated atom HTML before the native engine sees
   it. Use installed DOMPurify plus existing safe Markdown rendering; reject
   scripts/event attributes/javascript URLs/embedded frames/forms. Imported
   extension fields remain exportable data and are never executable markup.

Suggested files: `client/src/lib/textfold-native/`,
`client/src/components/textfold/NativeTextfold.tsx`, and
`client/scripts/build-textfold-native.cjs`. Keep an auditable checked-in patch
and generator producing ESM/CSS from the pinned vendored inputs. The check mode
must reproduce outputs and verify input/output hashes. Retain the original
assets and their manifest unchanged until legacy compatibility checks pass;
document every extraction patch rather than changing the pinned upstream hash
to disguise a custom rewrite. Build the derived module ahead of time, not by
executing source strings in the browser.

Map case sections, claim reasoning, findings and selected draft sections into
the existing Textfold schema with stable IDs. Excerpt-only folds use local
source excerpts and the existing provenance label, with no model call. Preserve
provided five-level Textfold data for legacy briefs. A summary of our argument
is labelled project-authored; a source quotation is labelled source text. They
must not be visually conflated. New surfaces must preserve author wording at
Full/Brief, exact source links, independent local expansion, reduced motion,
continuous zoom and Topic-map links. Draft editing itself remains an ordinary
editor; folding is its native preview, not a replacement text input.

## 7. Manual and assistant drafting

Manual flow: choose a target section, select claims/findings, and **Add to draft**.
Open an editable proposal with chosen evidence chips; **Insert paragraph** is
explicit. **Insert source quote** uses the verified source_quote block. These
actions are deterministic and work with no model credits. Cancel does nothing.
Save persists the block and its server-validated dependencies. Clicking a cited
finding reopens that finding/anchor, then the existing PDF reader. Extend
`openPaper` with a typed source target, keeping the old searchTerm callers valid.
If PDF text location fails, show the verified extracted quotation and an honest
location-failed state; do not highlight an unrelated passage.

Assistant flow, inside Draft:

1. Save current edits first. **Draft with assistant** opens a review sheet with
   target section, chosen claims/findings, instructions and configured provider.
   Show which supporting/challenging findings were omitted; allow the user to
   revise the selection. Never silently select the whole library. Blank/no-source
   selections use the manual editor; the AI paragraph flow requires at least one
   current finding and an existing target section.
2. One explicit Generate creates the stable UUID request described above and
   its normal saved project discussion. Replays reuse that identity. The server
   builds all context from saved case state and authorized source snapshots,
   never from client-supplied quotations. Bind request hash to the revision,
   section, selection, instructions and provider. A changed case before creation
   returns 412 with no discussion/model request.
3. Run claims pending → running atomically and commits before contacting the
   provider. Recheck permission/source versions/quota immediately before that
   claim. A duplicate run returns the existing state/discussion (409 while busy),
   never starts another paid request. UI disables duplicate submissions and on
   network ambiguity polls GET status. A running request older than its
   documented 120-second execution deadline is reported effectively uncertain;
   it is never reset to pending on read or automatically rerun. Starting over
   requires a new explicit Generate action/new UUID.
4. Reuse the existing stream encoding/keepalive, configured BaseLLMClient provider
   and credit calculation. Factor shared message/usage helpers if necessary;
   do not create a second billing counter or bypass credits. Stream cancellation
   cancels the provider coroutine; terminal persistence is guarded so a final
   message/result is stored once. Persist the normal user/assistant messages in
   the project discussion and mark the request completed/failed/uncertain.
   Do not record an empty/error-only answer as a completed proposal.
5. Use a bounded paragraph-generation operation with no tools, web search,
   whole-PDF upload or external retrieval. Instructions treat source content as
   untrusted data and require result/interpretation/speculation distinctions,
   caveats, counterevidence and `[[finding:<UUID>]]` citation markers. At most
   10,000 response characters; no fabricated DOI, source, exact quotation or
   experimental result. A model's compliance is not a truth guarantee.
6. Parse markers against the request's selected finding IDs on the server. A
   syntactically valid but unknown ID rejects the proposal; uncited text is
   marked uncited, not silently assigned citations. Arbitrary links or `[1]`
   strings in generated prose are not promoted to structured source references.
   Only validated markers become evidence chips. Show the proposed paragraph,
   source links, caveats, AI provenance and Edit / Insert / Discard actions.
7. Acceptance is a normal conditional document save, never a generation side
   effect. Validate request/message provenance, current membership and all
   dependency/source pins again. If workspace/source/target changed while the
   proposal ran, preserve the proposal and require explicit review against the
   current state before insertion; no automatic overwrite or silent pin update.
   PUT lists the request ID in `reviewed_proposal_ids` for that acknowledgment;
   the server still requires a current target and current accessible references.
   This records human review, never a server verdict that the prose is true.
   Discard changes no manuscript content; the ordinary discussion remains
   resumable. New AI blocks use only validated selected references.

Keep successful request identities even if the message is later deleted;
readback then says result unavailable instead of issuing a new generation.
Other saved project discussions and existing model/chat requests must continue
to work unchanged. Do not refactor all chat behavior as a prerequisite.

## 8. Export and compatibility

Export the current saved state; if local edits exist, prompt Save or explicitly
export an unsaved local bundle. Never mislabel unsaved content as server-saved.

- Bundle: `openpaper/investigation` v1 plus exported-at/project identity and
  current validation report. No credentials, signed URLs, private paper notes,
  hidden source snapshots or local reader annotations. On import, remap object
  IDs and revalidate each project source; unavailable sources remain gaps until
  the user deliberately binds an accessible paper/anchor. An arbitrary bundle
  never grants source access. Implement an explicit preview/confirm import
  that adds to a new unsaved document; do not silently replace saved work.
  Imported provenance records its origin without asserting a valid local
  assistant request. Findings without a currently validated source use an
  `unbound` source variant (origin locator and authored notes only); they do not
  persist/display an imported quote as a verified anchor. Rebinding supplies
  the canonical `anchored` variant from current project text. Imported dependency
  pins are untrusted until rebuilt on an explicit reviewed save; affected blocks
  retain a review-needed/imported label rather than becoming silently current.
- Markdown: manuscript headings/paragraphs, stable finding footnotes resolving
  to paper and exact extracted-text line range, and a Sources/limitations appendix
  recording stale/missing/uncited items. Historical/changed citations cannot be
  exported as current without the warning. Source-quote blocks obey redaction.
- BibTeX: deterministic deduplicated paper keys based on paper UUID, with escaped
  known metadata only. Include no invented year/venue/DOI and no signed file URL;
  return missing-field warnings. Exported Markdown links to app source context;
  BibTeX keys map to the same papers. Existing citation helpers can supply
  metadata/escaping patterns, with no metadata-hydration calls during export.
- Existing `textfold/doc` v0 JSON import/export remains a distinct reader feature
  with its five-level/source/provenance fidelity. Do not import it as verified
  findings automatically. Existing project APIs/MCP names and response contracts
  remain compatible; no new MCP integration is required for this release.

## 9. Ordered milestones and exit artifacts

| Milestone | Implementation and exit gate |
| --- | --- |
| M0 — recovery | Follow the handoff; inventory dirty state; preserve thumbnail repair; establish a feature branch without discarding files; record baseline and tool versions. No cloud write. |
| M1 — native engine | Implement the scoped static reader factory and wrapper. Prove native DOM, upstream algorithms, two instances, lifecycle cleanup, theme, shortcuts, reduced motion, hostile markup and old format fidelity. Save a technical extraction note and smoke screenshot. A frame-only result fails this milestone. |
| M2 — state/API | Add both tables/migration, strict schemas, access helper, conditional save and guarded tests. Prove legacy virtual state, concurrent initial creates, stale saves and rollback. Keep old project lists/briefs untouched. |
| M3 — case/evidence | Build routes, provider, case fields, claims, scoped source picker, finding editor, relations, comparison and native folding. Implement anchor validation/redaction/version changes and source-open callbacks. Complete the fixture through saved case/evidence + reload. |
| M4 — manual manuscript | Add sections/blocks, explicit insertion/edit/save, dependency pins, citation backtracking, stale review and mobile editing. Complete the full manual question → claim → source → cited paragraph → reload → changed source journey. |
| M5 — assistant | Add request ledger + bounded stream/proposals using existing model/message/credit seams. Prove replay, timeout/cancel/error/credit/access/stale-result behavior with a fake provider. Complete explicit Generate → review → insert/discard. No live inference in local acceptance. |
| M6 — exports/compatibility | Implement saved/unsaved export distinction, portable bundle import preview/remapping, Markdown + BibTeX and old brief/Textfold compatibility. Keep existing discussion flows and thumbnail regression passing. |
| M7 — acceptance/review | Run the complete acceptance matrix, exact production build and isolated database checks, review the feature diff independently, resolve findings and rerun affected checks. Record evidence and prepare the release runbook/artifact identifiers. |

At each milestone update the prepared `docs/work/VERIFICATION-investigation-workspace.md`
with actual commands, pass/fail counts, log paths, screenshots and known limits.
Mark acceptance IDs pending until executed. Update current.json with the actual
next milestone. Do not make a new strategy decision merely because a session
changes. The next session is authorized to finish M0–M7 when instructed to execute
this intent, rather than stopping to ask approval for each routine step.

## 10. Release preparation and conditional rollout

No release is executed during planning. Local completion includes a concrete
release record with source commit/diff, migration head, build inputs, test/review
evidence and rollback targets. Thumbnail release timing remains unanswered.
If release is later authorized, include its reviewed fix in the tested image
and record whether it was independently shipped already; never drop it.

For a release instruction: capture the live web/jobs revisions and exact images
first; do not trust the older current.json entries as live discovery. Use the
existing personal GCP project `openpaper-sammatuba`, region `asia-southeast1`,
canonical origin `https://papers.sammatuba.workers.dev`, and locked build files.
Build committed source only, excluding .env/runtime artifacts. Apply the new
additive migration with the server image before rolling web traffic. Preserve
existing client/server features, runtime identity, secrets and queue settings;
do not redeploy unrelated services from old tags. Use resolved image digests.

Run pretraffic readiness and public health/auth/discovery/assets checks, then
switch traffic and check exact digests again. Run the authenticated acceptance
journey using the operator's current session or an explicitly authorized test
session: do not manufacture an owner session from old pilot authorization.
Use a clearly named temporary test project and synthetic sources if actual
production test writes are authorized. Do not alter real research cases/papers
to demonstrate the feature. A live AI request is a separate explicit user action;
mocked model acceptance is sufficient for the local feature gate.

On readiness/compatibility failure, restore prior web revision traffic; keep the
additive schema and investigation records. Never downgrade/drop authored data as
an application rollback. Record remaining account-only checks and clean up only
test resources that the execution session created and is authorized to remove.
