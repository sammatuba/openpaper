"""Tutor mode in a project conversation.

The paper chat's tutor (tests/test_tutor_mode.py) over a set of papers. What
is new here, and what these tests hold:

- The session has a study path, and a note from the tutor to the model that
  fetches passages for it. Neither is trusted as written.
- A project turn has two models. The fetching one is asked for what the tutor
  needs, not for the learner's reply; the teaching one is given the session.
- A project conversation is read by every member of the project. A tutoring
  turn is taken only in a conversation the learner owns, and nobody else is
  sent it.
- The project answer stream is the one the tutor writes through, so the two
  defects fixed in the paper chat's stream are held fixed here too.
"""

import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from app.api import message_api
from app.llm.evidence_operations import EvidenceOperations
from app.llm.multi_paper_operations import MultiPaperOperations
from app.llm.prompts import TUTOR_PAPER_SYSTEM_PROMPT, TUTOR_PROJECT_SYSTEM_PROMPT
from app.llm.tutor import (
    TUTOR_STATE_END,
    TUTOR_STATE_START,
    build_project_tutor_system_prompt,
    build_tutor_gathering_question,
    split_tutor_state,
)
from app.schemas.message import EvidenceCollection, ResponseStyle
from app.schemas.responses import ToolCall
from app.schemas.tutor import TutorState, restrict_path_papers

PAPER_A = "11111111-1111-4111-8111-111111111111"
PAPER_B = "22222222-2222-4222-8222-222222222222"
NOT_IN_PROJECT = "99999999-9999-4999-8999-999999999999"

PAPERS = [
    SimpleNamespace(
        id=PAPER_A, title="Model organisms", authors=["A"], publish_date="2025"
    ),
    SimpleNamespace(
        id=PAPER_B, title="Narrow is hard", authors=["B"], publish_date="2026"
    ),
]

STATE = {
    "topic": "Emergent misalignment",
    "phase": "teaching",
    "target_level": 4,
    "difficulty": "normal",
    "focus": "Explain why a rank-1 adapter is not one feature",
    "diagnostic_asked": 4,
    "path": [
        {"title": "What was observed", "papers": [PAPER_A], "status": "done"},
        {
            "title": "Why broad is easier than narrow",
            "papers": [PAPER_A, PAPER_B],
            "status": "current",
        },
        {"title": "What is still open", "papers": [], "status": "todo"},
    ],
    "subskills": [
        {
            "name": "Explain why a rank-1 adapter is not one feature",
            "level": 3,
            "passes": 1,
            "unprompted": False,
            "last_checked": 6,
            "notes": "treats rank as a count of concepts",
        },
        {"name": "Design a held-out test of generalization", "level": 1},
    ],
    "misconceptions": ["thinks a harmful sample proves an intention"],
    "covered": ["what a LoRA update is"],
    "fetch": ["Narrow is hard: the stability comparison and its figure"],
}

BLOCK = f"{TUTOR_STATE_START}\n{json.dumps(STATE)}\n{TUTOR_STATE_END}"

EVIDENCE = (
    f'---EVIDENCE---\n@cite[1|{PAPER_B}]\n"The general solution is more stable"\n'
    "---END-EVIDENCE---"
)
# The parser keeps the quotation marks the model wrote; the client shows them.
CITATION = {
    "key": 1,
    "reference": '"The general solution is more stable"',
    "paper_id": PAPER_B,
}


def content(text: str) -> dict:
    return {"type": "content", "content": text}


def visible(chunks: list) -> str:
    return "".join(c["content"] for c in chunks if c.get("type") == "content")


def states(chunks: list) -> list:
    return [c["content"] for c in chunks if c.get("type") == "tutor_state"]


def citations(chunks: list) -> list:
    return [
        citation
        for c in chunks
        if c.get("type") == "references"
        for citation in c["content"]["citations"]
    ]


def evidence_from(paper_id: str = PAPER_B) -> EvidenceCollection:
    collection = EvidenceCollection()
    collection.add_evidence(paper_id, "The general solution is more stable")
    return collection


