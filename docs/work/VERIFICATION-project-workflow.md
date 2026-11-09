# Project workflow — local verification

Intent: [INTENT-project-workflow.md](INTENT-project-workflow.md). User chose a
research dossier: questions → evidence → synthesis → experiment plan.

Implemented: project question, recent saved discussions, four explicit guided
tasks and a free-form question; task deliverables and reviewable instructions;
paper scope carried to discussions; inline failed-start feedback with draft
retention; distinct workspace navigation; a lazy-loaded brief/Textfold disclosure
and direct brief entry; first-visit Artifacts closed, explicit desktop preference
honored. Current imported Full source is used as prompt context when present.
Brief disclosure remains open through a successful save/refetch. Admin/editor/
viewer permissions remain those of the existing product.

Executed on 2026-11-09 against the final production build:

- `cd client && npm run build`: PASS, including lint and TypeScript checks.
  Existing warnings remain in DiscoverResultCard, paper page, ArtifactsPanel,
  Zotero components and metadataBase; no changed-file lint errors.
- `cd client && npm run test:textfold`: PASS (format/source fidelity, rejection,
  roundtrip, pinned upstream hashes/patch/license/notice).
- `cd client && npm run test:project-workflow:browser`: PASS at 1440px dark and
  390px light, with a fresh default layout and no collapsed-sidebar seed.
  Checks actual guided synthesis through the existing conversation/model-stream
  path (mocked), one submitted model request, selected paper scope, no writes on
  task selection, inline failure/retry, retained focus/source choices, resume
  order/links, desktop/mobile home navigation, brief entry/native initialization,
  imported source context, free-form mode, viewer/editor roles, credit blocking
  including Enter, empty-source/library flow and explicit artifact preferences.
- `cd client && npm run test:research-overview:browser`: PASS at 1440px and
  390px. Existing actual upstream engine/map, stable word IDs, local unfolding,
  keyboard, continuous zoom, exact citations, import/export, save failure,
  source invalidation, native highlights/reload/export and access checks pass
  via the new brief disclosure. This caught and verified the fix for a brief
  collapsing during save/refetch.
- `git diff --check`: PASS.

Browser commands used local Playwright and Chromium via
`OPENPAPER_PLAYWRIGHT_MODULE` and `OPENPAPER_CHROMIUM`, against a local production
frontend on 127.0.0.1:3011. Every API call, including model streams and project
writes, was intercepted. No live model, production mutation or database change.
Visual evidence: `/tmp/openpaper-workflow-1440.png` and
`/tmp/openpaper-workflow-390.png`; native-reader images use the existing
`/tmp/openpaper-textfold-*.png` names.

Scope limits: these are guided research discussions and an explicitly edited
saved brief. There is no automatic promotion of chat answers into verified
evidence, no automatic novelty verdict, and no experiment execution. No server
code/schema changed in this workflow follow-up; earlier Textfold migration and
backend test evidence remain in VERIFICATION-project-research-overview.md.

Independent review: `.meos/reviews/20261109T004539Z.md` returned **rework** for one
important finding: the persistent workspace list was not refreshed after creating
a discussion, so the new entry was absent when returning home. The reviewer
independently passed TypeScript, parser/vendor checks and diff checks; browser
reruns could not resolve Playwright in its sandbox, and it did not rerun the build.

Disposition: fixed by awaiting `refetchConversations()` after saving the pending
prompt/scope and before navigation. The browser mock now adds successful creates
to its list, requires the new discussion to appear first on client-side return,
opens it and verifies saved messages load without a second model request. The
new assertion failed against the pre-fix build, reproducing the review finding.
After the fix, the production build and full workflow suite passed at both sizes;
actual final browser stdout is `/tmp/openpaper-workflow-final-browser.log`.
The existing reader suite passed before this list-refresh-only fix; reader code
was unchanged. This is an author-verified resolution of the review finding, not
a claim that the reviewer issued a later acceptance verdict. No material findings
remain unresolved.

Local browser tooling used for reproduction:

```
OPENPAPER_PLAYWRIGHT_MODULE=/home/sammatuba/.npm/_npx/e41f203b7505f1fb/node_modules/playwright
OPENPAPER_CHROMIUM=/home/sammatuba/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome
```

Pass these as environment variables when running the documented npm browser
commands against the local frontend. These are session-local tooling locations,
not runtime dependencies of the application. The local frontend was stopped at
wrapup. No commit, push or deployment performed.
