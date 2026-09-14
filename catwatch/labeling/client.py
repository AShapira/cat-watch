"""Bounded local Label Studio HTTP client with PAT refresh and no secret logging."""
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request


class LabelStudioError(RuntimeError):
    pass


class Client:
    def __init__(self, url, token_file, token_type='pat'):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.username or parsed.path not in ('', '/'):
            raise ValueError('Label Studio must use a local loopback HTTP address')
        if token_type not in ('pat', 'legacy'):
            raise ValueError('Unknown access token type')
        self.url, self.token_file, self.token_type = url.rstrip('/'), Path(token_file), token_type
        self.access, self.expiry = None, 0

    def request(self, path, method='GET', body=None, refresh=True):
        if not path.startswith('/api/'):
            raise ValueError('Only Label Studio API paths are supported')
        token = self.token_file.read_text().strip()
        if not token:
            raise LabelStudioError('Label Studio credential is missing')
        if self.token_type == 'pat' and (not self.access or time.monotonic() >= self.expiry):
            result = self._request('/api/token/refresh/', 'POST', {'refresh': token}, {})
            self.access, self.expiry = result['access'], time.monotonic()+240
        authorization = 'Bearer '+self.access if self.token_type == 'pat' else 'Token '+token
        try:
            return self._request(path, method, body, {'Authorization': authorization})
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and refresh and self.token_type == 'pat':
                self.access = None
                return self.request(path, method, body, refresh=False)
            raise LabelStudioError(f'Label Studio API returned HTTP {exc.code}') from None

    def _request(self, path, method, body, headers):
        request = urllib.request.Request(self.url+path, method=method,
            data=None if body is None else json.dumps(body, allow_nan=False).encode(),
            headers={**headers, 'Content-Type': 'application/json'})
        # Redirects must not forward Authorization to another origin.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=15) as response:
                data = response.read(32_000_001)
                if len(data) > 32_000_000:
                    raise LabelStudioError('Label Studio response exceeded the size limit')
                return json.loads(data) if data else None
        except urllib.error.HTTPError:
            raise
        except (OSError, ValueError):
            raise LabelStudioError('Label Studio is unavailable or returned an invalid response') from None

    def tasks(self, project):
        page = 1
        while True:
            data = self.request(f'/api/tasks?project={project}&page={page}&page_size=100')
            rows = data if isinstance(data, list) else data.get('tasks', data.get('results', []))
            yield from rows
            if isinstance(data, list) or not rows or page*100 >= data.get('total', data.get('count', len(rows))):
                break
            page += 1

    def project(self, project_id, dataset_id, config, guide):
        if project_id:
            project = self.request(f'/api/projects/{int(project_id)}/')
            if project['label_config'].strip() != config.strip():
                raise LabelStudioError('Project label configuration differs from taxonomy v1')
            return project['id']
        rows, page = [], 1
        while True:
            data = self.request(f'/api/projects/?page_size=100&page={page}')
            batch = data if isinstance(data, list) else data.get('results', [])
            rows.extend(batch)
            if isinstance(data, list) or not batch or page*100 >= data.get('count', len(rows)):
                break
            page += 1
        description = 'cat-watch dataset '+dataset_id
        matches = [p for p in rows if p.get('description') == description]
        if len(matches) > 1:
            raise LabelStudioError('Multiple projects match this dataset; configure an explicit project ID')
        if matches:
            return self.project(matches[0]['id'], dataset_id, config, guide)
        return self.request('/api/projects/', 'POST', {'title': 'Cat activities v1', 'description': description,
            'label_config': config, 'expert_instruction': guide, 'show_instruction': True})['id']
