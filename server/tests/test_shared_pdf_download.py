"""Browser and MCP imports share one policy and keep untrusted URLs private."""

import asyncio
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from app.helpers import pdf_download
from app.helpers.parser import validate_url_and_fetch_pdf


class SharedPDFDownloadTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def pdf_fixture():
        return (Path(__file__).resolve().parents[1] / "evals" / "seed_data" /
                "refusal-in-language-models-is-mediated-by-a-single-direction-Paper-Conference.pdf").read_bytes()

    async def test_both_entry_paths_use_common_isolated_worker_and_real_pdf_validation(self):
        from app.mcp.uploads import download_pdf as mcp_download

        pdf = self.pdf_fixture()
        signed_url = "https://papers.test/paper.pdf?token=secret"
        result = subprocess.CompletedProcess([], 0, stdout=b"1" + pdf)
        with patch("app.helpers.pdf_download.subprocess.run", return_value=result) as run:
            self.assertEqual(await validate_url_and_fetch_pdf(signed_url), (True, pdf, ""))
            self.assertEqual(mcp_download(signed_url), pdf)
        self.assertEqual(run.call_count, 2)
        for call in run.call_args_list:
            self.assertEqual(call.args[0], [sys.executable, "-m", "app.helpers.pdf_download"])
            self.assertEqual(call.kwargs["input"], signed_url.encode())
            self.assertEqual(call.kwargs["timeout"], 60)
            self.assertEqual(call.kwargs["stderr"], subprocess.DEVNULL)
            self.assertNotIn(signed_url, call.args[0])

    async def test_browser_rejects_downloaded_non_pdf_with_actual_validator(self):
        result = subprocess.CompletedProcess([], 0, stdout=b"1" + b"not a PDF" * 200)
        with patch("app.helpers.pdf_download.subprocess.run", return_value=result):
            valid, data, error = await validate_url_and_fetch_pdf("https://papers.test/a")
        self.assertFalse(valid)
        self.assertEqual(data, b"")
        self.assertIn("valid PDF", error)

    async def test_private_redirect_is_blocked_through_both_entry_paths(self):
        from app.mcp.uploads import download_pdf as mcp_download

        def execute_worker(_args, **kwargs):
            # Run the real network-policy function in-process with mocked DNS
            # and transport, retaining the production worker error boundary.
            try:
                data = pdf_download.download_pdf_bytes(kwargs["input"].decode())
                return subprocess.CompletedProcess([], 0, stdout=b"1" + data)
            except Exception:
                return subprocess.CompletedProcess([], 0, stdout=b"0private internals hidden")

        public = [(2, 1, 6, "", ("93.184.216.34", 443))]
        private = [(2, 1, 6, "", ("169.254.169.254", 443))]
        for entry in ("browser", "mcp"):
            with self.subTest(entry=entry):
                pool = Mock()
                pool.request.return_value = Mock(
                    status=302, headers={"Location": "https://metadata.test/?secret=hidden"})
                with (
                    patch("app.helpers.pdf_download.socket.getaddrinfo", side_effect=[public, private]),
                    patch("app.helpers.pdf_download.urllib3.HTTPSConnectionPool", return_value=pool),
                    patch("app.helpers.pdf_download.subprocess.run", side_effect=execute_worker),
                ):
                    if entry == "browser":
                        self.assertEqual(await validate_url_and_fetch_pdf("https://papers.test/start"),
                                         (False, b"", pdf_download.DOWNLOAD_ERROR))
                    else:
                        with self.assertRaisesRegex(ValueError, "direct public HTTPS") as caught:
                            mcp_download("https://papers.test/start")
                        self.assertNotIn("hidden", str(caught.exception))
                self.assertEqual(pool.request.call_count, 1)

    async def test_browser_process_deadline_does_not_block_event_loop(self):
        original_run = subprocess.run
        original_download = pdf_download.download_pdf

        def slow_worker(_args, **kwargs):
            return original_run([sys.executable, "-c", "import time; time.sleep(10)"], **kwargs)

        def bounded_download(url):
            return original_download(url, timeout=0.2)

        start = time.monotonic()
        with (
            patch("app.helpers.pdf_download.subprocess.run", side_effect=slow_worker),
            patch("app.helpers.pdf_download.download_pdf", side_effect=bounded_download),
        ):
            task = asyncio.create_task(validate_url_and_fetch_pdf("https://papers.test/slow"))
            await asyncio.sleep(0.05)
            self.assertFalse(task.done(), "The event loop should run while the downloader waits")
            self.assertEqual(await task, (False, b"", pdf_download.DOWNLOAD_ERROR))
        self.assertLess(time.monotonic() - start, 2)

    async def test_worker_errors_are_sanitized_and_not_sent_to_pdf_validator(self):
        from app.mcp.uploads import download_pdf as mcp_download

        url = "https://user:secret@private.test/?token=sensitive"
        for outcome in (
            subprocess.CompletedProcess([], 0, stdout=b"0https://user:secret@private.test"),
            subprocess.CompletedProcess([], 1, stdout=b"1partial"),
            OSError("https://user:secret@private.test/?token=sensitive"),
        ):
            with self.subTest(outcome=type(outcome).__name__):
                kwargs = {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
                with (
                    patch("app.helpers.pdf_download.subprocess.run", **kwargs),
                    patch("app.helpers.parser.validate_pdf_content", new=AsyncMock()) as validate,
                ):
                    self.assertEqual(await validate_url_and_fetch_pdf(url),
                                     (False, b"", pdf_download.DOWNLOAD_ERROR))
                    with self.assertRaises(ValueError) as caught:
                        mcp_download(url)
                    self.assertNotIn("secret", str(caught.exception))
                    self.assertNotIn("sensitive", str(caught.exception))
                    validate.assert_not_called()

    async def test_parent_rechecks_byte_limit_for_both_entry_paths(self):
        from app.mcp.uploads import download_pdf as mcp_download

        result = subprocess.CompletedProcess([], 0, stdout=b"1" + b"x" * (1024 * 1024 + 1))
        with (
            patch("app.helpers.pdf_download.MAX_UPLOAD_SIZE_MB", 1),
            patch("app.helpers.pdf_download.subprocess.run", return_value=result),
        ):
            self.assertEqual(await validate_url_and_fetch_pdf("https://papers.test/a"),
                             (False, b"", pdf_download.DOWNLOAD_ERROR))
            with self.assertRaisesRegex(ValueError, "upload limit"):
                mcp_download("https://papers.test/a")


class WorkerPolicyTests(unittest.TestCase):
    def test_mixed_private_multicast_and_reserved_dns_fail_closed(self):
        public = (2, 1, 6, "", ("93.184.216.34", 443))
        for address in ("127.0.0.1", "169.254.169.254", "224.0.0.1", "ff0e::1", "240.0.0.1"):
            with (
                self.subTest(address=address),
                patch("app.helpers.pdf_download.socket.getaddrinfo",
                      return_value=[public, (2, 1, 6, "", (address, 443))]),
                patch("app.helpers.pdf_download.urllib3.HTTPSConnectionPool") as pool,
            ):
                with self.assertRaisesRegex(ValueError, "public addresses"):
                    pdf_download.download_pdf_bytes("https://papers.test/a")
                pool.assert_not_called()

    def test_redirect_to_same_host_revalidates_dns_before_another_connection(self):
        public = [(2, 1, 6, "", ("93.184.216.34", 443))]
        rebound = [(2, 1, 6, "", ("127.0.0.1", 443))]
        pool = Mock()
        pool.request.return_value = Mock(status=302, headers={"Location": "/next.pdf"})
        with (
            patch("app.helpers.pdf_download.socket.getaddrinfo", side_effect=[public, rebound]),
            patch("app.helpers.pdf_download.urllib3.HTTPSConnectionPool", return_value=pool) as factory,
        ):
            with self.assertRaisesRegex(ValueError, "public addresses"):
                pdf_download.download_pdf_bytes("https://papers.test/start")
            factory.assert_called_once()
            pool.request.assert_called_once()

    def test_url_syntax_errors_are_rejected_before_transport(self):
        for url in ("http://papers.test/a", "https://@papers.test/a", "https://papers.test:8000/a",
                    "file:///tmp/a", "https://papers.test/a\r\nX-Secret: value"):
            with self.subTest(url=url), patch("app.helpers.pdf_download.socket.getaddrinfo") as dns:
                with self.assertRaises(ValueError):
                    pdf_download.download_pdf_bytes(url)
                dns.assert_not_called()

    def test_actual_worker_rejects_invalid_url_without_exposing_it(self):
        # No DNS or HTTP: the real child rejects the scheme before resolution.
        with self.assertRaisesRegex(ValueError, "direct public HTTPS") as caught:
            pdf_download.download_pdf("http://user:secret@127.0.0.1/?token=sensitive")
        self.assertNotIn("secret", str(caught.exception))
        self.assertNotIn("sensitive", str(caught.exception))
