# Verification: tutor mode in the paper chat

Intent: `docs/work/INTENT-socratic-tutor.md`. Written 2026-11-21.

Committed on `feat/spatial-workspace` as `d9cd3ec5` and the rework commit that
follows it. Because that branch also carries unreleased work, the release is
cut from two branches that hold only this change on top of what is live:
`feat/tutor-mode-server` (on `fix/investigation-dated-papers`, the live server)
and `feat/tutor-mode-client` (on `a3be08ca`, the live client). Conflicts on
both were confined to script lists (`client/package.json`,
`scripts/ci/run_isolated_postgres.py`).

## What was run

On `feat/spatial-workspace`:

| Check | Result |
| --- | --- |
| `cd server && GEMINI_API_KEY=test-key .venv/bin/python -m unittest discover -s tests` | 616 tests: 488 pass, 128 skipped (the suites that need the isolated cluster) |
| `server/.venv/bin/python scripts/ci/run_isolated_postgres.py` | 191 tests pass, none skipped; `tests.test_tutor_state_postgres` added to the required suites (5 tests) |
| `black==24.3.0` and `isort==5.13.2 --profile black` on the changed server files, from the repository root | No changes left to make |
| `cd client && tsc --noEmit` | Pass |
| `next lint` on `SidePanelContent.tsx`, `tutor/TutorPanel.tsx`, `lib/schema.ts` | No warnings or errors |
| `cd client && npm run build` | Pass |
| `npm run test:tutor:browser` against the production build on 127.0.0.1:3011, API mocked | Pass at 1440 px (light) and 390 px (dark) |

The server suite went from 570 tests to 616: 41 in `tests/test_tutor_mode.py`
and 5 in `tests/test_tutor_state_postgres.py`.

The release branches are checked again in the release record at the end.

## What the tests hold

- **The state model** repairs what a model wrote: out-of-range levels, unknown
  phases, forty subskills, `Infinity`. It keeps the newest twelve notes.
- **The stream.** A tutor turn is sent through the state filter and the real
  evidence parser at every two-chunk cut and as one chunk. Each time the
  visible text is identical, the citation arrives and the stored state equals
  the state written. The same sweep runs for an ordinary answer, and for a
  tutor reply that never closes its evidence block.
- **The prompt.** A stored state reaches the next turn's system prompt with the
  next turn number. No stored state does not tell the tutor to restart a
  session that is visibly under way.
- **The endpoints.** `/chat/paper` saves the state on the assistant message and
  sends it to the reader only after that save; a reply that is only state, or a
  save that fails, sends none. `GET /conversation/{id}` returns it to the
  owner. Neither the shared-paper conversation nor a project conversation
  carries it. A tutor turn aimed at any conversation but the paper's own is
  refused before the model is called.
- **The lookup**, on PostgreSQL: the latest tutor turn wins, ordinary turns
  since then do not end the session, and another user's or conversation's
  state is never read.
- **The reader**, in a browser: the switch is remembered per paper; a tutor turn
  is requested with `style: "tutor"` and an ordinary one without; the state
  chunk draws the map and never appears as text; levels are withheld during the
  diagnostic; a command chip leaves a half-typed answer in place; Save state
  copies the session and sends nothing; a reload restores the map.

## Defects found in the existing paper chat and fixed

Tutor mode puts content after the evidence block on every cited turn, which is
the path these were on. They affected ordinary answers too.

1. Text a model wrote after its evidence block was shown twice (once when the
   block closed, again when the buffer flushed). Confirmed by restoring the old
   line: the new test fails with "As Ask me about the decoder".
2. That text was cut from a stripped copy of the buffer, so a chunk ending in a
   space lost it and two words joined.
3. An evidence block that opened and closed inside the stream's last chunk was
   dropped whole: no citations.

A block the stream ends inside is still dropped, as before.

## Independent review

### Round 1: Claude reviewer agent, fresh context

Before the commit. It read the change and drove the parser with its own probe
scripts. Verdict: accept with findings. It reported no leak of state between
users and no regression in the ordinary styles.

