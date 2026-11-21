"""Tutor mode in the paper chat.

In tutor mode the model teaches a paper by asking instead of answering, and
keeps a skill map of what the learner has demonstrated. The chat replays only
the last ten messages to the model, so that map cannot live in the transcript:
five exchanges in, the levels would be gone and the tutor would start placing
the learner again.

So every tutor turn ends with a state block the learner never reads. These
tests hold the seams that block passes through: it is lifted out of the stream
however the chunks fall, a block that does not parse costs the turn nothing,
what a model wrote is repaired rather than trusted, the stored state reaches
the next turn's prompt, and none of it touches an ordinary answer.
"""

import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from app.api import conversation_api, message_api
from app.api.message_api import _stream_chat_chunks
from app.llm.paper_operations import PaperOperations
from app.llm.prompts import TUTOR_PAPER_SYSTEM_PROMPT
from app.llm.tutor import (
    TUTOR_STATE_END,
    TUTOR_STATE_START,
    build_tutor_system_prompt,
    parse_tutor_state,
    split_tutor_state,
)
from app.schemas.message import ResponseStyle
from app.schemas.tutor import TutorState, without_tutor_state

STATE = {
    "topic": "Attention is all you need",
    "phase": "teaching",
    "target_level": 4,
    "difficulty": "normal",
    "focus": "Explain why attention replaces recurrence",
    "diagnostic_asked": 4,
    "subskills": [
        {
            "name": "Explain why attention replaces recurrence",
            "level": 3,
            "passes": 1,
            "unprompted": False,
            "last_checked": 6,
            "notes": "confuses path length with depth",
        },
        {"name": "Derive scaled dot-product attention", "level": 1},
    ],
    "misconceptions": ["thinks positional encoding is learned in the base model"],
    "covered": ["what a residual connection is"],
}

BLOCK = f"{TUTOR_STATE_START}\n{json.dumps(STATE)}\n{TUTOR_STATE_END}"


def content(text: str) -> dict:
    return {"type": "content", "content": text}


async def stream_of(*chunks):
    for chunk in chunks:
        yield chunk


async def split(*chunks, turn: int = 7) -> list:
    return [c async for c in split_tutor_state(stream_of(*chunks), turn=turn)]


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


EVIDENCE = (
    '---EVIDENCE---\n@cite[1]\n"Self-attention layers are faster"\n---END-EVIDENCE---'
)
# The parser keeps the quotation marks the model wrote; the client shows them.
CITATION = {"key": 1, "reference": '"Self-attention layers are faster"'}


