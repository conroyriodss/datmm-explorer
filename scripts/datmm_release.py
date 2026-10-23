"""Opt-in DATMM packaging and GitHub release publication.

No import-time I/O. prepare() is offline. publish() alone uses the GitHub API.
Python standard library plus the Git executable for repository transport.
The caller supplies a secret in memory; it is never written into a URL or file.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import getpass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

NOTEBOOK = 'notebooks/DATMM_Consolidated_Acquisition_Architecture_Explorer.ipynb'
BASE_FILES = (
    'README.md', 'RELEASE_GUIDE.md', 'CHANGELOG.md', 'VALIDATION.md', 'requirements.txt',
    'THIRD_PARTY_NOTICES.md', '.gitignore', 'docs/.nojekyll',
    'docs/plotly-LICENSE.txt',
    'provenance/supplied-files.json', 'scripts/datmm_release.py',
    'tests/test_release.py',
)
OPTIONAL_FILES = ('LICENSE', 'CITATION.cff')
VERSION_RE = re.compile(r'v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?\Z')
SECRET_RE = re.compile(rb'(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
MAX_FILE_BYTES = 95_000_000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()


def safe_path(name):
    p = PurePosixPath(name)
    if (not name or p.is_absolute() or '..' in p.parts or '\\' in name
            or str(p) != name or any(ord(c) < 32 for c in name)):
        raise ValueError('Invalid relative artifact path')
    return name


def clean_notebook(data):
    nb = json.loads(data)
    if nb.get('nbformat') != 4 or not isinstance(nb.get('cells'), list):
        raise ValueError('Expected a version 4 notebook')
    nb['metadata'] = {k: v for k, v in nb.get('metadata', {}).items()
                      if k in ('kernelspec', 'language_info')}
    for cell in nb['cells']:
        cell['metadata'] = {}
        if cell['cell_type'] == 'code':
            cell['outputs'] = []
            cell['execution_count'] = None
            # A saved publication cell must never publish as part of Run all.
            if cell.get('id') == 'datmm-github-publish':
                src = ''.join(cell['source'])
                src, count = re.subn(r'(?m)^ACTION\s*=.*$', 'ACTION = "off"  # off, prepare, publish', src)
                if count != 1:
                    raise ValueError('Cannot reset the optional publication cell')
                cell['source'] = src.splitlines(keepends=True)
    return json_bytes(nb)


def scan(name, data):
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f'{name} exceeds the publisher file-size limit')
    if SECRET_RE.search(data):
        raise ValueError(f'Possible embedded credential in {name}; remove it before packaging')


def _read(path):
    path = Path(path)
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError('Symlinks are not accepted as release inputs')
    if not path.is_file():
        raise FileNotFoundError(f'Missing release input: {path}')
    return path.read_bytes()


def prepare(project_dir, version, notebook_path=None, browser_path=None,
            extra_files=None, notes='Initial packaging of the supplied DATMM snapshot.'):
    """Freeze only the explicit inputs. Reusing a version with changed bytes is an error.

    extra_files maps public exports/<name> paths to specific existing local files.
    No directory, cache, Drive tree, or checkpoint is scanned for publication.
    """
    root = Path(project_dir).resolve()
    if not VERSION_RE.fullmatch(version):
        raise ValueError('Use a version such as v0.1.0 or v0.2.0-rc.1')
    if not notes.strip():
        raise ValueError('Provide release notes describing this version')
    files = {name: _read(root / name) for name in BASE_FILES}
    for name in OPTIONAL_FILES:
        if (root / name).exists():
            files[name] = _read(root / name)
    nb_source = _read(notebook_path or root / NOTEBOOK)
    files[NOTEBOOK] = clean_notebook(nb_source)
    files['docs/index.html'] = _read(browser_path or root / 'docs/index.html')
    if not files['docs/index.html'].lstrip().lower().startswith(b'<!doctype html'):
        raise ValueError('Browser input is not an HTML document')
    for name, source in (extra_files or {}).items():
        safe_path(name)
        if not name.startswith('exports/') or PurePosixPath(name).suffix not in ('.json', '.csv', '.tsv', '.txt'):
            raise ValueError('Extra files must be explicit JSON/CSV/TSV/TXT files under exports/')
        files[name] = _read(source)
    files['VERSION'] = (version[1:] + '\n').encode()
    files['RELEASE_NOTES.md'] = (f'# DATMM {version}\n\n{notes.strip()}\n').encode()
    manifest = {
        'schema_version': 1, 'version': version,
        'input_notebook_sha256': digest(nb_source),
        'browser_sha256': digest(files['docs/index.html']),
        'scope': 'Explicit supplied files only; no acquisition, cache completeness, or scientific validation implied.',
        'files': {name: {'sha256': digest(data), 'bytes': len(data)} for name, data in sorted(files.items())},
    }
    files['release-manifest.json'] = json_bytes(manifest)
    files['SHA256SUMS.txt'] = ''.join(f'{digest(data)}  {name}\n' for name, data in sorted(files.items())).encode()
    for name, data in files.items():
        scan(name, data)
    build = root / 'dist' / version
    stage = build / 'package'
    build.mkdir(parents=True, exist_ok=True)
    if stage.exists():
        old = {p.relative_to(stage).as_posix(): p.read_bytes() for p in stage.rglob('*') if p.is_file()}
        if old != files:
            raise ValueError(f'{version} is already frozen with different inputs. Use a new version, or explicitly remove this unpublished local build.')
    else:
        temporary = Path(tempfile.mkdtemp(prefix='stage-', dir=build))
        try:
            for name, data in files.items():
                dest = temporary / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            temporary.rename(stage)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    archive = build / f'datmm-{version}.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(f'datmm-{version}/{name}', date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    (build / (archive.name + '.sha256')).write_text(f'{digest(archive.read_bytes())}  {archive.name}\n')
    verify(build)
    print(f'Prepared {version}: {len(files)} explicit files; {archive.stat().st_size:,} ZIP bytes')
    print(f'Review: {stage}\nArchive: {archive}\nNo GitHub request was made.')
    return build


def verify(build):
    build = Path(build)
    stage = build / 'package'
    manifest = json.loads(_read(stage / 'release-manifest.json'))
    expected = set(manifest['files']) | {'release-manifest.json', 'SHA256SUMS.txt'}
    actual = {p.relative_to(stage).as_posix() for p in stage.rglob('*') if p.is_file()}
    if expected != actual:
        raise ValueError('Frozen package file inventory changed')
    files = {safe_path(name): _read(stage / name) for name in sorted(expected)}
    for name, info in manifest['files'].items():
        if digest(files[name]) != info['sha256'] or len(files[name]) != info['bytes']:
            raise ValueError(f'Frozen file changed: {name}')
    sums = ''.join(f'{digest(data)}  {name}\n' for name, data in sorted(files.items()) if name != 'SHA256SUMS.txt')
    if files['SHA256SUMS.txt'] != sums.encode():
        raise ValueError('Checksum inventory changed')
    version = manifest['version']
    if not VERSION_RE.fullmatch(version):
        raise ValueError('Invalid frozen version')
    archive = build / f'datmm-{version}.zip'
    with zipfile.ZipFile(archive) as z:
        prefix = f'datmm-{version}/'
        if set(z.namelist()) != {prefix + name for name in files} or len(z.namelist()) != len(files):
            raise ValueError('Archive inventory differs from frozen package')
        for name, data in files.items():
            if z.read(prefix + name) != data:
                raise ValueError('Archive contents differ from frozen package')
    if _read(build / (archive.name + '.sha256')).decode() != f'{digest(archive.read_bytes())}  {archive.name}\n':
        raise ValueError('Archive checksum differs')
    for name, data in files.items():
        scan(name, data)
    return manifest, files, archive


def get_token():
    token = os.environ.get('GITHUB_DATMM', '').strip()
    if not token:
        try:
            from google.colab import userdata
            token = userdata.get('GITHUB_DATMM').strip()
        except ImportError:
            pass
        except Exception:
            print('Colab secret unavailable; enter the token in the hidden prompt.')
    if not token:
        token = getpass.getpass('GITHUB_DATMM (hidden): ').strip()
    if not token:
        raise ValueError('No GitHub token supplied')
    return token


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHub:
    def __init__(self, token, repository):
        self.token, self.repository = token, repository
        self.opener = urllib.request.build_opener(_NoRedirect())

    def user(self):
        return self.call('GET', '/user', account=True)

    def call(self, method, path, payload=None, missing_ok=False, binary=None, upload=False, account=False):
        host = 'uploads.github.com' if upload else 'api.github.com'
        if (path and not path.startswith('/')) or path.startswith('//'):
            raise ValueError('Expected an API-relative path')
        if account and (method, path, upload) != ('GET', '/user', False):
            raise ValueError('Only the authenticated identity endpoint is supported')
        url = f'https://{host}{path}' if account else f'https://{host}/repos/{self.repository}{path}'
        data = binary if binary is not None else (json_bytes(payload) if payload is not None else None)
        req = urllib.request.Request(url, data=data, method=method, headers={
            'Authorization': f'Bearer {self.token}', 'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2026-03-10', 'User-Agent': 'DATMM-release-publisher',
            'Content-Type': 'application/octet-stream' if binary is not None else 'application/json',
        })
        try:
            with self.opener.open(req, timeout=180) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            if missing_ok and exc.code == 404:
                return None
            try:
                body = json.loads(exc.read(16384))
                detail = str(body.get('message', ''))
                errors = body.get('errors', [])
                if isinstance(errors, list):
                    for error in errors[:3]:
                        if isinstance(error, dict):
                            detail += ' ' + ' '.join(f'{k}={error[k]}' for k in ('resource', 'field', 'code', 'message') if k in error)
            except (ValueError, UnicodeError, AttributeError):
                detail = 'The server did not return a readable JSON error.'
            detail = detail.replace(self.token, '[REDACTED]')
            detail = SECRET_RE.sub(b'[REDACTED]', detail.encode()).decode()[:1200]
            detail = ' '.join(detail.split())
            request_id = exc.headers.get('X-GitHub-Request-Id', '') if exc.headers else ''
            raise RuntimeError(f'GitHub HTTP {exc.code} during {method} {path.split("?")[0]}: {detail} Request ID: {request_id}. No force update was attempted.') from None
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError('GitHub connection failed. Keep the local dist folder and retry the same frozen build.') from None


class GitTransport:
    """Write exact bytes to an isolated Git object database, then push normally.

    No working-tree checkout, clean filters, inherited hooks, saved credentials,
    shell interpolation, force push, or base64 JSON blob uploads are used.
    local_remote is for offline tests only and rejects a supplied credential.
    """
    def __init__(self, build, repository, token, local_remote=None):
        if shutil.which('git') is None:
            raise RuntimeError('The Git executable is required. Install Git, then retry this frozen build.')
        if local_remote is not None and token:
            raise ValueError('A local test remote must not receive a credential')
        self.gitdir = Path(build).resolve() / 'git-transport'
        self.token = token
        self.local = local_remote is not None
        self.remote = str(Path(local_remote).resolve()) if self.local else f'https://github.com/{repository}.git'
        if not (self.gitdir / 'HEAD').exists():
            self._run('init', '--bare', str(self.gitdir))

    def _run(self, *args, data=None, extra_env=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_') and k not in ('GITHUB_DATMM', 'DATMM_GIT_TOKEN')}
        env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_TERMINAL_PROMPT='0', GIT_INDEX_FILE=str(self.gitdir / 'release.index'))
        env.update(extra_env or {})
        cmd = ['git', '--git-dir=' + str(self.gitdir), '-c', 'core.hooksPath=' + os.devnull,
               '-c', 'credential.helper=', '-c', 'http.followRedirects=false',
               '-c', 'protocol.ext.allow=never', '-c', 'protocol.file.allow=' + ('always' if self.local else 'never'),
               *args]
        try:
            proc = subprocess.run(cmd, input=data, capture_output=True, env=env, timeout=300)
        except subprocess.TimeoutExpired:
            raise RuntimeError('Git timed out. Keep this build and retry; a completed push will be detected.') from None
        if proc.returncode:
            detail = proc.stderr.decode('utf-8', errors='replace')
            if self.token:
                detail = detail.replace(self.token, '[REDACTED]').replace(base64.b64encode(('x-access-token:' + self.token).encode()).decode(), '[REDACTED]')
            detail = SECRET_RE.sub(b'[REDACTED]', detail.encode()).decode()[:2000]
            raise RuntimeError('Git operation failed; no force push was attempted. ' + detail) from None
        return proc.stdout

    @contextmanager
    def _auth(self):
        if self.local:
            yield {}
            return
        with tempfile.TemporaryDirectory(prefix='datmm-git-auth-') as temporary:
            helper = Path(temporary) / 'askpass.py'
            helper.write_text('#!' + sys.executable + '\n'
                'import os, sys\n'
                'prompt = sys.argv[1].lower() if len(sys.argv) > 1 else ""\n'
                'if "username" in prompt: print("x-access-token")\n'
                'elif "password" in prompt: print(os.environ["DATMM_GIT_TOKEN"])\n'
                'else: raise SystemExit(1)\n')
            helper.chmod(0o700)
            yield {'GIT_ASKPASS': str(helper), 'DATMM_GIT_TOKEN': self.token}

    def create_commit(self, files, parent, version, user):
        if not re.fullmatch(r'[0-9a-f]{40}', parent):
            raise ValueError('Expected an exact Git commit SHA')
        login, user_id = user.get('login', ''), user.get('id')
        if not re.fullmatch(r'[A-Za-z0-9-]+', login) or not isinstance(user_id, int):
            raise ValueError('Could not establish the authenticated GitHub author identity')
        with self._auth() as auth:
            self._run('fetch', '--no-tags', '--depth=1', self.remote, parent, extra_env=auth)
        if self._run('rev-parse', 'FETCH_HEAD').decode().strip() != parent:
            raise ValueError('Fetched commit differs from the expected parent')
        self._run('read-tree', parent)
        entries = []
        for name, data in sorted(files.items()):
            safe_path(name)
            print('Staging repository file:', name)
            blob = self._run('hash-object', '-w', '--stdin', data=data).decode().strip()
            expected = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if blob != expected:
                raise ValueError('Local Git blob hash mismatch')
            entries.append(f'100644 {blob}\t{name}\0'.encode())
        self._run('update-index', '-z', '--index-info', data=b''.join(entries))
        tree = self._run('write-tree').decode().strip()
        email = f'{user_id}+{login}@users.noreply.github.com'
        identity = {'GIT_AUTHOR_NAME': login, 'GIT_AUTHOR_EMAIL': email,
                    'GIT_COMMITTER_NAME': login, 'GIT_COMMITTER_EMAIL': email}
        return self._run('commit-tree', tree, '-p', parent, '-m', f'Release DATMM {version}', extra_env=identity).decode().strip()

    def push_commit(self, commit, branch):
        with self._auth() as auth:
            self._run('push', self.remote, f'{commit}:refs/heads/{branch}', extra_env=auth)


def publish(build, repository, token, branch='main', confirmation='', prerelease=False, client=None, transport=None):
    """Commit the frozen package, tag exact commit, attach assets, then publish.

    State is retained locally to resume interrupted uploads. Existing tags/releases
    without matching local state are never overwritten. Unrelated remote files
    remain untouched; remove retired exports explicitly in a separate commit.
    """
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Set repository to OWNER/REPOSITORY')
    if not re.fullmatch(r'[A-Za-z0-9_/-]+', branch):
        raise ValueError('Use a simple branch name such as main')
    manifest, files, archive = verify(build)
    version = manifest['version']
    if confirmation != f'{repository}@{version}':
        raise ValueError('Explicit repository@version confirmation is required')
    # Scan the exact runtime token too, without logging its value.
    if not token or any(token.encode() in data for data in files.values()):
        raise ValueError('Missing credential or credential found in an artifact')
    build = Path(build)
    state_path = build / 'publish-state.json'
    identity = {'repository': repository, 'branch': branch, 'version': version,
                'manifest_sha256': digest(files['release-manifest.json']),
                'archive_sha256': digest(archive.read_bytes()), 'prerelease': bool(prerelease)}
    state = json.loads(state_path.read_text()) if state_path.exists() else dict(identity)
    if any(state.get(k) != v for k, v in identity.items()):
        raise ValueError('Local publication state belongs to a different package or destination')

    def save():
        temp = state_path.with_suffix('.tmp')
        temp.write_bytes(json_bytes(state))
        temp.replace(state_path)

    api = client or GitHub(token, repository)
    repo = api.call('GET', '')
    if repo.get('private') is not False or repo.get('archived'):
        raise ValueError('Create an initialized public, nonarchived repository first. This tool does not change visibility.')
    refpath = '/git/ref/heads/' + urllib.parse.quote(branch, safe='/')
    head = api.call('GET', refpath)['object']['sha']
    tagpath = '/git/ref/tags/' + urllib.parse.quote(version, safe='')
    tag = api.call('GET', tagpath, missing_ok=True)
    release = api.call('GET', '/releases/tags/' + version, missing_ok=True)
    if (tag or release) and not state.get('commit'):
        raise ValueError('This tag/release already exists. Use a new version; existing releases are never replaced.')
    if tag and tag['object']['sha'] != state.get('commit'):
        raise ValueError('Remote tag no longer matches this frozen build')
    if release and release.get('target_commitish') != state.get('commit'):
        raise ValueError('Remote release target does not match this frozen build')
    if not state.get('commit'):
        transport = transport or GitTransport(build, repository, token)
        commit = transport.create_commit(files, head, version, api.user())
        state.update(parent=head, commit=commit, transport='git')
        save()
    # A retry can continue if our commit already became the branch head.
    if not state.get('branch_updated'):
        current = api.call('GET', refpath)['object']['sha']
        if current == state['parent']:
            if state.get('transport') == 'git':
                transport = transport or GitTransport(build, repository, token)
                print('Pushing the frozen package with Git (no force push).')
                transport.push_commit(state['commit'], branch)
            else:
                # Resume an older API-created commit without rewriting it.
                api.call('PATCH', '/git/refs/heads/' + branch, {'sha': state['commit'], 'force': False})
        elif current != state['commit']:
            raise ValueError('Branch advanced concurrently. No force update made. Inspect the repository before a new build.')
        state['branch_updated'] = True
        save()
    if not tag:
        api.call('POST', '/git/refs', {'ref': 'refs/tags/' + version, 'sha': state['commit']})
    notes = files['RELEASE_NOTES.md'].decode() + (
        f'\nCommit: `{state["commit"]}`\n\n'
        f'Archive SHA-256: `{identity["archive_sha256"]}`\n\n'
        'See release-manifest.json and SHA256SUMS.txt for the exact packaged files. '
        'Packaging does not independently validate graph assertions.\n')
    if release is None:
        release = api.call('POST', '/releases', {'tag_name': version, 'target_commitish': state['commit'],
                    'name': f'DATMM {version}', 'body': notes, 'draft': True, 'prerelease': bool(prerelease)})
    state['release_id'] = release['id']
    save()
    assets = [archive, build / (archive.name + '.sha256'), build / 'package/release-manifest.json', build / 'package/SHA256SUMS.txt']
    existing = {a['name']: a for a in api.call('GET', f'/releases/{release["id"]}/assets?per_page=100')}
    for path in assets:
        data = path.read_bytes()
        expected = 'sha256:' + digest(data)
        item = existing.get(path.name)
        if item is None:
            if not release.get('draft'):
                raise ValueError('Published release is missing an expected asset; it will not be modified')
            item = api.call('POST', f'/releases/{release["id"]}/assets?name=' + urllib.parse.quote(path.name), binary=data, upload=True)
        if item.get('state') != 'uploaded' or item.get('size') != len(data) or item.get('digest') != expected:
            raise ValueError(f'Asset could not be verified: {path.name}. Release remains draft if not already published; inspect it before retrying.')
    if release.get('draft'):
        release = api.call('PATCH', f'/releases/{release["id"]}', {'draft': False})
    state.update(published=True, release_url=release['html_url'])
    save()
    print(f'Published: {state["release_url"]}\nCommit: {state["commit"]}')
    print('Pages deployment, if enabled, is a separate GitHub job; inspect its status in Actions.')
    return dict(state)