class ProjectStateTest(unittest.TestCase):
    def test_a_path_is_repaired_not_rejected(self):
        state = TutorState.model_validate(
            {
                "subskills": [{"name": "A"}],
                "path": [
                    {"title": "One", "papers": PAPER_A, "status": "In Progress"},
                    {"title": "   ", "papers": [PAPER_A]},
                    "not a unit",
                    {"title": "Two", "papers": [PAPER_A, PAPER_A, "", PAPER_B]},
                    {"title": "Three", "papers": {"id": PAPER_A}, "status": "DONE"},
                ],
            }
        )

        self.assertEqual([u.title for u in state.path], ["One", "Two", "Three"])
        self.assertEqual([u.status for u in state.path], ["todo", "todo", "done"])
        self.assertEqual(
            [u.papers for u in state.path], [[PAPER_A], [PAPER_A, PAPER_B], []]
        )

    def test_neither_the_path_nor_the_fetch_note_can_grow_without_bound(self):
        state = TutorState.model_validate(
            {
                "subskills": [{"name": "A"}],
                "path": [
                    {"title": f"Unit {i}", "papers": [str(n) for n in range(40)]}
                    for i in range(40)
                ],
                "fetch": ["x" * 5000] * 40,
            }
        )

        self.assertEqual(len(state.path), 12)
        self.assertEqual(len(state.path[0].papers), 8)
        self.assertEqual(len(state.fetch), 6)
        self.assertLessEqual(len(state.fetch[0]), 300)

    def test_a_paper_session_is_stored_as_it_always_was(self):
        """The path and the fetch note are a project's. A paper session's
        stored state, which its tutor is handed back word for word, does not
        gain two keys its prompt never mentions."""
        paper = TutorState.model_validate({"subskills": [{"name": "A"}]}).dump()
        project = TutorState.model_validate(STATE).dump()

        self.assertNotIn("path", paper)
        self.assertNotIn("fetch", paper)
        self.assertEqual(len(project["path"]), 3)
        self.assertEqual(project["fetch"], STATE["fetch"])

    def test_a_path_names_only_papers_of_the_project(self):
        state = TutorState.model_validate(
            {
                "subskills": [{"name": "A"}],
                "path": [
                    {"title": "One", "papers": [PAPER_A, NOT_IN_PROJECT]},
                    {"title": "Two", "papers": [NOT_IN_PROJECT]},
                ],
            }
        ).dump()

        restricted = restrict_path_papers(state, [PAPER_A, PAPER_B])

        # The reference goes; the unit is still a step of the path.
        self.assertEqual(
            [(u["title"], u["papers"]) for u in restricted["path"]],
            [("One", [PAPER_A]), ("Two", [])],
        )

    def test_a_state_with_no_path_is_left_alone(self):
        state = TutorState.model_validate({"subskills": [{"name": "A"}]}).dump()

        self.assertIs(restrict_path_papers(state, [PAPER_A]), state)


class ProjectPromptTest(unittest.TestCase):
    def section(self, prompt: str, start: str, end: str) -> str:
        return prompt[prompt.index(start) : prompt.index(end)]

    def test_the_skill_map_is_the_same_in_both_tutors(self):
        """The two prompts are siblings kept in step by hand. The levels and
        the map are what the panel and the learner read; they must not drift."""
        self.assertEqual(
            self.section(TUTOR_PAPER_SYSTEM_PROMPT, "## Skill map", "## Teaching"),
            self.section(TUTOR_PROJECT_SYSTEM_PROMPT, "## Skill map", "## Study path"),
        )

    def test_the_prompt_asks_for_the_markers_and_citations_the_parsers_read(self):
        self.assertIn(TUTOR_STATE_START, TUTOR_PROJECT_SYSTEM_PROMPT)
        self.assertIn(TUTOR_STATE_END, TUTOR_PROJECT_SYSTEM_PROMPT)
        self.assertIn("@cite[1|paper_id]", TUTOR_PROJECT_SYSTEM_PROMPT)
        # Its example state is one the model can read back.
        example = TUTOR_PROJECT_SYSTEM_PROMPT.split(TUTOR_STATE_START)[1].split(
            TUTOR_STATE_END
        )[0]
        parsed = TutorState.model_validate(json.loads(example))
        self.assertEqual(len(parsed.path), 1)
        self.assertEqual(len(parsed.fetch), 1)

    def test_the_tutor_is_given_the_papers_and_the_session(self):
        prompt = build_project_tutor_system_prompt(
            {**STATE, "turn": 6},
            scope="The 2 paper(s) listed below are everything.",
            papers={
                PAPER_A: {"title": "Model organisms"},
                PAPER_B: {"title": "Narrow"},
            },
        )

        self.assertTrue(prompt.startswith(TUTOR_PROJECT_SYSTEM_PROMPT))
        self.assertIn("The 2 paper(s) listed below are everything.", prompt)
        self.assertIn(PAPER_A, prompt)
        self.assertIn("Model organisms", prompt)
        self.assertIn("This is turn 7", prompt)
        self.assertIn("treats rank as a count of concepts", prompt)
        # In that order: what to teach, then where the session stands.
        self.assertLess(prompt.index("## The papers"), prompt.index("## Session state"))

    def test_with_no_session_the_tutor_is_told_to_start(self):
        prompt = build_project_tutor_system_prompt(None, scope="Scope.", papers={})

        self.assertIn("No session state is stored", prompt)
        self.assertIn("This is turn 1", prompt)

    def test_the_fetching_model_is_asked_for_what_the_tutor_needs(self):
        brief = build_tutor_gathering_question(
            {**STATE, "turn": 6}, "Because the adapter is switched off."
        )

        self.assertIn("This is not a question to answer.", brief)
        self.assertIn("Because the adapter is switched off.", brief)
        self.assertIn("- Narrow is hard: the stability comparison", brief)
        self.assertIn("Why broad is easier than narrow", brief)

    def test_before_a_session_it_is_asked_to_cover_the_set(self):
        brief = build_tutor_gathering_question(None, "Teach me this project.")

        self.assertIn("No session has started.", brief)
        self.assertIn("Nothing yet.", brief)
        self.assertIn("cover the whole set", brief)

    def test_it_is_told_which_tools_it_does_not_have(self):
        """Its standing instructions describe charts and citation cards. Both
        are withheld on a tutor turn; a call to either would use up one of
        its few rounds on an error."""
        brief = build_tutor_gathering_question(None, "Teach me this project.")

        self.assertIn(
            "`find_citation` and `create_chart_artifact` are not available", brief
        )


