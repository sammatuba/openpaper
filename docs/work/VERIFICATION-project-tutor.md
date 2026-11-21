# Verification: tutor mode in a project conversation

Intent: `docs/work/INTENT-project-tutor.md`. Written 2026-11-21.

State: implemented on `feat/spatial-workspace`, in the working tree. Not
committed, not built into an image, not deployed. The paper tutor that is live
(`openpaper-00032-dox`) is unchanged by anything here until a release is cut.

## What was run

All of it after the review fixes described below.

| Check | Result |
| --- | --- |
| `cd server && GEMINI_API_KEY=test-key .venv/bin/python -m unittest discover -s tests` | 690 tests: 549 pass, 141 skipped (the suites that need the isolated cluster) |
| `server/.venv/bin/python scripts/ci/run_isolated_postgres.py` | 204 tests pass, none skipped; `tests.test_project_tutor_postgres` added to the required suites (9 tests) |
| `black==24.3.0` and `isort==5.13.2 --profile black` on the changed server files, from the repository root | No changes left to make |
| `cd client && tsc --noEmit` | Pass |
| `next lint` on the seven changed client files | No warnings or errors |
| `cd client && npm run build` | Pass |
| `npm run test:project-tutor:browser` against the production build on 127.0.0.1:3011, API mocked | Pass at 1440 px (light) and 390 px (dark) |
| `npm run test:tutor:browser` (the paper tutor; its panel is shared) | Pass at 1440 and 390 px |
| `npm run test:project-workflow:browser` (the Discuss page gained a section) | Pass at 1440 and 390 px |
| `git diff --check` | Clean |

The server suite went from 633 tests to 690: 48 in `tests/test_project_tutor.py`
and 9 in `tests/test_project_tutor_postgres.py`. Two expectations in
`tests/test_tutor_mode.py` changed from `model_dump()` to `dump()`; see "The
paper tutor" below.

## What the tests hold

- **The state model.** A study path is repaired, not rejected: an unknown
  status becomes "todo", an untitled unit is dropped, paper ids are
  de-duplicated, and neither the path (12 units, 8 papers each) nor the fetch
  note (6 lines) can grow without bound. A path names only papers of the
  project; a unit that named none of them stays as a step.
- **The paper tutor.** A paper session's stored state has neither new field.
  It is stored, and handed back to its tutor, as it was before.
- **The prompts.** The skill map section is word for word the same in the
  paper and project prompts. The project prompt's own example state parses.
  The tutor is given the papers, then the session, with the next turn number.
  The fetching model is given a brief with the session, the tutor's fetch
  note and the learner's words, and before a session is told to cover the set.
- **The stream.** A tutor turn goes through the state filter and the
  multi-paper evidence parser at every two-chunk cut and as one chunk; each
  time the visible text is identical, the citation arrives with its paper id
  and the stored state equals the state written. The same for an ordinary
  answer. An unclosed evidence block cannot carry the state into a citation. A
  restart discards the abandoned attempt and its state. A failed stream says
  so and shows nothing it was holding.
- **Gathering.** A tutor turn is gathered with the tutoring turns in view and
  is offered neither charts nor citation cards. An ordinary turn is gathered
  without the tutoring turns.
- **The endpoint.** A tutor turn is saved with both halves marked, the session
  on the tutor's half and the gathering trace kept; the state is sent after
  the save and last; the conversation is not renamed. Both models are given
  the session, and the tutor is given the learner's own words. Open reader
  tabs do not narrow a tutor turn. The tutor replies when nothing was
  gathered. Tutor mode is refused in someone else's conversation and in the
  library-wide chat, before either model is called and before the session is
  read. A reply that is only state, or a save that fails, sends no state. A
  state written without its markers is not saved as the reply. An ordinary
  turn is saved without any mark, still scoped by mentions, still renamed, and
  still says so when nothing was gathered.
