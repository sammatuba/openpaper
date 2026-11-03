# Curated corpus import and landscape bridge

`corpus-manifest.json` is an offline inventory of 48 authored dossiers and two
separate PDFs. The Apart report is a sprint report, not published literature.
It also records 3,598 landscape sources and 17 ideas, none of which are bulk
import targets. Twenty-six dossier entries currently have an exact identifier
match to at least one landscape source. These are candidate links, not proof of
full-text equivalence or endorsement of a relation. Ideas and graph edges remain
in ai-safety. The manifest contains paths, hashes, original read and dossier
statuses, identity aliases, and matching source IDs; it does not copy source
records or credentials. It does not change the landscape or its map.

Before any live requests, the reliability baseline must be verified and deployed.
The three-item pilot is authorized; the script has made no live
requests. Back up the manifest before editing; keep working state private if it
contains personal paper or project IDs. Do not run concurrent importers against
the same manifest. The manifest is a local checkpoint, not a distributed lock.

Pilot preflight on 2026-11-04 selected `local-pdf:2306.12001v6.pdf`,
`T17`, and `R11`. The local PDF is already represented by completed paper
`96732597-785f-46ca-88b6-eba26f43aa78` and is linked in the manifest; do
not upload it again. An older placeholder for the same PDF has a stale running
job and was left untouched. The T17 direct arXiv PDF and the R11 PDF linked
from the PMLR proceedings were checked as public PDF downloads; their exact
URLs are in the manifest. The owner authorized a temporary session of at most
30 minutes, with its token held only in memory and deletion on finish. Deploy
the reviewed reliability baseline before running the pilot.

The first pilot submission attempt received Cloudflare 1010 responses before
reaching the application. Read-only database reconciliation found no new upload
jobs and confirmed removal of the temporary session. The reviewed importer now
sends a descriptive user agent, which reached the app in an unauthenticated
probe; the two absent jobs were manually reset to `ready` for the approved retry.

The retry completed both new jobs. T17 paper
`7f1ebfc5-e0db-44d8-be46-2226aad97d1c` and R11 paper
`39a02fd5-6d03-4a93-aa45-fd8e08f421bc` each have extracted text and an
accessible signed PDF; their saved notes match their dossier files exactly.
Authenticated note responses include an ETag and expose it for credentialed
CORS. These are API checks; browser rendering of the new items remains a
separate check. The operator confirmed browser sign-in and rendering of the
existing 55-page paper, and confirmed ChatGPT OAuth connection and search.

Regenerate a fresh inventory to a new file (existing state is never overwritten):

```sh
python3 scripts/research/corpus.py inventory --manifest /tmp/corpus-new.json
python3 -m unittest discover -s scripts/research -p test_*.py -v
```

For each approved pilot item, first inspect its original dossier and verify the
identity against the library and existing jobs. The API does not expose reliable
complete library DOI/source matching or an upload idempotency key. A local
manifest alone cannot detect papers already uploaded outside this workflow.
Record known existing papers by setting `paper_id` and `status` to `completed`;
never submit an item before checking. For a new item, set `status` to `ready`,
and select either its existing `local_pdf` or a verified publicly accessible
**direct PDF** `upload_url`. Dossier pages and DOI landing pages are not assumed
to be PDFs. Record unavailable items as `skipped` with a reason in `error`.
Set an existing `project_id` and existing `tag_ids` as desired; no projects or
tags are invented. The local literature PDF can be piloted with ID
`local-pdf:2306.12001v6.pdf`; choose representative arXiv and non-arXiv
entries only after verifying direct PDF availability. Attach a dossier to a
previously imported local PDF by recording the same verified paper ID, rather
than uploading the PDF again. The report remains a separate item.

Authenticate by securely setting `OPENPAPER_SESSION_TOKEN` in the current
process environment to the authenticated browser session token, without writing
it to a file, shell history, command line, or chat. Supply the HTTPS origin
without a trailing slash, path, credentials, query, or fragment, and the
exact ID, for example:

```sh
python3 scripts/research/corpus.py step --base-url https://YOUR-ORIGIN --id local-pdf:2306.12001v6.pdf
```

Each invocation submits at most one item and polls once. Repeat to poll; it
persists the job and paper IDs atomically. A `failed` job remains terminal for
manual inspection. A `submitting` or `uncertain` state means the server may have
accepted the request without returning its job ID. Reconcile manually in the
application before setting a verified `job_id` and `submitted`, or resetting to
`ready` only after establishing no upload occurred. No automatic resubmission is
safe. Status-query errors leave the job resumable. A local crash between the
server accepting a request and receiving its ID requires the same reconciliation.

On completion, the importer checks project membership and verifies it after an
add, applies selected existing tags, and creates a dossier note only if none
exists. It never updates a note. The database enforces one note per paper; a
concurrent creation or lost response is recorded as `uncertain` and must be
inspected manually. A crash during creation can leave `creating`, which also
requires manual reconciliation before changing it to `created` or `pending`.
Full Markdown, including front matter, is saved verbatim. The reader's Notes
panel displays and edits paper notes as Markdown; it keeps a draft when a
concurrent save conflicts, so copy the draft before cancelling and refreshing.
Confirm the deployed panel displays imported dossiers acceptably during the pilot. This is
separate from generated summaries. An already existing note is marked
`existing_preserved`, and its dossier remains available locally instead of being
merged automatically. Check PDF rendering, metadata, citations and project chat
before expanding the pilot. No claim of live verification is made here.

The manifest is the versioned bridge: an entry joins its dossier ID and
`source_ids` to its verified `paper_id`; `identities` hold DOI, arXiv or exact
canonical URL aliases. An authenticated app link is
`https://YOUR-ORIGIN/paper/<paper_id>`. Export the completed links as JSON to
standard output with the read-only command:

```sh
python3 scripts/research/corpus.py bridge --base-url https://YOUR-ORIGIN
```

Each entry contains the dossier or local PDF ID, source IDs, identity aliases,
paper ID and link. A map consumer can join on `source_ids`; the output contains
only completed entries with explicitly recorded paper IDs. It is empty until
items are linked. Do not assume that a completed or manually entered ID has been
independently verified by the export; check it during the pilot. Keep the
landscape visualization and its own relation types unchanged. No arbitrary title
matching or inferred semantic edges are used. Resolve ambiguous identity matches
manually. The existing map does not yet consume this output automatically.