class PaperSessionTest(unittest.IsolatedAsyncioTestCase):
    async def states_of(self, **kwargs):
        async def answer():
            yield content(f"Why?\n\n{BLOCK}")

        return states([c async for c in split_tutor_state(answer(), turn=1, **kwargs)])

    async def test_a_paper_tutor_that_writes_a_path_does_not_get_one(self):
        """Nothing asks a paper's tutor for a path or a fetch note. If it
        writes them anyway they are dropped, as they were before a project
        had them: kept, the paper's panel would draw a study path."""
        (paper,) = await self.states_of()
        (project,) = await self.states_of(project=True)

        self.assertNotIn("path", paper)
        self.assertNotIn("fetch", paper)
        self.assertEqual(len(paper["subskills"]), 2)
        self.assertEqual(len(project["path"]), 3)
        self.assertEqual(project["fetch"], STATE["fetch"])


class ChatWithPapersTest(unittest.IsolatedAsyncioTestCase):
    """The project answer stream, with the model and the database replaced."""

    async def run_chat(
        self,
        model_text="",
        *,
        tutor=False,
        stored_state=None,
        pieces=None,
        fail_after=None,
    ):
        operations = MultiPaperOperations.__new__(MultiPaperOperations)
        seen = {}
        if pieces is None:
            # Small pieces, so markers straddle chunk boundaries as they do live.
            pieces = [model_text[i : i + 9] for i in range(0, len(model_text), 9)]

        async def send_message_stream(**kwargs):
            seen.update(kwargs)
            for index, piece in enumerate(pieces):
                if fail_after is not None and index == fail_after:
                    raise RuntimeError("upstream closed")
                if piece is None:
                    yield SimpleNamespace(text="", is_restart=True)
                else:
                    yield SimpleNamespace(text=piece, is_restart=False)

        operations.send_message_stream = send_message_stream

        with patch(
            "app.llm.multi_paper_operations.message_crud.get_conversation_messages",
            return_value=[],
        ) as history_lookup:
            chunks = [
                c
                async for c in operations.chat_with_papers(
                    conversation_id=str(uuid.uuid4()),
                    question="Because the adapter is switched off.",
                    current_user=SimpleNamespace(id=uuid.uuid4()),
                    all_papers=PAPERS,
                    evidence_gathered=evidence_from(),
                    project_title="EM study",
                    is_tutor_turn=tutor,
                    tutor_state=stored_state,
                    db=None,
                )
            ]
        self.history_lookup = history_lookup
        # The "still working" pings depend on timing, not on the answer.
        return [c for c in chunks if c.get("type") != "status"], seen

    async def test_a_tutor_turn_carries_its_state_and_hides_the_block(self):
        model_text = (
            f"Close. What does that cost in stability? [^1]\n\n{EVIDENCE}\n\n{BLOCK}"
        )

        chunks, seen = await self.run_chat(
            model_text, tutor=True, stored_state={**STATE, "turn": 6}
        )

        self.assertEqual(
            visible(chunks).strip(), "Close. What does that cost in stability? [^1]"
        )
        self.assertEqual(citations(chunks), [CITATION])
        self.assertEqual(len(states(chunks)), 1)
        self.assertEqual(states(chunks)[0]["turn"], 7)
        self.assertEqual(states(chunks)[0]["path"][1]["status"], "current")
        # The tutor reads the whole conversation, its own turns included.
        self.assertFalse(self.history_lookup.call_args.kwargs["shareable_only"])
        self.assertTrue(seen["system_prompt"].startswith(TUTOR_PROJECT_SYSTEM_PROMPT))
        self.assertIn("This is turn 7", seen["system_prompt"])
        self.assertIn("Model organisms", seen["system_prompt"])
        self.assertIn('"EM study"', seen["system_prompt"])
        texts = [part.text for part in seen["message"] if hasattr(part, "text")]
        self.assertIn("The learner says:", texts[0])
        self.assertNotIn("Query:", texts[0])

    async def test_a_path_that_names_a_paper_outside_the_project_loses_it(self):
        state = json.loads(json.dumps(STATE))
        state["path"][0]["papers"] = [PAPER_A, NOT_IN_PROJECT]
        block = f"{TUTOR_STATE_START}\n{json.dumps(state)}\n{TUTOR_STATE_END}"

        chunks, _ = await self.run_chat(f"Why?\n\n{block}", tutor=True)

        self.assertEqual(states(chunks)[0]["path"][0]["papers"], [PAPER_A])
        self.assertEqual(len(states(chunks)[0]["path"]), 3)

    async def test_a_tutor_turn_cut_anywhere_keeps_its_text_citation_and_state(self):
        """State filter, then evidence parser, at every two-chunk cut and as
        one chunk. Whatever the cut, the learner reads the same message."""
        model_text = f"Right. Why would that be? [^1]\n\n{EVIDENCE}\n\n{BLOCK}"
        expected = {**TutorState.model_validate(STATE).dump(), "turn": 1}

        for cut in range(len(model_text) + 1):
            pieces = [p for p in (model_text[:cut], model_text[cut:]) if p]
            with self.subTest(cut=cut):
                chunks, _ = await self.run_chat(tutor=True, pieces=pieces)

                self.assertEqual(
                    visible(chunks).strip(), "Right. Why would that be? [^1]"
                )
                self.assertEqual(citations(chunks), [CITATION])
                self.assertEqual(states(chunks), [expected])

    async def test_an_unclosed_evidence_block_cannot_carry_the_state_out(self):
        """The tutor forgets `---END-EVIDENCE---` and goes straight on to its
        state. The state is lifted first, so it is in no citation."""
        opening = EVIDENCE.replace("---END-EVIDENCE---", "")
        model_text = f"Right. [^1]\n\n{opening}\n{BLOCK}"

        for cut in range(len(model_text) + 1):
            pieces = [p for p in (model_text[:cut], model_text[cut:]) if p]
            with self.subTest(cut=cut):
                chunks, _ = await self.run_chat(tutor=True, pieces=pieces)

                everything = json.dumps(
                    [c for c in chunks if c.get("type") != "tutor_state"]
                )
                self.assertNotIn("treats rank as a count of concepts", everything)
                self.assertNotIn("TUTOR-STATE", everything)
                self.assertEqual(len(states(chunks)), 1)

    async def test_an_ordinary_answer_is_written_without_the_tutoring_turns(self):
        """Members of the project read an ordinary answer. It is written
        from a history that leaves the tutoring turns out, so it cannot
        repeat what was said in them."""
        chunks, seen = await self.run_chat(f"It is more stable [^1].\n\n{EVIDENCE}")

        self.assertTrue(self.history_lookup.call_args.kwargs["shareable_only"])
        self.assertEqual(states(chunks), [])
        self.assertEqual(citations(chunks), [CITATION])
        self.assertNotIn("personal tutor", seen["system_prompt"])
        texts = [part.text for part in seen["message"] if hasattr(part, "text")]
        self.assertIn("Query: Because the adapter is switched off.", texts[0])

    async def test_an_ordinary_answer_is_not_searched_for_a_state_block(self):
        """With tutor off the markers are just text the model wrote."""
        chunks, _ = await self.run_chat(f"An answer.\n\n{BLOCK}")

        self.assertEqual(states(chunks), [])
        self.assertIn("TUTOR-STATE", visible(chunks))

    async def test_an_ordinary_answer_cut_anywhere_reads_the_same(self):
        closing = "The second paper tests this directly."
        model_text = f"It is more stable [^1].\n\n{EVIDENCE}\n\n{closing}"

        for cut in range(len(model_text) + 1):
            pieces = [p for p in (model_text[:cut], model_text[cut:]) if p]
            with self.subTest(cut=cut):
                chunks, _ = await self.run_chat(pieces=pieces)

                self.assertEqual(
                    visible(chunks), f"It is more stable [^1].\n\n\n\n{closing}"
                )
                self.assertEqual(citations(chunks), [CITATION])

    async def test_text_after_the_evidence_block_arrives_once(self):
        """It used to arrive twice: once when the block closed, and again when
        the buffer it had been left in was flushed."""
        closing = "Ask me about the second paper next, it is the harder one."

        # The closing marker and what follows it, in one chunk.
        chunks, _ = await self.run_chat(
            pieces=["It is more stable [^1].\n\n", f"{EVIDENCE}\n\n{closing}"]
        )

        self.assertEqual(
            " ".join(visible(chunks).split()), f"It is more stable [^1]. {closing}"
        )

    async def test_a_space_at_a_chunk_boundary_after_the_block_is_kept(self):
        """What followed the block was cut from a stripped copy of the buffer,
        so a chunk ending in a space lost it and two words joined."""
        closing_marker = "---END-EVIDENCE---"
        opening = EVIDENCE.split(closing_marker)[0]

        chunks, _ = await self.run_chat(
            pieces=[
                f"Stable [^1].\n\n{opening}",
                f"{closing_marker}\n\nRead the ",
                "second paper.",
            ]
        )

        self.assertEqual(
            " ".join(visible(chunks).split()), "Stable [^1]. Read the second paper."
        )
        self.assertEqual(citations(chunks), [CITATION])

    async def test_an_evidence_block_the_stream_ended_inside_is_still_cited(self):
        """As this chat has always done, unlike the paper chat. Not changed
        here: an ordinary answer is read by the person who asked."""
        unclosed = EVIDENCE.replace("---END-EVIDENCE---", "")

        chunks, _ = await self.run_chat(f"It is more stable [^1].\n\n{unclosed}")

        self.assertEqual(citations(chunks), [CITATION])
        self.assertEqual(visible(chunks).strip(), "It is more stable [^1].")

    async def test_a_restart_discards_the_abandoned_attempt(self):
        chunks, _ = await self.run_chat(
            tutor=True,
            pieces=[f"A first try.\n\n{BLOCK}", None, "Why would that be?"],
        )

        after = chunks[[c["type"] for c in chunks].index("reset") + 1 :]
        self.assertEqual(visible(after), "Why would that be?")
        self.assertEqual(states(after), [])

    async def test_a_failed_stream_says_so_and_shows_nothing_it_was_holding(self):
        chunks, _ = await self.run_chat(
            pieces=["It is more stable [^1].\n\n---EVIDENCE---\n@cite[1|", "x"],
            fail_after=1,
        )

        self.assertEqual(chunks[-1]["type"], "error")
        self.assertEqual(citations(chunks), [])
        self.assertNotIn("@cite", visible(chunks))


