# REPORT: First end-to-end run of a real project in the live account (TARA capstone)

Date: 2026-11-19. Owner-authorized. Project: "TARA capstone: Independent Review When Every AI Reviewer Reads the Same Brief", `52bd2d45-c7b5-451c-ad58-1543524b8924`, on `https://papers.sammatuba.workers.dev`. Client under test for the interface steps: a local production build of `feat/spatial-workspace` (the canvas is not deployed), with every `/api` request forwarded to the live API.

This is the first time a real project went through import, evidence, draft, export and the canvas against the real server. Every earlier browser check mocked the API.

## Outcome

The run found two server defects that made Evidence unusable on real papers. One is fixed and deployed. The other is fixed, tested and built, and **waits for the owner's go to deploy**.

| # | Defect | Effect on a user | State |
| --- | --- | --- | --- |
| 1 | `publish_date` (a timestamp) was put into JSON answers and into the saved document unchanged | Reading a paper's lines returned 500, and saving a quoted finding failed, for every paper with a publication date. All 9 project papers were affected. | **Fixed and live.** `afbd6fee` on `fix/investigation-dated-papers`; revision `openpaper-00026-rum` at 100%. |
| 2 | The proxy (`encode zstd gzip` in the Caddyfile) appends `-gzip` or `-zstd` to the ETag of every compressed answer; through the Worker the tag also arrives weak. The server then rejects it as "Malformed If-Match". | The first save of an empty investigation works. **Every later save from a browser fails** with "Save failed". Paper note edits compare unequal the same way (tag read only; no note edit was attempted). | **Fixed, not deployed.** `16a7f1b6` on `fix/investigation-dated-papers`; image built, see Release below. |

Neither defect was reachable by the existing tests: fixtures had no publication date, and no test passed a tag through a compressing proxy.

## What was run

| Step | Result |
| --- | --- |
| Create the project; link the existing "AI Control" paper | 201; 1 paper |
| Import 8 sources by URL through the real pipeline | All 8 accepted and completed in one 145 s session; 9 papers in the project. No duplicate of an existing library paper. |
| Read every paper's extracted lines (`/investigation/sources/{paper}`) | First attempt: 500 for 8 of 9, then for the 9th once its date was filled in. After the fix: 9 of 9, 15,810 lines. |
| Save the investigation through the API (revision 1) | 5 claims, 15 findings (14 anchored to exact lines, 1 unbound), 19 relations, 4 sections, 11 blocks. All anchored findings read back `current`. |
| Refusals | A paragraph that cited the unbound finding: 409 "Review requires current accessible evidence". A stale tag: 412. |
| Exports | Markdown, BibTeX (years present) and bundle: 200. |
| Read-only interface journey, 1440 and 390 | 11 of 11 steps at both widths; 41 to 43 live API calls; no page errors; no horizontal overflow; no write attempted by the page. |
| Canvas | 1 question, 5 claims, 15 findings, 9 papers, 4 sections drawn from the live investigation. Claim tallies shown. |
| Reader from the canvas | "Open source" loaded the real PDF from storage and highlighted the quoted line. |
| Capture a finding through the Evidence interface | Add finding, search (10 results), Use these lines, Attach, describe, relate, Save. With the live server: **400 Malformed If-Match**; the page kept the work and offered download, retry and reload. With the harness removing the proxy's suffix from the tag (a stand-in for defect 2's fix): 200, revision 2, present after reload. |
| Add a section through the API (revision 3) | Threat model section added; the interface test finding archived; exports regenerated. |
| Revise claims and case text through the API, acknowledging paragraphs (revision 4) | 200. 10 paragraphs acknowledged with `reviewed_block_ids`; 13 of 14 blocks read back `current`. One paragraph that cites two revised claims and no finding stays `review_needed`; it is left so the owner can see that state. |

Temporary owner sessions minted: 19, each deleted on exit; the longest lasted 147 s. No token was printed or written to disk.

## What the run says about the design

### Worked as intended

