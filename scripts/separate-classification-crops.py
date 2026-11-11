"""Apply the independent-area queue bridge without restarting a live recorder.

Run with the existing container's Python and the reviewed crop_policy.py supplied
via --policy-file. The eventual patched application removes this bridge at startup.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import time


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def clip_history(db):
    # Model workers may continue proposing labels; this migration changes none
    # of the immutable manifests or human review fields.
    return fingerprint(db.execute('SELECT id,manifest,decision,version FROM clips ORDER BY id').fetchall())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action', choices=['plan', 'apply'], default='plan')
    parser.add_argument('--root', type=Path, default=Path('/data'))
    parser.add_argument('--policy-file', type=Path, required=True)
    parser.add_argument('--session-id', type=int, required=True)
    parser.add_argument('--polygons-sha256', required=True)
    parser.add_argument('--overrides-file', type=Path,
                        help='Optional calibration-bound classification crop overrides')
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root / '.cat-watch-data').is_file():
        raise ValueError('Application data ownership marker missing')
    spec = importlib.util.spec_from_file_location('catwatch.learning._online_crop_policy', args.policy_file)
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    with sqlite3.connect((root / 'catwatch.sqlite3').as_uri() + '?mode=ro', uri=True) as source:
        row = source.execute('SELECT id,deadline,stop,config_snapshot FROM investigations ORDER BY id DESC LIMIT 1').fetchone()
        if not row or row[0] != args.session_id or row[2] is not None or row[1] <= time.time():
            raise ValueError('Expected active monitoring session changed')
        config = json.loads(row[3])
    polygons = config['polygons']
    if fingerprint(polygons) != args.polygons_sha256:
        raise ValueError('Saved monitoring areas differ from the inspected areas')
    overrides = json.loads(args.overrides_file.read_text()) if args.overrides_file else {}
    if overrides and (set(overrides) != {'water_fountain'} or
                      overrides['water_fountain']['polygon'] != polygons['water_fountain']):
        raise ValueError('Online crop tightening must match the saved fountain polygon')
    regions = policy.classification_regions(polygons, 2560, 1440, overrides=overrides)
    if overrides:
        policy.legacy_fountain_polygon(overrides['water_fountain'])
    if len({tuple(r['box']) for r in regions}) != len(regions):
        raise ValueError('Legacy workers require distinct crop boxes; use the native patch for identical areas')
    db_path = root / 'learning/agent.sqlite3'
    receipt = {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'policy': policy.CROP_POLICY, 'implementation': 'online-extraction-queue',
               'session_id': args.session_id, 'polygons_sha256': args.polygons_sha256,
               'policy_file_sha256': hashlib.sha256(args.policy_file.read_bytes()).hexdigest(),
               'expected_regions_2560x1440': regions, 'action': args.action,
               'classification_crop_overrides': overrides}
    with sqlite3.connect(db_path, timeout=20) as db:
        cfg = json.loads(db.execute('SELECT body FROM settings WHERE id=1').fetchone()[0])
        if not cfg['continuous'] or cfg['training']:
            raise ValueError('Expected continuous monitoring and training disabled')
        receipt['counts'] = {t: db.execute('SELECT count(*) FROM ' + t).fetchone()[0]
                             for t in ('clips', 'predictions', 'revisions', 'models', 'datasets')}
        receipt['bridge_already_present'] = bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?", (policy.BRIDGE,)).fetchone())
        receipt['running_extractions'] = db.execute("SELECT count(*) FROM jobs WHERE kind='extract' AND state='running'").fetchone()[0]
        if args.action == 'apply':
            directory = root / 'learning/backups'
            directory.mkdir(exist_ok=True)
            backup = directory / ('before-independent-crops-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sqlite3')
            with sqlite3.connect(backup) as target:
                db.backup(target)
                if target.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                    raise ValueError('Database backup check failed; bridge was not installed')
            receipt['backup'] = str(backup.relative_to(root))
            db.execute('BEGIN IMMEDIATE')
            before_config = db.execute('SELECT body FROM settings WHERE id=1').fetchone()[0]
            current = json.loads(before_config)
            if not current['continuous'] or current['training']:
                raise ValueError('Monitoring or training settings changed during preparation')
            before_history = clip_history(db)
            receipt['existing_job_boundary'] = db.execute('SELECT COALESCE(MAX(id),0) FROM jobs').fetchone()[0]
            receipt['pending_extractions_split'] = policy.install_queue_bridge(db)
            if overrides:
                receipt['pending_fountain_crops_tightened'] = policy.install_fountain_bridge(db, overrides['water_fountain'])
                db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',
                           ('classification_crop_overrides', json.dumps(overrides)))
            receipt['applied_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            receipt['existing_clip_history_unchanged'] = clip_history(db) == before_history
            assert receipt['existing_clip_history_unchanged']
            assert db.execute('SELECT body FROM settings WHERE id=1').fetchone()[0] == before_config
            db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', ('classification_crop_policy', json.dumps(receipt)))
            db.commit()
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
