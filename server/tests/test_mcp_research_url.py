"""Focused regression tests for publisher URL controls and bounded PDF retrieval."""
import socket
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.mcp.research_url import (
    fetch_research_pdf,
    normalize_research_pdf_url,
)


class TestResearchURLNormalization(unittest.TestCase):
    def test_arxiv_abstract_and_pdf_are_same_source(self):
        a = normalize_research_pdf_url("https://arxiv.org/abs/2502.14143")
        b = normalize_research_pdf_url("https://arxiv.org/pdf/2502.14143.pdf")
        self.assertEqual(a, b)
        self.assertEqual(a[0], "arxiv:2502.14143")

    def test_openreview_forum_and_pdf_are_same_source(self):
        a = normalize_research_pdf_url("https://openreview.net/forum?id=GCkhEPE1FG")
        b = normalize_research_pdf_url("https://openreview.net/pdf?id=GCkhEPE1FG")
        self.assertEqual(a, b)
        self.assertEqual(a[1], "https://openreview.net/pdf?id=GCkhEPE1FG")

    def test_landing_pages_require_an_actual_pdf(self):
        with self.assertRaisesRegex(ValueError, "not a PDF"):
            normalize_research_pdf_url("https://www.nature.com/articles/s41562-025-02172-y")

    def test_private_network_and_unapproved_hosts_are_rejected(self):
        for url in (
            "http://arxiv.org/pdf/2502.14143",
            "https://127.0.0.1/file.pdf",
            "https://arxiv.org.evil.test/pdf/file.pdf",
            "https://arxiv.org:8443/pdf/2502.14143",
            "https://user@arxiv.org/pdf/2502.14143",
            "https://arxiv.org/pdf/2502.14143#x",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize_research_pdf_url(url)


class TestResearchPDFNetwork(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def make_response(data=b"%PDF-1.7 fake"):
        response = MagicMock()
        response.status_code = 200
        response.iter_content.return_value = [data]
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        return response

    async def test_fetch_uses_no_redirects_and_checks_pdf(self):
        response = self.make_response()
        with patch("app.mcp.research_url._require_public_dns"), \
             patch("app.mcp.research_url.requests.get", return_value=response) as get, \
             patch("app.mcp.research_url.validate_pdf_content", new_callable=AsyncMock, return_value=(True, "")):
            data = await fetch_research_pdf("https://arxiv.org/pdf/2502.14143.pdf")
        self.assertEqual(data, b"%PDF-1.7 fake")
        self.assertFalse(get.call_args.kwargs["allow_redirects"])

    async def test_cross_host_redirect_is_never_followed(self):
        response = self.make_response()
        response.status_code = 302
        response.headers = {"Location": "http://127.0.0.1/admin"}
        with patch("app.mcp.research_url._require_public_dns"), \
             patch("app.mcp.research_url.requests.get", return_value=response):
            with self.assertRaisesRegex(ValueError, "redirect rejected"):
                await fetch_research_pdf("https://arxiv.org/pdf/2502.14143.pdf")

    def test_private_resolved_dns_rejected(self):
        fake_records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443))]
        with patch("app.mcp.research_url.socket.getaddrinfo", return_value=fake_records):
            from app.mcp.research_url import _require_public_dns
            with self.assertRaisesRegex(ValueError, "non-public"):
                _require_public_dns("arxiv.org")


if __name__ == "__main__":
    unittest.main()
