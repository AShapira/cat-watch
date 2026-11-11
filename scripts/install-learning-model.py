"""Build-time public weight download, pinned revision, no inference or user data."""
import hashlib
import json
from pathlib import Path
from huggingface_hub import hf_hub_download

REPO = 'MCG-NJU/videomae-base-finetuned-kinetics'
REVISION = '488eb9a0565f257b32866000305c8178965eb9f6'
target = Path('/opt/models/videomae')
target.mkdir(parents=True, exist_ok=True)
checksums = {}
for name in ('model.safetensors', 'config.json', 'preprocessor_config.json', 'README.md'):
    downloaded = Path(hf_hub_download(REPO, name, revision=REVISION, local_dir=target))
    h = hashlib.sha256()
    with downloaded.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    checksums[name] = h.hexdigest()
(target/'PROVENANCE.json').write_text(json.dumps({'repo': REPO, 'revision': REVISION,
    'license': 'CC-BY-NC-4.0', 'files': checksums}, sort_keys=True, indent=2))
print(json.dumps({'checkpoint': REPO, 'revision': REVISION, 'files': checksums}))
