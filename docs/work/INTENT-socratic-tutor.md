# Tutor mode in the paper chat

Owner request, 2026-11-21: apply the `socratic-tutor` skill (structured Socratic
tutoring: diagnostic placement, a skill map with levels 0 to 5, strict
evaluation, spaced review, a final assessment) in the OpenPaper platform itself,
not in a coding session.

## Outcome

The paper reader's chat gains a second mode. With Tutor on, the model teaches
the open paper by asking instead of answering: it breaks the paper into 4 to 10
subskills, places the learner with a short diagnostic, then works subskill by
subskill, checking answers against the paper's own text. The learner sees where
they stand in a skill map beside the chat, and can come back to the session
later.

## Scope

- Single-paper chat only (`/api/message/chat/paper`, the reader's side panel).
  The paper is the topic.
- Not the project or library chat. That path gathers evidence with one model
  and answers with another; tutoring across papers is a separate slice.
- No schema migration. The session is stored in the existing `messages.trace`
  JSONB column under the key `tutor`.

## Decisions

1. **The session is stored, not left in the transcript.** The chat replays only
   the last ten messages to the model (`get_conversation_messages`, page size
   10). A skill map kept in the transcript is out of view five exchanges later.
   So each tutor turn ends with a state block the learner never reads; the
   server lifts it out of the stream, stores it with the assistant message and
   hands the latest one back in the next turn's system prompt. This is the
   skill's own "save state" / "resume from" mechanism, done automatically.
2. **The tutor writes its own state.** A second model call that grades the turn
   would be more robust to format slips, but it would judge levels separately
   from the tutor that asked the question. One judge, one record.
3. **A lost state block costs nothing visible.** If the block is missing or does
   not parse, the turn is saved as an ordinary message and the session continues
   from the last stored state.
4. **Turning the mode on is the consent.** The skill asks before starting a
   tutoring loop; here the learner flips a switch, so the tutor does not ask.
5. **A tutoring session is the learner's.** A shared paper shows its chat, but
   not its tutoring turns: every message of one is marked, and the shared
   conversation leaves marked turns out. This is decided by the mark and not
   by inspecting the reply, because no inspection can tell a reply that is
   safe to show from one in which the model put its notes somewhere they
   should not be. Beyond that, the state (which holds notes on what the
   learner gets wrong) is not part of the chat even for the learner. It is
   stored only in the paper's own conversation, removed from the
   shared and project conversation responses, lifted out of a reply before
   anything reads that reply as evidence, and never written into the chat by
   the tutor. The skill's "save state" and "resume from" are therefore not
   offered: both pass the notes through the chat, and what they were for
   (coming back later) the stored session already does. "The learner's" means
   kept from other readers of the chat; the operator of the service can read
   the stored session as they can read any message.
6. **Tutor mode replaces the answering prompt, it does not extend it.** That
   prompt requires a direct answer with evidence; the tutor's first rule is not
   to give one. Citations remain, but only when the tutor explains, confirms or
   corrects.

## Failure behaviour

- State block split across stream chunks, placed before or after the evidence
  block, cut off by the output limit, or not valid JSON: the learner's message
  is unaffected in every case.
- The upstream request restarts mid-answer: the abandoned attempt's state is
  discarded with its text.
- Values a model wrote out of range (level 7, unknown phase, forty subskills) are
  repaired, not trusted and not rejected.
- Ordinary questions asked in the middle of a session do not end it.
- Tutor mode off: the paper chat behaves exactly as before.

## Checks

- Unit tests for the state model, the stream filter at every chunk boundary,
  the prompt handed to the model, and the unchanged ordinary path.
- The session lookup against the isolated PostgreSQL cluster (it asks whether a
  JSONB column has a key).
- A browser check of the reader at 1440 and 390 px with the API mocked.
- Server suite, client type check, lint and production build.
- Independent review.

## Not in this change

- A run against a real model. Whether the prompt holds a model to the method
  (one question at a time, strict levels, a well-formed state block every turn)
  is the first thing to check once this is in an environment with model access.
- Release. Building and deploying are separate steps on the owner's go. The
  deployed server is built from `fix/investigation-dated-papers`, not from the
  development branch this was written on.
