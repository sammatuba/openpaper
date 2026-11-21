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
| `cd server && GEMINI_API_KEY=test-key .venv/bin/python -m unittest discover -s tests` | 633 tests: 501 pass, 132 skipped (the suites that need the isolated cluster) |
| `server/.venv/bin/python scripts/ci/run_isolated_postgres.py` | 195 tests pass, none skipped; `tests.test_tutor_state_postgres` added to the required suites (9 tests) |
| `black==24.3.0` and `isort==5.13.2 --profile black` on the changed server files, from the repository root | No changes left to make |
| `cd client && tsc --noEmit` | Pass |
| `next lint` on `SidePanelContent.tsx`, `tutor/TutorPanel.tsx`, `lib/schema.ts` | No warnings or errors |
| `cd client && npm run build` | Pass |
| `npm run test:tutor:browser` against the production build on 127.0.0.1:3011, API mocked | Pass at 1440 px (light) and 390 px (dark) |

The server suite went from 570 tests to 633: 54 in `tests/test_tutor_mode.py`
and 9 in `tests/test_tutor_state_postgres.py`.

The release branches are checked again in the release record at the end.

## What the tests hold

- **The state model** repairs what a model wrote: out-of-range levels, unknown
  phases, forty subskills, `Infinity`. It keeps the newest twelve notes.
- **The stream.** A tutor turn is sent through the state filter and the real
  evidence parser at every two-chunk cut and as one chunk. Each time the
  visible text is identical, the citation arrives and the stored state equals
  the state written. The same sweep runs for an ordinary answer, for a tutor
  reply that never closes its evidence block, and for a state whose own JSON
  contains the closing marker. Nothing after a malformed state block is shown.
- **The scrub.** A state that arrives without its markers (bare, fenced, under
  a misspelt marker, or cut off) is removed from the reply and from its
  citations before they are saved; text that is not a state, JSON included, is
  returned untouched, and an ordinary answer is never scrubbed.
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
- **Sharing**, on PostgreSQL: the shared-paper conversation returns no
  tutoring turn, neither the learner's half nor the tutor's, with or without a
  stored session; its pages stay full around a tutoring session; the owner
  still reads every turn.
- **The reader**, in a browser: the switch is remembered per paper; a tutor turn
  is requested with `style: "tutor"` and an ordinary one without; the state
  chunk draws the map and never appears as text; levels are withheld during the
  diagnostic; a command chip leaves a half-typed answer in place; the session
  cannot be exported and its notes are never on the page; a reload restores
  the map.

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
| "Save state" had the tutor write its notes on the learner into the visible chat, which a shared paper shows | blocking | First moved to the reader (copy to clipboard), which round 3 showed only moved the problem. Removed in the end: see round 3 |
| A reply that never closed its evidence block could carry the state into a citation, and citations are shared | blocking | Fixed twice over. The state is lifted out of the raw text before evidence is parsed, and an unclosed evidence block is discarded again |
| A tutor turn could be saved to a conversation other than the paper's own (the request names both separately), where project members read the trace | blocking | Fixed. A tutor turn is refused unless the conversation is this user's conversation for this paper; the project conversation reader also strips the state |
| Ordinary chat showed an unfinished evidence block as a citation | important | Fixed: reverted to dropping it. Introduced by the round 1 fix, never released |
| The panel could show a state the server did not save (a reply with no visible text, or a failed save) | important | Fixed: the state is sent to the reader only after the turn is saved |
| The work packet called the change uncommitted and counted skipped tests as passes | minor | Fixed in this record and in `current.json` |

### Round 3: `./meos review` on the first rework (`a88966d2`)

Report: `.meos/reviews/20261121T050607Z.md`. Verdict: **rework**. It confirmed
three round 2 findings closed (unfinished evidence, state before citations,
the conversation check) and found no regression in the ordinary parser across
201 further checks. The images built from this commit were not deployed.

What the state is protected from is set by the intent: people who read the
learner's chat without being the learner, which here means readers of a shared
paper and members of a project. The service's operator is not in that set. The
operator reads the database, the logs and the traces, and every message in
them, tutor mode or not.

