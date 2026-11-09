# Project home as a research workspace

The project page currently presents a long brief, papers and artifact formats but
does not explain what to do next. Textfold addresses reading depth; it does not
provide a research workflow. The chosen bounded change makes existing research
discussions and the saved working brief usable as a dossier workflow, without
inventing experiment execution, verified evidence or completion scores.

User-confirmed direction: the primary workflow is question → evidence
comparison → synthesis → experiment plan. Reading/annotation supports this;
experiments still run in the researcher's experiment environment.

Local implementation: show task choices with concrete deliverables, an editable
focus and explicit start action; show recent discussions and a distinct home
navigation link; put the full brief and upstream Textfold behind an accessible
disclosure; make Artifacts opt-in for first-time visitors while honoring explicit
saved preferences. Guided discussions include the current brief as context and
source/uncertainty requirements. Starting a task must never save a brief or call
a model before the user submits. Keep free-form questions available. Preserve
paper mention scope, viewers, credit restrictions, mobile navigation and drafts
on failed conversation creation. Use the existing saved conversation mechanism,
not fictional evidence-ledger or experiment state. No commit, push or deployment.

Checks: production build/TypeScript, mocked browser at desktop/mobile showing
default sidebars; task selection causes no writes; intentional start passes the
right prompt and mentions to the conversation; failure retains draft and allows
retry; resume links, home navigation, empty/viewer/credit states, brief disclosure
and native Textfold remain accessible. Rerun the existing reader browser checks
with its disclosure entry point updated. Request focused independent MEOS review
and record actual evidence and unresolved findings.