class TutorStateRepairTest(unittest.TestCase):
    def test_out_of_range_values_are_clamped_not_rejected(self):
        state = TutorState.model_validate(
            {
                "phase": "warming up",
                "target_level": 9,
                "difficulty": "brutal",
                "focus": "   ",
                "subskills": [
                    {"name": "A", "level": 7, "passes": -2, "unprompted": "true"},
                    {"name": "B", "level": "2.0", "last_checked": None},
                ],
                "misconceptions": "one line, not a list",
            }
        )

        self.assertEqual(state.phase, "teaching")
        self.assertEqual(state.target_level, 5)
        self.assertEqual(state.difficulty, "normal")
        self.assertIsNone(state.focus)
        self.assertEqual([s.level for s in state.subskills], [5, 2])
        self.assertEqual(state.subskills[0].passes, 0)
        self.assertTrue(state.subskills[0].unprompted)
        self.assertEqual(state.subskills[1].last_checked, 0)
        self.assertEqual(state.misconceptions, ["one line, not a list"])

    def test_the_state_cannot_grow_without_bound(self):
        state = TutorState.model_validate(
            {
                "subskills": [{"name": f"skill {i}"} for i in range(40)]
                + [{"level": 3}, "not a subskill"],
                "covered": [f"point {i}" for i in range(100)],
                "misconceptions": ["x" * 5000],
            }
        )

        self.assertEqual(len(state.subskills), 10)
        self.assertEqual(len(state.misconceptions[0]), 300)
        # The newest notes survive. Keeping the first twelve instead would
        # refuse every note after the twelfth for the rest of the session.
        self.assertEqual(state.covered, [f"point {i}" for i in range(88, 100)])

    def test_a_number_json_allows_but_int_cannot_hold_is_repaired(self):
        """`Infinity` and `1e999` are valid to json.loads and raise
        OverflowError from int(), which would otherwise fail the whole turn
        after the learner had already read the answer."""
        raw = json.dumps(STATE).replace('"level": 3', '"level": Infinity')
        raw = raw.replace('"passes": 1', '"passes": 1e999')

        state = parse_tutor_state(raw)

        self.assertIsNotNone(state)
        self.assertEqual(state.subskills[0].level, 0)
        self.assertEqual(state.subskills[0].passes, 0)

    def test_a_block_with_no_subskills_is_not_a_state(self):
        self.assertIsNone(parse_tutor_state('{"topic": "x", "subskills": []}'))

    def test_a_block_that_is_not_json_is_not_a_state(self):
        self.assertIsNone(parse_tutor_state("levels went up a bit"))
        self.assertIsNone(parse_tutor_state("[1, 2, 3]"))
        self.assertIsNone(parse_tutor_state(""))

    def test_json_wrapped_in_a_code_fence_is_still_read(self):
        state = parse_tutor_state(f"```json\n{json.dumps(STATE)}\n```")

        self.assertIsNotNone(state)
        self.assertEqual(state.subskills[0].level, 3)

    def test_a_shared_conversation_does_not_carry_the_tutors_notes(self):
        """A shared paper shows its chat to anyone with the link. The tutor's
        notes on what the learner gets wrong are not part of the chat."""
        messages = [
            {"content": "Why?", "trace": {"tutor": STATE}},
            {"content": "Why?", "trace": {"tutor": STATE, "tool_calls": [1]}},
            {"content": "An answer", "trace": {"tool_calls": [2]}},
            {"content": "A question", "trace": None},
        ]

        shared = without_tutor_state(messages)

        self.assertEqual(
            [m["trace"] for m in shared],
            [None, {"tool_calls": [1]}, {"tool_calls": [2]}, None],
        )
        self.assertEqual(
            [m["content"] for m in shared], [m["content"] for m in messages]
        )
        self.assertIn("tutor", messages[0]["trace"], "the stored rows are left alone")


class SplitTutorStateTest(unittest.IsolatedAsyncioTestCase):
    async def test_the_block_is_lifted_out_and_the_question_is_left(self):
        chunks = await split(content(f"Why does that hold?\n\n{BLOCK}"))

        self.assertEqual(visible(chunks), "Why does that hold?\n\n")
        self.assertEqual(len(states(chunks)), 1)
        self.assertEqual(states(chunks)[0]["subskills"][0]["level"], 3)

    async def test_the_turn_number_comes_from_the_server_not_the_model(self):
        block = BLOCK.replace('"topic"', '"turn": 999, "topic"')

        chunks = await split(content(f"Next question?{block}"), turn=7)

        self.assertEqual(states(chunks)[0]["turn"], 7)

    async def test_a_block_cut_at_every_possible_chunk_boundary(self):
        """Wherever the stream is cut — through a marker, through the JSON —
        the learner sees the same text and the same one state arrives."""
        whole = f"Predict the result.\n\n{BLOCK}\n"

        for cut in range(1, len(whole)):
            with self.subTest(cut=cut):
                chunks = await split(content(whole[:cut]), content(whole[cut:]))

                self.assertEqual(visible(chunks), "Predict the result.\n\n\n")
                self.assertEqual(len(states(chunks)), 1)

    async def test_one_character_at_a_time(self):
        whole = f"Predict the result.\n\n{BLOCK}"

        chunks = await split(*[content(ch) for ch in whole])

        self.assertEqual(visible(chunks), "Predict the result.\n\n")
        self.assertEqual(len(states(chunks)), 1)

    async def test_dashes_that_never_become_a_marker_still_reach_the_learner(self):
        chunks = await split(content("See the rule below\n---"), content("TUTOR"))

        self.assertEqual(visible(chunks), "See the rule below\n---TUTOR")
        self.assertEqual(states(chunks), [])

    async def test_an_unparseable_block_is_dropped_without_touching_the_text(self):
        chunks = await split(
            content(f"What follows?{TUTOR_STATE_START}oops{TUTOR_STATE_END}")
        )

        self.assertEqual(visible(chunks), "What follows?")
        self.assertEqual(states(chunks), [])

    async def test_a_block_cut_off_before_its_closing_marker_is_still_read(self):
        chunks = await split(
            content(f"What follows?{TUTOR_STATE_START}{json.dumps(STATE)}")
        )

        self.assertEqual(visible(chunks), "What follows?")
        self.assertEqual(len(states(chunks)), 1)

    async def test_a_block_cut_off_mid_json_shows_nothing_of_itself(self):
        chunks = await split(content(f'What follows?{TUTOR_STATE_START}{{"topic": "At'))

        self.assertEqual(visible(chunks), "What follows?")
        self.assertEqual(states(chunks), [])

    async def test_a_restart_discards_the_abandoned_attempt(self):
        chunks = await split(
            content(f"First attempt {TUTOR_STATE_START}" + '{"topic": "half'),
            {"type": "reset", "content": ""},
            content(f"Second attempt?{BLOCK}"),
        )

        after_reset = chunks[[c.get("type") for c in chunks].index("reset") + 1 :]
        self.assertEqual(visible(after_reset), "Second attempt?")
        self.assertEqual(len(states(chunks)), 1)

    async def test_other_chunks_pass_straight_through(self):
        references = {"type": "references", "content": {"citations": []}}

        chunks = await split(content("Right. "), references, content(f"Why?{BLOCK}"))

        self.assertIn(references, chunks)
        self.assertEqual(visible(chunks), "Right. Why?")


