# Nightly pg_dump of the Neon database to the R2 bucket. pg_dump must be at
# least the server's major; bump the tag if Neon moves ahead.
FROM postgres:18-alpine
RUN apk add --no-cache aws-cli
COPY backup.sh /usr/local/bin/backup.sh
RUN chmod +x /usr/local/bin/backup.sh
ENTRYPOINT ["/usr/local/bin/backup.sh"]
