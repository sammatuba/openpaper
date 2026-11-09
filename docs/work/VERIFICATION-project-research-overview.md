# Project research overview — final verification

Implemented locally, 2026-11-09. Intent: INTENT-project-research-overview.md.
Usage: ../PROJECT-RESEARCH-BRIEFS.md. No production deployment or data change.

## Final implementation

Project home now has a question-centered overview, relevance/novelty prompts,
evidence-for/against and reconciliation framework, discriminating experiments,
update criteria, missing-section prompts and reviewable chat shortcuts. Viewer
and empty-project states retain the overview. The editor preserves failed-save
drafts and accepts validated public Textfold v0 JSON alongside Markdown.

The actual Textfold browser reader is reused from commit
`92ad625ab6887bf0060374c1fd86a558513baed2`, cloned at
`/tmp/openpaper-textfold-source`. The shipped assets, original Apache-2.0 LICENSE
and NOTICE, source/shipped SHA-256 manifest, update instructions and exact patch
are in `client/public/vendor/textfold/`. CSS, i18n and template are unchanged.
The JS patch supports an independently supplied unit Takeaway, including its
selection/notes, while preserving the legacy/common-prefix path. All word morphs,
zoom gestures/keyframes, paragraph expansion, Topic map and settings use upstream.
The earlier custom React reading UI was removed.

The OpenPaper adapter maps safe Markdown to native tokens/atoms, preserves exact
citation identity and case, maps IDs to safe internal IDs, allowlists roles,
performs single-pass template substitution and escapes script JSON. A local app
frame has no outbound connection permission; unconnected model actions are hidden.
Local native highlights/notes are scoped to user, document and SHA-256 source
revision using Textfold's existing saved-file namespace. Source revision is also
checked on frame-ready messages. UI and docs state browser/version-local storage.

Canonical original source, sentence anchors and provenance remain in the saved
public-format document. Imported folds persist separately in nullable JSONB
`project.research_brief`; changed descriptions invalidate stale folds unless
replacement levels are explicitly supplied. Project lists omit/defer full briefs.
Existing admin-write/member-read permissions remain intact. Local excerpt levels
do not call a model or claim a new research/novelty assessment.

## Executed checks

- Final production `npm run build`: PASS, including TypeScript and lint checks.
  Only existing warnings outside this change remain. No lockfile/dependency edits.
- `npm run test:textfold`: PASS. Actual TS parser/source/quote/anchor/format tests,
  rendered citation regressions, Unicode bounds, compact export reimport near
  1 MB, plus pinned upstream asset hashes and Apache license/notice checks.
- `./node_modules/.bin/tsc --noEmit`: PASS.
- Required isolated PostgreSQL runner: **28 passed, zero skips**. Real HTTP
  create/get/PATCH, source invalidation, explicit replacement/clear, invalid import
  rejection without mutation, viewer/outsider access, list omission and real
  migration downgrade/upgrade, plus existing required suites. Exact socket URL,
  data-directory and no-TCP guards and sanitized dummy environment were used.
  No server logic changed during the upstream reader revision.
- Integration launcher tests: **5 passed**.
- Final production-build browser suite: **PASS at 1440px and 390px**, mock-only APIs,
  no overflow/page errors. Desktop uses normal motion; mobile reduced motion.
  Verified actual upstream commit/API and word identities; map, global/local
  expansion and keyboard levels; fractional zoom position; nested-entity and
  multiline citation URL/title; duplicate-label/different-case/different-URL Brief
  selecting the correct source; independent Takeaway vs Key; repeated Topic words;
  template placeholders/special IDs/role injection; canonical export/reimport;
  draft retention and permissions; local Takeaway highlight exact quote, reload
  restoration without wrong Key marks, and native notes JSON export. The headless
  native file-picker fallback was used for download verification.
  Output: `/tmp/openpaper-textfold-final-browser.log`.
  Screenshots: `/tmp/openpaper-textfold-1440.png`,
  `/tmp/openpaper-textfold-390.png`; overview previews use openpaper-research-*.
- Exact patch applies cleanly to the pinned clone (`git apply --check`): PASS.
- `git diff --check`: PASS. Migration graph has one head,
  `project_research_brief_01`.

## Independent review and dispositions

The custom-reader baseline and source-fidelity fixes were independently accepted
in `.meos/reviews/20261108T162801Z.md`. The user clarified actual upstream reuse;
that earlier prototype was replaced.

`.meos/reviews/20261108T232218Z.md` verified upstream hashes/licenses and requested
exact Brief citation matching and level-aware Takeaway note anchors. Both were
fixed with regressions. `.meos/reviews/20261109T000403Z.md` independently verified
both corrections, legacy/common-prefix equivalence, TypeScript and asset/patch
hashes; it requested rework solely for pending final browser evidence.

That remaining evidence item is closed by the author's executed complete final
browser run recorded above and its retained output. The final run exposed and
resolved the iframe's missing local-form permission; CSP still blocks actual
network form actions and connections. No material code findings remain. This is
an author disposition of the final runtime-evidence item, not a claim that the
reviewer independently reran the browser or issued a new acceptance verdict.

## Handoff

Apply `project_research_brief_01` before deploying the updated web service.
Implementation is uncommitted and undeployed; unrelated existing dirty work was
preserved. No paid inference, paper import, production maintenance, commit or push
was performed. The clone is retained for reproducibility. The local test server
is stopped at wrapup. Next action: inspect the previews and usage guide, then
include this reviewed change in separately authorized release work with the
migration before the web service.

The upstream reader is embedded locally; the standalone Textfold model bridge,
PDF/math engines and bundled fonts are not installed. Source is read with system
font fallbacks. Papers and chat messages retain their existing readers.