| Finding | Severity | Disposition |
| --- | --- | --- |
| The copied session is resumed by pasting it into the chat, which stores it as a message a shared paper shows | blocking | Fixed by removal. There is no Save state and no "resume from": the session is kept with the paper and resumes by itself, which is what those two commands were for. The prompt tells the tutor never to write the session into the chat |
| A closing marker inside the state's own JSON ended the block early and showed the rest of the state as text | blocking | Fixed. The filter fails closed: after the opening marker nothing is visible until a closing marker follows complete JSON, and a malformed block takes everything after it with it |
| Provider traces and debug logs record the system prompt, which carries the state; a failed save can put exception text in telemetry | important | Not changed. Operator-side, and true of every prompt and message in the service already |
| The admin message view shows `trace` | important | Not changed. Same reason: the administrator of this service is its operator |
| A reader left open across an account switch in another tab keeps the previous session on screen | important | Partly. The panel is cleared when the signed-in user or the conversation changes. A tab that never learns of the switch keeps its whole chat on screen, not only the panel; that is how the reader already behaves |
| A reply whose save failed still looks delivered until reload | important | Not changed. True of ordinary chat as well: the stream has no "saved" acknowledgement, and the server does keep a partial answer after a mid-stream error, so the client cannot tell the two apart. Worth its own change |
| The work pointer was stale and this record pointed to a release record that did not exist yet | minor | The release record is written at release, below |

### Round 4: `./meos review` on the second rework (`b64f2d01`)

Report: `.meos/reviews/20261121T051546Z.md`. Verdict: **rework**. It confirmed
the save and resume finding closed, agreed that operator access is outside
decision 5, and reported no regression in the ordinary paper chat. The images
built from this commit were not deployed.

| Finding | Severity | Disposition |
| --- | --- | --- |
| The "is the block finished" check used the lenient JSON reader, which accepts prose containing a fenced JSON example, so a contrived note could still end the block early | blocking | Fixed. The block ends only where everything before the marker parses, start to end, as one JSON object; a fence is allowed only around the whole object |
| A state written with its opening marker missing or misspelt is never seen as a block and is saved as reply text | blocking | Fixed at the point of storage. A tutor reply and its citations are scrubbed before saving: any JSON object carrying a state's keys is cut out, with stray marker lines, and an unfinished one is cut to the end. The reader is sent the cleaned reply in place of the streamed one |
| A history read or reply already in flight when the user or conversation changes could put the old session back on screen | important | Fixed: each notes the session it started under and checks before writing. A tab that never learns of an account switch is unchanged, as recorded in round 3 |
| The work pointer and the release record | minor | Written at release, below |

A limit was recorded here as not removable by a filter: the tutor is given its
notes so that it can teach from them, and nothing stops a model from saying
one in an ordinary sentence of its reply. Round 5 removed it another way, by
keeping tutoring turns out of what a shared paper shows.

### Round 5: `./meos review` on the third rework (`e8513451`)

Report: `.meos/reviews/20261121T052456Z.md`. Verdict: **rework**. It confirmed the strict block ending
closed, the scrub applied before saving, and no regression in the ordinary
paper chat. The images built from this commit were not deployed.

| Finding | Severity | Disposition |
| --- | --- | --- |
| The scrub misses other shapes: a lone subskill record, a state written as a single-quoted mapping. The notes in them are saved in the reply or a citation and reach a shared-paper reader | blocking | Fixed by taking the route away, not by adding shapes. Every message of a tutoring turn, the learner's and the tutor's, is saved with a mark, and the shared-paper conversation leaves marked turns out in its query. What the tutor wrote in a tutoring turn, well-formed or not, is no longer something a shared paper shows. This also removes the limit recorded after round 4: a tutor that says a note in a plain sentence says it only to the learner. The scrub stays, for what the learner themself sees stored |
| A reply in flight when the mounted reader's account changes went on rendering its text and citations | important | Fixed: the stream is cancelled and nothing of it is shown once the session it was asked in is no longer the current one |
| A slow history read could roll the panel back past a newer saved turn | minor | Fixed: the newer turn is kept |

### Round 6: `./meos review` on the fourth rework (`02318b7f`)

Report: `.meos/reviews/20261121T053402Z.md`. Verdict: **rework**. It confirmed round 5's direct disclosure closed: both
halves of a tutoring turn carry the mark, replies with no usable state
included, and the shared-paper query leaves them out before paging, whatever
the tutor wrote. It found no regression in ordinary chat or in the shared
conversation of papers that were never tutored. What it reported next are
indirect routes, in which a later model call repeats something from a
tutoring turn into something a shared paper shows.

| Finding | Severity | Disposition |
| --- | --- | --- |
| With Tutor switched off, an ordinary answer is written from a history that includes the tutoring turns and could repeat them; the answer is shareable | blocking | Fixed. An ordinary answer's history leaves tutoring turns out (`shareable_only`). The tutor still reads everything |
| The rename action makes a title from the last messages, tutoring ones included, and the title is returned with a shared paper | blocking | Fixed. The title is made from shareable messages only; a conversation of tutoring turns only is not named |
| A mounted reader switched directly between two signed-in accounts keeps the previous transcript, and a delayed history read or a finishing stream can add to it | important | Not changed. This is the reader's ordinary chat, tutor mode or not. The tutor panel and an in-flight reply are covered (rounds 4 and 5) |
| The shared response shows gaps in message sequence numbers where tutoring turns were left out, and a conversation of tutoring turns only is reported as present | minor | Not changed. It shows that tutoring happened, and how many messages, not what was said |

