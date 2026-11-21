# Verification: tutor mode in the paper chat

Intent: `docs/work/INTENT-socratic-tutor.md`. Written 2026-11-21 on
`feat/spatial-workspace`, uncommitted. Not built into an image, not deployed.

## What was run

| Check | Result |
| --- | --- |
| `cd server && GEMINI_API_KEY=test-key .venv/bin/python -m unittest discover -s tests` | 610 tests pass, 128 skipped (the suites that need the isolated cluster) |
| `server/.venv/bin/python scripts/ci/run_isolated_postgres.py` | 191 tests pass, none skipped; `tests.test_tutor_state_postgres` added to the required suites (5 tests) |
| `black==24.3.0` and `isort==5.13.2 --profile black` on the changed server files, from the repository root | No changes left to make |
| `cd client && tsc --noEmit` | Pass |
| `next lint` on `SidePanelContent.tsx`, `tutor/TutorPanel.tsx`, `lib/schema.ts` | No warnings or errors |
| `cd client && npm run build` | Pass |
| `npm run test:tutor:browser` against the production build on 127.0.0.1:3011, API mocked | Pass at 1440 px (light) and 390 px (dark) |

The server suite went from 570 tests to 610: 35 in `tests/test_tutor_mode.py`
and 5 in `tests/test_tutor_state_postgres.py`.

## What the tests hold

- **The state model** repairs what a model wrote: out-of-range levels, unknown
  phases, forty subskills, `Infinity`. It keeps the newest twelve notes.
- **The stream.** A tutor turn is sent through the real evidence parser and the
  state filter at every two-chunk cut and as one chunk. Each time the visible
  text is identical, the citation arrives and the stored state equals the state
  written. The same sweep runs for an ordinary answer.
- **The prompt.** A stored state reaches the next turn's system prompt with the
  next turn number. No stored state does not tell the tutor to restart a
  session that is visibly under way.
- **The endpoints.** `/chat/paper` saves the state on the assistant message.
  `GET /conversation/{id}` returns it to the owner. The shared-paper
  conversation does not carry it.
- **The lookup**, on PostgreSQL: the latest tutor turn wins, ordinary turns
  since then do not end the session, and another user's or conversation's
  state is never read.
- **The reader**, in a browser: the switch is remembered per paper; a tutor turn
  is requested with `style: "tutor"` and an ordinary one without; the state
  chunk draws the map and never appears as text; levels are withheld during the
  diagnostic; a command chip leaves a half-typed answer in place; a reload
  restores the map.

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

## Independent review

One round, by a Claude reviewer agent with a fresh context (not the Codex
reviewer `./meos review` runs). It read the change and drove the parser with
its own probe scripts. Verdict: accept with findings. It reported no leak of
state between users and no regression in the ordinary styles.

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

The fixes were made after the verdict and have not been re-reviewed.

## Not verified

- **No run against a real model.** There are no model credentials in this
  checkout. Everything above shows that a well-formed tutor reply is handled
  correctly, and that a malformed one costs nothing visible. None of it shows
  that a model, given this prompt, asks one question at a time, holds levels
  back until they are earned, or writes the state block on every turn.
- The authenticated production UI.
- Long sessions: how the state and the method hold up over dozens of turns.

## Known limits

- The switch is remembered in the browser (`localStorage`), per paper. The
  session itself is with the conversation on the server.
- A paper has one conversation, so it has one tutoring session. "Start over"
  begins a new one in place.
- A tutor turn costs what an ordinary turn costs: the paper is attached each
  time. Turns are longer by the state block.
- The same duplicate-yield and `strip()` pattern is in
  `multi_paper_operations.py` (project and library chat). Untouched here.
