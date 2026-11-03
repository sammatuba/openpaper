"""GOOGLE_GENAI_USE_VERTEXAI switches the Gemini client from an API key to Vertex AI."""

import os
import unittest
from unittest import mock

os.environ.setdefault("TASK_BACKEND", "cloudtasks")
os.environ.setdefault("GOOGLE_API_KEY", "test-key")

from src import llm_client  # noqa: E402

VERTEX_ENV = {
    "GOOGLE_GENAI_USE_VERTEXAI": "true",
    "GOOGLE_CLOUD_PROJECT": "proj",
    "GOOGLE_CLOUD_LOCATION": "global",
}


class GeminiVertex(unittest.TestCase):
    def test_vertex_client_needs_no_api_key(self):
        with mock.patch.dict(os.environ, VERTEX_ENV):
            client = llm_client.PaperOperations(api_key=None)._create_client()
        api = client._api_client
        self.assertTrue(api.vertexai)
        self.assertEqual((api.project, api.location), ("proj", "global"))

    def test_api_key_client_by_default(self):
        with mock.patch.dict(os.environ, {"GOOGLE_GENAI_USE_VERTEXAI": ""}):
            client = llm_client.PaperOperations(api_key="k")._create_client()
        self.assertFalse(client._api_client.vertexai)

    def test_missing_key_without_vertex_is_an_error(self):
        with mock.patch.dict(os.environ, {"GOOGLE_GENAI_USE_VERTEXAI": ""}):
            with self.assertRaises(ValueError):
                llm_client.PaperOperations(api_key=None)._create_client()


if __name__ == "__main__":
    unittest.main()
