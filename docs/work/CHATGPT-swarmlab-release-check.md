# ChatGPT handoff: live MCP acceptance and SwarmLab context

Status: **draft; wait for the deployment evidence before running**.
Run this in the existing ChatGPT thread containing the SwarmLab scaffold/RRL,
using the existing authenticated OpenPaper custom integration. No new
credentials, token sharing or fresh paper imports are needed.

## Prompt

Verify the deployed OpenPaper MCP project-management tools through my existing
authenticated connection. Confirm that `create_project`, `update_project`,
`list_project_papers`, `add_paper_to_project` and `remove_paper_from_project` are
available. If they are missing, report the actual tool availability and do not
pretend the release is verified. Use the available discovery/refresh behavior of
this existing integration if needed; do not register new credentials.

Call `list_projects` first. Look for **MEOS SwarmLab — Swarm Alignment 2026**,
including plausible earlier matching workspaces. Inspect any match and reuse
the correct existing project. Keep the reviewer-collusion project separate.

If no matching project exists, call `create_project` with exactly the JSON in
the next section. Preserve this UUID and the original creation payload for
every retry, including after later updates. On a timeout or uncertain result,
retry the same payload; never generate another UUID. After successful creation,
replay it once and verify the same project ID with `already_created`, and confirm
the project through `list_projects` and `list_project_papers`.

Use the earlier SwarmLab experimental scaffold and RRL already in this thread
to prepare a project description of at most 10,000 characters. Preserve source
references, prior findings and experimental caveats. Clearly distinguish prior
research results from new 2026 sprint hypotheses and planned experiments. Do
not invent missing outcomes or copy reviewer-collusion context into this project.
Save that description with `update_project` on the verified project, then verify
the saved metadata through `list_projects`.

Do not import or add research papers in this verification step. Do not test
unauthorized access against real third-party resources or unlink existing papers.
Report the actual tool names available, authenticated read/write results,
project ID, creation versus reuse, replay status and saved-context confirmation.
Report any errors without claiming release completion.

## Fixed creation arguments

```json
{
  "title": "MEOS SwarmLab — Swarm Alignment 2026",
  "request_id": "b3738396-babb-49cb-8645-3d1a27d049eb",
  "description": "SwarmLab research workspace for swarm alignment in 2026. Use the previous SwarmLab experimental scaffold and RRL from this ChatGPT thread as initial context. Preserve prior research results as prior evidence and distinguish them from new sprint hypotheses and experiments. Keep the earlier reviewer-collusion project separate. Populate the detailed project context from those existing sources after creation; verify project creation and authorization before importing any papers."
}
```

Machine-readable identical payload: [SWARMLAB-create-request.json](SWARMLAB-create-request.json).
This request has been allocated and persisted but **has not been sent**.
