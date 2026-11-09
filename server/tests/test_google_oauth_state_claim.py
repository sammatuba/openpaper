"""OAuth claim transactions on the explicitly isolated socket-only PostgreSQL.

Imports do not initialize or probe the configured application database. The
suite opts in to the same disposable cluster contract as other integration
checks and creates only its own random schema, preserving real model behavior.
"""

import datetime
import getpass
import os
import secrets
import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4


@unittest.skipUnless(os.environ.get("OPENPAPER_ISOLATED_PG_TEST") == "1", "requires isolated /tmp PostgreSQL")
class TestClaim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        username = getpass.getuser()
        expected = f"postgresql://{username}@/postgres?host=/tmp&port=55439"
        if (os.getcwd() != "/tmp" or os.environ.get("PYTHON_DOTENV_DISABLED") != "1"
                or os.environ.get("DATABASE_URL") != expected):
            raise RuntimeError("Requires /tmp, disabled dotenv and the dedicated local database")
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import URL
        from sqlalchemy.orm import sessionmaker
        from app.database.crud.google_oauth_crud import ClaimOutcome, google_oauth_state_crud
        from app.database.models import GoogleOAuthState

        cls.Outcome, cls.crud, cls.State = ClaimOutcome, google_oauth_state_crud, GoogleOAuthState
        cls.text = staticmethod(text)
        url = URL.create("postgresql+psycopg2", username=username, database="postgres",
                         query={"host": "/tmp", "port": "55439"})
        cls.admin = create_engine(url)
        with cls.admin.connect() as connection:
            if (connection.execute(text("SHOW data_directory")).scalar_one() != "/tmp/openpaper-pg-transaction-test"
                    or connection.execute(text("SHOW listen_addresses")).scalar_one()):
                raise RuntimeError("Refusing non-isolated PostgreSQL cluster")
        cls.schema = "google_oauth_claim_" + uuid4().hex
        with cls.admin.begin() as connection:
            connection.execute(text("CREATE SCHEMA " + cls.schema))
        cls.engine = create_engine(url, connect_args={"options": "-csearch_path=" + cls.schema})
        try:
            with cls.engine.begin() as connection:
                # The optional session FK is not exercised by claim/release;
                # its parent exists only inside this suite's disposable schema.
                connection.execute(text("CREATE TABLE sessions (id uuid PRIMARY KEY)"))
                GoogleOAuthState.__table__.create(connection)
            cls.Session = sessionmaker(bind=cls.engine)
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.admin.begin() as connection:
            connection.execute(cls.text("DROP SCHEMA " + cls.schema + " CASCADE"))
        cls.admin.dispose()

    def setUp(self) -> None:
        self.db = self.Session()
        self.state = f"test-{secrets.token_urlsafe(16)}"
        self.addCleanup(self._cleanup)

    def _cleanup(self) -> None:
        try:
            self.db.rollback()
            self.db.query(self.State).filter(
                self.State.state.in_([self.state, self.state + "-stale"])
            ).delete(synchronize_session=False)
            self.db.commit()
        finally:
            self.db.close()

    def test_first_claim_wins_second_is_a_replay(self) -> None:
        self.crud.create(self.db, state=self.state)

        first = self.crud.claim(self.db, state=self.state)
        second = self.crud.claim(self.db, state=self.state)

        self.assertIs(first.outcome, self.Outcome.CLAIMED)
        self.assertIs(second.outcome, self.Outcome.REPLAY)
        self.assertIsNotNone(second.record)

    def test_unissued_state(self) -> None:
        result = self.crud.claim(self.db, state="test-never-issued")
        self.assertIs(result.outcome, self.Outcome.UNKNOWN)

    def test_expired_state(self) -> None:
        record = self.crud.create(self.db, state=self.state)
        record.expires_at = datetime.datetime.now(  # type: ignore[assignment]
            datetime.timezone.utc
        ) - datetime.timedelta(minutes=1)
        self.db.commit()

        result = self.crud.claim(self.db, state=self.state)
        self.assertIs(result.outcome, self.Outcome.EXPIRED)

    def test_release_lets_a_retry_through(self) -> None:
        self.crud.create(self.db, state=self.state)
        claimed = self.crud.claim(self.db, state=self.state)
        assert claimed.record is not None

        self.crud.release(self.db, record=claimed.record)

        # After a failure that never spent the code, the user retrying the same
        # URL must be able to complete rather than being told it's a replay.
        retry = self.crud.claim(self.db, state=self.state)
        self.assertIs(retry.outcome, self.Outcome.CLAIMED)

    def test_concurrent_callbacks_yield_exactly_one_winner(self) -> None:
        """A scanner and the browser hitting the callback at the same instant."""
        self.crud.create(self.db, state=self.state)

        def attempt():
            db = self.Session()
            try:
                return self.crud.claim(db, state=self.state).outcome
            finally:
                db.close()

        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(lambda _: attempt(), range(8)))

        self.assertEqual(outcomes.count(self.Outcome.CLAIMED), 1)
        self.assertEqual(outcomes.count(self.Outcome.REPLAY), 7)

    def test_delete_stale_spares_rows_still_in_retention(self) -> None:
        fresh = self.crud.create(self.db, state=self.state)
        stale = self.crud.create(self.db, state=f"{self.state}-stale")
        stale.expires_at = datetime.datetime.now(  # type: ignore[assignment]
            datetime.timezone.utc
        ) - datetime.timedelta(days=1)
        self.db.commit()

        # Read the values off before the delete; the instances go stale with it.
        fresh_state, stale_state = str(fresh.state), str(stale.state)

        self.crud.delete_stale(self.db)

        remaining = {
            row.state
            for row in self.db.query(self.State).filter(
                self.State.state.like("test-%")
            )
        }
        self.assertIn(fresh_state, remaining)
        self.assertNotIn(stale_state, remaining)


if __name__ == "__main__":
    unittest.main()
