# ChatGPT importer acceptance after the hostname release

OpenPaper origin: https://papers.sammatuba.workers.dev
MCP endpoint: https://papers.sammatuba.workers.dev/api/mcp

In the existing Google OAuth client, register both exact redirects:
- https://papers.sammatuba.workers.dev/api/auth/google/callback
- https://papers.sammatuba.workers.dev/api/mcp/auth/callback

In ChatGPT workspace settings, update/reconnect the existing custom OpenPaper connection to the endpoint above. Refresh its tools/actions. Confirm import_paper_from_url(project_id,request_id,url) and get_paper_import_status(request_id) appear. Official instructions: https://developers.openai.com/api/docs/guides/custom-mcp-server . Do not paste OAuth credentials into chat.

Use list_projects then list_project_papers to verify the exact SwarmLab project and existing readings. Preserve the separate collusion project. Choose one authorized missing reading from scripts/research/swarm_alignment_2026_resources.json, persist a fresh request UUID, and use that identical UUID/project/URL for retries. On ambiguity, poll get_paper_import_status; never generate a new request to repair a stalled import. Confirm processing_status=completed, actual paper_id, project association, title and extracted text. submitted alone is not completion. Only then continue the separately authorized sequential reading imports. This release run creates no production paper or processing job.