class GatherEvidenceTest(unittest.IsolatedAsyncioTestCase):
    """What the fetching model is given on a tutor turn, and on any other."""

    async def gather(self, tool_calls=(), **kwargs):
        operations = EvidenceOperations.__new__(EvidenceOperations)
        seen = {}
        rounds = [list(tool_calls)]

        def generate_content(**call):
            seen.update(call)
            # The calls asked for in the first round, then nothing more.
            return SimpleNamespace(
                tool_calls=rounds.pop() if rounds else [], thinking=None
            )

        async def no_keywords(*args, **kwargs):
            return []

        operations.generate_content = generate_content
        operations._extract_search_keywords = no_keywords
        papers = [
            SimpleNamespace(
                id=PAPER_A,
                title="Model organisms",
                raw_content="text",
                tags=[],
                authors=[],
                publish_date=None,
                abstract="We study model organisms.",
            )
        ]
        with (
            patch(
                "app.llm.evidence_operations.project_crud.get",
                return_value=SimpleNamespace(title="EM study"),
            ),
            patch(
                "app.llm.evidence_operations.project_paper_crud.get_all_papers_by_project_id",
                return_value=papers,
            ),
            patch(
                "app.llm.evidence_operations.message_crud.get_conversation_messages",
                return_value=[],
            ) as history_lookup,
            patch("app.llm.evidence_operations.track_event"),
            patch(
                "app.llm.evidence_operations.search_file",
                return_value=["12: The general solution is more stable"],
            ),
        ):
            events = [
                event
                async for event in operations.gather_evidence(
                    question="What the tutor needs.",
                    current_user=SimpleNamespace(id=uuid.uuid4()),
                    conversation_id=str(uuid.uuid4()),
                    project_id=str(uuid.uuid4()),
                    db=None,
                    **kwargs,
                )
            ]
        offered = {declaration["name"] for declaration in seen["function_declarations"]}
        return events, offered, history_lookup

    async def test_a_tutor_turn_is_gathered_with_the_session_in_view(self):
        events, offered, history_lookup = await self.gather(for_tutor=True)

        self.assertFalse(history_lookup.call_args.kwargs["shareable_only"])
        # Neither is something a tutoring turn shows.
        self.assertNotIn("create_chart_artifact", offered)
        self.assertNotIn("find_citation", offered)
        self.assertIn("view_file", offered)
        self.assertEqual(events[-1]["type"], "evidence_gathered")

    SEARCH = ToolCall(
        name="search_file", args={"paper_id": PAPER_A, "query": "more stable"}
    )

    def statuses(self, events):
        return [e["content"] for e in events if e.get("type") == "status"]

    async def test_a_tutor_turns_progress_lines_do_not_say_what_was_searched_for(self):
        """The learner watches them arrive with the tutor's next question, and
        part of what is read is read for that question. The query is where
        its answer is."""
        events, _, _ = await self.gather([self.SEARCH], for_tutor=True)

        self.assertIn("Search File - Model organisms", self.statuses(events))
        self.assertNotIn("more stable", " ".join(self.statuses(events)))
        # The passage is still gathered for the tutor.
        self.assertTrue(events[-1]["content"].has_evidence())

    async def test_an_ordinary_turns_progress_lines_still_do(self):
        events, _, _ = await self.gather([self.SEARCH])

        self.assertIn(
            "Search File - Model organisms 'more stable'", self.statuses(events)
        )

    async def test_an_ordinary_turn_is_gathered_without_the_tutoring_turns(self):
        """Its searches are kept as the answer's trace, which members read."""
        _, offered, history_lookup = await self.gather()

        self.assertTrue(history_lookup.call_args.kwargs["shareable_only"])
        self.assertIn("create_chart_artifact", offered)
        self.assertIn("find_citation", offered)


