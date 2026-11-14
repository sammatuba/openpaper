# CONTRACT: AI-native research platform — frozen interface proposals (P01)

Date: 2026-11-13. Status: frozen for P02 implementation. Strategy: [STRATEGY-ai-native-research-platform.md](STRATEGY-ai-native-research-platform.md) §2, §6.1, §10, §11.3. Baseline: [BASELINE-ai-native-research-platform.md](BASELINE-ai-native-research-platform.md). Golden fixture: [ai-native-research-fixture.json](ai-native-research-fixture.json).

These are the interface contracts P02 implements. Names, states and error mappings below are binding for the new storage layer; the deployed v1 investigation path is untouched.

## 1. Identity model

One canonical research record per project. Every mutable record has a stable UUID, a monotonically increasing `revision` (≥1), and lives under exactly one `project_id`. The project root carries `change_sequence` (BigInteger, monotonic per project) incremented by every committed mutation; receipts return it for client synchronization.

### 1.1 Record families (P02 scope)

| Table | Identity | Notes |
| --- | --- | --- |
| `research_projects` | `project_id` PK (FK project) | `storage_generation` (`v1`/`v2`), `change_sequence`; one authoritative write path per project. |
| `research_source_versions` | `id` PK | Immutable extracted-text snapshot: `paper_id` FK nullable, `kind` (`paper_text`\|`artifact`\|`external_locator`), `extractor`, `text_sha256` (64-hex), `line_count`, `byte_size`, `metadata` JSONB. Link-only locators are `external_locator` and are **never** verified anchors. |
| `research_entities` | `id` PK | `type` (`question`\|`claim`\|`finding`\|`assumption`\|`decision`\|`gap`), `revision`, `payload` JSONB, `archived`, `created_by`. Payload schema per type in §2. |
| `research_entity_revisions` | (`entity_id`,`revision`) unique | Append-only. `payload` JSONB, `origin` provenance (§3), `actor_id`, `derived_from` nullable (`entity_id`,`revision`). History is never rewritten; undo writes a new revision. |
| `research_relations` | `id` PK | `relation_type`, `source_id`/`target_id` FK research_entities, `rationale`, `revision`, `archived`. Endpoint legality enforced server-side (§2.3); presentation-only connectors never enter this table. |
| `review_protocols` | `id` PK | `version`, `mode` (`systematic`\|`scoping`\|`literature`), `unit_of_analysis`, `count_policy` JSONB, `criteria` JSONB, `status`, `parent_version_id` nullable. Amendments create a new version row; historic snapshots are immutable. |
| `review_acquisitions` | `id` PK | One acquisition occurrence: `provider`, `query_ref`, `external_hit_id`, `search_execution_id`. Delivery retries/page resumes never create rows; a new search execution retrieving the same report creates a new occurrence. |
| `review_reports` | `id` PK | Scholarly report identity: `identity_state` (`unreviewed`\|`confirmed`\|`merged`\|`split`), `merged_into` nullable self-FK. Preprint/publication versions share a report ID only after explicit identity review. |
| `review_report_versions` | `id` PK | `report_id` FK, `version_label`, `source_version_id` nullable FK, `sha256`, `bibliographic` JSONB. Exact document versions are separately preserved. |
| `review_candidates` | `id` PK | One candidate per (protocol version, report): `report_id`, `selected_version_id` FK, `retained` bool, `prescreen_category` nullable (`duplicate_removal`\|`other_prescreen`). Screening counts candidates, not hits or bytes. |
| `review_studies` | `id` PK | Underlying empirical investigation at the protocol's declared unit. |
| `review_report_studies` | (`report_id`,`study_id`) PK | Many-to-many; `linkage_state` (`proposed`\|`confirmed`\|`unresolved`), `rationale`. Unresolved linkage is never counted as independent corroboration. |
| `review_decisions` | `id` PK | `candidate_id` FK, `stage` (`title_abstract`\|`fulltext`), `protocol_version`, `actor_id`, `decision` (`included`\|`excluded`\|`unclear`), `criterion_judgments` JSONB, `reason`, `cited_text`. Independent mode hides peer decisions until both submitted (service rule; dual rows exist per stage). |
| `review_mapping_events` | `id` PK | Append-only: `kind` (`occurrence_map`\|`report_merge`\|`report_split`\|`version_replace`\|`protocol_amend`\|`study_link`), `payload` JSONB (before/after sets), `actor_id`. Flow snapshots derive from these; overrides are explicit events, not edits. |
| `research_proposals` | `id` PK | Proposal/approval core (§4). |
| `metered_price_tables` | (`version`) PK | Versioned unit prices per `operation_type`; prices JSONB. |
| `metered_operations` | `id` PK | Admission/reservation/replay ledger (§5); `idempotency_key` unique per (`project_id`,`operation_type`,`key`). |

All tables carry `created_at`/`updated_at` server defaults and `project_id` FK with `ON DELETE CASCADE`. Migration `research_core_01` is additive on head `project_investigation_01`; one Alembic head; no deployed migration is modified.

### 1.2 Authoritative generation and conversion

