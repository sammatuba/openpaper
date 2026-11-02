"""ALLOWED_EMAILS closes sign-up on a public deployment; unset keeps upstream's
open sign-up."""

import os
import unittest
from unittest import mock

from app.auth.utils import allowed_emails, is_email_allowed


class AllowedEmails(unittest.TestCase):
    def test_unset_means_everyone(self):
        with mock.patch.dict(os.environ, {"ALLOWED_EMAILS": ""}):
            self.assertIsNone(allowed_emails())
            self.assertTrue(is_email_allowed("anyone@example.com"))

    def test_list_is_case_insensitive_and_tolerates_spaces(self):
        with mock.patch.dict(os.environ, {"ALLOWED_EMAILS": " Me@Gmail.com, other@x.org "}):
            self.assertTrue(is_email_allowed("me@gmail.com"))
            self.assertTrue(is_email_allowed("OTHER@X.ORG"))
            self.assertFalse(is_email_allowed("stranger@gmail.com"))

    def test_missing_email_is_rejected_when_a_list_is_set(self):
        with mock.patch.dict(os.environ, {"ALLOWED_EMAILS": "me@gmail.com"}):
            self.assertFalse(is_email_allowed(None))
            self.assertFalse(is_email_allowed(""))


if __name__ == "__main__":
    unittest.main()
