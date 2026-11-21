"""Who is sent a project conversation's tutoring turns, against PostgreSQL.

A project conversation is read by every member of the project. A tutoring
session in it is its owner's: the turns are left out, in the query, for
anyone else. Whether a JSONB column has a key is asked of PostgreSQL, which no
mock can answer, and this is the whole of what keeps one member's session
from another.
"""

import getpass
import os
import unittest
from types import SimpleNamespace
from uuid import uuid4

TUTORING = {"tutor_turn": True}


@unittest.skipUnless(
    os.environ.get("OPENPAPER_ISOLATED_PG_TEST") == "1",
    "requires isolated /tmp PostgreSQL",
)
class ProjectTutoringTurnsPostgresTests(unittest.TestCase):
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
        from app.database.crud.projects.project_conversation_crud import (
            project_conversation_crud,
        )
        from app.database.models import Conversation, Message, ProjectRole
        from sqlalchemy import Column, MetaData, Table, create_engine, text
        from sqlalchemy.engine import URL
        from sqlalchemy.orm import sessionmaker

        self.text = text
        self.message_crud = message_crud
        self.conversation_crud = project_conversation_crud
        self.Message, self.Conversation, self.ProjectRole = (
            Message,
            Conversation,
            ProjectRole,
        )
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
        self.schema = "project_tutor_" + uuid4().hex
        with self.admin.begin() as conn:
            conn.execute(text("CREATE SCHEMA " + self.schema))
        self.addCleanup(self.cleanup_database)
        self.engine = create_engine(
            url, connect_args={"options": "-csearch_path=" + self.schema}
        )
        # The real column types, without the foreign keys and constraints
        # this test has no use for.
        for model in (Message, Conversation, ProjectRole):
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

        self.project_id = uuid4()
        self.learner = SimpleNamespace(id=uuid4())
        self.colleague = SimpleNamespace(id=uuid4())
        self.outsider = SimpleNamespace(id=uuid4())
        for member in (self.learner, self.colleague):
            self.join(member, self.project_id)
        self.conversation_id = self.converse(self.learner)

    def cleanup_database(self):
        if hasattr(self, "engine"):
            self.engine.dispose()
        with self.admin.begin() as conn:
            conn.execute(self.text("DROP SCHEMA " + self.schema + " CASCADE"))
        self.admin.dispose()

    def join(self, user, project_id, role="editor"):
        self.db.add(
            self.ProjectRole(
                id=uuid4(), project_id=project_id, user_id=user.id, role=role
            )
        )
        self.db.commit()

    def converse(self, owner, project_id=None, title="Study session"):
        conversation_id = uuid4()
        self.db.add(
            self.Conversation(
                id=conversation_id,
                title=title,
                user_id=owner.id,
                conversable_id=project_id or self.project_id,
                conversable_type="project",
            )
        )
        self.db.commit()
        return conversation_id

    def add(self, sequence, *, trace=None, role="assistant", conversation=None):
        self.db.add(
            self.Message(
                id=uuid4(),
                conversation_id=conversation or self.conversation_id,
                role=role,
                content="text",
                trace=trace,
                sequence=sequence,
                user_id=self.learner.id,
            )
        )
        self.db.commit()

    def read(self, reader, page=1, page_size=10, conversation=None):
        return [
            message.sequence
            for message in self.message_crud.get_project_conversation_messages(
                self.db,
                conversation_id=conversation or self.conversation_id,
                project_id=self.project_id,
                current_user=reader,
                page=page,
                page_size=page_size,
            )
        ]

    def listed(self, reader):
        return {
            conversation.id
            for conversation in self.conversation_crud.get_by_project_id(
                self.db, project_id=self.project_id, user=reader
            )
        }

    def a_mixed_conversation(self):
        self.add(1, role="user")
        self.add(2, trace={"tool_calls": []})
        self.add(3, role="user", trace=TUTORING)
        self.add(4, trace={**TUTORING, "tutor": {"turn": 1}, "tool_calls": []})
        self.add(5, role="user", trace=TUTORING)
        self.add(6, trace=TUTORING)  # a tutor reply that lost its state
        self.add(7, role="user")
        self.add(8)
        self.add(9, trace={"tutor": {"turn": 2}})  # a state with no turn mark

    def test_the_owner_reads_every_turn(self):
        self.a_mixed_conversation()

        self.assertEqual(self.read(self.learner), list(range(1, 10)))

    def test_another_member_is_sent_no_tutoring_turn(self):
        self.a_mixed_conversation()

        self.assertEqual(self.read(self.colleague), [1, 2, 7, 8])

    def test_someone_outside_the_project_is_sent_nothing(self):
        self.a_mixed_conversation()

        self.assertEqual(self.read(self.outsider), [])

    def test_pages_stay_full_around_a_tutoring_session(self):
        """The turns are left out by the query, before paging. Dropped
        afterwards, a page that fell on a session would come back short or
        empty and the reader would stop loading."""
        for sequence in range(1, 13):
            self.add(sequence, role="user" if sequence % 2 else "assistant")
        for sequence in range(13, 33):
            self.add(sequence, trace=TUTORING)
        for sequence in range(33, 37):
            self.add(sequence)

        self.assertEqual(
            self.read(self.colleague, page=1),
            list(range(7, 13)) + list(range(33, 37)),
        )
        self.assertEqual(self.read(self.colleague, page=2), list(range(1, 7)))
        self.assertEqual(self.read(self.learner, page=1), list(range(27, 37)))

    # The list of a project's conversations.

    def test_a_conversation_of_tutoring_turns_only_is_listed_for_its_owner_alone(self):
        self.add(1, role="user", trace=TUTORING)
        self.add(2, trace={**TUTORING, "tutor": {"turn": 1}})

        self.assertIn(self.conversation_id, self.listed(self.learner))
        self.assertNotIn(self.conversation_id, self.listed(self.colleague))

    def test_a_conversation_with_ordinary_turns_too_stays_listed(self):
        self.a_mixed_conversation()

        self.assertIn(self.conversation_id, self.listed(self.colleague))

    def test_an_ordinary_conversation_is_listed_as_before(self):
        ordinary = self.converse(self.learner, title="Evidence comparison")
        self.add(1, role="user", conversation=ordinary)
        self.add(2, conversation=ordinary, trace={"tool_calls": []})

        self.assertIn(ordinary, self.listed(self.colleague))
        self.assertEqual(self.listed(self.outsider), set())

    def test_a_study_session_is_not_listed_before_its_first_turn_is_saved(self):
        """It is created, and named, when the learner starts it. The first
        turn is saved only once the tutor has replied, and never if that
        reply fails. Listed meanwhile, it would tell the project who is
        studying."""
        # setUp made the learner's conversation, titled "Study session"; it
        # has no messages yet.
        self.assertIn(self.conversation_id, self.listed(self.learner))
        self.assertNotIn(self.conversation_id, self.listed(self.colleague))

        self.add(1, role="user", trace=TUTORING)
        self.add(2, trace={**TUTORING, "tutor": {"turn": 1}})

        self.assertNotIn(self.conversation_id, self.listed(self.colleague))

    # The conversation has to be one of the project the caller named.

    def test_a_conversation_is_not_reached_through_another_project(self):
        """The role check is on the project in the request. With the
        conversation then fetched by id alone, a member of one project could
        post into a conversation of another."""
        elsewhere = uuid4()
        self.join(self.outsider, elsewhere)

        def reach(user, project_id):
            return self.conversation_crud.get_by_conversation_id(
                self.db,
                project_id=project_id,
                conversation_id=self.conversation_id,
                user=user,
            )

        self.assertIsNone(reach(self.outsider, elsewhere))
        self.assertIsNone(reach(self.outsider, self.project_id))
        self.assertEqual(
            reach(self.colleague, self.project_id).id, self.conversation_id
        )


if __name__ == "__main__":
    unittest.main()
