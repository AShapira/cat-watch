import json
import os
from pathlib import Path
import socket
import sys
import time

from .store import Store

SOCKET = "/tmp/catwatch-credential.sock"


def main():
    if "--health" in sys.argv:
        import urllib.request
        urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=3).close()
        return
    if "--credentials" in sys.argv:
        payload = sys.stdin.readline(16384).strip().encode()
        for _ in range(60):
            try:
                with socket.socket(socket.AF_UNIX) as client:
                    client.connect(SOCKET)
                    client.sendall(payload + b"\n")
                return
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(.5)
        raise RuntimeError("Credential receiver unavailable")
    from .runtime import Runtime
    if "--check-gpu" in sys.argv:
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            runtime = Runtime(Store(root))
            runtime.load_model()
            print(json.dumps({"inference": "passed", "gpu": runtime.state["gpu"]}))
        return
    root = Path(os.environ.get("CATWATCH_DATA", "/data"))
    if not (root / ".cat-watch-data").is_file():
        raise RuntimeError("Data ownership marker missing; start through PowerShell")
    if '--review-only' in sys.argv:
        import uvicorn
        from .web import create_app
        store = Store(root)
        runtime = Runtime(store)
        runtime.state.update(review_only=True, camera='stopped', detector='stopped',
            motion_analysis='stopped', video_description='stopped', detector_comparison='stopped',
            message='Review only: recording, analysis and automatic deletion are stopped')
        uvicorn.run(create_app(store, runtime, run_worker=False), host='127.0.0.1',
                    port=8765, access_log=False, log_level='warning')
        return
    if '--credential-file' in sys.argv:
        credential_path = Path(sys.argv[sys.argv.index('--credential-file')+1])
        info = credential_path.stat()
        if info.st_mode & 0o077 or info.st_uid != os.getuid() or info.st_size > 16384:
            raise RuntimeError('Credential file must be private to the runtime user')
        credential = json.loads(credential_path.read_text())
    else:
        # Legacy handoff through a UID-restricted local socket.
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(SOCKET)
            os.chmod(SOCKET, 0o600)
            server.listen(1)
            server.settimeout(120)
            client, _ = server.accept()
            with client, client.makefile("rb") as stream:
                credential = json.loads(stream.readline(16384))
        os.unlink(SOCKET)
    services = credential.pop('services', {})
    for key, environment in [('telegram_token', 'CATWATCH_TELEGRAM_TOKEN'), ('openai_api_key', 'CATWATCH_OPENAI_API_KEY')]:
        if services.get(key):
            os.environ[environment] = services[key]
    import uvicorn
    from .web import create_app
    store = Store(root)
    runtime = Runtime(store, credential)
    uvicorn.run(create_app(store, runtime), host="127.0.0.1", port=8765, access_log=False, log_level="warning")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("cat-watch startup failed; verify deployment, credentials and GPU checks", file=sys.stderr)
        sys.exit(1)
