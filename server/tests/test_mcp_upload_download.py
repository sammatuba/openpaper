import unittest
from unittest.mock import Mock, patch

from app.mcp.pdf_download import download_pdf_bytes as download_pdf


class PDFDownloadTests(unittest.TestCase):
    def test_public_https_pinned_tls_and_relative_redirect(self):
        responses = [Mock(status=302, headers={'Location':'/paper.pdf'}), Mock(status=200, headers={})]
        responses[1].stream.return_value = [b'%PDF-fixture']
        pool = Mock()
        pool.request.side_effect = responses
        with patch('app.mcp.pdf_download.socket.getaddrinfo', return_value=[(2,1,6,'',('93.184.216.34',443))]), patch('app.mcp.pdf_download.urllib3.HTTPSConnectionPool', return_value=pool) as factory:
            self.assertEqual(download_pdf('https://papers.test/start'), b'%PDF-fixture')
            self.assertEqual(factory.call_args.args[0],'93.184.216.34')
            self.assertEqual(factory.call_args.kwargs['server_hostname'],'papers.test')
            self.assertEqual(factory.call_args.kwargs['assert_hostname'],'papers.test')
            self.assertEqual(pool.request.call_args.args[1],'/paper.pdf')
            self.assertFalse(pool.request.call_args.kwargs['redirect'])

    def test_private_destination_and_redirect_are_blocked(self):
        public=[(2,1,6,'',('93.184.216.34',443))]
        private=[(2,1,6,'',('169.254.169.254',443))]
        pool=Mock()
        pool.request.return_value=Mock(status=302,headers={'Location':'https://metadata.test/secret'})
        with patch('app.mcp.pdf_download.socket.getaddrinfo',side_effect=[public,private]), patch('app.mcp.pdf_download.urllib3.HTTPSConnectionPool',return_value=pool):
            with self.assertRaisesRegex(ValueError,'public addresses'): download_pdf('https://papers.test/start')
            self.assertEqual(pool.request.call_count,1)
        for url in ['http://papers.test/a','https://user:secret@papers.test/a','https://papers.test:8000/a','file:///tmp/a']:
            with self.assertRaises(ValueError): download_pdf(url)

    def test_non_pdf_http_size_and_stream_caps(self):
        dns=[(2,1,6,'',('93.184.216.34',443))]
        for status,headers,chunks in [(404,{},[]),(200,{'Content-Length':str(31*1024*1024)},[]),(200,{},[b'x'*(31*1024*1024)])]:
            pool=Mock();response=Mock(status=status,headers=headers);response.stream.return_value=chunks;pool.request.return_value=response
            with patch('app.mcp.pdf_download.socket.getaddrinfo',return_value=dns),patch('app.mcp.pdf_download.urllib3.HTTPSConnectionPool',return_value=pool):
                with self.assertRaises(ValueError):download_pdf('https://papers.test/a')
                response.close.assert_called_once()

    def test_hard_deadline_kills_slow_worker(self):
        import subprocess, sys, time
        from app.mcp.uploads import download_pdf as isolated_download
        run = subprocess.run
        # Exercise a real child that stalls beyond the deadline, as DNS or a
        # slow HTTP stream can. subprocess.run kills/reaps it on timeout.
        def slow_worker(_args, **kwargs):
            return run([sys.executable, '-c', 'import time; time.sleep(10)'], **kwargs)
        start = time.monotonic()
        with patch('app.mcp.uploads.DOWNLOAD_TIMEOUT',0.2),patch('subprocess.run',side_effect=slow_worker):
            with self.assertRaisesRegex(ValueError,'deadline'): isolated_download('https://papers.test/slow')
        self.assertLess(time.monotonic()-start,2)
