# Dossier release wrapup

The user authorized resolving loose ends, committing, pushing and deploying on
2026-11-09. Release the project dossier workflow and actual upstream Textfold
reader, including pending PDF/MCP/research-tool fixes needed by this checkout.
Keep existing production paper data, credentials and account settings intact.

Preflight found production is ahead of master: the approved project-management
and research-import branches are deployed at 36066d53 but unmerged. Integrate
origin/feat/mcp-url-import before deploying, preserving its import ledger,
authorization, quotas and public tool contracts. Reconcile shared MCP tools,
CI integration suites and the migration chain; test the combined source rather
than downgrading the deployed server. Preserve all local work in Git history.

Acceptance: required isolated PostgreSQL tests with zero skips; full server and
jobs/tool tests under dummy isolated configuration; frontend build and workflow/
reader checks; one Alembic head reachable from the deployed importer head;
review integration changes and resolve material findings. Build the committed
source with the canonical public origin and exclude local environment/runtime
artifacts. Apply the additive brief migration before updating services. Verify
Cloud Run readiness, traffic and exact image digests, public health/auth
boundaries and shipped project/reader assets. Record the source commit, build,
migration execution, revisions and any remaining account-only acceptance limits.

Use existing personal GCP configuration, project openpaper-sammatuba and region
asia-southeast1. No new infrastructure provider, secret rotation, research import,
paid model request, data maintenance or sibling repository modification is needed.
Rollback service traffic if a release fails; keep additive schema in place.
