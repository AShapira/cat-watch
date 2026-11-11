"""Check deployed capacity accounting without starting a training workload."""
from datetime import datetime, timezone
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import tempfile

import torch
from catwatch.learning import training, worker
from catwatch.learning.store import LearningStore

cuda = torch.cuda.mem_get_info()[0]/1024**2
host_before = float(subprocess.check_output(
    ['nvidia-smi', '--query-gpu=memory.free', '--format=csv,noheader,nounits'], text=True).strip())
effective = training.gpu_free_mib()
assert 0 < effective <= cuda, 'Shared capacity must be a conservative usable reading'
host_after = float(subprocess.check_output(
    ['nvidia-smi', '--query-gpu=memory.free', '--format=csv,noheader,nounits'], text=True).strip())
assert min(abs(effective-host_before), abs(effective-host_after)) <= 256, 'Host GPU reading changed too much; repeat the check'
with tempfile.TemporaryDirectory(prefix='catwatch-memory-check-') as directory:
    root = Path(directory)
    store = LearningStore(root)
    (root/'datasets').mkdir()
    (root/'datasets/capacity-check.json').write_text('{}')
    threshold = store.config()['training_free_mib']
    # An empty dataset is intentional: a low-capacity result must return before
    # dataset partitioning or model allocation. No live data are mounted here.
    paused = training.train(root, 'capacity-check') if effective < threshold else None
    if paused is not None:
        assert paused == {'paused': True, 'reason': 'Waiting for GPU capacity'}
    print(json.dumps({'checked_at': datetime.now(timezone.utc).isoformat(),
        'cuda_free_mib': cuda, 'host_free_before_mib': host_before,
        'host_free_after_mib': host_after, 'effective_free_mib': effective,
        'training_admission_mib': threshold, 'capacity_gate_result': paused,
        'training_workload_started': False,
        'source_sha256': {module.__name__: hashlib.sha256(Path(inspect.getfile(module)).read_bytes()).hexdigest()
                          for module in (training, worker)}}))
