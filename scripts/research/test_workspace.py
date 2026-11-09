"""Workspace ownership, authentication, containment and bounded context behavior."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib import error
import uuid

import workspace as w

ORIGIN = 'https://papers.example.test'


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'projects/collusion').mkdir(parents=True)
        (self.root / 'README.md').write_text('# Research\n[HYPOTHESIS] An untested claim.\n')
        self.project = str(uuid.uuid4())
        self.account = str(uuid.uuid4())

    def bind(self, **kw):
        options = dict(root=self.root, project_dir='projects/collusion', project_id=self.project,
                       origin=ORIGIN, title='Collusion', records=['README.md'])
        options.update(kw)
        return w.bind(**options)

    def api(self, account=None, title='Renamed project'):
        api = Mock(origin=ORIGIN)
        api.project_identity.return_value = (account or self.account, title)
        return api

    def test_idempotence_rename_and_account_pin(self):
        first = self.bind()
        path = self.root / 'projects/collusion' / w.BINDING
        before = path.stat().st_mtime_ns
        self.assertEqual(first, self.bind(title='Local display rename'))
        self.assertEqual(path.stat().st_mtime_ns, before)
        verified = self.bind(api=self.api())
        self.assertEqual(verified['account_id'], self.account)
        self.assertEqual(verified['project_title'], 'Renamed project')
        self.assertTrue(w.doctor(self.root, 'projects/collusion', self.api())['online_access_checked'])
        wrong = self.api(str(uuid.uuid4()))
        with self.assertRaisesRegex(ValueError, 'account'):
            self.bind(api=wrong)
        with self.assertRaisesRegex(ValueError, 'account'):
            w.doctor(self.root, 'projects/collusion', wrong)
        self.assertEqual(json.loads(path.read_text()), verified)

    def test_offline_is_not_authentication_and_revocation_does_not_rewrite(self):
        self.bind()
        status = w.doctor(self.root, 'projects/collusion')
        self.assertFalse(status['online_access_checked'])
        api = self.api()
        api.project_identity.side_effect = ValueError('Access revoked')
        with self.assertRaisesRegex(ValueError, 'revoked'):
            self.bind(api=api)
        self.assertFalse(w.doctor(self.root, 'projects/collusion')['account_pinned'])

    def test_project_root_origin_and_record_conflicts_preserve_data(self):
        self.bind()
        for options in ({'project_id': str(uuid.uuid4())}, {'origin': 'https://other.test'}, {'records': []}):
            with self.assertRaisesRegex(ValueError, 'Conflicting'):
                self.bind(**options)
        (self.root / w.MARKER).unlink()
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            self.bind()
        self.assertFalse((self.root / w.MARKER).exists())
        api = self.api(); api.origin = 'https://other.test'
        with self.assertRaisesRegex(ValueError, 'origin'):
            self.bind(api=api)

    def test_traversal_symlinks_and_secrets_are_rejected(self):
        (self.root / 'shortcut').symlink_to(self.root / 'projects', target_is_directory=True)
        for directory in ('../escape', '/tmp', 'shortcut/collusion'):
            with self.assertRaises(ValueError):self.bind(project_dir=directory)
        (self.root / 'alias.md').symlink_to(self.root / 'README.md')
        (self.root / '.secret.md').write_text('secret')
        (self.root / 'sources').mkdir()
        (self.root / 'sources/raw.md').write_text('untrusted')
        for record in ('../outside.md', 'alias.md', '.secret.md', 'sources/raw.md'):
            with self.assertRaises(ValueError):self.bind(records=[record])
        (self.root / 'README.md').write_text('x' * (w.MAX_RECORD_BYTES + 1))
        with self.assertRaises(ValueError):self.bind()

    def test_tampered_metadata_and_binding_symlink_fail_closed(self):
        self.bind()
        path = self.root / 'projects/collusion' / w.BINDING
        binding = json.loads(path.read_text()); binding['token'] = 'must-not-print'
        path.write_text(json.dumps(binding))
        with self.assertRaises(ValueError):w.doctor(self.root, 'projects/collusion')
        with self.assertRaises(ValueError):self.bind()
        path.unlink();path.symlink_to(self.root/'README.md')
        with self.assertRaises(ValueError):self.bind()

    def test_brief_is_bounded_hashed_repeatable_and_preserves_author_text(self):
        before = (self.root/'README.md').read_bytes()
        (self.root/'large.md').write_text('evidence ' * 1000)
        self.bind(records=['README.md', 'large.md'])
        text = w.brief(self.root, 'projects/collusion', 1400)
        self.assertLessEqual(len(text), 1400)
        self.assertIn('Source truncated', text)
        self.assertIn('SHA-256:', text)
        self.assertEqual(text, w.brief(self.root, 'projects/collusion', 1400))
        self.assertEqual(before, (self.root/'README.md').read_bytes())
        self.assertIn('not a complete project export', text)

    def test_existing_corpus_ids_become_links_without_claiming_membership(self):
        self.bind()
        corpus = self.root/'corpus.json'
        paper = str(uuid.uuid4())
        corpus.write_text(json.dumps({'entries':[{'path':'README.md','status':'completed','paper_id':paper}]}))
        text = w.brief(self.root, 'projects/collusion', corpus_manifest=corpus)
        self.assertIn(f'{ORIGIN}/paper/{paper}', text)
        self.assertIn('membership not checked', text)
        self.assertEqual(json.loads(corpus.read_text())['entries'][0]['status'], 'completed')

    def test_online_client_auth_and_project_identity_and_sanitized_error(self):
        api = w.Api(ORIGIN, 'private-token')
        with patch.object(api, 'get', side_effect=[{'success': True, 'user': {'id':self.account}}, {'id':self.project,'title':'New'}]):
            self.assertEqual(api.project_identity(self.project), (self.account, 'New'))
        with patch.object(api, 'get', return_value={'success':False}):
            with self.assertRaisesRegex(ValueError, 'authentication'):api.project_identity(self.project)
        with patch.object(api.opener, 'open', side_effect=error.HTTPError('https://secret-url',403,'private-token',{},None)):
            with self.assertRaises(ValueError) as exc:api.get('/api/auth/me')
            self.assertNotIn('private-token', str(exc.exception))
            self.assertNotIn('secret-url', str(exc.exception))
        self.assertIsNone(w.NoRedirect().redirect_request(None,None,302,'',{},'https://other.test'))

    def test_directory_swap_after_marker_cannot_overwrite_outside_binding(self):
        with tempfile.TemporaryDirectory() as outside:
            outside = Path(outside)
            victim = outside / w.BINDING
            victim.write_text('DO NOT REPLACE')
            original = w.Workspace.write_json

            def swap_after_marker(workspace, relative, value, **kwargs):
                original(workspace, relative, value, **kwargs)
                if relative == w.MARKER:
                    (self.root / 'projects/collusion').rename(self.root / 'projects/old')
                    (self.root / 'projects/collusion').symlink_to(outside, target_is_directory=True)

            with patch.object(w.Workspace, 'write_json', new=swap_after_marker):
                with self.assertRaises((ValueError, OSError)):
                    self.bind()
            self.assertEqual(victim.read_text(), 'DO NOT REPLACE')
            self.assertFalse((self.root / 'projects/old' / w.BINDING).exists())
            self.assertEqual(list(outside.iterdir()), [victim])

    def test_input_swapped_to_symlink_before_open_is_not_read(self):
        self.bind()
        with tempfile.TemporaryDirectory() as outside:
            secret = Path(outside) / 'secret.md'
            secret.write_text('OUTSIDE PRIVATE CONTENT')
            original = os.open
            swapped = False

            def swap_input(path, flags, *args, **kwargs):
                nonlocal swapped
                if path == 'README.md' and flags == w.READ_FLAGS and not swapped:
                    swapped = True
                    (self.root / 'README.md').unlink()
                    (self.root / 'README.md').symlink_to(secret)
                return original(path, flags, *args, **kwargs)

            with patch.object(w.os, 'open', side_effect=swap_input):
                with self.assertRaises(ValueError):
                    w.brief(self.root, 'projects/collusion')
            self.assertTrue(swapped)

    def test_root_swap_during_brief_does_not_read_new_root(self):
        self.bind()
        outside = self.root / 'replacement'
        outside.mkdir()
        (outside / 'README.md').write_text('OUTSIDE PRIVATE CONTENT')
        original = w._load_binding
        old = self.root.with_name(self.root.name + '-old')

        def swap_root(workspace, project_dir):
            binding = original(workspace, project_dir)
            self.root.rename(old)
            self.root.symlink_to(old / 'replacement', target_is_directory=True)
            return binding

        try:
            with patch.object(w, '_load_binding', side_effect=swap_root):
                with self.assertRaises((ValueError, OSError)):
                    w.brief(self.root, 'projects/collusion')
        finally:
            if self.root.is_symlink():
                self.root.unlink()
                old.rename(self.root)

    def test_concurrently_created_authored_binding_is_not_replaced(self):
        original = w.Workspace.write_json
        victim = self.root / 'projects/collusion' / w.BINDING

        def create_before_binding(workspace, relative, value, **kwargs):
            if relative.endswith(w.BINDING):
                victim.write_text('UNRELATED AUTHORED RECORD')
            return original(workspace, relative, value, **kwargs)

        with patch.object(w.Workspace, 'write_json', new=create_before_binding):
            with self.assertRaises(FileExistsError):
                self.bind()
        self.assertEqual(victim.read_text(), 'UNRELATED AUTHORED RECORD')

    def test_existing_invalid_json_binding_is_not_replaced(self):
        victim = self.root / 'projects/collusion' / w.BINDING
        victim.write_text('null')
        with self.assertRaises(ValueError):
            self.bind()
        self.assertEqual(victim.read_text(), 'null')

    def test_binding_conflicts_fail_before_contacting_online_api(self):
        self.bind()
        for options in ({'project_id': str(uuid.uuid4())}, {'origin': 'https://other.test'},
                        {'records': []}):
            with self.subTest(options=options):
                api = self.api()
                api.origin = options.get('origin', ORIGIN)
                with self.assertRaisesRegex(ValueError, 'Conflicting'):
                    self.bind(api=api, **options)
                api.project_identity.assert_not_called()

    def test_record_growing_after_stat_still_has_a_hard_read_cap(self):
        path = self.root / 'README.md'
        path.write_bytes(b'x' * (w.MAX_RECORD_BYTES + 1))
        original = os.fstat

        def small_reported_size(fd):
            result = original(fd)
            values = list(result)
            values[6] = 1  # Emulate growth immediately after a small initial stat.
            return os.stat_result(values)

        with w.Workspace(self.root) as workspace, patch.object(w.os, 'fstat', side_effect=small_reported_size):
            with self.assertRaisesRegex(ValueError, 'size limit'):
                w.read_record(workspace, 'README.md')

    def test_online_marker_change_cannot_promote_a_stale_workspace_binding(self):
        self.bind()
        before = (self.root / 'projects/collusion' / w.BINDING).read_bytes()
        api = self.api()

        def change_marker(_project):
            marker = self.root / w.MARKER
            marker.write_text(json.dumps({'schema_version':1,'workspace_id':str(uuid.uuid4())}))
            return self.account, 'New title'

        api.project_identity.side_effect = change_marker
        with self.assertRaisesRegex(ValueError, 'marker changed'):
            self.bind(api=api)
        self.assertEqual((self.root / 'projects/collusion' / w.BINDING).read_bytes(), before)


if __name__ == '__main__':unittest.main()
