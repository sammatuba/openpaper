# Textfold reading space and TARA verification

Three live paper notes were appended and read back verbatim in the TARA project on November 26, Manila time. Yan grounds the human sequence comparison and faithful-brief cost. Kumaran et al. motivate tracking correct-to-wrong and wrong-to-correct transitions. Zanolini grounds shared-source failures and the distinction between marginal and joint miss rates.

The owner approved replacing the project brief, including clearing any previously imported reading levels. After updating the live project description, a fresh list request returned the exact 5,313 characters of the saved draft at `.meos/artifacts/tara-e2e/refined-brief-draft.md`. [Open the TARA project](https://papers.sammatuba.workers.dev/projects/52bd2d45-c7b5-451c-ad58-1543524b8924). The preregistration remains open. No research inference was run.

The first production client build and nine local folding checks passed. The project-workflow browser suite passed at 1440 and 390 px. The initial investigation and research-overview journeys exposed two assertions that accessed the hidden editor while reading. The corrected investigation and research-overview journeys passed on the production build at both widths. The investigation journey measured full workspace width and verified Back focus, scroll and unsaved draft recovery, plus navigation to a cited finding. The flow journey passed desktop and mobile, with a timing failure on the additional reduced-motion cache check; all three configurations subsequently passed in isolation.

## Independent review follow-up

The first independent review requested changes in `.meos/reviews/20261125T230809Z.md`. Project and rail links now dismiss the folded view on same-tab navigation without reopening the PDF. A relative Markdown link opened in a new tab keeps the current reading space. Both launch controls require a loaded project. Focus restoration now works for a dismissed chunk-load failure too. Back and Escape were exercised with unsaved prose, including an editor scrolled 80 pixels before opening from the persistent toolbar. The research intent records the owner's explicit replacement decision.

Fresh production builds passed in the development checkout and on production base `d0829efb`. Investigation, research-overview, and project-workflow browser journeys passed at 1440 and 390 px in both. The development flow suite also passed at both widths and with reduced motion, including the failed-chunk and previously open PDF scenarios. Release build `94ad55b3-aff8-42b2-aea0-283e0798e7c5` uses tracked client files from `b7e8d3d5`.

The second independent review reproduced a phone Back action reopening an already hidden PDF. The final change saves the visible panel on entry and restores that panel on Back, Escape, and toggle-close. The flow journey now also dismisses a failed reader load from the Write header and checks focus on that exact button. This produced intermediate release commit `d7dbc883`.

The release follow-up found that temporarily hiding a PDF could steal focus from the folded view and lose the original PDF opener. Commit `4eb50921` captures that opener on an explicit PDF open and restores focus when the paper reader closes. The extended investigation journey exercises Artifacts → PDF → Brief → Escape → PDF → Close and checks the source control. The staged preceding version passed a focused desktop and phone reading smoke test. The final Cloud Build ID is `ac5af8a6-5771-4ee6-be92-3951b6b147fe`.

Independent review accepted release commit `4eb50921` in `.meos/reviews/20261126T043842Z.md`. The reviewer reproduced both keyboard failures on the previous release commit and confirmed the fixes on the final commit. Both final local production builds and the full 1440 px and 390 px investigation journeys passed in both worktrees. Development commit `24319aa6` and release commit `4eb50921` were pushed.

## Production release

Cloud Build `ac5af8a6-5771-4ee6-be92-3951b6b147fe` succeeded. Revision `openpaper-00039-dey` serves release commit `4eb50921` at 100% traffic. The client digest is `sha256:1a69504bad6031fe484d4a926968d090d141587eaea4e90ca39dccd2c0f07231`. The server and Caddy image references matched the prior production revision, `openpaper-00035-ziw`. The temporary test tag was removed.

On the staged revision and again at the public hostname, Chromium exercised Overview, Evidence and Write at 1440 and 390 px with synthetic project API responses. Each header launcher was in view before scrolling, the document occupied the main area, Back returned focus to the launcher, and an unsaved question survived navigation. The public health endpoint returned healthy. The live research content was verified separately through the authenticated OpenPaper connector.
