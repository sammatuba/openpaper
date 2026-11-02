#!/bin/sh
# Dump the database and ship it to the bucket; keep BACKUP_KEEP_DAYS of history.
# DATABASE_URL_DIRECT is Neon's non-pooled string (pg_dump wants one session);
# falls back to DATABASE_URL.
set -eu
url="${DATABASE_URL_DIRECT:-$DATABASE_URL}"
bucket="${S3_BUCKET_NAME:?S3_BUCKET_NAME is required}"
keep_days="${BACKUP_KEEP_DAYS:-14}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="/tmp/openpaper-${stamp}.dump"

echo "dumping to ${out}"
pg_dump "$url" --format=custom --no-owner --no-privileges --file "$out"
size="$(wc -c < "$out")"
echo "dump size ${size} bytes"

aws s3 cp "$out" "s3://${bucket}/backups/openpaper-${stamp}.dump"
echo "uploaded backups/openpaper-${stamp}.dump"

# busybox date: no "-14 days" syntax, but @epoch works everywhere.
cutoff="$(date -u -d "@$(( $(date -u +%s) - keep_days * 86400 ))" +%Y%m%dT%H%M%SZ)"
aws s3 ls "s3://${bucket}/backups/" | awk '{print $4}' | while read -r name; do
  [ -n "$name" ] || continue
  s="${name#openpaper-}"; s="${s%.dump}"
  if [ "$s" \< "$cutoff" ]; then
    echo "pruning ${name}"
    aws s3 rm "s3://${bucket}/backups/${name}"
  fi
done
echo "done"
