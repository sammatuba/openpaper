# Owner corpus pilot

This is an administrative maintenance operation, not a user sign-in. It creates a database-backed session for the existing verified, active, unblocked owner and uses it against the fixed `https://papers.jansammat26.workers.dev` origin. The session expires in at most 30 minutes and is deleted in a `finally` block, including when an upload fails or a session commit has an ambiguous result. A forced process termination or unavailable database can prevent deletion; the expiry still limits the session lifetime. The database credential and session token stay in process memory and are never printed or written to a file. This requires the locally authenticated `gcloud` personal configuration, permission to read the `DATABASE_URL` secret, database connectivity, and the server virtual environment. No account is created.

Before running, obtain explicit approval for session creation and the selected pilot. Manually reconcile existing papers and ambiguous submissions, verify each input PDF and destination, and select at most three distinct IDs in the existing manifest. A `ready` status represents that manual preflight; `submitted` and `completed` entries can be resumed. The wrapper rejects uncertain states and identity conflicts. Each invocation advances each selected item by one `corpus.step`, so later polling or note work needs another explicitly selected invocation. Check the manifest after any interruption; never automatically resubmit an `uncertain` upload.

From the repository root, replace the quoted example IDs with the exact selected IDs:

```sh
server/.venv/bin/python scripts/research/operator_pilot.py --run-three-item-pilot --id 'FIRST-ID' --id 'SECOND-ID' --id 'THIRD-ID'
```

One or two IDs may be supplied instead. The target origin is intentionally fixed; changing the origin requires a code change and review. Tests are local and do not create sessions or access cloud services:

```sh
python3 -m unittest discover -s scripts/research -p test_operator_pilot.py
```