`research_projects.storage_generation` starts `v1`. The deterministic converter (§6) applies typed records atomically and flips the generation to `v2` in the same transaction only after all comparisons pass; any mismatch aborts with no partial state. There is never dual-write: exactly one generation is authoritative per project. The v1 row is retained read-only as the historical snapshot. Production cutover is not part of P02.

## 2. Payload schemas (typed JSON, extra=forbid, strict)

### 2.1 Entity payloads

- `question`: `text` ≤20k, `target_decision` ≤20k, `status` (`open`\|`resolved`\|`withdrawn`).
- `claim`: `statement` ≤2000, `reasoning` ≤20k, `caveats` ≤20k, `status` (`provisional`\|`supported`\|`disputed`\|`reconciled`\|`withdrawn`), `archived` bool.
- `finding`: `label` ≤500, `observed_result` ≤20k, `author_interpretation` ≤20k, `our_interpretation` ≤20k, `limitations` ≤20k, `setup` object (`model`/`task`/`training`/`intervention`/`evaluation`/`other`, each ≤20k), `anchor` nullable object: `source_version_id` UUID, `start_line`/`end_line` ≥1 (end≥start), `quote` ≤20k, `quote_sha256` 64-hex, `page_span` nullable tuple. Missingness distinctions (`not_reported`\|`not_applicable`\|`not_yet_inspected`\|`cited`) are explicit values, never zero.
- `assumption`: `text` ≤20k, `basis_entity_ids` ≤100 UUIDs, `status` (`active`\|`retired`).
- `decision`: `text` ≤20k, `rationale` ≤20k, `decided_by` actor UUID, `status` (`active`\|`superseded`).
- `gap`: `description` ≤20k, `blocking_entity_ids` ≤100 UUIDs, `status` (`open`\|`addressed`).

Bounds mirror v1 (`InvestigationDocument` maxima: 100 claims, 500 findings, 1000 relations, 1000 blocks); the relational layer enforces per-record bounds and pagination instead of a 2 MB whole-document cap.

### 2.2 Provenance (on every revision and proposal)

`origin` ∈ `human` | `assembled` | `assistant` | `imported` | `external_ai`. Rules preserved from v1 (`server/app/schemas/investigation.py:91` + save service):

- `assistant` (native assistant) requires the durable local `request_id` + `message_id` and inherits v1 validation semantics; it cannot be applied to a record whose expected origin is external.
- `external_ai` (§10.5) requires: `client_identity` (validated MCP client id), `submitting_actor_id`, `content_sha256` (submitted bytes), `declared_model` (label only — a declaration, not attestation). External content can never be relabeled `assistant`; native requests cannot be reattributed to an external client.
- Editing, copying or accepting creates a **new revision with `derived_from`** pointing at its source revision; origin is never reset or erased. Exports and reads carry origin.

### 2.3 Relation types and endpoint legality

`supports`|`challenges`|`qualifies` (scientific, v1-compatible; claim↔finding) and `assumes`|`motivates`|`tests`|`measures`|`derived_from`|`cites`. Allowed endpoint type pairs are a frozen table in the service; illegal combinations are rejected server-side (HTTP 422). Every scientific relation requires a rationale (≥1 char, ≤20k). v1 relations map 1:1 with their IDs preserved.

## 3. Shared authorization (one semantic)

`app.services.research_access.authorize(db, project_id, actor_id, *, write=False)`:

- Project missing → 404 (identical to v1 `investigation.access`, avoiding existence leaks).
- **Owner (`project.admin_id`) passes read and write without a membership row**; membership roles `admin`/`editor` pass write; `viewer` read-only; non-member 404.
- Returns the project. All new research services, proposals and ledger mutations call this inside their transaction. Retrofitting the three divergent legacy checks (§5 of baseline) into this semantic is deferred to the packages that touch those tools; behavior of deployed tools is unchanged in P02.

## 4. Proposal and approval core

State machine: `pending` → `approved` → `applied` | `discarded` | `expired` | `stale`.

- `research_proposals` fields: `origin` (§2.2), `payload` JSONB (typed edit set: create/revise entities or relations, each with full payload), `payload_sha256`, `targets` JSONB (`entity_id` → expected revision), `state`, `approval` JSONB nullable (`approver_id`, `approved_at`, `expires_at`, `bound_payload_sha256`, `bound_targets`), `receipt` JSONB nullable (resulting revisions + `change_sequence`), `idempotency_key` unique per project.
- Approval is a server-recorded write by an authorized actor (admin/editor) through the application; client confirmations, tool annotations and `confirmed=true` flags are never approval. Approval binds the exact `payload_sha256` + `targets` + expiry.
- Apply (`apply_proposal`): single transaction — re-authorize, re-check every target's current revision equals the bound expectation (else → `stale`, proposal returns to `pending` review), re-verify payload hash, write new entity revisions with provenance derived from the proposal, consume the approval (single use), increment `change_sequence`, emit receipt. Replay with the same idempotency key returns the original receipt after re-authorization; a different payload under the same key is a 409.
- Forged or expired approvals are rejected at apply time (409/410); a stale proposal never auto-applies.