class ProjectTutorEndpointTest(unittest.IsolatedAsyncioTestCase):
    """What the project chat endpoint refuses, saves and sends on a tutor turn."""

    def setUp(self):
        self.user = SimpleNamespace(id=uuid.uuid4())
        self.project_id = str(uuid.uuid4())
        self.conversation = SimpleNamespace(
            id=uuid.uuid4(), conversable_type="project", user_id=self.user.id
        )

    async def chat(
        self,
        *chunks,
        style=ResponseStyle.TUTOR,
        evidence=None,
        stored_state=None,
        conversation=None,
        project_id="own",
        mentioned=None,
        save_error=None,
    ):
        """Run the endpoint; return what it saved, in order."""
        self.gathered_with = None
        self.chatted_with = None

        async def gather_evidence(**kwargs):
            self.gathered_with = kwargs
            yield {"type": "status", "content": "Reading"}
            if evidence is not None:
                yield {"type": "evidence_gathered", "content": evidence}

        async def chat_with_papers(**kwargs):
            self.chatted_with = kwargs
            for chunk in chunks:
                yield chunk

        request = message_api.MultiPaperChatRequest(
            conversation_id=str(uuid.uuid4()),
            user_query="Because the adapter is switched off.",
            project_id=self.project_id if project_id == "own" else project_id,
            mentioned_paper_ids=mentioned,
            style=style,
        )
        found = self.conversation if conversation is None else conversation
        self.sent = []
        with (
            patch.object(message_api.operations, "gather_evidence", gather_evidence),
            patch.object(message_api.operations, "chat_with_papers", chat_with_papers),
            patch.object(message_api.operations, "rename_conversation") as self.rename,
            patch.object(
                message_api.project_crud,
                "get",
                return_value=SimpleNamespace(title="EM study"),
            ),
            patch.object(
                message_api.project_conversation_crud,
                "get_by_conversation_id",
                return_value=found,
            ),
            patch.object(message_api.conversation_crud, "get", return_value=found),
            patch.object(
                message_api.project_paper_crud,
                "get_all_papers_by_project_id",
                return_value=PAPERS,
            ),
            patch.object(
                message_api.project_paper_crud,
                "get_paper_by_project",
                return_value=PAPERS[0],
            ),
            patch.object(
                message_api.paper_crud, "get_all_available_papers", return_value=PAPERS
            ),
            patch.object(
                message_api.message_crud,
                "get_latest_tutor_state",
                return_value=stored_state,
            ) as self.latest_state,
            patch.object(
                message_api.message_crud, "create", side_effect=save_error
            ) as create,
            patch.object(message_api, "track_event"),
        ):
            response = await message_api.chat_message_multipaper(
                request,
                background_tasks=SimpleNamespace(add_task=lambda *a, **k: None),
                db=None,
                current_user=self.user,
            )
            async for event in response.body_iterator:
                body = event.replace("END_OF_STREAM", "")
                if body:
                    self.sent.append(json.loads(body))
        return [call.kwargs["obj_in"] for call in create.call_args_list]

    def sent_states(self):
        return [e["content"] for e in self.sent if e["type"] == "tutor_state"]

    async def test_a_tutor_turn_is_saved_with_its_marks_and_its_state(self):
        saved = await self.chat(
            content("Why?"),
            {"type": "tutor_state", "content": STATE},
            evidence=evidence_from(),
            stored_state={**STATE, "turn": 6},
        )

        self.assertEqual([m.role for m in saved], ["user", "assistant"])
        self.assertEqual(saved[1].content, "Why?")
        # Both halves carry the mark that keeps them from other members.
        self.assertEqual(saved[0].trace, {"tutor_turn": True})
        self.assertIs(saved[1].trace["tutor_turn"], True)
        self.assertEqual(saved[1].trace["tutor"], STATE)
        # What the fetching model did stays with the turn, as on any other.
        self.assertEqual(saved[1].trace["status_messages"][0], "Reading")
        # Told to the panel only once saved, and after everything else.
        self.assertEqual(self.sent_states(), [STATE])
        self.assertEqual(self.sent[-1]["type"], "tutor_state")
        # A title is read by the project's members; this turn adds nothing
        # they can read, so it names nothing.
        self.rename.assert_not_called()

    def searched(self) -> EvidenceCollection:
        evidence = evidence_from()
        evidence.add_tool_call(
            ToolCall(name="view_file", args={"paper_id": PAPER_B, "start_line": 40})
        )
        return evidence

    def sent_tool_calls(self):
        return [e["content"]["tool_calls"] for e in self.sent if e["type"] == "trace"]

    async def test_a_tutor_turns_trace_does_not_say_where_the_tutor_looked(self):
        """The learner can open the trace beside the question the tutor has
        just asked. Which tools ran is kept; their arguments are not."""
        saved = await self.chat(content("Why?"), evidence=self.searched())

        self.assertEqual(saved[1].trace["tool_calls"], [{"name": "view_file"}])
        self.assertEqual(self.sent_tool_calls(), [[{"name": "view_file"}]])

    async def test_an_ordinary_turns_trace_is_whole(self):
        saved = await self.chat(
            content("It is more stable."), style=None, evidence=self.searched()
        )

        self.assertEqual(
            saved[1].trace["tool_calls"][0]["args"],
            {"paper_id": PAPER_B, "start_line": 40},
        )
        self.assertEqual(self.sent_tool_calls()[0][0]["args"]["start_line"], 40)

    async def test_both_models_are_given_the_session(self):
        stored = {**STATE, "turn": 6}

        await self.chat(content("Why?"), evidence=evidence_from(), stored_state=stored)

        self.assertTrue(self.gathered_with["for_tutor"])
        self.assertIn(
            "This is not a question to answer.", self.gathered_with["question"]
        )
        self.assertIn(
            "Because the adapter is switched off.", self.gathered_with["question"]
        )
        self.assertIn("treats rank as a count", self.gathered_with["question"])
        self.assertTrue(self.chatted_with["is_tutor_turn"])
        self.assertEqual(self.chatted_with["tutor_state"], stored)
        # The learner's own words go to the tutor, not the brief.
        self.assertEqual(
            self.chatted_with["question"], "Because the adapter is switched off."
        )

    async def test_a_tutor_turn_covers_the_project_whatever_tabs_are_open(self):
        saved = await self.chat(
            content("Why?"), evidence=evidence_from(), mentioned=[PAPER_A]
        )

        self.assertIsNone(self.gathered_with["restrict_to_paper_ids"])
        self.assertFalse(self.chatted_with["is_mention_scoped"])
        self.assertEqual(len(self.chatted_with["all_papers"]), 2)
        self.assertIsNone(saved[0].scope)

    async def test_the_tutor_replies_even_when_nothing_was_gathered(self):
        """ "Easier" and "I don't know" need no passage."""
        saved = await self.chat(content("Then try this one."), evidence=None)

        self.assertEqual([m.role for m in saved], ["user", "assistant"])
        self.assertEqual(len(self.chatted_with["evidence_gathered"].evidence), 0)

    async def test_tutor_mode_is_refused_in_someone_elses_conversation(self):
        theirs = SimpleNamespace(
            id=uuid.uuid4(), conversable_type="project", user_id=uuid.uuid4()
        )

        saved = await self.chat(
            content("Why?"), evidence=evidence_from(), conversation=theirs
        )

        self.assertEqual(saved, [])
        self.assertEqual([e["type"] for e in self.sent], ["error"])
        self.assertEqual(self.sent[0]["content"], message_api.TUTOR_REFUSED)
        # Before either model was called, and before the session was read.
        self.assertIsNone(self.gathered_with)
        self.assertIsNone(self.chatted_with)
        self.latest_state.assert_not_called()

    async def test_tutor_mode_is_refused_in_the_library_wide_chat(self):
        everything = SimpleNamespace(
            id=uuid.uuid4(), conversable_type="everything", user_id=self.user.id
        )

        saved = await self.chat(
            content("Why?"),
            evidence=evidence_from(),
            conversation=everything,
            project_id=None,
        )

        self.assertEqual(saved, [])
        self.assertEqual(self.sent[0]["content"], message_api.TUTOR_REFUSED)
        self.assertIsNone(self.gathered_with)

    async def test_a_reply_that_is_only_state_changes_nothing_the_learner_sees(self):
        saved = await self.chat(
            {"type": "tutor_state", "content": STATE}, evidence=evidence_from()
        )

        self.assertEqual(saved, [])
        self.assertEqual(self.sent_states(), [])
        self.assertEqual(self.sent[-1]["type"], "error")

    async def test_a_turn_that_fails_to_save_does_not_send_its_state(self):
        await self.chat(
            content("Why?"),
            {"type": "tutor_state", "content": STATE},
            evidence=evidence_from(),
            save_error=RuntimeError("database unavailable"),
        )

        self.assertEqual(self.sent_states(), [])
        self.assertEqual(self.sent[-1]["type"], "error")

    async def test_a_tutor_turn_that_lost_its_state_is_still_marked(self):
        saved = await self.chat(content("Why?"), evidence=evidence_from())

        self.assertEqual(saved[0].trace, {"tutor_turn": True})
        self.assertIs(saved[1].trace["tutor_turn"], True)
        self.assertNotIn("tutor", saved[1].trace)

    async def test_a_state_written_without_its_markers_is_not_saved_as_the_reply(self):
        leaked = f"Why?\n\n{json.dumps(STATE)}"

        saved = await self.chat(content(leaked), evidence=evidence_from())

        self.assertEqual(saved[1].content, "Why?")
        self.assertNotIn(
            "treats rank as a count", json.dumps(saved[1].model_dump(mode="json"))
        )
        # The reader was sent the original; it is replaced.
        kinds = [e["type"] for e in self.sent]
        self.assertIn("reset", kinds)
        self.assertEqual(self.sent[kinds.index("reset") + 1]["content"], "Why?")

    async def test_an_ordinary_turn_is_untouched_by_tutor_mode(self):
        saved = await self.chat(
            content("It is more stable."),
            style=None,
            evidence=evidence_from(),
            mentioned=[PAPER_A],
        )

        self.assertEqual(
            self.gathered_with["question"], "Because the adapter is switched off."
        )
        self.assertFalse(self.gathered_with["for_tutor"])
        self.assertEqual(self.gathered_with["restrict_to_paper_ids"], [PAPER_A])
        self.assertFalse(self.chatted_with["is_tutor_turn"])
        self.assertIsNone(self.chatted_with["tutor_state"])
        self.assertIsNone(saved[0].trace)
        self.assertNotIn("tutor_turn", saved[1].trace or {})
        self.assertEqual(self.sent_states(), [])
        self.latest_state.assert_not_called()
        self.rename.assert_called_once()

    async def test_an_ordinary_turn_with_nothing_gathered_still_says_so(self):
        saved = await self.chat(content("unused"), style=None, evidence=None)

        self.assertEqual(saved, [])
        self.assertIsNone(self.chatted_with)
        self.assertIn("couldn't find any relevant papers", self.sent[-1]["content"])

    async def test_the_paper_chats_other_styles_mean_nothing_here(self):
        await self.chat(
            content("It is more stable."),
            style=ResponseStyle.DETAILED,
            evidence=evidence_from(),
        )

        self.assertFalse(self.chatted_with["is_tutor_turn"])


