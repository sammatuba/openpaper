# Private paper thumbnail repair — verification

Intent: [INTENT-paper-thumbnails.md](INTENT-paper-thumbnails.md).

The library/active/recent, project list, search, owned paper detail and public
shared-paper detail now return freshly signed previews from the configured
storage location. Durable preview URLs stay unchanged in the database. The
project's light metadata query loads preview_url without loading raw PDF text
or summaries. External legacy image links are preserved; only the configured
host/bucket prefix is signed. Existing ownership/membership/sharing checks
precede serialization. No frontend changes or schema migration.

Executed on 2026-11-11:

- Existing production preview objects are present. One exact PNG read returned
  HTTP403 anonymously, then HTTP200 / valid PNG magic / 400487 bytes using the
  new helper's signed URL with configured GCS HMAC credentials. Credential
  values and signed URL remained in process memory; neither was printed or
  persisted. This was a storage read, not authenticated production API/UI
  acceptance of the undeployed change.
- Signing/download unit checks: 8 pass. Covers real botocore query signature,
  expired signature replacement, exactly-once key decoding, foreign hosts and
  buckets, missing/empty previews, legacy CDN and signer failure.
- Required isolated PostgreSQL runner: 75 pass, zero skipped, using
  `server/.venv/bin/python scripts/ci/run_isolated_postgres.py --run-existing`.
  The runner refused the default create path because a dedicated local cluster
  already exists. Deliberate reuse retained its exact socket, data-directory,
  ownership and TCP guards; it did not stop or delete that cluster. Tests create
  and drop their own schemas. Log: `/tmp/openpaper-preview-required-pg.log`.
- Full server suite with scrubbed dummy configuration: 459 tests, OK (48 skipped).
  PostgreSQL requirements were executed separately above. Log:
  `/tmp/openpaper-preview-server-tests.log`.
- The added suite exercises real PostgreSQL access checks, project membership,
  deferred metadata loading, API/search/detail serialization and unchanged
  stored URLs. The final required 75-test run also exercises anonymous
  shared-paper preview access followed by revocation without signing a denied
  preview. An earlier focused run exposed a reserved-email fixture error; the
  fixture was corrected to use example.com before that final passing run.

Independent MEOS review `.meos/reviews/20261110T162653Z.md`: **accept**, no
findings. Reviewer independently passed 8 signing/download checks and diff
checks and inspected the complete execution logs. Its sandbox blocked its
PostgreSQL rerun; its full-suite rerun stalled and was stopped. The required
PostgreSQL and full-suite executions above are author evidence.

Local source is uncommitted and undeployed; production still serves the earlier
revision. Release timing was asked explicitly after verification/review. No
imports, inference, production data updates, bucket permission changes or
credential rotation. The repair needs only a server image rollout, with no
migration or client/jobs rebuild.


Release update,2026-11-11: this reviewed repair was preserved and bundled in
source `c757bbf0`, independently reviewed with the complete feature and deployed
as web `openpaper-00014-vjm` at 100%. Investigation required PG 100 zero skips includes
the thumbnail regressions. No new authenticated production thumbnail API
readback is claimed; current-account UI acceptance remains open.
