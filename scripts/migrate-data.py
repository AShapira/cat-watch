"""Copy a stopped deployment into new Linux storage, verifying every file."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(4*1024**2), b''):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('target', type=Path)
    p.add_argument('receipt', type=Path)
    args = p.parse_args()
    if not (args.source/'.cat-watch-data').is_file():
        raise SystemExit('Source ownership marker missing')
    if args.target.exists() and not (args.target/'.migration-in-progress').is_file():
        raise SystemExit('Target exists without this migration marker')
    args.target.mkdir(parents=True, exist_ok=True, mode=0o700)
    (args.target/'.migration-in-progress').touch()
    files = sorted(args.source.rglob('*'))
    if any(f.is_symlink() for f in files):
        raise SystemExit('Symlink in source requires explicit handling')
    sizes = sum(f.stat().st_size for f in files if f.is_file())
    if shutil.disk_usage(args.target).free < sizes + 6*1024**3:
        raise SystemExit('Insufficient destination space plus 6 GiB reserve')
    inventory, total, started = [], 0, time.time()
    for f in files:
        dest = args.target/f.relative_to(args.source)
        if f.is_dir():
            dest.mkdir(exist_ok=True, mode=0o700)
            continue
        before = f.stat()
        expected = sha(f)
        if not dest.exists() or dest.stat().st_size != before.st_size or sha(dest) != expected:
            shutil.copy2(f, dest)
            dest.chmod(0o600)
            if sha(dest) != expected:
                raise RuntimeError('Destination checksum mismatch')
        after = f.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError('Source changed during migration')
        inventory.append({'path': str(f.relative_to(args.source)), 'size': before.st_size, 'sha256': expected})
        total += before.st_size
        if len(inventory) % 1000 == 0:
            print(json.dumps({'verified_files': len(inventory), 'bytes': total}), flush=True)
    # Originals are preserved; no cleanup, deletion or source database write.
    receipt = {'source': str(args.source), 'target': str(args.target), 'files': len(inventory),
               'bytes': total, 'elapsed_seconds': round(time.time()-started, 1), 'inventory': inventory}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt))
    args.receipt.chmod(0o600)
    print(json.dumps({k: v for k, v in receipt.items() if k != 'inventory'}), flush=True)


if __name__ == '__main__':
    main()
