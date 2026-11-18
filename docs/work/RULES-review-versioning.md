# Rules: review records across protocol versions

Date: 2026-11-18 (revised the same day after review rounds 53 and 54 and two owner decisions).
Scope: `server/app/services/research_review.py`, `research_proposals.py`, the lock order in
`research_access.py`, and for rule 10 also `research_entities.py` and `metered.py`.
Source: strategy §6.1 ("historic flow snapshots retain their original sets"; a later change
"cannot rewrite historical counts or final decisions"), contract §1.

These are the rules the code is meant to satisfy. A reviewer judges the code against this page.
A behaviour that follows from a rule here is not a finding; a rule that is wrong or missing is
one finding, raised against this page, not once per consequence in the code.

## Why this page exists

Review rounds 48 to 52 each found a new way for a backdated write to disturb a later snapshot,
and each fix added another per-write simulation of "every later affected snapshot". Round 52's
third finding was a regression caused by round 51's guard. The cause was an unstated rule: the
code allowed a write at any earlier protocol version, so every write had to re-prove every
invariant at every later version. Rule 1 removes that freedom.

Round 53 found the first version of this page disagreeing with the code about rule 1, and
three computations of a candidate's outcome disagreeing with each other. Rule 1 is now stated
as the code enforces it, and rule 9 leaves one computation.

## Decision recorded for rule 1

Round 53 escalated one question: does **creating a later protocol** close the earlier snapshot,
or does **the first decision or mapping recorded at the later version** close it? This page
adopts the second. Reason: amending a protocol is preparation; reviewers finish outstanding work
(for example, adjudicating a version 1 disagreement) under the version it arose in until the
first record under the new version exists. The alternative would make an amendment an
irreversible cut-over with no way to finish open work at the old version.

Status: adopted on the implementer's recommendation; the owner was shown the recommendation and
said to continue, without ruling on it explicitly. It is the owner's to reverse. Reversing it means counting protocol rows in
`_snapshot_high_water` and changing the two tests named under rule 1.

## Rules

| # | Rule | Enforced by |
|---|---|---|
| 1 | **A snapshot closes when a review record exists at a later version.** Records that count: decisions, and mapping events of kind `occurrence_map`, `report_merge`, `report_split`, `study_link`. The highest version among them is the project's high-water mark. Protocol rows do not count. Versions start at 1, so a mark of 0 only ever means "nothing recorded". | `_snapshot_high_water`; tests `test_independent_review_privacy` (version 1 adjudication after a version 2 amendment), `test_acquisition_guards_on_the_open_snapshot` (mark 0 with protocol 1 present) |
| 2 | **Every versioned review write targets the open snapshot.** `map_occurrences`, `record_decision`, `link_study`, `merge_reports` and `split_report` refuse (409) a `protocol_version` below the high-water mark and refuse (422) a version below 1. A version above the mark is allowed and becomes the new mark. | `_require_open_snapshot` |
| 3 | **A protocol governs before anything is recorded, and a new protocol opens a new snapshot.** Every versioned write needs a protocol row at or below its version (404 otherwise), so the first protocol always precedes the first record. `create_protocol` refuses (409) a version at or below the high-water mark, because the row would change the screening mode that existing records were decided under, and refuses (422) a version below 1. | `_require_open_snapshot`, `create_protocol` |
| 4 | **Review writers on one project are serialized, in one lock order.** Order: project row, then research root row, then row locks (candidate, report, occurrence, in their existing order). Conversion and the legacy save take the project row `FOR UPDATE`; every other research writer takes it `FOR KEY SHARE` in `authorize(write=True)`. Review writers then take the root row before reading the high-water mark, the duplicate check or the amendment parent, so no writer decides against state another writer is about to change. | `research_access.authorize`, `research_access.lock_project` |
| 5 | **A merge compares outcomes once, when it is recorded.** Source versus the target's current representative, per stage, using the rule 9 outcome of each side. Differing decided values, or either side undecided for a recorded reason (unresolved merge conflict, disagreement, incomplete dual pair), are recorded on the merge event and force adjudication. A side with no decision at all is not a conflict: merging a decided source into an undecided target is not flagged, and the merged candidate then shows as unscreened until someone decides on it (the source's decision stays on the source and returns on a split). | `merge_reports` |
| 6 | **A decision made after a merge is a decision about the merged candidate.** It is recorded on the live representative (a merged-away candidate refuses, 409) and governs from its version on, exactly as an amendment cohort does, subject to rule 9 (an unresolved merge conflict or a standing adjudication at that version takes precedence). It is not compared with decisions of reports merged in earlier. An incomplete dual cohort leaves the candidate pending; that is not a conflict. | `record_decision` |
| 7 | **Adjudication is recorded only on an open disagreement at the requested snapshot.** Open means the rule 9 outcome at that version is pending for the reason "merge conflict" or "disagreement". A resolved conflict, a conflict superseded by a later agreeing cohort, and an incomplete dual pair are not adjudicable (409). The snapshot is the requested version, not the version of the protocol row that governs it. | `record_decision` |
| 8 | **A proposal's edit set applies all-or-nothing, together with its state and receipt.** Before the first mutation: the approval is checked whole (expiry, approver, payload hash, bound targets), the edit envelope is checked whole (each edit an object with a string id and an object payload, each id a bound target, each target edited once), and every payload is validated. The revisions, the `applied` state and the receipt are written in one savepoint, so a failure leaves none of them and a replay in the same transaction sees all of them. Target ids are stored in canonical UUID spelling. | `apply_proposal`, `_bound_edits`, `_canonical_targets` |
| 9 | **One derivation gives a candidate's outcome per stage.** Counts, merge conflict detection and adjudication eligibility all read it. Among records at or below the snapshot version: (a) an adjudication stands when it was recorded after every conflicting merge attached to the candidate and no screening decision exists at a higher version; a standing adjudication decides the stage and is final within its version. (b) Otherwise a conflicting merge with no resolving adjudication leaves the stage pending. (c) Otherwise the screening cohort of the latest version governs under the stage's mode, each reviewer's latest submission counting once: a solo stage decides on one agreed value, a dual stage needs two distinct reviewers who agree. | `_derive_decisions`, `_merge_state` |
| 10 | **A service call's writes are visible to the next call in the same transaction.** Every research service flushes before it returns, with or without `commit`, so a caller composing `commit=False` calls on a session that does not autoflush (the application's setting) reads its own writes back. | every `commit=False` exit; the PostgreSQL research tests run on non-autoflushing sessions |
| 11 | **An amendment sits above the latest protocol.** `amend_protocol` copies the latest protocol, so it refuses (409) a version at or below it. A protocol between two existing ones is created with `create_protocol`, stating its own criteria. | `amend_protocol` |

