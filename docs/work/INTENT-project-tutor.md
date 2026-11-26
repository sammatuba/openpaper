# Tutor mode in a project conversation

Owner request, 2026-11-21: tutor mode for a project, built into the platform.
The reference was a hand-made study guide for one notebook
(`arena_emergent_misalignment_socratic_study_guide.html`): 22 lessons in order,
8 skills, a diagnostic before any teaching, a skill map with levels, review,
an adversarial case and a teach-back for level 5, and a final mixed
assessment. The owner said it need not be copied.

This follows `INTENT-socratic-tutor.md` (tutor mode in the paper chat, live as
`openpaper-00032-dox`), which left this out as a separate slice.

## Outcome

A project conversation gains the Tutor switch the paper chat has. With it on,
the model teaches the project's papers as one subject: it lays out a study
path across the papers, places the learner with a short diagnostic, then works
through the path by asking, checking answers against the papers' text. Beside
the chat the learner sees the path (which unit they are on, which papers it
draws on) and the skill map, and can come back to the session later.

A session is started from the project's Discuss page ("Study these papers")
or by switching Tutor on in any conversation the learner owns.

## What is taken from the reference, and what is not

Taken: an ordered path through the material, each step tied to its source;
the diagnostic first; levels that are earned; review; a final assessment;
progress that survives leaving and returning.

Not taken: pre-written lessons, multiple-choice checks and self-graded
rubrics. The reference needs those because a static page cannot read an
answer. The tutor can, so it asks open questions and judges the answers
itself. Simulated labs and code exercises are also out: the tutor works from
what the papers say.

## Scope

- Project conversations only (`/api/message/chat/everything` with a
  `project_id`). Not the library-wide chat.
- No schema migration. The session is stored as in the paper chat, in
  `messages.trace` under `tutor`, with the turn mark `tutor_turn`.
- No release. Building and deploying are separate steps on the owner's go.

## Decisions

1. **The study path is part of the session state.** The state gains `path`:
   up to 12 units, each a title, the papers it draws on and a status. The
   tutor writes it at the start and keeps it current, like the skill map. A
   separate course record would need a migration and a generation job, and
   would fix the course before the diagnostic has said where the learner is.
2. **The tutor reads the papers through the project chat's evidence
   gathering, with its own brief.** That path has one model fetch passages and
   another write. On a tutor turn the fetching model is told what the tutor
   needs: the passages that settle the learner's last answer, the material for
   the unit in focus, or the whole set when a session starts. A learner's
   answer is not a search query, and gathering on it as one would fetch
   nothing useful. Charts and citation cards are not offered to it.
3. **A tutor turn covers the whole project.** The reader's open tabs normally
   narrow a project question to those papers. A tutor turn ignores that, on
   the server: opening the paper the tutor points to must not shrink what the
   next question can be about.
4. **A tutoring session is the learner's, here too.** A project conversation
   is read by every member of the project. Tutoring turns are marked, and a
   member who does not own the conversation is not sent them: they are left
   out in the query, as for a shared paper. Another member's conversation is
   listed only once it holds a turn they can read, so neither a conversation
   of tutoring turns only nor a study session not yet begun is. Tutor mode works
   only in a conversation the learner owns. An ordinary answer in the same
   conversation is written without sight of the tutoring turns, by both
   models, because members can read that answer. As before, the operator of
   the service can read the stored session.
5. **A lost state block still costs nothing visible**, and the same filter and
   scrub run before anything is stored or read as a citation.

## Found on the way

- `project_conversation_crud.get_by_conversation_id` checks that the caller
  has a role in the project named in the request, then fetches the
  conversation by id alone. A member of one project could therefore post into
  a conversation of another, given its id. Fixed here: the conversation must
  belong to the named project. A tutor turn depends on this check.
- The duplicate text and joined words after an evidence block, fixed in the
  paper chat, are in the project and library chat too. Tutor turns go through
  that code, so it is fixed here.
- The project conversation page hid an error the server sent mid-stream: no
  message, no Retry. A refused or failed tutor turn would have looked like
  one still waiting. Fixed on that page.

## Failure behaviour

- Everything listed in `INTENT-socratic-tutor.md` for the state block.
- Evidence gathering finds nothing: the tutor still replies, from the session
  and the conversation. An ordinary turn keeps its "no relevant papers" reply.
- A path naming a paper that is not in the project: the reference is dropped,
  the unit stays.
- Tutor mode asked for outside a project, in someone else's conversation, or
  with a conversation from another project: refused before any model is
  called.
- Tutor off: the project chat behaves as before, apart from the two fixes
  above.

## Checks

- Unit tests: the path in the state model; the gathering brief and the tutor
  prompt handed to the models; the project answer stream at every chunk cut,
  tutor and ordinary; the endpoint's refusals, what it saves and when it sends
  the state.
- Isolated PostgreSQL: what a member who does not own the conversation is
  sent, paging around a session, the conversation list, the project check.
- A browser check of the conversation page at 1440 and 390 px, API mocked.
- Server suite, client type check, lint and production build.
- Independent review.

## Not in this change

- A run against a real model. The paper tutor has not had one either; this
  adds a second prompt and a gathering brief that are equally untested live.
- Release.
