# Research ecosystem handoff — 2026-11-04

Resume on `master`, tracking `origin/master`. Implementation commit:
`0a1cffe77bf844691f08897fd18361f2016b8a08`, also pushed to
`origin/feat/cloud-run-personal` and fast-forward merged into `origin/master`.
This handoff is committed separately after the implementation. The live pointer
is [current.json](current.json); run `rtk proxy bash ./meos start --runtime codex`
when starting a new session.

## Delivered and verified

- Live URL: https://papers.jansammat26.workers.dev.
- Durable outcome recovery, notes with ETags, authenticated OAuth MCP, Exa
  wiring, short hostname and corpus tooling are deployed. Full review findings
  and the importer User-Agent fix received independent Terra follow-up acceptance.
- Locked five-image Cloud Build `01c4c5da-c4d8-4ed9-abb9-9584aa1bd2a4`
  succeeded; migration `openpaper-migrate-wbpvx` succeeded; web revision
  `openpaper-00006-gfh` and jobs deployed; schedules updated.
- Frontend typecheck/build and mocked desktop/mobile notes checks passed.
  Recovery/CORS tests and isolated PostgreSQL crash/replay checks passed.
  [Verification](VERIFICATION-research-ecosystem.md) records the executed evidence
  and limitations; local independent reports remain under ignored `.meos/reviews/`.
- Operator confirmed Google login, existing 55-page PDF rendering, Notes, ChatGPT
  OAuth connection and paper search. A bounded one-result Exa check passed using
  the deployed image/runtime; its temporary job was deleted.
- Pilot completed: existing local PDF reconciled without reupload; T17 and R11
  imported with dossier notes created once. Authenticated readbacks verified
  PDFs, extracted text, exact source notes, ETags and credentialed CORS.
  IDs and state are in [the manifest](corpus-manifest.json) and
  [pilot evidence](corpus-import.md). Do not resubmit completed entries.
- Initial Python requests were rejected by Cloudflare before origin. Database
  reconciliation verified no new jobs before the reviewed User-Agent fix and
  successful retry. Temporary owner sessions and temporary Cloudflare config
  copy were cleaned up; the original authentication config was preserved.

## Next actions

1. Collect the operator's pending browser rendering confirmation for the two new
   pilot PDFs and their Notes. The previous session requested it but received no
   result before this handoff.
2. Verify a second login after 30 minutes without application activity.
3. After a full week, review GCP and Neon billing against the original P3 targets
   in [the deployment intent](INTENT-personal-cloud-run-deploy.md).
4. Validate citations and project chat before any corpus expansion. No expansion
   beyond this pilot was performed or authorized.
5. Separately reconcile the stale duplicate placeholder paper and running job;
   preserve them until resolved. Do not automatically delete or reupload them.

An unchanged PDF-viewer import produced background SSR `window`/`document`
errors in the local server. The route returned HTTP 200 and the mocked UI passed;
the existing PDF also rendered live. A separate baseline runtime was not rebuilt.
Concurrent database-pool saturation and live MCP note append were not verified;
do not describe paper search confirmation as proof of every MCP write path.