| Finding | Severity | Disposition |
| --- | --- | --- |
| `covered` and `misconceptions` kept the first 12 lines, dropping every newer one | important | Fixed: the last 12 are kept, and the prompt states the cap |
| The evidence parser's `strip()` joined words after the block and corrupted state strings | minor | Fixed (defect 2 above) |
| Evidence and state arriving together in the last chunk lost both | minor | Fixed (defect 3 above) |
| A first turn that lost its state made the next turn restart the session | minor | Fixed in the session-state wording; how a model responds is untested |
| "Just tell me" contradicted the diagnostic rule, and the panel offered it then | minor | Fixed: the prompt says what it means during the diagnostic; the panel offers "I don't know" instead |
| Command chips discarded a typed draft | minor | Fixed: a command is sent on its own |
| `OverflowError` from `Infinity` failed the turn | nit | Fixed |
| A state block wrapped in a code fence leaves an empty code box | nit | Not fixed in code. The prompt now says to write the markers as plain lines |
| Client kept an abandoned attempt's state after a restart | nit | Fixed |
| Panel accessibility and design guide | nit | Disclosure now uses `ui/collapsible`; the target mark has a role; the map is keyboard-scrollable; disabled controls say why. The level bar stays hand-built: `ui/progress` is a 0 to 100 bar |
| Tests that passed with the behaviour broken | — | Endpoint tests added; the sweeps now go through the real parser and compare the state's content |

### Round 2: `./meos review` (GPT reviewer through Codex), on `d9cd3ec5`

Report: `.meos/reviews/20261121T045402Z.md`. Verdict: **rework**. Two of its
findings were caused by a round 1 fix (parsing an evidence block the stream
ended inside). The images built from `d9cd3ec5` were not deployed.

| Finding | Severity | Disposition |
| --- | --- | --- |
| "Save state" had the tutor write its notes on the learner into the visible chat, which a shared paper shows | blocking | Fixed. Save state is now done by the reader: it copies the stored session to the clipboard. The prompt tells the tutor not to write the session out |
| A reply that never closed its evidence block could carry the state into a citation, and citations are shared | blocking | Fixed twice over. The state is lifted out of the raw text before evidence is parsed, and an unclosed evidence block is discarded again |
| A tutor turn could be saved to a conversation other than the paper's own (the request names both separately), where project members read the trace | blocking | Fixed. A tutor turn is refused unless the conversation is this user's conversation for this paper; the project conversation reader also strips the state |
| Ordinary chat showed an unfinished evidence block as a citation | important | Fixed: reverted to dropping it. Introduced by the round 1 fix, never released |
| The panel could show a state the server did not save (a reply with no visible text, or a failed save) | important | Fixed: the state is sent to the reader only after the turn is saved |
| The work packet called the change uncommitted and counted skipped tests as passes | minor | Fixed in this record and in `current.json` |

### Round 3: `./meos review` on the rework

See the release record.

## Not verified

- **No run against a real model.** There are no model credentials in this
  checkout. Everything above shows that a well-formed tutor reply is handled
  correctly, and that a malformed one costs nothing visible. None of it shows
  that a model, given this prompt, asks one question at a time, holds levels
  back until they are earned, or writes the state block on every turn.
- The signed-in production UI.
- Long sessions: how the state and the method hold up over dozens of turns.

## Known limits

- The switch is remembered in the browser (`localStorage`), per paper. The
  session itself is with the conversation on the server.
- A paper has one conversation, so it has one tutoring session. "Start over"
  begins a new one in place.
- A tutor turn costs what an ordinary turn costs: the paper is attached each
  time. Turns are longer by the state block.
- A shared paper shows its tutoring chat like any other chat: the questions,
  the answers, and any skill map the tutor drew in it. What it does not show is
  the stored session.
- The ordinary chat's request still names the paper and the conversation
  separately and does not check that they match. Only tutor turns are checked.
- The same duplicate-yield and `strip()` pattern is in
  `multi_paper_operations.py` (project and library chat). Untouched here.
