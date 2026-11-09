# OpenPaper MCP project management

The authenticated MCP server exposes five project operations. These tools reuse the existing SQLAlchemy project membership model and subscription checks. Release evidence belongs in `docs/work/VERIFICATION-mcp-project-release.md`.

| Tool | Permission | Behavior |
| --- | --- | --- |
| `create_project(title, request_id, description?)` | Authenticated user, within plan's project quota | Atomic project and creator admin role creation; UUID `request_id` ensures a retry does not duplicate the project |
| `update_project(project_id, title?, description?, clear_description?)` | Project admin | Updates only explicitly supplied fields |
| `list_project_papers(project_id, offset?, limit?)` | Project member | Paginated project paper metadata; no signed PDF links |
| `add_paper_to_project(project_id, paper_id)` | Project admin/editor and paper owner | Checks quota and association before adding |
| `remove_paper_from_project(project_id, paper_id)` | Project admin/editor | Unlinks association only; underlying library paper and notes remain |

## Auth boundary

Each tool obtains the actor exclusively through `current_user(db)` in `server/app/mcp/server.py`. This verifies the Google OAuth token and maps its email to an active, unblocked database account. No tool accepts a user ID, email, or role argument from the caller. The project and paper operations then check membership and ownership against database state.

Do not treat model-authored roles or paper IDs as authority. UUIDs identify resources; they do not authorize them.

## Retry semantics

Generate a random UUID for each *new* project creation request and keep it unchanged across retries. The server derives a stable project ID from the authenticated user ID and request ID and records the original payload hash in `mcp_project_requests`, atomically with the project and creator membership. Titles are trimmed; omitted and null descriptions are equivalent. A repeated call with the same original payload returns `already_created` with the project's current metadata, even after a rename or description edit. A changed original payload fails. After project deletion the request history remains and the server rejects reuse without recreating the project. This does not deduplicate independent requests with different UUIDs.

MCP creation, browser creation, and invitation acceptance serialize quota admission on the user's row until their transaction commits. Replay lookup precedes quota checking; a retry of a successful request consumes no additional capacity.

Paper additions through MCP, browser batches and PDF-upload associations lock the project before checking duplicates and capacity. Browser batches commit together and count only distinct, new associations. A database constraint enforces one association per project/paper pair. The release migration retains one row for any legacy duplicate link; underlying research content is untouched.

Add and remove operations are state-idempotent (`already_present`, `not_present`). Update operations are idempotent when the same values are supplied.

Removing a project-paper association is annotated `destructiveHint=True`: it changes shared project contents. The explicitly authorized project-management scope permits this bounded unlink; it preserves the underlying paper, notes, highlights and annotations. MCP project deletion and role administration remain excluded.

`update_project` is also annotated `destructiveHint=True` because overwriting fields or clearing a description can remove prior content.

## Validation

- Project title: 1–200 characters after trimming.
- Project description: at most 10,000 characters.
- Project IDs, paper IDs and creation request IDs: valid UUID strings.
- Paper list: `offset >= 0`, `1 <= limit <= 100`.
- Members can list; only admins may update; admins/editors may add or remove; a member cannot link someone else's paper by its UUID.
- The quota gate is evaluated only for new projects or new project-paper associations.

## Test and rollout

Run from `server/`:

```bash
uv run python -m unittest tests.test_mcp_project_tools
uv run python -m unittest discover -s tests
uv run python ../scripts/ci/run_isolated_postgres.py
```

Before deploying, run the app in its disposable development stack, exercise the five tools with authenticated owner, editor, viewer, and non-member accounts, and confirm a second `create_project` invocation using the *same* request UUID produces no duplicate.

The required PostgreSQL runner creates a socket-only cluster and rejects skipped tests; `--run-existing` uses only an existing guarded disposable cluster without stopping or deleting it. Its transport tests use actual mappings and quota checks and substitute Google token verification only. Actual OAuth is verified separately against the live installation with an existing authorized connection.

Build the reviewed backend, apply the additive ledger migration with `bash deploy/deploy.sh migrate`, then deploy. Application rollback leaves the ledger migration and its records intact. Do not downgrade production schema to roll back code.

After merge and deployment, reconnect/refresh the OpenPaper MCP integration if the ChatGPT tool manifest still lists only the older tools. Availability in source code does not imply availability on the deployed MCP endpoint.

## Deferred

Bulk management, shared-paper fork workflows, project deletion, account impersonation, and role administration are excluded from this extension. Adding those would require separate risk review.
