"""Offline tests: actual packaging plus a stateful simulated GitHub service."""
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch
import urllib.parse
import urllib.error
import zipfile

spec = importlib.util.spec_from_file_location('datmm_release', Path(__file__).resolve().parents[1] / 'scripts/datmm_release.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
TOKEN = 'test-credential-that-is-not-a-real-GitHub-token'


class FakeGitHub:
    def __init__(self):
        self.head = 'a' * 40
        self.tag = None
        self.release = None
        self.assets = {}
        self.writes = []
        self.private = False
        self.interrupt_upload = False
        self.bad_digest = False
        self.concurrent = False
        self.head_reads = 0

    def user(self):
        return {'login': 'example', 'id': 123}

    def call(self, method, path, payload=None, missing_ok=False, binary=None, upload=False):
        if method != 'GET':
            self.writes.append((method, path, payload))
        if method == 'GET' and path == '':
            return {'private': self.private, 'archived': False}
        if method == 'GET' and path.startswith('/git/ref/heads/'):
            self.head_reads += 1
            if self.concurrent and self.head_reads == 2:
                self.head = 'c' * 40
            return {'object': {'sha': self.head}}
        if method == 'GET' and path.startswith('/git/ref/tags/'):
            return {'object': {'sha': self.tag}} if self.tag else None
        if method == 'GET' and path.startswith('/releases/tags/'):
            return dict(self.release) if self.release else None
        if method == 'GET' and path.startswith('/git/commits/'):
            return {'tree': {'sha': 'd' * 40}}
        if method == 'POST' and path == '/git/blobs':
            data = base64.b64decode(payload['content'])
            return {'sha': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()}
        if method == 'POST' and path == '/git/trees':
            assert payload['base_tree'] == 'd' * 40
            return {'sha': 'e' * 40}
        if method == 'POST' and path == '/git/commits':
            assert payload['parents'] == ['a' * 40]
            return {'sha': 'b' * 40}
        if method == 'PATCH' and path.startswith('/git/refs/heads/'):
            assert payload['force'] is False
            self.head = payload['sha']
            return {'object': {'sha': self.head}}
        if method == 'POST' and path == '/git/refs':
            assert self.tag is None
            self.tag = payload['sha']
            return {'object': {'sha': self.tag}}
        if method == 'POST' and path == '/releases':
            assert payload['draft'] is True
            self.release = dict(payload, id=7, html_url='https://github.com/example/datmm/releases/tag/v0.1.0')
            return dict(self.release)
        if method == 'GET' and path.startswith('/releases/7/assets'):
            return list(self.assets.values())
        if method == 'POST' and path.startswith('/releases/7/assets'):
            assert upload and self.release['draft']
            name = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)['name'][0]
            item = {'name': name, 'state': 'uploaded', 'size': len(binary), 'digest': 'sha256:' + r.digest(binary)}
            if self.bad_digest:
                item['digest'] = 'sha256:wrong'
            self.assets[name] = item
            if self.interrupt_upload:
                self.interrupt_upload = False
                raise RuntimeError('Simulated lost response after upload completed')
            return item
        if method == 'PATCH' and path == '/releases/7':
            assert len(self.assets) == 4
            self.release.update(payload)
            return dict(self.release)
        raise AssertionError((method, path))