class TutorPromptTest(unittest.TestCase):
    def test_with_no_stored_state_the_tutor_is_told_to_start(self):
        prompt = build_tutor_system_prompt(None)

        self.assertTrue(prompt.startswith(TUTOR_PAPER_SYSTEM_PROMPT))
        self.assertIn("No session state is stored", prompt)
        self.assertIn("This is turn 1", prompt)
        self.assertIn("start a session", prompt)

    def test_no_stored_state_does_not_mean_restart_a_session_in_progress(self):
        """A first turn whose state block was lost leaves nothing stored, with
        the tutor's question and the learner's answer already on the page."""
        prompt = build_tutor_system_prompt(None)

        self.assertIn("rebuild it from what you can see", prompt)
        self.assertIn("instead of starting again", prompt)

    def test_a_stored_state_is_handed_back_whole_with_the_next_turn_number(self):
        prompt = build_tutor_system_prompt({**STATE, "turn": 6})

        self.assertIn("This is turn 7", prompt)
        self.assertIn("confuses path length with depth", prompt)
        self.assertIn("thinks positional encoding is learned", prompt)
        self.assertNotIn("No session state is stored", prompt)

    def test_the_prompt_asks_for_the_markers_the_splitter_looks_for(self):
        self.assertIn(TUTOR_STATE_START, TUTOR_PAPER_SYSTEM_PROMPT)
        self.assertIn(TUTOR_STATE_END, TUTOR_PAPER_SYSTEM_PROMPT)