- **Reading a conversation.** The owner gets the session back with the
  conversation. Another member gets none, and the lookup is not made for them.
- **On PostgreSQL.** Another member of the project is sent no tutoring turn,
  with or without a stored session, and their pages stay full around one.
  Someone outside the project is sent nothing. A conversation of tutoring
  turns only is listed for its owner alone, and so is a study session whose
  first turn has not been saved; one with ordinary turns too, and an ordinary
  one, are listed as before. A conversation is not reached through another
  project.
- **What the learner sees of the gathering.** On a tutor turn the progress
  lines name the paper being read and not what is searched for in it, and the
  saved trace keeps which tools ran and not their arguments. An ordinary turn
  keeps both whole.
- **Charts.** Both chart-planning calls read the conversation without its
  tutoring turns.
- **The page**, in a browser: a study session is started from the Discuss
  page and its first turn goes to the tutor; the switch is remembered per
  conversation; the panel draws the path (which unit is current, which are
  done, the papers of each by title) and the map; levels are withheld during
  the diagnostic; opening a paper from the path does not narrow the next tutor
  turn; a command chip leaves a half-typed answer in place; a command that
  fails shows the error, and Retry sends the command again and not the draft
  beside it; the tutor's notes and its fetch note are never on the page; a reload restores the path and the
  map; with the switch off the next question is an ordinary one; another
  member's conversation offers no tutor.

## Defects found in existing code and fixed

1. **A conversation could be reached through another project.**
   `project_conversation_crud.get_by_conversation_id` checked the caller's
   role in the project named in the request, then fetched the conversation by
   id alone. Given a conversation's id, a member of any project could post
   into it through `/api/message/chat/everything`, and read its title. (Its
   messages were not readable that way: that query checks the project.) The
   conversation must now belong to the named project. Not known to have been
   used; ids are random UUIDs.
2. **Text after an evidence block in the project and library chat.** The same
   defects fixed in the paper chat on 2026-11-21. With the old code, on the
   inputs the new tests use: when the closing marker and the text after it
   arrived in one chunk, that text was lost into the last citation; when a
   chunk after the block ended in a space, the text came out as "Read the
   Read thesecond paper." (repeated, and with two words joined). Both tests
   fail on the old code and pass on the new.
3. **A server error mid-stream showed nothing on the project conversation
   page.** The page raised the error from inside the block that catches an
   unparseable event, which logged it and carried on. A turn the server
   refused or failed left the question sitting there with no reply, no
   message and no Retry. Found when the browser check for a failed tutor
   command waited for a Retry button that never came. The error is now raised
   outside that block. This changes ordinary project chat too: a failed
   answer now shows its error and offers Retry, which is what the page's
   error handling was written to do.

An evidence block the stream ends inside is still read as citations in this
chat, as it always was. The paper chat drops it. Left as it is.

## Independent review

### Codex: did not run

`./meos review --base HEAD` stopped after 15,883 tokens: "Your workspace is
out of credits" (`.meos/reviews/20261121T072137Z.md`). No GPT review of this
change exists.

### Stand-in: Claude reviewer agent, fresh context

The same model family as the author, so not independent in the sense the
Codex rounds are. It was given the diff and the intent, not the author's
conclusions, and ran its own probes: the real endpoint with the real stream
parser on 13 malformed-reply shapes at every two-chunk cut (about 13,000
runs), the old and new stream parsers on 4,736 chunkings of 12 ordinary
answers, the paper tutor's prompt builder and state filter against the
previous commit, and the access queries on the isolated PostgreSQL cluster.

Verdict: **rework**. It found no route by which a tutoring turn or the stored
session reaches another member, directly or through a later model call, and
no change to an ordinary answer except the fixes named above. The paper
tutor's prompt and filter were byte-identical on its samples but for finding
5. Its findings:

