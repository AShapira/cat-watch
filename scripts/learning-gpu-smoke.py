"""Native GPU smoke/benchmark using generated pixels, never private footage."""
import json
import tempfile
import time
from pathlib import Path

import numpy as np
import torch
from transformers import VideoMAEForVideoClassification, VideoMAEImageProcessor

root = '/opt/models/videomae'
assert torch.cuda.is_available(), 'CUDA is unavailable'
free, total = torch.cuda.mem_get_info()
assert free > 4*1024**3, 'Less than 4 GiB free; leave other applications alone'
torch.manual_seed(17)
torch.set_num_threads(2)
model = VideoMAEForVideoClassification.from_pretrained(root, num_labels=5, ignore_mismatched_sizes=True, local_files_only=True).cuda()
processor = VideoMAEImageProcessor.from_pretrained(root, local_files_only=True)
frames = [np.full((224,224,3), i*12, np.uint8) for i in range(16)]
pixels = processor(frames, return_tensors='pt')['pixel_values'].cuda()
measurements = {}
for mode in ('head', 'last-block'):
    for name, p in model.named_parameters():
        p.requires_grad = 'classifier' in name or mode == 'last-block' and 'encoder.layer.11.' in name
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-4)
    model.train()
    torch.cuda.synchronize(); started = time.perf_counter()
    for _ in range(3):
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast('cuda', dtype=torch.bfloat16):
            loss = model(pixel_values=pixels, labels=torch.tensor([0], device='cuda')).loss
        assert torch.isfinite(loss)
        loss.backward(); optimizer.step()
    torch.cuda.synchronize()
    measurements[mode] = {'seconds_per_step': (time.perf_counter()-started)/3, 'finite_loss': float(loss.detach())}
model.eval()
with torch.inference_mode(), torch.autocast('cuda', dtype=torch.bfloat16):
    before = model(pixel_values=pixels).logits.float()
with tempfile.TemporaryDirectory() as folder:
    model.save_pretrained(folder, safe_serialization=True)
    loaded = VideoMAEForVideoClassification.from_pretrained(folder, local_files_only=True).cuda().eval()
    with torch.inference_mode(), torch.autocast('cuda', dtype=torch.bfloat16):
        after = loaded(pixel_values=pixels).logits.float()
    assert torch.allclose(before, after, atol=.01)
print(json.dumps({'smoke': 'passed', 'data': 'synthetic pixels only; no behavior quality claim',
                  'gpu': torch.cuda.get_device_name(0), 'torch': torch.__version__, 'measurements': measurements,
                  'peak_allocated_mib': torch.cuda.max_memory_allocated()/1024**2,
                  'checkpoint_roundtrip': True}))