class ChatWithPaperTest(unittest.IsolatedAsyncioTestCase):
    """The paper chat end to end, with the model and the database replaced."""

    PAPER_ID = uuid.uuid4()
    # The paper's own conversation, which is what the reader always sends.
    OWN_CONVERSATION = SimpleNamespace(
        conversable_type="paper", conversable_id=PAPER_ID
    )

    async def run_chat(
        self,
        style,
        model_text,
        stored_state=None,
        pieces=None,
        conversation=OWN_CONVERSATION,
    ):
        operations = PaperOperations.__new__(PaperOperations)
        seen = {}
        if pieces is None:
            # Small pieces, so markers straddle chunk boundaries as they do live.
            pieces = [model_text[i : i + 9] for i in range(0, len(model_text), 9)]

        async def send_message_stream(**kwargs):
            seen.update(kwargs)
            for piece in pieces:
                yield SimpleNamespace(text=piece, is_restart=False)

        operations.send_message_stream = send_message_stream
        paper = SimpleNamespace(
            id=self.PAPER_ID, title="A paper", s3_object_key="k", raw_content="text"
        )

        with (
            patch("app.llm.paper_operations.paper_crud.get", return_value=paper),
            patch(
                "app.llm.paper_operations.conversation_crud.get_conversation_by_id",
                return_value=conversation,
            ) as own_conversation,
            patch(
                "app.llm.paper_operations.message_crud.get_conversation_messages",
                return_value=[],
            ),
            patch(
                "app.llm.paper_operations.message_crud.get_latest_tutor_state",
                return_value=stored_state,
            ) as latest_state,
            patch(
                "app.llm.paper_operations.s3_service.download_bytes",
                return_value=b"%PDF",
            ),
        ):
            chunks = [
                c
                async for c in operations.chat_with_paper(
                    paper_id=str(uuid.uuid4()),
                    conversation_id=str(uuid.uuid4()),
                    question="Because every position attends to every other one.",
                    current_user=SimpleNamespace(id=uuid.uuid4()),
                    response_style=style,
                    db=None,
                )
            ]
        self.conversation_lookup = own_conversation
        return chunks, seen, latest_state

    async def test_a_tutor_turn_carries_its_state_and_hides_the_block(self):
        model_text = (
            "Close. What does that cost as the sequence grows? [^1]\n\n"
            '---EVIDENCE---\n@cite[1]\n"Self-attention layers are faster"\n'
            f"---END-EVIDENCE---\n\n{BLOCK}"
        )

        chunks, seen, _ = await self.run_chat(
            ResponseStyle.TUTOR, model_text, stored_state={**STATE, "turn": 6}
        )

        self.assertEqual(
            visible(chunks).strip(),
            "Close. What does that cost as the sequence grows? [^1]",
        )
        self.assertEqual(len(states(chunks)), 1)
        self.assertEqual(states(chunks)[0]["turn"], 7)
        self.assertEqual(
            [c["type"] for c in chunks if c["type"] == "references"], ["references"]
        )
        self.assertIn("This is turn 7", seen["system_prompt"])
        self.assertIn("The learner says:", seen["message"][0].text)
        self.assertNotIn("Query:", seen["message"][0].text)

    async def test_the_block_may_come_before_the_evidence(self):
        model_text = (
            f"Right. Why? [^1]\n\n{BLOCK}\n\n"
            '---EVIDENCE---\n@cite[1]\n"Self-attention layers are faster"\n'
            "---END-EVIDENCE---"
        )

        chunks, _, _ = await self.run_chat(ResponseStyle.TUTOR, model_text)

        self.assertEqual(visible(chunks).strip(), "Right. Why? [^1]")
        self.assertEqual(len(states(chunks)), 1)
        self.assertEqual(states(chunks)[0]["turn"], 1)
        self.assertEqual(citations(chunks), [CITATION])

    async def test_a_tutor_turn_cut_anywhere_keeps_its_text_citation_and_state(self):
        """The whole path — evidence parser, then state filter — at every
        two-chunk cut and as a single chunk. Whatever the cut, the learner
        reads the same words, the citation arrives, and the state stored is
        the state written: not one with a space eaten out of a subskill name,
        which would stop the panel matching its focus."""
        question = "Close. What does that cost as the sequence grows? [^1]\n\n"
        whole = f"{question}{EVIDENCE}\n\n{BLOCK}"
        expected = {**TutorState.model_validate(STATE).model_dump(), "turn": 1}

        for cut in range(0, len(whole)):
            pieces = [whole[:cut], whole[cut:]] if cut else [whole]
            with self.subTest(cut=cut):
                chunks, _, _ = await self.run_chat(
                    ResponseStyle.TUTOR, whole, pieces=pieces
                )

                self.assertEqual(visible(chunks), f"{question}\n\n")
                self.assertEqual(citations(chunks), [CITATION])
                self.assertEqual(states(chunks), [expected])

    async def test_an_ordinary_answer_cut_anywhere_reads_the_same(self):
        closing = "Ask me about the decoder next, it is the harder half."
        answer = "It attends globally [^1].\n\n"
        whole = f"{answer}{EVIDENCE}\n\n{closing}"

        for cut in range(0, len(whole)):
            pieces = [whole[:cut], whole[cut:]] if cut else [whole]
            with self.subTest(cut=cut):
                chunks, _, _ = await self.run_chat(
                    ResponseStyle.NORMAL, whole, pieces=pieces
                )

                self.assertEqual(visible(chunks), f"{answer}\n\n{closing}")
                self.assertEqual(citations(chunks), [CITATION])

    async def test_an_evidence_block_the_stream_ended_inside_is_not_cited(self):
        """Cut off in the quotation or in the closing marker itself, an
        unfinished block yields no citation, as before this change. A quotation
        that stops wherever the output did is not the paper's words, and one
        ending in half a marker is not even text."""
        for ending in ('"Self-attention layers', '"Full passage."\n---END-EVIDENC'):
            with self.subTest(ending=ending):
                whole = f"Right [^1].\n\n---EVIDENCE---\n@cite[1]\n{ending}"

                chunks, _, _ = await self.run_chat(ResponseStyle.NORMAL, whole)

                self.assertEqual(visible(chunks), "Right [^1].\n\n")
                self.assertEqual(citations(chunks), [])

    async def test_an_unclosed_evidence_block_cannot_carry_the_state_out(self):
        """The tutor forgets `---END-EVIDENCE---` and goes straight on to its
        state. Citations are stored with the message and shown to anyone the
        paper is shared with, so nothing of the state may end up in one."""
        whole = (
            "Right. Why? [^1]\n\n"
            '---EVIDENCE---\n@cite[1]\n"Self-attention layers are faster"\n\n'
            f"{BLOCK}"
        )
        expected = {**TutorState.model_validate(STATE).model_dump(), "turn": 1}

        for cut in range(0, len(whole)):
            pieces = [whole[:cut], whole[cut:]] if cut else [whole]
            with self.subTest(cut=cut):
                chunks, _, _ = await self.run_chat(
                    ResponseStyle.TUTOR, whole, pieces=pieces
                )

                self.assertEqual(states(chunks), [expected])
                everything_else = json.dumps(
                    [c for c in chunks if c.get("type") != "tutor_state"]
                )
                self.assertNotIn("confuses path length with depth", everything_else)
                self.assertNotIn("TUTOR-STATE", everything_else)
                self.assertEqual(visible(chunks), "Right. Why? [^1]\n\n")

    async def test_tutor_mode_is_refused_outside_the_papers_own_conversation(self):
        """The request names the paper and the conversation separately. A
        tutor turn sent to a project conversation would store the learner's
        state where the project's other members read."""
        elsewhere = [
            None,  # not this user's conversation, or not a conversation at all
            SimpleNamespace(conversable_type="project", conversable_id=uuid.uuid4()),
            SimpleNamespace(conversable_type="everything", conversable_id=None),
            SimpleNamespace(conversable_type="paper", conversable_id=uuid.uuid4()),
        ]
        for conversation in elsewhere:
            with self.subTest(conversation=conversation):
                with self.assertRaises(ValueError):
                    await self.run_chat(
                        ResponseStyle.TUTOR, f"Why?{BLOCK}", conversation=conversation
                    )

    async def test_the_model_is_not_called_for_a_refused_tutor_turn(self):
        operations = PaperOperations.__new__(PaperOperations)
        called = []

        async def send_message_stream(**kwargs):
            called.append(kwargs)
            yield SimpleNamespace(text="Why?", is_restart=False)

        operations.send_message_stream = send_message_stream
        paper = SimpleNamespace(id=uuid.uuid4(), title="A paper", s3_object_key="k")
        with (
            patch("app.llm.paper_operations.paper_crud.get", return_value=paper),
            patch(
                "app.llm.paper_operations.conversation_crud.get_conversation_by_id",
                return_value=None,
            ),
            patch(
                "app.llm.paper_operations.message_crud.get_conversation_messages",
                return_value=[],
            ),
            patch(
                "app.llm.paper_operations.message_crud.get_latest_tutor_state"
            ) as latest_state,
        ):
            with self.assertRaises(ValueError):
                async for _ in operations.chat_with_paper(
                    paper_id=str(paper.id),
                    conversation_id=str(uuid.uuid4()),
                    question="x",
                    current_user=SimpleNamespace(id=uuid.uuid4()),
                    response_style=ResponseStyle.TUTOR,
                    db=None,
                ):
                    pass

        self.assertEqual(called, [])
        latest_state.assert_not_called()

    async def test_an_ordinary_answer_is_untouched_by_tutor_mode(self):
        model_text = (
            "It attends globally [^1].\n\n"
            '---EVIDENCE---\n@cite[1]\n"Self-attention layers are faster"\n'
            "---END-EVIDENCE---"
        )

        chunks, seen, latest_state = await self.run_chat(
            ResponseStyle.NORMAL, model_text
        )

        self.assertEqual(visible(chunks).strip(), "It attends globally [^1].")
        self.assertEqual(states(chunks), [])
        self.assertIn("You are in normal mode", seen["system_prompt"])
        self.assertNotIn("personal tutor", seen["system_prompt"])
        self.assertIn("Query:", seen["message"][0].text)
        latest_state.assert_not_called()
        # The conversation check belongs to tutor turns. An ordinary answer
        # stores nothing private, and is sent as it always was.
        self.conversation_lookup.assert_not_called()

    async def test_text_after_the_evidence_block_arrives_once(self):
        """It used to arrive twice: once when the block closed, and again when
        the buffer it had been left in was flushed."""
        closing = "Ask me about the decoder next, it is the harder half."
        model_text = (
            "It attends globally [^1].\n\n"
            '---EVIDENCE---\n@cite[1]\n"Self-attention layers are faster"\n'
            f"---END-EVIDENCE---\n\n{closing}"
        )

        chunks, _, _ = await self.run_chat(ResponseStyle.NORMAL, model_text)

        # Compared whole, not by counting the sentence: the repeat was of
        # whatever fragment shared a chunk with the closing marker, which is
        # rarely the full sentence.
        self.assertEqual(
            " ".join(visible(chunks).split()),
            f"It attends globally [^1]. {closing}",
        )


