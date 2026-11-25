# Finding passage verification

The change runs in the client on `feat/spatial-workspace` against `daec9f8f`. Opening an anchored passage reads the project-scoped line endpoint. The original PDF uses the separately authorized project file URL. The finding ID ties each folded section to the Evidence card.

## Checks

- Production client build and TypeScript passed. The build reported existing lint and metadata warnings.
- All nine scripts in `npm run test:textfold` passed. The Evidence regressions cover duplicate finding labels, reordered findings, identical text under different attribution labels at all five levels, and a quotation containing a Markdown heading and joined columns.
- The production Playwright investigation journey passed at 1440 and 390 CSS pixels using synthetic project responses and a rendered one-page PDF. It tested exact focus restoration from the card, selected Map node and Read section, including a non-default reading level. It exercised source and quotation digest changes, range loss, denied access, a missing extraction with a readable PDF, an unbound finding, and a 201-line quotation with valid and invalid full digests. Passage actions left the investigation write and model-call counters unchanged.
- After the second review fixes, the build, TypeScript, folding suite, diff check, and full Playwright journey passed again. Both viewport sizes rendered a standalone Markdown-style reference as a visible attributed quotation in Map and Read. A freshly loaded redacted finding offered the PDF from all three views, rendered the authorized PDF, and displayed an error with no PDF or quotation when file access was refused. A changed 20,001-character line produced the changed-passage message.
- After the third review fixes, the production build, TypeScript, the nine folding regression scripts, and the full 1440- and 390-pixel Playwright journeys passed. Both widths rendered the PDF before the held line request resolved. Map and Read showed separate unavailable and unbound statuses with zero quotation units for either finding.
- Final independent review accepted the working tree with no findings.

## Independent review

The first review requested rework (`.meos/reviews/20261124T153258Z.md`). The changes add attribution to map nodes, retain a PDF action on extraction failures, read ranges in chunks of up to 200 lines, verify the full quotation digest for multi-request passages, recognize a saved range past the end of the extraction, and exercise the three launch controls. The live work packet points to this slice.

The second review requested rework (`.meos/reviews/20261124T155111Z.md`). The Evidence card and folded views now offer a project-authorized PDF when the server returns a redacted source that is still in the project paper list. A line response of HTTP 413 marks the saved range as changed. Evidence field values use literal text in both folded views, including quotations that look like Markdown reference definitions.

The third review confirmed the preceding fixes and requested two changes (`.meos/reviews/20261124T234050Z.md`). Only anchored findings now produce quotation units. The Map selection and Read section show the unavailable or unbound status separately. The PDF control remains available while the line check is pending. The browser regression holds the line request open until a PDF page renders, then releases it and checks the verified text.

The initial follow-up run stalled and was interrupted. The retry returned **accept** with no findings in `.meos/reviews/20261124T235613Z.md`. The reviewer independently ran TypeScript, the nine folding regressions, browser-script syntax, work-pointer JSON parsing and the Git whitespace check. The desktop and narrow browser evidence comes from local production builds using synthetic project and file responses. The slice is uncommitted and unreleased.
