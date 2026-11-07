# OpenPaper MCP project management

The authenticated MCP server now exposes five project operations. These tools reuse the existing SQLAlchemy project membership model and subscription checks. **No project creation or import was executed against a live user account during this change.**

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

Generate a random UUID for each *new* project creation request and keep it unchanged across retries. The server derives a stable project ID from the authenticated user ID and request ID. A repeated call with the same title and description returns `already_created`; a changed payload with the same request ID fails. This does not deduplicate independent requests with different UUIDs. Renaming an existing project is a separate operation.

Add and remove operations are state-idempotent (`already_present`, `not_present`). Update operations are idempotent when the same values are supplied.

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
```

Before deploying, run the app in its disposable development stack, exercise the five tools with authenticated owner, editor, viewer, and non-member accounts, and confirm a second `create_project` invocation using the *same* request UUID produces no duplicate.

After merge and deployment, reconnect/refresh the OpenPaper MCP integration if the ChatGPT tool manifest still lists only the older tools. Availability in source code does not imply availability on the deployed MCP endpoint.

## Deferred

Bulk management, shared-paper fork workflows, project deletion, account impersonation, and role administration are excluded from this extension. Adding those would require separate risk review.
