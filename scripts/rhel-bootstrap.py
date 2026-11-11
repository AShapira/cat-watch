"""Receive DPAPI-decrypted credentials over stdin into private WSL tmpfs."""
import json
import os
from pathlib import Path
import subprocess
import sys

payload = sys.stdin.buffer.readline(16384)
value = json.loads(payload.decode('utf-8-sig'))
if not all(isinstance(value.get(k), str) and value[k] for k in ('ip', 'username', 'password')):
    raise SystemExit('Incomplete camera credential handoff')
runtime = Path('/run/user')/str(os.getuid())/'cat-watch-credentials'
runtime.mkdir(mode=0o700, exist_ok=True)
runtime.chmod(0o700)
temporary = runtime/'credentials.tmp'
fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as stream:
    json.dump(value, stream)
os.chmod(temporary, 0o600)
os.replace(temporary, runtime/'credentials.json')
environment = {**os.environ, 'XDG_RUNTIME_DIR': str(runtime.parent),
               'DBUS_SESSION_BUS_ADDRESS': 'unix:path='+str(runtime.parent/'bus')}
subprocess.run(['systemctl', '--user', 'start', 'cat-watch.service'], check=True, env=environment)
print('RHEL cat-watch service started; credentials retained only in private runtime memory')
