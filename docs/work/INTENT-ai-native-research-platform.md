# INTENT: AI-native research platform — first implementation packages (P00–P02)

Date: 2026-11-13. Strategy: [STRATEGY-ai-native-research-platform.md](STRATEGY-ai-native-research-platform.md) (independently reviewed, accept).

## Outcome

Execute the strategy's first implementation action (§20): packages **P00, P01, P02** only.

- **P00** — re-establish the baseline: inventory deployed/source divergence, test commands, role semantics, OAuth/computed-column boundaries, outstanding operator gates; reproduce applicable current regression suites in an isolated setup.
- **P01** — freeze interface contracts: schema/API proposals, golden fixture with stable IDs and the §17.1 exact review-count fixture, compatibility/licensing checks for React Flow and a schema-based editor.
- **P02** — versioned research identity and safe persistence: additive migration, typed research entities/relations, review identity mappings (occurrence/report/candidate/study), revision history, external-AI provenance, proposal/approval core, metered-operation admission/reservation/replay core, deterministic v1 conversion — with tests.

Delivered as a **stacked PR** targeting `feat/native-investigation-workspace` (the deployed investigation feature is unmerged; new work builds on it).

## Scope

In scope: the three packages above, their tests, docs/work records, and the PR.

Out of scope (remains pending, per strategy): P03–P12 (shell, discovery, editor, MCP extension, local companion, lab, canvas, review pipeline, AI assistance, release hardening), any deployment, any live/paid inference, any production migration, any account/ChatGPT changes, corpus expansion. The existing open gates (A25 authenticated acceptance, live-AI acceptance) remain open and untouched.

## Constraints and failure behavior

- One Alembic head; additive migrations only; never modify a deployed migration.
- No model/provider calls anywhere in the new code paths or tests; fake providers only.
- No localStorage persistence of research content; preserve v1 save semantics.
- Conversion: atomic compare-and-swap per project; abort without partial state on any mismatch; v1 snapshot retained read-only.
- Metered operations stay **unavailable** until the admission core passes C29-style tests; deterministic/manual paths unaffected.
- Unexecuted checks are recorded as pending with the reason; never relabeled as passes.

## Acceptance checks (from strategy §17.3, mapped to these packages)

- C01: historical release evidence stays separate from new acceptance. (P00)
- C05/C08/C10: forgery rejection, concurrency/rollback, atomic v1 conversion. (P02 tests)
- C17: exact §17.1 count fixture reproduced by the review identity mappings. (P01 fixture → P02 tests)
- C29: admission/reservation/replay core enforced with fake metered providers before any new paid dispatch. (P02)
- C35: applicable existing regressions re-run with skips disclosed. (P00)

## Verification commands

Recorded in the P00 baseline inventory and the final verification record; only actually-executed commands count as evidence.
