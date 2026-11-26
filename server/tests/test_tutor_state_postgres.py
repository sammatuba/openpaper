"""Reading a tutoring session back, against the isolated local PostgreSQL cluster.

The lookup asks PostgreSQL whether a JSONB column has a key, which no mock can
answer. It is also the whole of the session's memory: get it wrong and the
tutor either forgets the learner or picks up somebody else's map.
"""

import getpass
import os
import unittest
from types import SimpleNamespace
from uuid import uuid4


@unittest.skipUnless(
    os.environ.get("OPENPAPER_ISOLATED_PG_TEST") == "1",
    "requires isolated /tmp PostgreSQL",
)
class LatestTutorStatePostgresTests(unittest.TestCase):
    def setUp(self):
        username = getpass.getuser()
        expected = f"postgresql://{username}@/postgres?host=/tmp&port=55439"
        if (
            os.getcwd() != "/tmp"
            or os.environ.get("PYTHON_DOTENV_DISABLED") != "1"
            or os.environ.get("DATABASE_URL") != expected
        ):
            raise RuntimeError(
                "Requires /tmp, disabled dotenv and the dedicated local database"
            )
        from app.database.crud.message_crud import message_crud
        from app.database.models import Message
        from sqlalchemy import Column, MetaData, Table, create_engine, text
        from sqlalchemy.engine import URL
        from sqlalchemy.orm import sessionmaker

        self.text, self.message_crud, self.Message = text, message_crud, Message
        url = URL.create(
            "postgresql+psycopg2",
            username=username,
            database="postgres",
            query={"host": "/tmp", "port": "55439"},
        )
        self.admin = create_engine(url)
        with self.admin.connect() as conn:
            if (
                conn.execute(text("SHOW data_directory")).scalar_one()
                != "/tmp/openpaper-pg-transaction-test"
                or conn.execute(text("SHOW listen_addresses")).scalar_one()
            ):
                raise RuntimeError("Refusing non-isolated PostgreSQL cluster")
        self.schema = "tutor_state_" + uuid4().hex
        with self.admin.begin() as conn:
            conn.execute(text("CREATE SCHEMA " + self.schema))
        self.addCleanup(self.cleanup_database)
        self.engine = create_engine(
            url, connect_args={"options": "-csearch_path=" + self.schema}
        )
        # The real column types, without the foreign keys and constraints
        # this test has no use for.
        from app.database.models import Conversation, Paper

        self.Conversation, self.Paper = Conversation, Paper
        for model in (Message, Conversation, Paper):
            Table(
                model.__tablename__,
                MetaData(),
                *[
                    Column(column.name, column.type, primary_key=column.primary_key)
                    for column in model.__table__.columns
                ],
            ).create(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.addCleanup(self.db.close)
        self.user = SimpleNamespace(id=uuid4())
        self.conversation_id = uuid4()

    def cleanup_database(self):
        if hasattr(self, "engine"):
            self.engine.dispose()
        with self.admin.begin() as conn:
            conn.execute(self.text("DROP SCHEMA " + self.schema + " CASCADE"))
        self.admin.dispose()

    def add(
        self, sequence, *, trace=None, role="assistant", user=None, conversation=None
    ):
        self.db.add(
            self.Message(
                id=uuid4(),
                conversation_id=conversation or self.conversation_id,
                role=role,
                content="text",
                trace=trace,
                sequence=sequence,
                user_id=(user or self.user).id,
            )
        )
        self.db.commit()

    def latest(self):
        return self.message_crud.get_latest_tutor_state(
            self.db, conversation_id=self.conversation_id, current_user=self.user
        )

    def test_a_conversation_that_was_never_tutored_has_no_state(self):
        self.add(1, role="user")
        self.add(2)
        self.add(3, trace={"tool_calls": []})

        self.assertIsNone(self.latest())

    def test_the_most_recent_tutor_turn_wins(self):
        self.add(2, trace={"tutor": {"turn": 1}})
        self.add(4, trace={"tutor": {"turn": 2}})

        self.assertEqual(self.latest(), {"turn": 2})

    def test_ordinary_turns_since_the_last_tutor_turn_do_not_end_the_session(self):
        self.add(2, trace={"tutor": {"turn": 1}})
        for sequence in range(3, 30):
            self.add(sequence, role="user" if sequence % 2 else "assistant")

        self.assertEqual(self.latest(), {"turn": 1})

    def test_another_conversation_or_another_user_is_never_read(self):
        self.add(2, trace={"tutor": {"turn": 5}}, conversation=uuid4())
        self.add(2, trace={"tutor": {"turn": 6}}, user=SimpleNamespace(id=uuid4()))

        self.assertIsNone(self.latest())

    def test_a_stored_state_that_is_not_an_object_counts_as_none(self):
        self.add(2, trace={"tutor": "not a state"})

        self.assertIsNone(self.latest())

    # A shared paper shows its chat to anyone with the link. Tutoring turns
    # are not part of that: whatever the tutor wrote in them, well-formed or
    # not, a reader of the shared paper never receives it.

    def share_paper(self):
        paper_id = uuid4()
        self.db.add(self.Paper(id=paper_id, share_id="share-1", user_id=self.user.id))
        self.db.add(
            self.Conversation(
                id=self.conversation_id,
                conversable_id=paper_id,
                conversable_type="paper",
                user_id=self.user.id,
            )
        )
        self.db.commit()

    def shared(self, page=1, page_size=10):
        return [
            message.sequence
            for message in self.message_crud.get_shared_conversation_messages(
                self.db,
                conversation_id=self.conversation_id,
                share_paper_id="share-1",
                page=page,
                page_size=page_size,
            )
        ]

    def test_a_shared_paper_shows_no_tutoring_turns(self):
        self.share_paper()
        self.add(1, role="user")
        self.add(2)
        self.add(3, role="user", trace={"tutor_turn": True})
        self.add(4, trace={"tutor_turn": True, "tutor": {"turn": 1}})
        self.add(5, role="user", trace={"tutor_turn": True})
        self.add(6, trace={"tutor_turn": True})  # a tutor reply that lost its state
        self.add(7, role="user")
        self.add(8, trace={"tool_calls": []})
        self.add(9, trace={"tutor": {"turn": 2}})  # a state with no turn mark

        self.assertEqual(self.shared(), [1, 2, 7, 8])

    def test_the_owner_still_reads_every_turn(self):
        self.share_paper()
        self.add(1, role="user", trace={"tutor_turn": True})
        self.add(2, trace={"tutor_turn": True, "tutor": {"turn": 1}})

        own = self.message_crud.get_conversation_messages(
            self.db, conversation_id=self.conversation_id, current_user=self.user
        )

        self.assertEqual([message.sequence for message in own], [1, 2])
        self.assertEqual(self.shared(), [])

    def test_what_an_ordinary_answer_or_a_title_is_made_from_has_no_tutoring(self):
        """Both are things a shared paper shows, and both are written by a
        model from the conversation so far. Given the tutoring turns, either
        could repeat what was said in them."""
        self.add(1, role="user")
        self.add(2)
        self.add(3, role="user", trace={"tutor_turn": True})
        self.add(4, trace={"tutor_turn": True, "tutor": {"turn": 1}})
        self.add(5, role="user")
        self.add(6, trace={"tool_calls": []})

        def history(**kwargs):
            return [
                message.sequence
                for message in self.message_crud.get_conversation_messages(
                    self.db,
                    conversation_id=self.conversation_id,
                    current_user=self.user,
                    **kwargs,
                )
            ]

        self.assertEqual(history(shareable_only=True), [1, 2, 5, 6])
        self.assertEqual(history(), [1, 2, 3, 4, 5, 6])  # the owner, and the tutor

    def test_shared_pages_stay_full_around_a_tutoring_session(self):
        """The turns are left out by the query, before paging. Dropped
        afterwards, a page that fell on a tutoring session would come back
        short or empty and the reader would stop loading."""
        self.share_paper()
        for sequence in range(1, 13):
            self.add(sequence, role="user" if sequence % 2 else "assistant")
        for sequence in range(13, 33):
            self.add(sequence, trace={"tutor_turn": True})
        for sequence in range(33, 37):
            self.add(sequence)

        self.assertEqual(self.shared(page=1), list(range(7, 13)) + list(range(33, 37)))
        self.assertEqual(self.shared(page=2), list(range(1, 7)))


if __name__ == "__main__":
    unittest.main()
