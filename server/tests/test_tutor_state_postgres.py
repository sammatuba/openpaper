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
        # The real column types, without the foreign keys to tables this test
        # has no use for.
        messages = Table(
            "messages",
            MetaData(),
            *[
                Column(column.name, column.type, primary_key=column.primary_key)
                for column in Message.__table__.columns
            ],
        )
        messages.create(self.engine)
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


if __name__ == "__main__":
    unittest.main()
