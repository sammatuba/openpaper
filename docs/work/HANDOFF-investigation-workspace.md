# Execute the investigation workspace in a new session

Execution update,2026-11-11: reviewed source `c757bbf0` is deployed as
web `openpaper-00014-vjm` at 100%. Independent verdict **accept**; local/database/browser
and public rollout gates pass. Resume at current-account authenticated production
UI acceptance, which is unavailable in this execution environment. Read
[session report](REPORT-investigation-workspace-session.md),
[verification](VERIFICATION-investigation-workspace.md) and current.json first.
The planning handoff below is historical.

Prepared on 2026-11-11 at the operator's request using `meos-intent`.
This session produced the plan only. No native-investigation implementation,
database migration, cloud build, deployment or paid model request was run.

## Read in order

1. Root AGENTS.md and `/home/sammatuba/.codex/RTK.md`.
2. Run `rtk proxy bash ./meos start --runtime codex` at the Git root and read
   `.meos/lifecycle.md` and `.agents/skills/meos-implement/SKILL.md`.
3. `docs/work/current.json` — the live pointer overrides old local checkpoints.
4. [INTENT-investigation-workspace.md](INTENT-investigation-workspace.md).
5. [PLAN-investigation-workspace.md](PLAN-investigation-workspace.md).
6. [ACCEPTANCE-investigation-workspace.md](ACCEPTANCE-investigation-workspace.md)
   and [synthetic fixture](investigation-workspace-fixture.json).

The previous session's product intuition is captured in
[STRATEGY-investigation-workspace.md](STRATEGY-investigation-workspace.md).
The intent/plan are now the implementation contracts; do not reopen the basic
direction or replace the actual Textfold engine with a superficial imitation.

## Exact starting state

Repository: `/home/sammatuba/projects/ps/openpaper`, branch master, baseline HEAD
`09bf3bae02ed55a1537b0f4a71a01e536f17b0b3`.

Before editing, compare `rtk git status --short --branch`, HEAD and
[BASELINE-investigation-workspace.json](BASELINE-investigation-workspace.json).
That manifest records hashes of the pre-existing thumbnail repair, not the new
investigation implementation. If hashes or HEAD changed, inspect the real diff
and preserve newer work; do not reset the tree to force a match. Make a feature
branch such as `feat/native-investigation-workspace` from the actual current
state without discarding the dirty files. Record the feature review base and
baseline changes separately in the verification record. Do not depend on a
temporary worktree or old /tmp browser paths surviving.

The dirty application files belong to the **already implemented thumbnail fix**:

- `scripts/ci/run_isolated_postgres.py`
- `server/app/api/paper_api.py`
- `server/app/api/projects/project_papers_api.py`
- `server/app/api/search_api.py`
- `server/app/database/crud/projects/project_paper_crud.py`
- `server/app/helpers/s3.py`
- `server/tests/test_paper_previews.py` (new/untracked)

Its intent and results are in INTENT-paper-thumbnails.md and
VERIFICATION-paper-thumbnails.md. Review `.meos/reviews/20261110T162653Z.md`
accepted it with no findings. Required isolated suite:75 tests, zero skips;
full server:459 tests OK48skips; 8 signing/download checks. An existing production
PNG returned unsigned403 and signed200 with valid PNG magic; this proved a
storage read, not a live deployment of the API fix. These are historical
thumbnail results, not investigation-workspace acceptance results.

The operator has not answered whether to deploy thumbnails immediately or
bundle them. Preserve the repair and test it with the new feature. Do not
deploy it solely because this handoff is being resumed. The planning files and
current.json are also local changes and must be kept, including untracked files.

## First executable action

After recovery, start M1 of the plan: extract the pinned document-global reader
into a scoped static ESM factory with a native React mount. Use the checked-in
vendor inputs rather than relying on `/tmp/openpaper-textfold-source` or
downloading the current upstream main. Prove native DOM, the actual five-level
engine, two independent instances, cleanup, theme and keyboard isolation before
building the rest of the interface. Record findings in a short extraction note.
Then execute M2–M7 without waiting for another product-design conversation.

Use `docs/work/VERIFICATION-investigation-workspace.md`, whose A01–A25 are pending,
and record actual results as work proceeds. If interrupted, preserve the exact
completed milestone, current failing check and next command in current.json.
Do not conflate a reader spike, mock screenshot or prepared migration with the
complete working investigation and drafter.

## Completion and release boundary

Finish the manual and assistant end-to-end journeys, exports, compatibility,
required checks and independent review. Normal dependency installation, local
test fixtures, feature branches and implementation fixes are within execution
scope once the operator asks to execute this intent. Use the session's selected
model; old strategy records are not a new model/delegation instruction. No
parallel implementation agents are required by this plan.

If no release instruction is present, end with a verified release-ready local
result and exact rollout/rollback preparation. Do not invent production
acceptance, reuse old temporary owner-session authorization, start paid
inference, publish, push or deploy because a lifecycle phase changed. Preserve
real research data and sibling repositories. The plan includes the conditional
release sequence so a later release instruction needs no design work.

## Resume prompt

> Use meos-implement. Execute docs/work/INTENT-investigation-workspace.md and its
> linked PLAN/ACCEPTANCE packet through all M0–M7 milestones. First recover and
> preserve the reviewed uncommitted thumbnail repair using the handoff/baseline
> manifest. Implement the actual native upstream Textfold engine, persistent
> claim/evidence investigation and linked manual/assistant paper drafter. Run
> the complete local acceptance suite and independent review, resolve material
> findings and record the release-ready result. Preserve production/research
> data. This instruction authorizes local implementation and verification;
> deployment and live paid inference remain separate explicit actions.

## Planning verification

The planning session inspected the existing workspace routes/providers,
Textfold format/adapter and document-global upstream engine, project roles,
source index/anchors, message/provider/usage infrastructure, migration chain and
test/CI/deploy commands. It validated the packet's local links, baseline hashes,
JSON fixture/quotation invariants and work pointer plus `git diff --check`.
Application suites were not rerun for these documentation-only planning edits.
There is no claim of independent implementation acceptance for the planned
feature; M7 requires that review after code exists.
