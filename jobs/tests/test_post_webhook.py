"""post_webhook retries transient failures so an upload outcome is not dropped."""

import os
import unittest
from unittest import mock

import requests

os.environ.setdefault("TASK_BACKEND", "cloudtasks")

from src import tasks  # noqa: E402


def response(status: int) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r.url = "http://server/api/webhooks/paper-processing/job"
    return r


class PostWebhook(unittest.TestCase):
    def setUp(self):
        sleep = mock.patch.object(tasks.time, "sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def post(self, *outcomes):
        with mock.patch.object(tasks.requests, "post", side_effect=list(outcomes)) as post:
            try:
                tasks.post_webhook("http://server/hook", {"task_id": "t"}, delays=(1, 2))
            finally:
                self.calls = post.call_count

    def test_retries_connection_errors_then_succeeds(self):
        self.post(requests.ConnectionError("down"), response(503), response(200))
        self.assertEqual(self.calls, 3)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [1, 2])

    def test_gives_up_after_the_last_delay(self):
        with self.assertRaises(requests.ConnectionError):
            self.post(*[requests.ConnectionError("down")] * 3)
        self.assertEqual(self.calls, 3)

    def test_client_errors_are_not_retried(self):
        with self.assertRaises(requests.HTTPError):
            self.post(response(422))
        self.assertEqual(self.calls, 1)
        self.sleep.assert_not_called()

    def test_job_not_found_yet_is_retried(self):
        # The server stores the task id just after enqueueing; a fast outcome can beat it.
        self.post(response(404), response(200))
        self.assertEqual(self.calls, 2)

    def test_rate_limit_is_retried(self):
        self.post(response(429), response(200))
        self.assertEqual(self.calls, 2)

    def test_failure_webhook_swallows_final_error(self):
        with mock.patch.object(
            tasks.requests, "post", side_effect=requests.ConnectionError("down")
        ) as post:
            tasks.send_failure_webhook("http://server/hook", "t", error="boom")
        self.assertEqual(post.call_count, len(tasks.WEBHOOK_RETRY_DELAYS) + 1)


if __name__ == "__main__":
    unittest.main()
