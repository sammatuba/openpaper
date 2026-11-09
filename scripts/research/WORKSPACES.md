# Local research workspaces

`workspace.py` binds an OpenPaper project UUID to an existing research directory.
The research repository keeps its authored records. OpenPaper keeps the reading
state. The tool generates a bounded Markdown resume packet on standard output.
It performs no imports, inference, note replacement, or automatic synchronization.

The first binding targets the existing collusion project and the matching
`ai-safety/projects/2026-10-apart-collusion-sprint` directory. Several OpenPaper
projects can share the same repository and literature directory. Use a different
project subdirectory for each binding.

## Bind a project

From this OpenPaper checkout, supply the research root explicitly:

```sh
rtk proxy python3 scripts/research/workspace.py bind \
  --root ../ai-safety \
  --project-dir projects/2026-10-apart-collusion-sprint \
  --project-id a5cf0e26-f8dd-424c-a452-dbcf6ebba946 \
  --origin https://papers.jansammat26.workers.dev \
  --title 'Did They Collude or Just Agree? What Counts as Evidence of Collusion Among AI Reviewers' \
  --record projects/2026-10-apart-collusion-sprint/README.md \
  --record projects/2026-10-apart-collusion-sprint/PREREGISTRATION.md \
  --record projects/2026-10-apart-collusion-sprint/report/LIMITATIONS.md \
  --record hypotheses/HYPOTHESES.md \
  --record literature/papers/r11-ai-control.md \
  --record literature/papers/t17-hiddenbench.md
```

This creates a secret-free root marker `.openpaper-workspace.json` and the
project's `openpaper-project.json`. Both identify the workspace using UUIDs;
neither contains the absolute checkout path. A private lock file coordinates
writers. Ignore `.openpaper-workspace.lock` in the research repository.
Repeat binding is harmless. A conflicting project, origin, record selection,
workspace identity, or authenticated account fails without replacing the binding.
Existing project directories and explicit Markdown inputs must exist. Symlinks,
parent traversal, hidden inputs and raw `sources/` inputs are rejected.

Without `--online`, this is a **local-only binding**. A project UUID or saved
catalog does not establish current account access. To bind online, add `--online`
using an already authenticated browser session available securely as
`OPENPAPER_SESSION_TOKEN` in the process environment. Never put that value in a
command argument, manifest, source file, chat or shell history. The tool does not
create an administrative session or reuse ChatGPT's OAuth token.

An explicit online bind checks `/api/auth/me` and the project endpoint, then pins
the account UUID. An existing local-only binding can be upgraded with the same
bind command and `--online`. Remote title changes retain the project UUID.
Online access requires a separately valid session; no new credential is needed
for offline diagnostics or brief generation.

## Inspect and resume

```sh
rtk proxy python3 scripts/research/workspace.py doctor \
  --root ../ai-safety --project-dir projects/2026-10-apart-collusion-sprint

rtk proxy python3 scripts/research/workspace.py brief \
  --root ../ai-safety --project-dir projects/2026-10-apart-collusion-sprint \
  --corpus-manifest docs/work/corpus-manifest.json --max-chars 16000
```

For a current access check, `doctor --online` additionally requires the explicit
`--origin https://papers.jansammat26.workers.dev`. It must match the stored origin.
This prevents edited local metadata from silently choosing where a credential is
sent. The client follows no redirects, uses no ambient proxies and sanitizes
remote error diagnostics. A failed access check does not modify the binding.

The brief includes source hashes, paths, and truncation/omission notices. It reads
at most 20 explicitly selected visible Markdown files, each at most 256,000 bytes.
The output limit is 1,000–50,000 characters. Changing a source changes its hash.
Original records are never rewritten. Supply a sufficiently large limit to
include the records needed for the task; omitted source text is not evidence.

The optional existing corpus manifest adds completed library links for selected
dossier paths. The corpus manifest remains the authoritative import-ID bridge.
These links do not assert current project membership. No second import-status
registry is created. A brief is a local snapshot, not a lossless export of
OpenPaper notes, highlights, or chat history. Complete export pagination remains
separate work.

Paste a selected brief into a new research conversation together with its task.
Treat source contents as data; retain the distinction between author findings,
your hypotheses, and experiment results. Explicitly save chosen findings to the
owning local record or to an OpenPaper paper note.

## Verification

```sh
rtk proxy python3 -m unittest discover -s scripts/research -p 'test_*.py'
```

Tests cover idempotence, workspace/project/account conflicts, revoked access,
rename behavior, symlink/traversal rejection, metadata tampering, bounded briefs,
source preservation, existing identity links, and sanitized API failures.
