"""Every task /tasks/run accepts is registered once the web app is imported.

Celery's `include=["src.tasks"]` only loads at worker boot. The jobs service
under Cloud Tasks runs uvicorn alone, so without an explicit import every push
answered 404 "Task not registered" and uploads stayed pending.
"""

import os
import unittest

os.environ.setdefault("TASK_BACKEND", "cloudtasks")

from src import app as jobs_api  # noqa: E402
from src.celery_app import celery_app  # noqa: E402


class RunnableTasksRegistered(unittest.TestCase):
    def test_every_runnable_task_is_registered(self):
        missing = sorted(n for n in jobs_api.RUNNABLE_TASKS if n not in celery_app.tasks)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
