# ChatGPT research tools — first release

This is the first bounded expansion. Refresh the existing Open Paper connection's
available tools in ChatGPT after deployment, then start a new conversation with
that connection selected. Availability of research-mode integration must be
checked in the actual workspace.

## Find and verify evidence

> Use Open Paper search to find evidence about distributed information loss.
> Fetch each relevant result before making a claim. Include source links and
> extracted-text line locations. Distinguish the paper's evidence from your
> interpretation, and say if the indexed evidence does not answer the question.

`search` searches indexed PDF passages in papers you own. `fetch` accepts its
opaque evidence ID and returns the full passage item (up to 20,000 characters),
a citation URL and line locations. Changed or stale indexed text is rejected.
These lines are not PDF page numbers. Owned-paper links open the paper directly;
shared-paper links open an authorized project, where you select the cited paper
in the existing project reader. Very large passages require the existing
`read_paper_text` range reader. Search is lexical, not semantic, and excludes
unindexed papers, notes and external web sources. No match proves no absence.

## Resume a project

> List my projects, load the context for [project], and follow pagination.
> Summarize the research question, my saved observations, and what remains
> uncertain. Search evidence within this project and verify relevant passages.

Use `get_project_context(project_id, offset, limit)` and follow `next_offset`.
Context returns the existing project description, member paper metadata and
only your own notes/highlights/annotations. Other members' private notes are
not exposed. It does not invent a saved progress summary. For truncated notes,
call `get_paper_note` with its `next_offset`; other bounded lists report has_more.
`search_evidence` supports an authorized project_id, including papers shared by
other members. Outside a project it searches your owned library only.

## Explicitly save chosen observations

> Append exactly this selected observation to my note for [owned paper].
> Preserve existing notes. Read it back and verify it appears once.

`append_paper_note` uses a UUID request_id. Reuse that UUID for retries of the
same content/paper. It returns status and a note ETag; `get_paper_note` verifies
content and version in a fresh request. A retry does not append twice. Shared
project access does not grant write access to someone else's paper notes.
Changes remain subject to ChatGPT's tool confirmation settings. No chat history
is automatically saved. General ideas and experiments remain canonical in
ai-safety and use the reviewed repository workflow.

## Acceptance still requiring the operator

After refresh, confirm all five additions appear: search, fetch, search_evidence,
get_project_context and list_highlights. Run one search/fetch, then a selected
note append/readback, and load project context in a fresh conversation. Verify
the saved note in the Open Paper browser. Server protocol and isolated database
tests do not prove those account-specific ChatGPT interactions.

## Upload directly from ChatGPT (URLs and attachments)

After deployment, refresh the Open Paper connection again to discover the three
new tools (15 total). Select the connection and ask:

> Use Open Paper import_paper_from_url to import this direct PDF URL: [URL].
> Poll get_paper_upload_status until completed, then give me the paper link.
> Do not use browser automation.

Or attach a PDF to the ChatGPT conversation and ask:

> Use Open Paper upload_paper_file to upload this attached PDF directly.
> Use ChatGPT's file handoff, then poll get_paper_upload_status until completed.
> Do not use browser automation or invent a public URL for the file.

The file tool advertises official `openai/fileParams`; ChatGPT supplies a
`download_url` and `file_id`, optionally `mime_type` and `file_name`. It cannot
read a local `/mnt/data/...` path sent as a string. Account-specific file handoff
needs a real attachment acceptance check after refreshing tools.

Both paths validate the PDF and reuse existing storage/processing and quota
checks (30MB and800 pages). Optional project_id requires editor/admin access.
Normal processing costs still apply. The source must be downloadable via public
HTTPS, without an additional login; landing pages need a direct PDF URL.

Identical PDF bytes sent by the same user to the same destination through these
MCP tools reuse the same durable upload job, including when a signed attachment
URL changes. This does not reconcile uploads from the UI or earlier corpus
imports, and different project destinations have separate identities. Check your
library before importing previously uploaded papers. Existing notes are untouched.

Use the returned job_id for polling; only completed=true means the paper is
ready. Failed or interrupted claims are not automatically re-enqueued. A stalled
or uncertain job needs operator reconciliation; uploading again does not repair
it. The status tool is owner-only and does not cancel or mutate jobs.