| Finding | Severity | Disposition |
| --- | --- | --- |
| A study session is created and titled before its first turn is saved, and an empty conversation was listed to every member with its owner's name; if that turn never saved it stayed listed for good. The page and this record said nobody else could tell | important | Fixed. Another member's conversation is listed only once it holds a turn they can read. Reached by its id, one that shows them nothing has no title for them. Tests on PostgreSQL and at the endpoint |
| Retry after a failed command sent the draft in the input, not the command | minor | Fixed, with a browser check. That check is what found defect 3 above |
| A reply in flight when the user or conversation changed went on being read and was appended | minor | Fixed: the read stops and nothing of it is shown, as in the paper reader |
| The progress lines and the saved trace of a tutor turn showed what was searched for, part of it for the question the tutor was about to ask | minor | Fixed: see "What the learner sees of the gathering" |
| A paper tutor that wrote a path or a fetch note would now have them stored, where before they were dropped | minor | Fixed: both are kept only for a project session |
| The fetching model's standing instructions still describe the two tools withheld on a tutor turn | minor | Fixed: the brief says neither is available |

**These fixes have not been reviewed.** They were checked by the tests added
with them and by the full run in "What was run".

Reported by the reviewer as already there and not from this change: any
member of a project can post an ordinary turn into another member's
conversation, because the server checks membership and not ownership (the
page disables the input; the server does not refuse). It exposes no tutoring
turn. Not changed here: whether members may write in each other's
conversations is a decision about collaboration, not a detail of the tutor.
The owner's answer, 2026-11-21: the platform has one author for now, and
collaboration is not a feature yet. So it stays as it is, and is to be
settled when collaboration is taken up.

## Not verified

- **No run against a real model.** There are no model credentials in this
  checkout. The paper tutor has not had one either. This change adds a second
  prompt and a gathering brief, and one mechanism the paper tutor does not
  have: the tutor writes what it wants read, and another model reads it. None
  of the checks above shows that the fetching model brings back what lets the
  tutor judge an answer, or that the tutor lays out a sensible path.
- **How long a turn takes.** A project turn runs evidence gathering (up to
  four rounds of tool calls) before the answer. For a question-and-answer
  loop that wait matters more than it does for a research question. Not
  measured.
- The signed-in production UI.
- Two members of a real project: one studying, one reading the list.

## Known limits

- The tutor judges answers only against the passages gathered for that turn.
  Its prompt tells it not to rule on what they do not settle. Whether it
  holds to that is part of what a real run would show.
- A study session is one conversation. A second "Start a study session"
  makes a second, independent session.
- The switch is remembered in the browser, per conversation. The session is
  with the conversation on the server.
- Two things still tell other members that tutoring happened, though not what
  was said or by whom: a conversation with both ordinary and tutoring turns
  shows gaps in its message numbering, and the number of discussions on a
  project's card counts every conversation, a study session included.
- Another member's conversation is now listed only once it holds a turn they
  can read. An empty one of somebody else's used to be listed.
- An ordinary answer in a conversation does not know what was said in its
  tutoring turns, and a study session keeps the title it was given.
- The learner can see which papers were read for a tutor turn (the progress
  lines and the "Thinking trace"), not what was looked for in them.
- The paper chat's page raises a server error from inside the same kind of
  block that hid it on the project page (defect 3). Seen by reading the
  code, not by running it. Not changed here: that page is live and outside
  this change.
- On a phone the open panel takes about half the screen. It folds to one
  line.
- The library-wide chat has no tutor.
- The stored session is readable by whoever operates the service, as every
  message is.
- A request that names the wrong project for a conversation is now refused.
  The client always sent the right one.

## For a release

Nothing was built. As with the paper tutor, a release would be cut on the two
live bases, not from this branch. Checked on 2026-11-21: every server file
this change touches is identical on `feat/tutor-mode-server` and on this
branch's last commit, and of the client files only
`ProjectWorkspaceProvider.tsx` differs (this change adds one field to a type
there). No migration.
