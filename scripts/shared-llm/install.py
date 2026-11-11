"""Install the authorized, user-owned shared model service; no camera restart."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
LOCK = json.loads((HERE/'model-lock.json').read_text())
BASE = Path.home()/'.local/share/catwatch-shared-llm'
VOLUME = 'shared-qwen-models'


def podman(*args):
    return subprocess.check_output(['podman', *args], text=True).strip()


def volume(name):
    names = podman('volume', 'ls', '--format', '{{.Name}}').splitlines()
    if name not in names:
        podman('volume', 'create', '--label', 'app=catwatch-shared-llm', name)
    item = json.loads(podman('volume', 'inspect', name))[0]
    if (item.get('Labels') or {}).get('app') != 'catwatch-shared-llm':
        raise SystemExit('Refusing an existing unowned volume')
    return Path(item['Mountpoint'])


def install(source):
    manifest_path = Path('manifests/registry.ollama.ai/library/qwen3.5/9b')
    raw = (source/manifest_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != LOCK['model_digest']:
        raise SystemExit('Source model identity differs from the approved lock')
    manifest = json.loads(raw)
    items = [manifest['config'], *manifest['layers']]
    for item in items:
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', item['digest']):
            raise SystemExit('Invalid blob identity')
    config = json.loads((source/'blobs'/items[0]['digest'].replace(':', '-')).read_text())
    if config.get('file_type') != LOCK['quantization'] or config.get('model_family') != 'qwen35':
        raise SystemExit('Unexpected model family or quantization')
    # This validates availability; no implicit network pull or mutable image tag.
    podman('image', 'inspect', LOCK['image'], '--format', '{{.Id}}')
    if BASE.exists() and not (BASE/'.owned').is_file():
        raise SystemExit('Refusing an unmarked installation directory')
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE/'.owned').write_text('catwatch-shared-llm-v1\n')
    target = volume(VOLUME)
    volume('shared-qwen-state')
    needed = sum(i['size'] for i in items if not (target/'blobs'/i['digest'].replace(':', '-')).exists())
    if shutil.disk_usage(target).free < needed+3*1024**3:
        raise SystemExit('Insufficient space for independent weights and reserve')
    (target/'blobs').mkdir(exist_ok=True)
    for item in items:
        name = item['digest'].replace(':', '-')
        dest = target/'blobs'/name
        temp = dest.with_suffix('.partial')
        checksum = hashlib.sha256()
        copying = not dest.exists()
        with (source/'blobs'/name if copying else dest).open('rb') as reader:
            writer = temp.open('wb') if copying else None
            try:
                for chunk in iter(lambda: reader.read(8*1024**2), b''):
                    checksum.update(chunk)
                    if writer:
                        writer.write(chunk)
            finally:
                if writer:
                    writer.close()
        checked = temp if copying else dest
        if checksum.hexdigest() != item['digest'][7:] or checked.stat().st_size != item['size']:
            if copying:
                temp.unlink(missing_ok=True)
            raise SystemExit('Blob verification failed; service not started')
        if copying:
            os.replace(temp, dest)
        print(f"Verified {item['digest']} ({item['size']} bytes)", flush=True)
    destination = target/manifest_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    for name in ['model-lock.json', 'gateway.py', 'runtime.sh', 'catwatch-response.schema.json']:
        shutil.copyfile(HERE/name, BASE/name)
    (BASE/'runtime.sh').chmod(0o755)
    (BASE/'cdi').mkdir(exist_ok=True)
    units = Path.home()/'.config/systemd/user'
    units.mkdir(parents=True, exist_ok=True)
    for name in ['shared-qwen-runtime.service', 'shared-qwen.service']:
        destination = units/name
        if destination.exists() and '# Owned by catwatch-shared-llm' not in destination.read_text():
            raise SystemExit('Refusing to overwrite an unrelated service unit')
        shutil.copyfile(HERE/name, destination)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    print(json.dumps({'installation': str(BASE), 'model_volume': VOLUME,
                      'model_digest': LOCK['model_digest'], 'bytes_verified': sum(i['size'] for i in items)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-models', type=Path, required=True)
    install(parser.parse_args().source_models.resolve())
