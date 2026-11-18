# Rules: review records across protocol versions

Date: 2026-11-18. Scope: `server/app/services/research_review.py` and `research_proposals.py`.
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

## Rules

| # | Rule | Enforced by |
|---|---|---|
| 1 | **A snapshot closes when any review record exists at a later version.** Records that count: protocol rows, decisions, and mapping events of kind `occurrence_map`, `report_merge`, `report_split`, `study_link`. The highest version among them is the project's high-water mark. | `_snapshot_high_water` |
| 2 | **Every versioned review write targets the open snapshot.** `map_occurrences`, `record_decision`, `link_study`, `merge_reports` and `split_report` refuse (409) a `protocol_version` below the high-water mark. A version above it is allowed and becomes the new mark. | `_require_open_snapshot` |
| 3 | **A new protocol opens a new snapshot.** `create_protocol` refuses (409) a version at or below the high-water mark once any record exists, because the row would change the screening mode that existing records were decided under. | `create_protocol` |
| 4 | **Review writers on one project are serialized.** Each takes the project root row lock before reading the high-water mark, so two writers cannot both pass rule 2 against a stale mark. Row-level locks taken afterwards (candidate, report, occurrence) keep their existing order. | `research_access.lock_project` |
| 5 | **A merge compares prior decisions only, once, when it is recorded.** Source versus the target's current representative, per stage. Differing decided values, or an unresolved state on either side (`adjudication`, `pending_dual`), are recorded on the merge event and force adjudication. | `merge_reports` |
| 6 | **A decision made after a merge is a decision about the merged candidate.** It is recorded on the live representative (a merged-away candidate refuses, 409) and governs from its version on, exactly as an amendment cohort does in `compute_flow_counts`. It is not compared with decisions of reports merged in earlier. An incomplete dual cohort leaves the candidate pending; that is not a conflict. | `record_decision` |
| 7 | **Adjudication is looked up at the requested snapshot version**, not at the version of the protocol row that governs it. | `_has_conflict` |
| 8 | **A proposal's edit set applies all-or-nothing.** Every edit is validated before the first mutation, and the mutations run inside a savepoint, so a failed apply leaves no edit flushed in the caller's session. | `apply_proposal` |

## What rule 1 and rule 2 make impossible

- A decision recorded below an existing merge's version (rounds 50 and 51).
- A merge recorded below existing decisions, merges or splits (rounds 48, 50 and 51).
- A remap recorded below a later mapping of the same candidate (round 49).
- A cycle that only exists at a later snapshot (round 50).

The tests that used to assert the per-case outcome of these writes now assert one outcome: 409,
snapshot closed.

## Known limits

- Rule 2 allows a version far above the high-water mark (for example 99). That closes every
  version below it. Nothing ties a version number to an existing protocol row; the governing
  protocol is the highest row at or below the version (`_protocol_for`).
- `link_study` on an existing linkage updates its state and rationale in place; only the first
  linkage is versioned. The update is still refused on a closed snapshot.
- PostgreSQL concurrency for rule 4 is covered by one two-session test, not by a stress run.