- **Import is fast and hands-off.** Eight papers, including arXiv, a conference PDF, a journal PDF and a university repository copy, were processed in under three minutes.
- **Exact-line anchoring holds.** The server recomputed every quotation and both digests, refused a paragraph that cited unanchored evidence, and refused a stale save. The exports carry line ranges, source versions and a status per citation.
- **The canvas reads.** Question, claims, findings and papers in four columns, with support and challenge counts on each claim, gave the shape of the argument at a glance. Selecting a finding showed its claims and its source.
- **The reader lands on the quote.** From a finding to the PDF with the sentence highlighted was one click.
- **A failed save is handled well.** The page said so, kept the unsaved work and offered a download.
- **Overview** presents the case fields (provisional answer, tension, experiment, update criteria) clearly.

### Problems, most serious first

1. **Saves fail after the first one** (defect 2). Blocking until the fix is deployed.
2. **Extracted text is unreadable for two-column papers, and it is the unit of evidence.** Words run together and columns interleave. Measured on the nine papers: run-together tokens per 1,000 tokens were 523 (Fogliato, FAccT), 108 (AI Control), 51, 40, 12, 12, 11, 0.4 and 0. Table rows arrive as pipe characters in up to 42% of lines. Consequences seen in this run:
   - a captured quotation reads `fromtheproblemdescriptionandgeneratedsolutionthat…`;
   - search results are shown in that form;
   - search for "provisional decision" found nothing although the phrase is in an abstract, because the words are not separated in the text.
   Only the two single-column papers were clean. The quote highlight in the PDF still worked for a clean line.
