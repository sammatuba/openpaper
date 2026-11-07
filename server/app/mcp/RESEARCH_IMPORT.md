# OpenPaper MCP research PDF import — rollout and SwarmLab

**Branch:** `feat/mcp-url-import`, based on the authenticated project-management feature `feat/mcp-project-management`. Deploy only from this reviewed branch (not `master`) until the earlier PR is merged.

## Scope

Two additive authenticated MCP tools:

- `import_paper_from_url(project_id, request_id, url)`: start one PDF ingestion job into a project where the authenticated user is admin/editor. Provide a fresh UUID for each distinct import and **reuse the identical request UUID and URL on retries**. A replay returns the durable existing request; a second UUID for the same canonical source returns `already_requested` instead of importing a duplicate. Existing owned arXiv papers are linked without new ingestion where their DOI can be matched.
- `get_paper_import_status(request_id)`: read the durable request and any associated upload-job/paper status; only the authenticated owner with current project edit access can see it. `submitted` means a job was accepted, **not that extraction completed**.

The new table `mcp_paper_import_requests` holds the request ID, project, canonical source key, original URL, upload job, paper, and status. Its unique constraints preserve retry identity and per-project/source deduplication. If a process crashes in an ambiguous state, the tool returns a durable `reserved`, `submitting` or `needs_reconciliation` state. **Do not start a new import** until the existing job and paper have been reconciled. The importer does not automatically retry failed/uncertain work.

## Network and access controls

This tool is deliberately **not** a general web-fetch endpoint.

- HTTPS only, explicit allowlist of known research publishers, no arbitrary ports/userinfo, no local/private DNS resolutions, no redirect following, 30 MB download limit, and PDF content validation.
- Convert arXiv abstract links and OpenReview forum links to their known PDF URLs. Reject publisher HTML landing pages and require a verified direct PDF URL instead.
- Use the existing browser PDF-processing client and Cloud Tasks pipeline. Preserve the separate reviewer-collusion project and existing library papers.
- Source provenance and bibliographic identity are not proofs of PDF integrity. Confirm publisher metadata and matching titles after extraction.
- DNS validation on trusted hosts is a defense in depth; avoid introducing arbitrary user-configurable host allowlists.

## Current sprint reading manifest

Pinned exact sprint resource links:
`scripts/research/swarm_alignment_2026_resources.json`.

Counts at collection time (7 Nov 2026):
- **32** entries total, including **28** research papers and **4** supporting resources.
- **2** papers already linked to SwarmLab via OpenPaper, no new ingestion needed.
- **19** pending papers use arXiv/OpenReview source URLs and can be attempted with this tool after release.
- **7** pending paper publisher landing pages require an explicitly verified direct PDF URL or an authorized local PDF upload workflow. Do **not** guess publisher PDF paths.
- **4** references (ARIA, CRUX, Concordia, A2A) are not papers; preserve as source links rather than importing them as PDFs.

SwarmLab project ID: `075d0311-79ed-5852-8a2c-151831ccfbd7`.

## Local checks

```bash
git fetch origin --prune
git switch --track origin/feat/mcp-url-import
cd server
uv sync --locked
uv run python -m unittest tests.test_mcp_research_url tests.test_mcp_research_import -v
uv run python -m unittest discover -s tests
cd ..
```

If the feature branch already exists locally, use `git switch feat/mcp-url-import` and `git pull --ff-only origin feat/mcp-url-import`. Keep local edits safe and verify `git diff --check` before deployment. Execute PostgreSQL integration and authenticated FastMCP tests in the disposable dev environment before merging.

## Deploy using your **local** personal GCP configuration

This release includes a **database migration**. Do not skip migration or recreate/rotate existing MCP signing and encryption keys.

```bash
export CLOUDSDK_ACTIVE_CONFIG_NAME=personal
gcloud auth list --filter=status:ACTIVE
gcloud config get-value project
# Record current Cloud Run web/jobs revision IDs before the release.
bash deploy/deploy.sh build backend
bash deploy/deploy.sh migrate
bash deploy/deploy.sh deploy
```

Read `deploy/README.md` and confirm `deploy/config.env` still targets the correct account, project, region, origin and `MCP_ENABLED=true`. Deploy from the exact feature commit; do not merge automatically or run infrastructure bootstrap. Health, auth rejection and OAuth discovery alone do not establish successful new-tool authorization.

## Acceptance and import protocol

1. Reconnect/refresh the existing ChatGPT OpenPaper integration after deploying. Confirm both tools appear. No new credentials shared here.
2. `list_projects` → verify the exact SwarmLab project. `list_project_papers` → record existing links.
3. Select **one** pending arXiv item (for example Distributional AGI Safety, https://arxiv.org/abs/2512.16856). Generate and persist one fresh UUID; call `import_paper_from_url`. If an error or timeout occurs, retry **only with that same request ID and URL**. Query `get_paper_import_status`, wait for completed job, then read back the actual project paper ID and extracted text/title. Never claim an ingest on a `submitted` response alone.
4. Once the pilot is confirmed, process the remaining canonical arXiv/OpenReview entries sequentially, reconciling status and duplicates after each batch; respect storage/compute quotas and rate limits.
5. For each publisher landing page, find an official available direct PDF link from the primary publisher or a valid open-access copy, then ingest with a new stable request UUID; record original landing URL separately in the manifest.
6. Verify all final project associations, dedupe by DOI/title, preserve failed/ambiguous rows, and report the remaining access/licensing blockers. No paper is removed automatically.

Current code has not been deployed or accepted through live MCP. No new papers were imported by this feature-branch work.
