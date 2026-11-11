# Restore private paper thumbnails

Operator report, 2026-11-11: paper thumbnails are not working. Existing preview
objects are present in the private production GCS bucket; an anonymous read of
one existing preview returns HTTP 403. Library APIs currently return persisted
unsigned preview URLs. The lightweight project paper list omits preview_url.

Return fresh signed preview URLs after existing paper ownership, project
membership or shared-paper access checks. Recover the object key from existing
configured storage URLs; preserve stored URLs and regenerate signatures on
read so existing papers need no reupload, backfill or schema migration.
Preserve external legacy preview links. Include preview metadata in the light
project query without loading PDF text/summary. Sign only recognized URLs in
the configured storage location; never fetch arbitrary URLs while signing.

Checks: reproduce anonymous production image denial; unit tests for signing,
expired signatures, encoded keys, foreign URLs, missing previews and failures;
API response regression checks for library/project/search/detail paths and
access denial; isolated PostgreSQL query/loading and membership checks;
relevant server suite and independent MEOS review. No inference, import,
production data mutation, bucket ACL changes or credential rotation.

Release is a separate concrete step after the local fix and verification.