3. **A draft can cite only findings anchored to a project paper.** An unbound finding (the owner's own earlier result) can be recorded but not cited. Sources that are not PDFs in the project (a web page, a system card kept elsewhere, own data) have no path into the draft. For this capstone, the grounding sources and the owner's pilot data are exactly what the draft needs to cite.
4. **Relating a new finding to a claim marks every paragraph that cites that claim "review needed".** After one finding was added and archived, the first paragraph of the draft was flagged. This follows the stated rule, but a growing project will be flagged constantly.
5. **The Brief panel opens on a nearly empty map** for a project built in the investigation views: three nodes (title, "Project context", the description). The investigation's content is under the second tab, "Write preview".
6. **Text drafted outside the app cannot be marked as AI-written.** The `assistant` provenance needs an in-app draft request. Text saved through the API was stored as "assembled" with an origin label, and the Write view shows "Assembled from source"; the origin label is not shown. This matters for the ChatGPT connector and any agent workflow.
7. **Publication dates and other metadata are filled in after import, in the background.** One paper's date appeared during the run. Metadata under a saved finding can therefore change later.
8. **A new finding is labelled "New finding"**, and the first search hit is taken as it stands; with garbled text the reader cannot judge the lines before attaching them.
9. **Canvas at 390 px** shows the question, the sections and part of the claims; the rest is reached by panning. Consistent with the desktop-first decision.
10. **Third-party scripts on signed-in pages:** the Google tag (already known) and `plausible.io`.

Independent review of the first fix also noted that re-inspecting the same lines after metadata hydration changes a finding's dependency digest and marks its paragraphs for review, because the digest covers title, authors, date and DOI. Whether that is intended is a product decision.

### Not exercised

Assistant drafting and Discuss (model credits; not authorized), audio, tables and charts, collaborators and invitations, the MCP connector, a viewer role, a real phone, and the client that is actually deployed (the interface steps used this branch's build). The note edit path was not attempted; only its tag was read.

## Release

| | |
| --- | --- |
| Hotfix branch | `fix/investigation-dated-papers`, from the deployed server commit `c757bbf0`; pushed |
| Fix 1 | `afbd6fee`; Cloud Build `e6ce7ebb-5b12-49f2-8b73-3a3ffb078a0f`; `server@sha256:505d4e7b74f508565124872671b1d39ebfdebdac23d4c7c32b24f744911fcbaa` |
| Deployed | Staged as `openpaper-00026-rum` (tag `dated`), smoke and 9 of 9 signed-in source reads on the staged URL, then 100% on the owner's go; tag removed. Client and Caddy images unchanged. No migration. |
| Rollback | `gcloud run services update-traffic openpaper --region asia-southeast1 --to-revisions=openpaper-00023-wov=100` |
| Smoke after promotion, both hosts | `/api/health`, `/`, `/login`, `/projects` 200; unauthenticated investigation 401; unauthenticated MCP POST 401 |
| Fix 2 | `16a7f1b6`; image `server:dated-etag-16a7f1b6`, digest `sha256:1ddcd9557d38512bf6fbd1d169bd809fdc8f91cfceef166c87cc3e7ff6db1e8d` (Cloud Build `4856ef9a-a153-4228-9dab-0f14eccc5457`). **Deployed 2026-11-20 on the owner's go**: staged as `openpaper-00029-jen` (tag `etag`), checked, then 100%; tag removed. Rollback: `openpaper-00026-rum`. Client and Caddy images unchanged. No migration. |
| Checks of fix 2 | Staged URL: health, `/`, `/login`, `/projects` 200; unauthenticated investigation and MCP POST 401; 9 of 9 signed-in source reads; a save sent with the received tag (`…:4-zstd`) answered 200 (revision 5); a tag one revision behind answered 412; a nonsense tag 400. After the traffic move, on both public hosts: the same smoke; a save through `papers.sammatuba.workers.dev` with the received tag (`…:5-gzip`) answered 200 (revision 6). Both saves sent the document unchanged; document and all statuses read back identical. On the two public hosts the stale-tag check also altered the project id in the tag by mistake, so there it shows a refusal (412), not specifically the stale-revision case; the staged check is the clean one. Not checked: a save from a real browser. |
| Case question reworded at the owner's request (2026-11-21, revision 7) | 200; only `case.question` changed; all block and finding statuses read back unchanged. |
| Note edit after fix 2 (2026-11-21) | Through `papers.sammatuba.workers.dev`: the existing note of one project paper was read with a browser's `Accept-Encoding` (tag ending `-gzip"`), sent back unchanged with that tag: 200; a wrong tag: 412; content read back identical. No note was created. |
| Development branch | Both fixes and the review follow-ups committed locally on `feat/spatial-workspace` (`cd09afcb`, `7091c036`, `032aa17b`), with the conversion path and the note path covered; not pushed. |
| Still to ship after fix 2 | The client change (revision parsed from a suffixed tag): `032aa17b` on the development branch, and `1cf4437d` on the hotfix branch `fix/investigation-dated-papers` (pushed 2026-11-21), which is the deployed code line. The deployed client computes `NaN` for the revision behind the proxy, so assistant drafting is expected to send no usable base revision. **No client image is built and nothing is deployed for this.** On the hotfix tree the expression was checked with node against four tags; the type check and lint ran on the development branch only. |

Fix 2 was deployed the same way: `gcloud run services update openpaper --region=asia-southeast1 --no-traffic --tag=etag --container=server --image=<image@digest>`, a save checked on the staged URL, then traffic moved.

## Checks

| Check | Result |
| --- | --- |
| Required PostgreSQL suite, development tree | 186 tests OK, zero skips (was 184 before the two new tests; the note test extends an existing one) |
| Required PostgreSQL suite, hotfix tree | 102 tests OK |
| New test for defect 1 on the pre-fix code | Fails with the production error (confirmed by the author and independently by the reviewer) |
| New test for defect 2 | Passes with the fix; fails on the parent commit (run by the reviewer) |
| Independent review of fix 1 (fresh Claude reviewer agent; same model family as the author) | Accept with findings: commit the fix on the development branch (done), test the conversion path (done), make the size check tolerant (done), and the product question above |
| Review of fix 2 (fresh Claude reviewer agent; same model family as the author) | **Accept with findings; safe to deploy as is.** The new test fails on the parent commit with "Malformed If-Match". Lost-update protection is unchanged: the format check, the UUID check and the comparison with the current revision still run under the row lock. Findings: the page parsed the revision out of the tag, so a suffixed tag gave no base revision for assistant drafting (fixed on the development branch, `032aa17b`; needs a client build; not exercised in a browser); the note path had no test with a suffixed tag (added, `032aa17b`); a README sentence was stale (corrected). |
| Client checks after `032aa17b` | Provider harness, investigation unit test, `tsc --noEmit` and eslint on the touched file: pass. They were run after the commit, not before it: the first attempt did not find `node` on the path. |

## Next

1. Done 2026-11-20: fix 2 is live. A note edit was checked at the API on 2026-11-21. Owner: confirm one save from a real browser. Owner: decide on a client build and deploy from `fix/investigation-dated-papers` at `1cf4437d`.
2. Owner: open the TARA project and judge the canvas as project home, with real content now in it.
3. Decide what to do about extracted text for two-column papers; it limits Evidence more than any interface choice.
4. Decide whether a draft may cite evidence that is not a project paper.
