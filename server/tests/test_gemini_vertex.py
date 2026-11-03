"""GOOGLE_GENAI_USE_VERTEXAI switches the server's Gemini provider to Vertex AI."""

import os
import unittest
from unittest import mock

from app.llm.base import LLMProvider, _provider_configured
from app.llm.provider import GeminiProvider

VERTEX_ENV = {
    "GOOGLE_GENAI_USE_VERTEXAI": "true",
    "GOOGLE_CLOUD_PROJECT": "proj",
    "GOOGLE_CLOUD_LOCATION": "global",
}


class GeminiVertex(unittest.TestCase):
    def test_vertex_needs_no_api_key(self):
        env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"} | VERTEX_ENV
        with mock.patch.dict(os.environ, env, clear=True):
            provider = GeminiProvider()
            self.assertTrue(_provider_configured(LLMProvider.GEMINI))
        api = provider.client._api_client
        self.assertTrue(api.vertexai)
        self.assertEqual((api.project, api.location), ("proj", "global"))

    def test_api_key_by_default(self):
        with mock.patch.dict(os.environ, {"GOOGLE_GENAI_USE_VERTEXAI": "", "GEMINI_API_KEY": "k"}):
            self.assertFalse(GeminiProvider().client._api_client.vertexai)

    def test_missing_key_without_vertex_is_an_error(self):
        env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
        env["GOOGLE_GENAI_USE_VERTEXAI"] = ""
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError):
                GeminiProvider()
            self.assertFalse(_provider_configured(LLMProvider.GEMINI))


if __name__ == "__main__":
    unittest.main()
