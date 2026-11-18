# Research briefs and folded reading

Project home opens on a research workspace: the question recorded in the brief,
recent discussions, and tasks with concrete outputs. Start with **Compare the
evidence**, add a session focus if useful, select papers with @, then choose
**Start evidence comparison**. You can also **Resolve the tension**, **Assess
relevance & novelty**, **Plan the next experiment**, or **Ask my own question**.
Task selection is local; submission starts a normal saved project discussion.
Review the discussion instructions before sending if you want to see the full
guidance and project context. Failed starts retain your focus and source choices.

Check the cited passages, compare setups, and record your provisional synthesis
through **Read or update the brief → Edit brief** (project admins). Other members
can share conclusions with an admin. Discussions hold working analysis; the brief
holds the synthesis you choose to retain. Experiment planning drafts a test to run
in your research environment; bring the results back into the evidence comparison.
Resume discussions from the workspace or project navigation. Artifacts are
available from the header and open on request unless you saved an open preference.

Open **Research brief** for the folded reader. Explain why the answer matters,
what evidence points each way, how disagreements might be reconciled, and which
experiment would decide between the explanations. The landscape/novelty section
compares the closest existing work and records actual source coverage and search
dates; missing sections remain writing gaps.

Use **Edit brief → Use research framework** for the scaffold. Existing descriptions
remain intact. Markdown headings become the reader's sections. A one-line description containing inline headings offers an
explicit repair action in the editor; review the result before saving.

The five reading levels are Topic, Takeaway, Key, Brief and Full. Keys 1–5
select them in that order (1 Topic, 5 Full) while focus is inside the reader;
the arrow keys move one step on the level control. Under each paragraph, **Show
source sentences** opens that paragraph to the sentences its summary rests on,
**Show full text** opens the original paragraph, and **Fold back** returns it to
the document level. Tables, code, lists and quotations show their full text at Brief.
Original Markdown is retained for descriptions; source hyperlinks work across
folds, including Markdown reference links.

Descriptions fold locally by taking their leading sentences. These are excerpts,
not an automatic literature assessment. Guided tasks prepare instructions for
evidence comparison, synthesis, relevance/novelty and experiment design. Review
the response before editing the brief. Opening a project, selecting a task or
changing a reading level does not call a model.

**Import Textfold JSON** accepts the public
[`textfold/doc` version 0 format](https://github.com/chenxiachan/textfold/blob/main/docs/format.md)
from [Textfold](https://github.com/chenxiachan/textfold) or another compatible
writer. AI provenance, generated levels, source sentences, argument links and
extension fields survive import/export. Full and Brief must preserve source
wording; evidence indexes are zero-based sentence references. The importer checks
format, source excerpts, links, unique IDs and the 1 MB bound. It cannot establish
whether a cited finding is true, whether an AI summary follows from a passage,
or whether a literature search was comprehensive.

Imported reading levels are saved separately from the description. Editing the
description switches back to local excerpts; import fresh levels after finishing
source edits. API updates to descriptions also invalidate old levels unless a
replacement is explicitly supplied. Project admins can save briefs; project
members can read them under existing permissions. Failed saves keep the draft
open with an error and retry action.

For ChatGPT-authored projects, request these Markdown headings: The question;
Why this matters; Landscape and novelty; Evidence for; Evidence against; Tension
and possible reconciliation; Discriminating experiment; Update and abandonment
criteria; Sources and limitations. Ask for short point-first paragraphs, primary
citations, experimental setup differences, a search date and explicit coverage
limits. An authorized client of the existing create/PATCH project API can
optionally supply a validated `research_brief` document alongside `description`.

The reader is OpenPaper's own component (`client/src/components/fold/FoldedReader.tsx`,
level logic in `client/src/lib/fold-view.ts`). It renders the saved document in
the page with the app's Markdown renderer: no frame, no browser storage, no
request and no model call. The five reading levels and the `textfold/doc` format
originate from [TextFold](https://github.com/chenxiachan/textfold) by Xia Chen
(Apache-2.0); OpenPaper implements the format and ships none of TextFold's code.
Until 2026-11-18 OpenPaper embedded TextFold's reader; its word morphs, gesture
zoom, map canvas, display settings and browser-local highlights were not carried
over. See `docs/work/STRATEGY-native-fold-reader.md`.

Deployment requires migration `project_research_brief_01` before the updated web
service. The implementation session did not deploy or change production data.

Checks: `cd client && npm run test:textfold`, `npm run build`, and the mocked
`npm run test:research-overview:browser` and `npm run test:project-workflow:browser`
against a running production frontend.
The browser harness accepts `OPENPAPER_BROWSER_BASE`, `OPENPAPER_PLAYWRIGHT_MODULE`
and `OPENPAPER_CHROMIUM` for local tooling. Server tests run through the guarded
`scripts/ci/run_isolated_postgres.py` runner; no production database is used.
