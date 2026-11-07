"""Publisher normalization, pinned connections and hard resource bounds."""
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import MagicMock, patch
from app.mcp import research_url as urls

class TestResearchURLNormalization(unittest.TestCase):
    def test_arxiv_aliases_use_extensionless_pdf_without_redirect(self):
        expected = ("arxiv:2502.14143", "https://arxiv.org/pdf/2502.14143")
        for url in ("https://arxiv.org/abs/2502.14143", "https://arxiv.org/pdf/2502.14143.pdf", "https://export.arxiv.org/pdf/2502.14143"):
            self.assertEqual(urls.normalize_research_pdf_url(url), expected)

    def test_openreview_aliases(self):
        self.assertEqual(urls.normalize_research_pdf_url("https://openreview.net/forum?id=GCkhEPE1FG"), urls.normalize_research_pdf_url("https://openreview.net/pdf?id=GCkhEPE1FG"))

    def test_reject_unsafe_or_landing_urls(self):
        for url in ("http://arxiv.org/pdf/2502.14143", "https://127.0.0.1/file.pdf", "https://arxiv.org.evil.test/file.pdf", "https://arxiv.org:8443/pdf/2502.14143", "https://user@arxiv.org/pdf/2502.14143", "https://arxiv.org/pdf/2502.14143#x", "https://www.nature.com/articles/example", "https://arxiv.org/pdf/2502.14143\n", "https://openreview.net/pdf?id=abcd&id=efgh", "https://aclanthology.org/" + "a"*600 + ".pdf"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                urls.normalize_research_pdf_url(url)

class TestResearchPDFNetwork(unittest.TestCase):
    def download(self, response):
        pool = MagicMock()
        pool.request.return_value = response
        with patch.object(urls, "_require_public_dns", return_value="8.8.8.8"), patch.object(urls.urllib3, "HTTPSConnectionPool", return_value=pool) as factory:
            data = urls._download_research_pdf("https://arxiv.org/pdf/2502.14143")
        return data, pool, factory

    def response(self, status=200):
        response = MagicMock(status=status, headers={})
        response.stream.return_value = [b"%PDF-1.7 fake"]
        return response

    def test_pins_vetted_address_and_preserves_tls_hostname(self):
        data, pool, factory = self.download(self.response())
        self.assertEqual(data, b"%PDF-1.7 fake")
        self.assertEqual(factory.call_args.args[0], "8.8.8.8")
        self.assertEqual(factory.call_args.kwargs["assert_hostname"], "arxiv.org")
        self.assertEqual(factory.call_args.kwargs["server_hostname"], "arxiv.org")
        self.assertFalse(pool.request.call_args.kwargs["redirect"])
        self.assertEqual(pool.request.call_args.kwargs["headers"]["Host"], "arxiv.org")
        pool.close.assert_called_once()

    def test_redirect_and_size_rejected_and_closed(self):
        for status, headers, chunks in ((302, {"Location":"http://127.0.0.1"}, []), (200, {"Content-Length":"999999999"}, []), (200, {}, [b"x"*31*1024*1024])):
            response = self.response(status)
            response.headers, response.stream.return_value = headers, chunks
            with self.assertRaises(ValueError):
                self.download(response)
            response.close.assert_called_once()

    def test_private_or_mixed_dns_rejected(self):
        for addresses in (("10.0.0.1",), ("8.8.8.8", "127.0.0.1")):
            records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip,443)) for ip in addresses]
            with patch.object(urls.socket, "getaddrinfo", return_value=records), self.assertRaises(ValueError):
                urls._require_public_dns("arxiv.org")

    def test_child_deadline_kills_and_reaps_real_stalled_process(self):
        run = subprocess.run
        def stalled(*args, **kwargs):
            return run([sys.executable,"-c","import time; time.sleep(30)"], **kwargs)
        start = time.monotonic()
        with patch.object(urls.subprocess,"run",side_effect=stalled), self.assertRaisesRegex(ValueError,"deadline"):
            urls._fetch_validated_pdf("https://arxiv.org/pdf/2502.14143", timeout=0.1)
        self.assertLess(time.monotonic()-start, 3)

    def test_worker_failure_never_exposes_diagnostics(self):
        with patch.object(urls.subprocess,"run",return_value=subprocess.CompletedProcess([],0,b"0secret-url")), self.assertRaisesRegex(ValueError,"validation failed"):
            urls._fetch_validated_pdf("https://arxiv.org/pdf/2502.14143")