class ChartPlanningTest(unittest.TestCase):
    """A chart is the project's, seen by all its members. It is planned from
    the conversation it was asked for in, and so without the tutoring turns."""

    def test_a_chart_is_planned_without_sight_of_the_tutoring_turns(self):
        from app.llm.chart_operations import planning

        planner = planning.ChartPlanning.__new__(planning.ChartPlanning)
        planner.generate_content = lambda **kwargs: None
        arguments = dict(
            papers=[(PAPER_A, "Model organisms")],
            conversation_id=str(uuid.uuid4()),
            current_user=SimpleNamespace(id=uuid.uuid4()),
            db=object(),
        )

        with patch.object(
            planning.message_crud, "get_conversation_messages", return_value=[]
        ) as history_lookup:
            planner.resolve_chart_scope("Chart the effect sizes.", **arguments)
            planner.propose_chart_plan("Chart the effect sizes.", **arguments)

        self.assertEqual(history_lookup.call_count, 2)
        for call in history_lookup.call_args_list:
            self.assertTrue(call.kwargs["shareable_only"])


class ProjectConversationReadTest(unittest.IsolatedAsyncioTestCase):
    """Who is handed the session when a project conversation is read."""

    async def read(self, *, owner: bool, nothing_to_read: bool = False):
        from app.api.projects import project_conversations_api as api

        reader = SimpleNamespace(id=uuid.uuid4())
        conversation = SimpleNamespace(
            id=uuid.uuid4(),
            title="Study session",
            user_id=reader.id if owner else uuid.uuid4(),
        )
        with (
            patch.object(
                api.project_conversation_crud,
                "get_by_conversation_id",
                return_value=conversation,
            ),
            patch.object(
                api.message_crud, "get_project_conversation_messages", return_value=[]
            ),
            patch.object(
                api.message_crud,
                "messages_to_dict",
                return_value=(
                    []
                    if nothing_to_read
                    else [
                        {
                            "content": "Why?",
                            "trace": {
                                "tutor_turn": True,
                                "tutor": STATE,
                                "tool_calls": [],
                            },
                        }
                    ]
                ),
            ),
            patch.object(
                api.message_crud, "get_latest_tutor_state", return_value=STATE
            ) as latest_state,
        ):
            response = await api.get_project_conversation(
                str(uuid.uuid4()), str(conversation.id), db=None, current_user=reader
            )
        return json.loads(response.body), response.body.decode(), latest_state

    async def test_the_owner_gets_the_session_back_with_the_conversation(self):
        body, _, _ = await self.read(owner=True)

        self.assertTrue(body["is_owner"])
        self.assertEqual(body["tutor_state"], STATE)
        self.assertEqual(body["messages"][0]["trace"]["tutor"], STATE)

    async def test_another_member_does_not(self):
        """The query leaves the turns out for them; if one came back anyway,
        its session is not handed out, and the lookup is not made."""
        body, raw, latest_state = await self.read(owner=False)

        self.assertFalse(body["is_owner"])
        self.assertIsNone(body["tutor_state"])
        self.assertNotIn("treats rank as a count of concepts", raw)
        latest_state.assert_not_called()

    async def test_a_conversation_that_shows_a_member_nothing_has_no_title_for_them(
        self,
    ):
        """It is not in their list either. Reached by its id, the title of a
        study session is the one thing left that would say what it is."""
        theirs, raw, _ = await self.read(owner=False, nothing_to_read=True)
        own, _, _ = await self.read(owner=True, nothing_to_read=True)
        readable, _, _ = await self.read(owner=False)

        self.assertIsNone(theirs["title"])
        self.assertNotIn("Study session", raw)
        self.assertEqual(own["title"], "Study session")
        self.assertEqual(readable["title"], "Study session")


if __name__ == "__main__":
    unittest.main()
