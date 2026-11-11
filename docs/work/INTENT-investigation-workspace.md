# Native investigation workspace and paper drafter

Status: implementation intent prepared on 2026-11-11. This session is planning
only. The operator requested a precise packet that a new session can execute
end to end; no implementation of this feature has started.

## Outcome

A project opens as a persistent research investigation. A researcher can state
a disputed question, organize claims and exact evidence, inspect disagreements,
record a provisional reconciliation and discriminating experiment, then write
a manuscript whose paragraphs retain their evidence links. Textfold's actual
upstream interaction engine works in the OpenPaper DOM throughout this flow.

The primary acceptance journey is:

1. Open an existing project without changing its description, brief or papers.
2. Create a question and a claim. Attach two exact findings from project papers,
   one supporting and one challenging/qualifying that claim. Record their
   experimental conditions and a candidate explanation for the difference.
3. Unfold a finding from its topic to full source wording using native Textfold,
   then open the PDF in the existing reader without losing the case selection.
4. Create a draft paragraph from the selected argument, edit it, save, reload,
   and follow its citation back to the exact finding and source.
5. Explicitly request an assistant paragraph, inspect its proposed citations,
   and accept or discard it. Generating a proposal never edits the manuscript.
6. Change a cited claim/finding or replace its source text. The old paragraph
   remains intact and visibly needs review; no citation silently retargets.
7. Export Markdown, bibliography and a portable investigation JSON bundle.
   Existing descriptions, briefs, discussions, PDFs and MCP behavior still work.

## Binding product decisions

- One investigation and one manuscript per project in this release.
- Three project views: **Case**, **Evidence**, **Draft**. Default is Case.
  Use an ordered argument outline and a comparison inspector; a freeform canvas
  is outside this release. Textfold's Topic map remains available.
- David Africa's research-tension framework supplies the question, significance,
  evidence on both sides, explanations for disagreement, provisional synthesis,
  discriminating experiment and update criteria. Landscape/coverage limits stay
  explicit. Counts of papers or findings never become confidence/novelty scores.
- A finding is a specific result with a source anchor; support/challenge/qualify
  is a relationship to a claim. A paper can supply several findings.
- Textfold native means a scoped, lifecycle-managed mount of the pinned upstream
  engine in the host DOM, without iframe/srcDoc or another reader window in the
  new flow. Retain all five levels, word morphs, local unfolding, keyboard and
  continuous zoom behavior. Renaming the frame or substituting an unrelated
  accordion is insufficient.
- Durable, validated project state; explicit Save and real conflict handling.
  Local view state is separate. Admin/editor can edit the new investigation;
  viewer can read/export currently accessible content. Existing brief editing
  remains admin-only. The new permission does not extend to old settings.
- A manual drafter and an explicit assistant-proposal flow are both in scope.
  Reuse the existing model/provider, quota and saved-message infrastructure.
  No model call on navigation, folding, source selection, saving or export.
- Source matches establish quotation integrity, not scientific truth. Human
  interpretations and generated prose remain labelled as such. A proposed
  experiment is never presented as an executed result.

## Implementation contract and execution

[PLAN-investigation-workspace.md](PLAN-investigation-workspace.md) fixes the
storage, API, anchoring, reader, drafting and compatibility contracts and orders
the milestones. [ACCEPTANCE-investigation-workspace.md](ACCEPTANCE-investigation-workspace.md)
defines observable checks and the commands required before completion.
[HANDOFF-investigation-workspace.md](HANDOFF-investigation-workspace.md) gives
the exact entry point, baseline and pending thumbnail repair.

Complete every milestone, not just the reader spike or a static board. Resolve
routine implementation details within these contracts without reopening the
product direction. If the native engine cannot meet its mount/lifecycle checks,
continue the extraction work and report that milestone incomplete; the current
frame is only a compatibility reader, not a completion fallback.

## Boundaries

This is an additive app feature in this repository and its existing stack.
Preserve the reviewed uncommitted thumbnail repair. Preserve production papers,
research results and sibling repositories. No new infrastructure, library-wide
reindex, bulk import, automatic promotion of chat into evidence, public sharing,
novelty verdict, experiment execution, external document sync or new MCP tools.
Whole-paper Textfold conversion/OCR and a full LaTeX/DOCX editor are deferred.

The next execution session can implement, migrate disposable local test data,
run mocked-model/browser checks, fix review findings and prepare a release.
This planning request does not itself publish, push or deploy. Release commands
and rollback are part of the plan so deployment can follow an actual release
instruction without another design phase. The thumbnail deployment timing
question is unanswered; do not treat this request as its answer.

## Completion

All acceptance IDs pass with recorded commands, logs and desktop/mobile evidence;
required isolated database suites skip nothing; an independent MEOS review
accepts the final feature diff after material findings are resolved. Record
limitations honestly, including any account-only/live checks not performed.
Leave a precise release-ready handoff if deployment has not been authorized.
