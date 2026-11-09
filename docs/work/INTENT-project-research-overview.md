# Project research overview and native Textfold

Replace the project landing page's centered description with a digestible,
question-centered research overview. Organize around David Africa's supplied
research-tension framework: question, relevance to AI safety, evidence for and
against, candidate reconciliations, landscape/novelty, discriminating experiment,
and update criteria. Missing material is an explicit gap, never an inferred finding.

Implement a native React reader of Textfold's public `textfold/doc` v0 format,
with Topic/map, Takeaway, Key, Brief and Full levels, independently expandable
sections, sentence anchors, provenance, and JSON import/export. Existing Markdown
descriptions work without a model call using labeled local excerpts. Imported
folds persist separately from descriptions; editing description invalidates stale
folds. Retain original text and source links; never treat project claims as verified
literature, score novelty automatically, or mistake absent counterevidence for
evidence against. Provide a guided Markdown template and explicit save failures.

Keep existing project access control and chat/paper navigation. Show the overview
for empty projects and viewers as well. Support narrow/mobile layouts, keyboard
reading controls, safe Markdown, and reduced motion. No external model call,
deployment, production data edits, import of papers, commit or push is authorized
by this local implementation. Preserve pre-existing dirty files.

Checks: TypeScript, production client build, focused parser/format tests, server
validation/API persistence and invalidation tests, migration graph, mocked browser
desktop/mobile including source anchors, map/levels, editing, import/export and
save failure. Request the MEOS independent review, resolve material findings, and
record actual evidence in VERIFICATION-project-research-overview.md.

References: supplied Africa article; https://github.com/chenxiachan/textfold and
https://github.com/chenxiachan/textfold/blob/main/docs/format.md (read 2026-11-08).
This is a native implementation of the public format and reading model, not a
claim to ship Textfold's standalone app, animation engine, model bridge or PDF engine.


User clarification (2026-11-09): Textfold should be reused from upstream rather
than independently recreating its interaction engine. Clone and inspect the
actual upstream code, pin reusable reader assets with license/attribution, and
integrate those into OpenPaper. The Africa research framework remains an
OpenPaper layer. The earlier custom-reader implementation is a tested baseline,
not completion of the clarified integration. Update implementation and browser
checks to prove the upstream engine is actually used. Preserve existing data
validation/persistence and original source/provenance guarantees.