**These two fixes have not been reviewed.** Six rounds in, the review has gone
from direct disclosure of the stored state to second-order repetition by a
later model call, and each round has found a further route. No seventh round
was run before staging. The owner decides whether the release goes to traffic
on this evidence.

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
- A shared paper does not show tutoring turns. Its reader sees the paper's
  ordinary questions and answers and nothing of a tutoring session. The share
  dialog still says "annotations and chats"; it does not mention this.
- For the same reason an ordinary answer does not know what was said in the
  paper's tutoring session, and the tutor's turns do not count toward the
  conversation's title.
- The skill's "save state" and "resume from" are not offered. The session is
  kept per paper and resumes by itself; it cannot be moved to another paper.
- The stored session is readable by whoever operates the service (database,
  admin view, logs, traces), as every message is.
- If the model writes a malformed state block, anything it wrote after that
  block in the same reply, citations included, is dropped with it.
- A reply whose save fails still looks delivered until the page is reloaded.
  Ordinary chat has the same gap.
- The ordinary chat's request still names the paper and the conversation
  separately and does not check that they match. Only tutor turns are checked.
- The same duplicate-yield and `strip()` pattern is in
  `multi_paper_operations.py` (project and library chat). Untouched here.

## Release record (2026-11-21)

**State: staged, not live.** Revision `openpaper-00032-dox` exists with no
traffic, under the tag `tutor`. Traffic is 100% on `openpaper-00029-jen`, as
before. Moving traffic waits on the owner, because the last review verdict is
rework and the last commit has not been reviewed (round 6 above).

Why two branches: the live service is not one commit. Its server is built from
`fix/investigation-dated-papers` (`16a7f1b6`, image `dated-etag-16a7f1b6`) and
its client from `a3be08ca` (image `fold-a3be08cadbdd`), while
`feat/spatial-workspace` also carries an unreleased migration and the project
canvas. Each release branch is the six tutor commits on top of one live base
and nothing else. No migration. Caddy unchanged.

| | Server | Client |
| --- | --- | --- |
| Branch | `feat/tutor-mode-server` | `feat/tutor-mode-client` |
| Base | `1cf4437d` (head of `fix/investigation-dated-papers`; server code as live) | `a3be08ca` (the live client commit) |
| Head | `d6b10239` | `a9c78382` |
| Development branch equivalent | `9889c461` on `feat/spatial-workspace` | same |
| Checks at that head | Unit suite 549 tests (478 pass, 71 skipped); isolated PostgreSQL suites 111 of 111; server files this change touches byte-identical to the development branch | `tsc --noEmit`, `npm run build`, `npm run test:tutor:browser` at 1440 and 390 px |
| Image | `server:tutor-d6b10239`, `sha256:8d657b49d6d375395d991670e00757310cc7e2f857ce25f9d50805ccb42bf59e` (Cloud Build `06ff8674-7faa-4c28-a7e7-0dcb7b5b12d8`) | `client:tutor-a9c78382`, `sha256:c4bf5f9ffc003875e2d5e83a04105908c8c57cfd7d4903789e68cdbb23e2e6d0` |

All three branches are pushed. Each image was built with the matching step of
`deploy/cloudbuild.yaml` on its own, from a clean worktree of its branch.

Staged with `gcloud run services update openpaper --region=asia-southeast1
--no-traffic --tag=tutor --container=server --image=<server@digest>
--container=client --image=<client@digest>`.

Signed-out smoke of the staged URL
(`https://tutor---openpaper-rfv24u7kqa-as.a.run.app`): `/api/health` 200, `/`
200, the server's `ResponseStyle` lists `tutor`, `POST /api/message/chat/paper`
and `GET /api/conversation/{id}` answer 401, and the reader page's script
carries the tutor switch. The public origin was checked afterwards: 200, still
the previous build (`ResponseStyle` has no `tutor`).

Not checked on the staged revision: anything signed in, and therefore the
tutor itself against the real model.

To put it live:
`gcloud run services update-traffic openpaper --region asia-southeast1 --to-revisions=openpaper-00032-dox=100`,
then `--remove-tags=tutor`. Rollback: `--to-revisions=openpaper-00029-jen=100`.
To drop it instead: `gcloud run services update-traffic openpaper --region
asia-southeast1 --remove-tags=tutor`; the revision then receives nothing and
can be deleted.

Images built from earlier heads and never deployed, safe to delete:
`server:tutor-{e438dbe6,0fb6401b,915bdd74,b6c7bb79,1f8be7b3}` and
`client:tutor-{14972c5d,5aa66b01,f5487289,8bb02155,86178e2f}`.
