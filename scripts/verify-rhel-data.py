"""Verify the copy and protect migrated media before starting the new recorder."""
from pathlib import Path
import hashlib
import json
import sqlite3
import time

source = Path('/mnt/c/Alex/data/tapo-cat-monitor/cat-watch')
target = Path.home()/'.local/share/cat-watch/data'
receipts = Path('/mnt/c/Alex/data/tapo-cat-monitor/rhel-migration-20261109')
inventory = json.loads((receipts/'data-inventory.json').read_text())
assert inventory['target'] == str(target) and inventory['source'] == str(source)
assert (target/'.migration-in-progress').exists(), 'Do not repeat the cutover preparation on a live deployment'
report = {'checked_unix': time.time(), 'files': inventory['files'], 'bytes': inventory['bytes'], 'databases': {}}
for relative in ['catwatch.sqlite3', 'learning/agent.sqlite3']:
    copied = target/relative
    digest = hashlib.sha256(copied.read_bytes()).hexdigest()
    expected = next(x['sha256'] for x in inventory['inventory'] if x['path'] == relative)
    assert digest == expected, 'Copied database changed before cutover'
    with sqlite3.connect('file:'+str(copied)+'?mode=ro', uri=True) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        counts = {name: db.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0] for name in tables}
        report['databases'][relative] = {'integrity': 'ok', 'sha256': digest, 'counts': counts}
with sqlite3.connect(target/'catwatch.sqlite3') as db:
    segments = list(db.execute('SELECT id,path FROM segments'))
    assert all((target/path).is_file() for _, path in segments), 'Registered recording missing'
    db.execute("INSERT OR IGNORE INTO protected_segments SELECT id,'Preserved by RHEL migration 2026-11-09' FROM segments")
    report['protected_migrated_segments'] = len(segments)
    known = {path for _, path in segments}
    orphans = []
    for path in (target/'media').iterdir():
        if str(path.relative_to(target)) not in known:
            destination = target/'migration-preserved-media'/path.name
            destination.parent.mkdir(exist_ok=True)
            path.rename(destination)
            orphans.append({'path': str(destination.relative_to(target)), 'bytes': destination.stat().st_size})
    report['preserved_unregistered_media'] = orphans
with sqlite3.connect(target/'learning/agent.sqlite3') as db:
    cfg = json.loads(db.execute('SELECT body FROM settings WHERE id=1').fetchone()[0])
    assert cfg['training'] is False
    db.execute("INSERT OR REPLACE INTO metadata VALUES ('pause_training','true')")
    report['training'] = False
    report['continuous'] = cfg['continuous']
    report['calibration_id'] = cfg['calibration_id']
    report['crop_overrides'] = {r[0]: json.loads(r[1]) for r in db.execute("SELECT key,body FROM metadata WHERE key LIKE '%crop%override%'")}
(target/'.migration-in-progress').rename(target/'.migration-verified')
(receipts/'data-verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ('crop_overrides','calibration_id')},indent=2))