## What rules 1 to 3 make impossible

- A decision recorded below an existing merge's version (rounds 50 and 51).
- A merge recorded below existing decisions, merges or splits (rounds 48, 50 and 51).
- A remap recorded below a later mapping of the same candidate (round 49).
- A cycle that only exists at a later snapshot (round 50).
- A record that exists before any protocol and then blocks the protocol meant to govern it
  (round 53).

The tests that used to assert the per-case outcome of these writes now assert one outcome: 409,
snapshot closed.

## Consequences worth knowing

- With protocols 1 and 3 and nothing recorded above version 1, a record at version 1 or 2 is
  still allowed, and a protocol 2 may still be created with `create_protocol` (not by amendment,
  rule 11). The first record at version 3 ends both.
- A version 1 disagreement can be adjudicated at version 1 after a version 2 amendment, until
  the first version 2 record exists. After that it is adjudicated at version 2.
- An adjudication is final within its version (rule 9a; owner decision, 2026-11-18). Screening
  decisions recorded at that version afterwards are kept but change nothing, and the stage cannot
  be adjudicated a second time. To change the outcome, amend the protocol: the first screening
  decision at the new version ends the adjudication's hold, and the cohort at that version
  governs (a dual stage is pending until two reviewers agree). A conflicting merge recorded after
  the adjudication still reopens the stage, because the adjudication did not consider it.

- **Open question for the owner (gate review, 2026-11-18).** Finality attaches to the version an
  adjudication is labelled with, not to the cohort it settled. Two effects. (1) A version 1
  disagreement adjudicated at version 2 (because a version 2 record already exists) is final for
  version 2: if both reviewers later record an agreed decision on that candidate at version 2,
  the adjudication still decides it, whereas the same cohort recorded before the adjudication
  would have decided it. (2) An adjudication that resolved a merge conflict keeps deciding the
  target after the merge is split away. Changing either outcome takes another amendment. The
  alternative is to let a complete cohort at the adjudication's own version supersede an
  adjudication of a lower-version cohort. Nothing is lost either way: outcomes are derived from
  append-only records.

## Known limits

- Rule 2 allows a version far above the high-water mark (for example 99). That closes every
  version below it. Nothing ties a version number to an existing protocol row; the governing
  protocol is the highest row at or below the version (`_protocol_for`).
- `link_study` on an existing linkage updates its state and rationale in place; only the first
  linkage is versioned. The update is still refused on a closed snapshot.
- Rule 4 is covered by two-session tests (a backdated writer, two protocol creators, two
  amendments, a writer queued behind a project-row holder), not by a stress run. No PostgreSQL
  deadlock was reproduced before the lock order changed; the change follows from the order.
- Proposal envelopes are checked at apply, not at creation, because creation accepts payloads
  that carry no edit set. Only the targets are checked and normalized at creation.