class FakeGitTransport:
    def __init__(self, api):
        self.api = api

    def create_commit(self, files, parent, version, user):
        assert parent == self.api.head and files['docs/index.html']
        assert user['login'] == 'example'
        return 'b' * 40

    def push_commit(self, commit, branch):
        self.api.head = commit
        self.api.writes.append(('GIT_PUSH', branch, {'sha': commit, 'force': False}))


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)
        for name in r.BASE_FILES:
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('test fixture\n')
        p = self.root / r.NOTEBOOK
        p.parent.mkdir(parents=True, exist_ok=True)
        self.nb = {'nbformat': 4, 'nbformat_minor': 5, 'metadata': {'widgets': {'private': True}}, 'cells': [
            {'cell_type': 'code', 'id': 'datmm-github-publish', 'metadata': {'private': True},
             'source': ['ACTION = "publish"\n'], 'execution_count': 12,
             'outputs': [{'output_type': 'stream', 'name': 'stdout', 'text': ['private output']}]}]}
        p.write_text(json.dumps(self.nb))
        (self.root / 'docs/index.html').write_text('<!DOCTYPE html><html>fixture</html>')

    def prepare(self, **kwargs):
        return r.prepare(self.root, 'v0.1.0', **kwargs)

    def publish(self, build, api, **kwargs):
        return r.publish(build, 'example/datmm', TOKEN, confirmation='example/datmm@v0.1.0', client=api, transport=FakeGitTransport(api), **kwargs)

    def test_prepare_strips_outputs_and_resets_action(self):
        with patch.object(r.urllib.request, 'build_opener', side_effect=AssertionError('No network allowed')):
            build = self.prepare()
        nb = json.loads((build / 'package' / r.NOTEBOOK).read_text())
        self.assertEqual(nb['cells'][0]['outputs'], [])
        self.assertIsNone(nb['cells'][0]['execution_count'])
        self.assertEqual(nb['metadata'], {})
        self.assertIn('ACTION = "off"', ''.join(nb['cells'][0]['source']))

    def test_repeat_prepare_is_byte_identical(self):
        build = self.prepare()
        first = (build / 'datmm-v0.1.0.zip').read_bytes()
        self.prepare()
        self.assertEqual(first, (build / 'datmm-v0.1.0.zip').read_bytes())

    def test_changed_version_reuse_is_rejected(self):
        self.prepare()
        (self.root / 'docs/index.html').write_text('<!DOCTYPE html>changed')
        with self.assertRaisesRegex(ValueError, 'already frozen'):
            self.prepare()

    def test_only_explicit_extra_files_included(self):
        (self.root / '.env').write_text('private=1')
        extra = self.root / 'checks.csv'
        extra.write_text('name,status\nfixture,PASS\n')
        build = self.prepare(extra_files={'exports/checks.csv': extra})
        manifest, files, archive = r.verify(build)
        self.assertNotIn('.env', files)
        self.assertIn('exports/checks.csv', files)
        with zipfile.ZipFile(archive) as z:
            self.assertNotIn('datmm-v0.1.0/.env', z.namelist())

    def test_missing_extra_is_not_invented(self):
        with self.assertRaises(FileNotFoundError):
            self.prepare(extra_files={'exports/graph.json': self.root / 'missing.json'})

    def test_unsafe_extra_path_rejected(self):
        with self.assertRaises(ValueError):
            self.prepare(extra_files={'exports/../../secret.txt': self.root / 'README.md'})

    def test_source_credential_rejected(self):
        (self.root / 'README.md').write_text('ghp_' + 'x' * 36)
        with self.assertRaisesRegex(ValueError, 'credential'):
            self.prepare()

    def test_symlink_source_rejected(self):
        target = self.root / 'docs/linked.html'
        target.symlink_to(self.root / 'docs/index.html')
        with self.assertRaisesRegex(ValueError, 'Symlinks'):
            self.prepare(browser_path=target)

    def test_tampered_stage_rejected(self):
        build = self.prepare()
        (build / 'package/README.md').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'Frozen file changed'):
            r.verify(build)

    def test_tampered_archive_rejected(self):
        build = self.prepare()
        with zipfile.ZipFile(build / 'datmm-v0.1.0.zip', 'a') as z:
            z.writestr('unexpected.txt', 'injected')
        with self.assertRaisesRegex(ValueError, 'Archive inventory'):
            r.verify(build)

    def test_publish_tags_exact_commit_and_verifies_assets(self):
        build, api = self.prepare(), FakeGitHub()
        result = self.publish(build, api)
        self.assertEqual(result['commit'], api.head)
        self.assertEqual(api.tag, result['commit'])
        self.assertFalse(api.release['draft'])
        self.assertEqual(len(api.assets), 4)
        self.assertNotIn(TOKEN, (build / 'publish-state.json').read_text())
        self.assertNotIn(TOKEN, self.output.getvalue())

    def test_publish_requires_explicit_confirmation(self):
        build, api = self.prepare(), FakeGitHub()
        with self.assertRaisesRegex(ValueError, 'confirmation'):
            r.publish(build, 'example/datmm', TOKEN, client=api)
        self.assertFalse(api.writes)

    def test_private_repository_rejected(self):
        build, api = self.prepare(), FakeGitHub()
        api.private = True
        with self.assertRaisesRegex(ValueError, 'public'):
            self.publish(build, api)
        self.assertFalse(api.writes)

    def test_existing_tag_without_receipt_rejected(self):
        build, api = self.prepare(), FakeGitHub()
        api.tag = 'f' * 40
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.publish(build, api)
        self.assertFalse(api.writes)

    def test_concurrent_branch_update_is_not_overwritten(self):
        build, api = self.prepare(), FakeGitHub()
        api.concurrent = True
        with self.assertRaisesRegex(ValueError, 'advanced concurrently'):
            self.publish(build, api)
        self.assertEqual(api.head, 'c' * 40)
        self.assertFalse(any(method == 'PATCH' for method, _, _ in api.writes))

    def test_resume_after_lost_upload_response(self):
        build, api = self.prepare(), FakeGitHub()
        api.interrupt_upload = True
        with self.assertRaisesRegex(RuntimeError, 'lost response'):
            self.publish(build, api)
        self.assertTrue(api.release['draft'])
        self.publish(build, api)
        self.assertFalse(api.release['draft'])
        self.assertEqual(sum(m == 'POST' and p.startswith('/releases/7/assets') for m, p, _ in api.writes), 4)

    def test_completed_publish_retry_has_no_writes(self):
        build, api = self.prepare(), FakeGitHub()
        self.publish(build, api)
        api.writes.clear()
        self.publish(build, api)
        self.assertEqual(api.writes, [])

    def test_asset_digest_mismatch_keeps_draft(self):
        build, api = self.prepare(), FakeGitHub()
        api.bad_digest = True
        with self.assertRaisesRegex(ValueError, 'could not be verified'):
            self.publish(build, api)
        self.assertTrue(api.release['draft'])

    def test_real_api_client_accepts_repository_root(self):
        api = r.GitHub(TOKEN, 'example/datmm')
        response = io.BytesIO(b'{"private": false}')
        with patch.object(api.opener, 'open', return_value=response) as mocked:
            self.assertFalse(api.call('GET', '')['private'])
            req = mocked.call_args.args[0]
            self.assertEqual(req.full_url, 'https://api.github.com/repos/example/datmm')
            self.assertNotIn(TOKEN, req.full_url)
            self.assertIn(TOKEN, req.get_header('Authorization'))

    def test_error_message_retained_and_secret_redacted(self):
        api = r.GitHub(TOKEN, 'example/datmm')
        error = urllib.error.HTTPError('https://api.github.com', 422, 'Invalid',
            {'X-GitHub-Request-Id': 'test-id'}, io.BytesIO(json.dumps({'message': 'Blob too large ' + TOKEN}).encode()))
        with patch.object(api.opener, 'open', side_effect=error):
            with self.assertRaises(RuntimeError) as caught:
                api.call('POST', '/git/blobs', {})
        self.assertIn('Blob too large', str(caught.exception))
        self.assertIn('test-id', str(caught.exception))
        self.assertNotIn(TOKEN, str(caught.exception))

    def test_publish_makes_no_blob_api_calls(self):
        build, api = self.prepare(), FakeGitHub()
        self.publish(build, api)
        self.assertFalse(any(path == '/git/blobs' for _, path, _ in api.writes))
        self.assertTrue(any(method == 'GIT_PUSH' for method, _, _ in api.writes))

    def test_resume_after_lost_push_response(self):
        build, api = self.prepare(), FakeGitHub()
        transport = FakeGitTransport(api)
        push = transport.push_commit
        def lost(commit, branch):
            push(commit, branch)
            raise RuntimeError('lost push response')
        transport.push_commit = lost
        with self.assertRaisesRegex(RuntimeError, 'lost push response'):
            r.publish(build, 'example/datmm', TOKEN, confirmation='example/datmm@v0.1.0', client=api, transport=transport)
        self.publish(build, api)
        self.assertFalse(api.release['draft'])
        self.assertEqual(sum(method == 'GIT_PUSH' for method, _, _ in api.writes), 1)


class RealGitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / 'remote.git'
        self.work = self.root / 'seed'
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.git('init', '--bare', str(self.remote))
        self.git('init', str(self.work))
        self.git('-C', str(self.work), 'config', 'user.name', 'Fixture')
        self.git('-C', str(self.work), 'config', 'user.email', 'fixture@example.invalid')
        (self.work / 'unrelated.txt').write_text('preserve this\n')
        self.git('-C', str(self.work), 'add', 'unrelated.txt')
        self.git('-C', str(self.work), 'commit', '-m', 'initial fixture')
        self.parent = self.git('-C', str(self.work), 'rev-parse', 'HEAD').decode().strip()
        self.git('-C', str(self.work), 'push', str(self.remote), 'HEAD:refs/heads/main')
        self.build = self.root / 'build'
        self.build.mkdir()

    def git(self, *args):
        p = subprocess.run(['git', *args], capture_output=True, timeout=90)
        if p.returncode:
            raise AssertionError(p.stderr.decode())
        return p.stdout

    def test_native_transport_preserves_large_file_and_other_files(self):
        # Larger than the failed supplied HTML; test actual Git transport, not a mock.
        data = b'<!DOCTYPE html>\n' + (b'0123456789abcdef' * 3_000_000)
        files = {'docs/index.html': data, 'binary.dat': b'\x00\xff\r\n'}
        transport = r.GitTransport(self.build, 'example/datmm', '', local_remote=self.remote)
        commit = transport.create_commit(files, self.parent, 'v0.1.1', {'login': 'example', 'id': 123})
        transport.push_commit(commit, 'main')
        self.assertEqual(self.git('--git-dir=' + str(self.remote), 'rev-parse', 'refs/heads/main').decode().strip(), commit)
        for name, content in files.items():
            self.assertEqual(self.git('--git-dir=' + str(self.remote), 'show', f'{commit}:{name}'), content)
        self.assertEqual(self.git('--git-dir=' + str(self.remote), 'show', f'{commit}:unrelated.txt'), b'preserve this\n')

    def test_native_transport_refuses_concurrent_change(self):
        transport = r.GitTransport(self.build, 'example/datmm', '', local_remote=self.remote)
        commit = transport.create_commit({'new.txt': b'new'}, self.parent, 'v0.1.1', {'login': 'example', 'id': 123})
        (self.work / 'unrelated.txt').write_text('concurrent change\n')
        self.git('-C', str(self.work), 'commit', '-am', 'concurrent fixture')
        self.git('-C', str(self.work), 'push', str(self.remote), 'HEAD:refs/heads/main')
        with self.assertRaisesRegex(RuntimeError, 'Git operation failed'):
            transport.push_commit(commit, 'main')
        self.assertNotEqual(self.git('--git-dir=' + str(self.remote), 'rev-parse', 'refs/heads/main').decode().strip(), commit)

    def test_askpass_file_contains_no_secret_and_is_removed(self):
        transport = r.GitTransport(self.build, 'example/datmm', TOKEN)
        with transport._auth() as env:
            helper = Path(env['GIT_ASKPASS'])
            self.assertNotIn(TOKEN, helper.read_text())
            self.assertEqual(env['DATMM_GIT_TOKEN'], TOKEN)
            self.assertEqual(helper.stat().st_mode & 0o777, 0o700)
        self.assertFalse(helper.exists())

    def test_local_test_transport_rejects_credentials(self):
        with self.assertRaises(ValueError):
            r.GitTransport(self.build, 'example/datmm', TOKEN, local_remote=self.remote)


if __name__ == '__main__':
    unittest.main()