class StreamChatChunksTest(unittest.IsolatedAsyncioTestCase):
    async def collect(self, *chunks):
        container = {"evidence": None}
        sent = [
            json.loads(event.replace("END_OF_STREAM", ""))
            async for event in _stream_chat_chunks(
                chunk_generator=stream_of(*chunks),
                content_chunks=[],
                evidence_container=container,
            )
        ]
        return sent, container

    async def test_the_state_is_kept_for_saving_but_not_yet_sent(self):
        """Sending it is the endpoint's job, after the save. Forwarded from
        here it would reach the panel before anyone knew the turn was kept."""
        sent, container = await self.collect(
            content("Why?"), {"type": "tutor_state", "content": STATE}
        )

        self.assertEqual(container["tutor_state"], STATE)
        self.assertEqual(sent, [{"type": "content", "content": "Why?"}])

    async def test_a_restart_forgets_the_state_of_the_abandoned_attempt(self):
        _, container = await self.collect(
            {"type": "tutor_state", "content": STATE},
            {"type": "reset", "content": ""},
            content("Why?"),
        )

        self.assertNotIn("tutor_state", container)


class TutorEndpointsTest(unittest.IsolatedAsyncioTestCase):
    """Where the state is written, read back, and withheld.

    The session's memory is one keyword argument on a save and one key on a
    response. Each is a line that can be deleted without any other test
    noticing, so each is held here at the endpoint itself.
    """

    async def chat(self, style, *chunks, save_error=None):
        """Run the endpoint; return what it saved, in order, and what it sent."""

        async def chat_with_paper(**kwargs):
            for chunk in chunks:
                yield chunk

        request = message_api.ChatMessageRequest(
            paper_id=str(uuid.uuid4()),
            conversation_id=str(uuid.uuid4()),
            user_query="Because every position attends to every other one.",
            style=style,
        )
        self.sent = []
        with (
            patch.object(message_api.operations, "chat_with_paper", chat_with_paper),
            patch.object(
                message_api.message_crud, "create", side_effect=save_error
            ) as create,
            patch.object(message_api, "track_event"),
        ):
            response = await message_api.chat_message_stream(
                request, db=None, current_user=SimpleNamespace(id=uuid.uuid4())
            )
            async for event in response.body_iterator:
                body = event.replace("END_OF_STREAM", "")
                if body:
                    self.sent.append(json.loads(body))
        return [call.kwargs["obj_in"] for call in create.call_args_list]

    def sent_states(self):
        return [e["content"] for e in self.sent if e["type"] == "tutor_state"]

    async def test_a_tutor_turn_is_saved_with_its_state(self):
        saved = await self.chat(
            ResponseStyle.TUTOR,
            content("Why?"),
            {"type": "tutor_state", "content": STATE},
        )

        self.assertEqual([m.role for m in saved], ["user", "assistant"])
        self.assertEqual(saved[1].content, "Why?")
        self.assertEqual(saved[1].trace, {"tutor": STATE})
        self.assertIsNone(saved[0].trace)
        # And only then told to the reader, as the last thing in the stream.
        self.assertEqual(self.sent_states(), [STATE])
        self.assertEqual(self.sent[-1]["type"], "tutor_state")

    async def test_a_reply_that_is_only_state_changes_nothing_the_learner_sees(self):
        """No visible text is a failed turn: nothing is saved. The panel must
        not move on to a state the server threw away."""
        saved = await self.chat(
            ResponseStyle.TUTOR, {"type": "tutor_state", "content": STATE}
        )

        self.assertEqual(saved, [])
        self.assertEqual(self.sent_states(), [])
        self.assertEqual([e["type"] for e in self.sent], ["error"])

    async def test_a_turn_that_fails_to_save_does_not_send_its_state(self):
        await self.chat(
            ResponseStyle.TUTOR,
            content("Why?"),
            {"type": "tutor_state", "content": STATE},
            save_error=RuntimeError("database unavailable"),
        )

        self.assertEqual(self.sent_states(), [])
        self.assertEqual(self.sent[-1]["type"], "error")

    async def test_a_project_member_reading_a_conversation_gets_no_tutor_state(self):
        """Tutor mode is refused outside a paper's own conversation, so none
        should ever be stored here. If one is, it still is not handed out."""
        from app.api.projects import project_conversations_api as api

        project_id, conversation_id = uuid.uuid4(), uuid.uuid4()
        with (
            patch.object(
                api.project_conversation_crud,
                "get_by_conversation_id",
                return_value=SimpleNamespace(
                    id=conversation_id, title="Shared thread", user_id=uuid.uuid4()
                ),
            ),
            patch.object(
                api.message_crud, "get_project_conversation_messages", return_value=[]
            ),
            patch.object(
                api.message_crud,
                "messages_to_dict",
                return_value=[
                    {"content": "Why?", "trace": {"tutor": STATE, "tool_calls": []}}
                ],
            ),
        ):
            response = await api.get_project_conversation(
                str(project_id),
                str(conversation_id),
                db=None,
                current_user=SimpleNamespace(id=uuid.uuid4()),
            )

        body = json.loads(response.body)
        self.assertEqual([m["content"] for m in body["messages"]], ["Why?"])
        self.assertEqual(body["messages"][0]["trace"], {"tool_calls": []})
        self.assertNotIn("confuses path length with depth", response.body.decode())

    async def test_a_tutor_turn_that_lost_its_state_is_still_saved(self):
        saved = await self.chat(ResponseStyle.TUTOR, content("Why?"))

        self.assertEqual([m.role for m in saved], ["user", "assistant"])
        self.assertIsNone(saved[1].trace)

    async def test_an_ordinary_turn_is_saved_without_one(self):
        saved = await self.chat(ResponseStyle.NORMAL, content("An answer."))

        self.assertIsNone(saved[1].trace)

    async def test_the_owner_gets_the_session_back_with_the_conversation(self):
        conversation_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4())
        with (
            patch.object(
                conversation_api.conversation_crud,
                "get",
                return_value=SimpleNamespace(id=conversation_id, title="A paper"),
            ),
            patch.object(
                conversation_api.message_crud,
                "get_conversation_messages",
                return_value=[],
            ),
            patch.object(
                conversation_api.message_crud, "messages_to_dict", return_value=[]
            ),
            patch.object(
                conversation_api.message_crud,
                "get_latest_tutor_state",
                return_value=STATE,
            ) as latest,
        ):
            response = await conversation_api.get_conversation(
                str(conversation_id), db=None, current_user=user
            )

        self.assertEqual(json.loads(response.body)["tutor_state"], STATE)
        latest.assert_called_once_with(
            None, conversation_id=conversation_id, current_user=user
        )

    async def test_a_reader_of_a_shared_paper_does_not(self):
        with (
            patch.object(
                conversation_api.conversation_crud,
                "get_by_share_paper_id",
                return_value=SimpleNamespace(id=uuid.uuid4(), title="A paper"),
            ),
            patch.object(
                conversation_api.message_crud,
                "get_shared_conversation_messages",
                return_value=[],
            ),
            patch.object(
                conversation_api.message_crud,
                "messages_to_dict",
                return_value=[{"content": "Why?", "trace": {"tutor": STATE}}],
            ),
            patch.object(
                conversation_api.message_crud, "get_latest_tutor_state"
            ) as latest,
            patch.object(conversation_api, "track_event"),
        ):
            response = await conversation_api.get_shared_paper_conversation(
                "share-1", db=None, current_user=None
            )

        body = json.loads(response.body)
        self.assertEqual([m["content"] for m in body["messages"]], ["Why?"])
        self.assertNotIn("confuses path length with depth", response.body.decode())
        self.assertNotIn("tutor_state", body)
        latest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
