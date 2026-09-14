"""Container entry point. Secrets enter process env from a restricted mount, not OCI metadata."""
import json
import os
from pathlib import Path

config = json.loads(Path('/private/bootstrap.json').read_text())
os.environ.update({
    'LABEL_STUDIO_USERNAME': config['username'],
    'LABEL_STUDIO_PASSWORD': config['password'],
    'LABEL_STUDIO_USER_TOKEN': Path('/private/token').read_text().strip(),
    'LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED': 'true',
    'LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT': '/dataset',
    'LABEL_STUDIO_DISABLE_SIGNUP_WITHOUT_LINK': 'true',
    'LABEL_STUDIO_COLLECT_ANALYTICS': 'false',
    'LABEL_STUDIO_LATEST_VERSION_CHECK': 'false',
    'LABEL_STUDIO_SENTRY_DSN': '',
    'LABEL_STUDIO_FRONTEND_SENTRY_DSN': '',
})
os.execvp('label-studio', ['label-studio', 'start', '--no-browser', '--internal-host', '127.0.0.1',
    '--port', '8767', '--data-dir', '/label-studio/data', '--enable-legacy-api-token'])
