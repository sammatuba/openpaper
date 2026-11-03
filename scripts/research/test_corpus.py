import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import request
import corpus


class FakeApi:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []
    def json(self, method, path, value=None):
        self.calls.append((method, path, value))
        return next(self.results)


class CorpusTests(unittest.TestCase):
    def test_identities(self):
        ids = corpus.identities("https://arxiv.org/pdf/2306.12001v6.pdf https://doi.org/10.1234/FOO")
        self.assertIn("arxiv:2306.12001", ids)
        self.assertIn("doi:10.1234/foo", ids)
        self.assertEqual(corpus.identities("https://arxiv.org/abs/2306.12001v1"), ["arxiv:2306.12001"])

    def test_frontmatter_excludes_code_and_preserves_arxiv_version(self):
        text = '---\nid: "T1"\narxiv: "2306.12001v6"\nurls:\n  paper: "https://arxiv.org/abs/2306.12001"\n  code: "https://github.com/example/repo"\nextraction:\n  sources_used: ["https://example.org/unrelated"]\n---\n'
        keys, versions = corpus.dossier_identity(corpus.frontmatter(text))
        self.assertEqual(keys, ["arxiv:2306.12001"])
        self.assertEqual(versions, ["v6"])

    def test_origin_and_redirect_reject_cookie_forwarding(self):
        for origin in ("http://site.test", "https://user@site.test", "https://site.test/a", "https://site.test?x=1", "https://site.test#frag", "https://site.test:bad"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                corpus.validate_origin(origin)
        req = request.Request("https://site.test/api", headers={"Cookie": "session_token=secret"})
        self.assertIsNone(corpus.NoRedirect().redirect_request(req, None, 302, "Found", {}, "https://attacker.test/"))

    def test_bridge_exports_only_completed_verified_ids(self):
        m = {"entries": [{"id": "T1", "kind": "dossier", "status": "completed", "paper_id": "a12c296b-36e4-4a2c-a8a1-6bdbf572876d", "source_ids": ["src-1"]}, {"id": "T2", "status": "submitted", "paper_id": None}]}
        rows = corpus.bridge(m, "https://papers.test")["entries"]
        self.assertEqual(rows[0]["source_ids"], ["src-1"])
        self.assertEqual(rows[0]["paper_url"], "https://papers.test/paper/a12c296b-36e4-4a2c-a8a1-6bdbf572876d")
        self.assertEqual(len(rows), 1)

    def test_note_response_loss_is_uncertain_and_never_retried(self):
        e = {"id": "T1", "kind": "dossier", "identities": [], "status": "completed", "paper_id": "paper", "project_id": None, "tag_ids": [], "note_status": "pending", "path": "dossier.md", "sha256": corpus.digest(b"text")}
        m = {"entries": [e]}
        api = FakeApi([(404, None), TimeoutError()])
        original_json = api.json
        def call(*args, **kwargs):
            value = original_json(*args, **kwargs)
            if isinstance(value, Exception): raise value
            return value
        api.json = call
        with tempfile.TemporaryDirectory() as d:
            Path(d, "dossier.md").write_text("text")
            p = Path(d, "state.json")
            with self.assertRaises(TimeoutError): corpus.step(m, e, api, p, Path(d))
            corpus.step(m, e, api, p, Path(d))
            self.assertEqual(e["note_status"], "uncertain")
            self.assertEqual(len(api.calls), 2)

    def test_resume_never_reuploads_or_overwrites_note(self):
        e = {"id": "T1", "kind": "dossier", "identities": [], "status": "submitted", "job_id": "job", "paper_id": None, "project_id": None, "tag_ids": [], "note_status": "pending"}
        m = {"entries": [e]}
        api = FakeApi([(200, {"status": "completed", "paper_id": "paper"}), (200, {"content": "mine"})])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "state.json"
            with patch.object(corpus, "upload", side_effect=AssertionError("must not upload")):
                corpus.step(m, e, api, p)
                corpus.step(m, e, api, p)
            self.assertEqual(e["note_status"], "existing_preserved")
            self.assertTrue(all(call[0] == "GET" for call in api.calls))

    def test_uncertain_upload_never_retries(self):
        e = {"id": "T1", "kind": "dossier", "identities": [], "status": "ready", "local_pdf": None, "upload_url": "https://example.org/x.pdf"}
        m = {"entries": [e]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "state.json"
            with patch.object(corpus, "upload", side_effect=TimeoutError) as call:
                with self.assertRaises(TimeoutError): corpus.step(m, e, None, p)
                corpus.step(m, e, None, p)
                self.assertEqual(call.call_count, 1)
                self.assertEqual(e["status"], "uncertain")

    def test_duplicate_identity_blocks_submission(self):
        e = {"id": "T1", "status": "ready", "identities": ["doi:10.1/a"], "upload_url": "https://a.test/a.pdf"}
        m = {"entries": [e, {"id": "T2", "identities": ["doi:10.1/a"], "paper_id": "p"}]}
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): corpus.step(m, e, None, Path(d) / "m.json")


if __name__ == "__main__": unittest.main()