## 5. Metered-operation admission/reservation/replay core (C29)

- A paid operation may dispatch **only** through `app.services.metered.dispatch_operation(...)` when: the operation type exists in the active price table version, per-operation limits are configured, and a reservation was admitted. With an empty price table (the shipped default) every metered path is unavailable; deterministic/manual paths are unaffected.
- `metered_operations` lifecycle: `reserved` → `admitted` → `running` → `completed` | `failed` | `uncertain` | `cancelled` | `expired`.
- `reserve(project_id, actor_id, operation_type, estimate, payload_digest, idempotency_key)`: price-table lookup (missing type → 409 `operation_not_priceable`), cap check against declared project/run limits (exceeded → 429), reservation of the allowed maximum (conservative bounded), idempotent replay by key: same payload digest → original record returned verbatim; different digest → 409.
- `settle(id, usage)` reconciles actual usage (estimate vs settled are stored separately, never overwritten); `fail(id, uncertain: bool)` — `uncertain=True` **retains the reservation** pending reconciliation and forbids silent retry of the same paid work; admission limits + bounded in-flight exposure are the enforcement, not invoice-exact caps.
- No database transaction spans a provider call: reserve/commit, dispatch, then settle/fail in separate transactions. Receipts are durable before dispatch.

## 6. Deterministic v1 conversion

`app.services.research_convert.convert_project(db, project_id, actor_id)`:

1. `authorize(..., write=True)`; lock the `project_investigations` row `with_for_update`; read the v1 document + revision.
2. Create `research_projects` root (`storage_generation='v2'`, `change_sequence=0`) if absent.
3. For each distinct referenced `paper_id` with matching raw-content hash, create one `research_source_versions` row (kind `paper_text`, `text_sha256` = v1 `source_sha256`, `line_count`, `extractor='v1_raw_content'`). Unknown hashes are recorded as unresolved and left for review — never auto-bound.
4. Claims → `claim` entities; findings → `finding` entities (anchor maps to source_version_id + lines + quote + quote hashes; `unbound`/`redacted` preserved as-is); relations → `research_relations` 1:1 with v1 IDs; provenance preserved per §2.2 (`assistant` stays `assistant` with request/message ids; `imported` stays `imported` with `reviewed` state).
5. Manuscript blocks become `paragraph`-content revisions of derived draft records **not in P02** — instead, blocks are preserved inside the v1 snapshot and their claim/finding/quote dependencies are captured as typed references recorded in the conversion manifest; full manuscript records arrive with P05. Conversion never drops or alters block text.
6. Compare: counts of claims/findings/relations, per-entity text equality, anchor quote/line/hash equality, provenance equality. Any mismatch → raise before any write of the generation flag (transaction rollback; no partial state).
7. Write revisions, manifest (`mappings`, `counts`, `unresolved_sources`, converter `version='research_core_v1'`), flip `storage_generation='v2'` — all in one transaction. The v1 JSONB row is retained untouched as read-only history; the converter does not modify it.

## 7. Error mapping

| Condition | Status |
| --- | --- |
| Missing If-Match/expected precondition | 428 |
| Stale entity/proposal target revision | 412 |
| Dependency incompatibility (source changed, archived evidence, endpoint/anchor violation) | 409 |
| Malformed payload / schema violation / unknown reference | 400/422 |
| Idempotency key reused with different payload | 409 |
| Metered cap exceeded / not priceable | 429/409 |
| Authorization | 403/404 per v1 semantics |

Permissions are re-checked inside each mutation transaction. Multi-record actions validate all targets before writing and commit atomically; no transaction spans a provider call, upload or execution.

## 8. Product-loop navigation (P01 prototype + P03 shell contract)

Six destinations (Overview, Library, Evidence, Canvas, Lab, Write) over one record set; Case remains the Overview/argument entry; existing Case/Evidence/Draft URLs stay navigable. One contextual inspector with source/provenance/history tabs; closing returns focus to the opener; no stacked source-modal + chat + evidence drawer on mobile. The P01 prototype demonstrates the loop with the golden fixture: question → finding (observed vs interpretation) → claim link → spatial board → experiment specification → manuscript paragraph, with zero provider calls; desktop (1440) and mobile (390) states included. First-value usability exercise (C03, unfamiliar user) stays pending until a human runs it.

## 9. Compatibility and licensing (verified 2026-11-13)

- **React Flow `@xyflow/react`** 12.x — MIT (Pro plan sells examples/support only). Suitable as the P09 board foundation pending a performance/accessibility spike.
- **Tiptap / ProseMirror** — editor core MIT (v3 moved emoji/math/file extensions into the OSS package); paid tiers are cloud/platform services only, not required for the core workflow. Suitable as the P05 editor foundation pending schema round-trip tests.
- Both are new dependencies: **renewed license/version review is required at the package that installs them** (§0.2 invariant 4); nothing is installed in P01/P02.
- AGPL obligations, Textfold notices and transitive licenses remain intact; no redistribution changes in this PR.
