"""Independent classification crops and an online bridge for pre-patch workers.

The bridge splits extraction jobs while an older recorder stays running. Once
the patched application starts, it removes the bridge: add_video then creates
all independent area manifests from a single encoded source clip.
"""
import json
import math
import time

from ..regions import crop_regions

CROP_POLICY = 'independent-areas-v1'
BRIDGE = 'catwatch_independent_classification_crops'
FOUNTAIN_BRIDGE = 'catwatch_fountain_classification_crop'


def override_box(override, width, height):
    """Validate a calibration-bound crop and scale its source-pixel boundaries."""
    sw, sh = override['source_size']
    x1, y1, x2, y2 = override['box']
    if not all(type(v) is int for v in (sw, sh, x1, y1, x2, y2)) or not (
            0 <= x1 < x2 <= sw and 0 <= y1 < y2 <= sh):
        raise ValueError('Classification override must be inside its source frame')
    return [math.floor(x1*width/sw), math.floor(y1*height/sh),
            math.ceil(x2*width/sw), math.ceil(y2*height/sh)]


def classification_regions(polygons, width, height, context=.5, overrides=None):
    regions = [region for area in sorted(polygons)
               for region in crop_regions({area: polygons[area]}, width, height, context)]
    for region in regions:
        area = region['areas'][0]
        override = (overrides or {}).get(area)
        if override and polygons[area] == override['polygon']:
            region['box'] = override_box(override, width, height)
    return regions


def legacy_fountain_polygon(override):
    """Invert the legacy 50% context margin without touching camera calibration."""
    sw, sh = override['source_size']
    x1, y1, x2, y2 = override_box(override, sw, sh)
    if min(x2-x1, y2-y1) < 2:
        raise ValueError('Legacy classification override must span at least two pixels')
    # Quarter-pixel inset avoids float floor/ceil spilling into an adjacent pixel.
    l, t, r, b = (x1+.25)/sw, (y1+.25)/sh, (x2-.25)/sw, (y2-.25)/sh
    a, c, d, e = (3*l+r)/4, (3*t+b)/4, (l+3*r)/4, (t+3*b)/4
    polygon = [[a,c], [d,c], [d,e], [a,e]]
    assert crop_regions({'water_fountain':polygon},sw,sh)[0]['box'] == override['box']
    return polygon


def install_fountain_bridge(db, override):
    """Tighten single-fountain jobs, including companions from the split bridge.

    Only matching saved calibration is affected. Running jobs and old clips keep
    their recorded inputs; originals retained in the payload support native handoff.
    """
    polygon = legacy_fountain_polygon(override)
    def sql_json(value):
        return "json('" + json.dumps(value,separators=(',',':')).replace("'","''") + "')"
    db.execute(f'DROP TRIGGER IF EXISTS {FOUNTAIN_BRIDGE}')
    db.execute(f'''
        CREATE TRIGGER {FOUNTAIN_BRIDGE} AFTER INSERT ON jobs
        WHEN NEW.kind='extract' AND NEW.state='queued'
          AND (SELECT count(*) FROM json_each(NEW.payload,'$.polygons'))=1
          AND json_extract(NEW.payload,'$.polygons.water_fountain')={sql_json(override['polygon'])}
        BEGIN
            UPDATE jobs SET payload=json_set(NEW.payload,
                '$.classification_original_polygons',json_extract(NEW.payload,'$.polygons'),
                '$.polygons.water_fountain',{sql_json(polygon)}) WHERE id=NEW.id;
        END
    ''')
    changed = 0
    for ident, body in db.execute("SELECT id,payload FROM jobs WHERE kind='extract' AND state='queued'").fetchall():
        payload = json.loads(body)
        if payload.get('polygons') != {'water_fountain':override['polygon']}:
            continue
        payload['classification_original_polygons'] = payload['polygons']
        payload['polygons'] = {'water_fountain':polygon}
        db.execute('UPDATE jobs SET payload=? WHERE id=?',(json.dumps(payload),ident))
        changed += 1
    return changed


def install_queue_bridge(db):
    """Install within the caller's transaction; never rewrite saved clips."""
    db.execute(f'''
        CREATE TRIGGER IF NOT EXISTS {BRIDGE}
        AFTER INSERT ON jobs
        WHEN NEW.kind='extract' AND NEW.state='queued'
          AND json_type(NEW.payload,'$.polygons.eating_pad')='array'
          AND json_type(NEW.payload,'$.polygons.water_fountain')='array'
        BEGIN
            UPDATE jobs
               SET payload=json_remove(NEW.payload,'$.polygons.water_fountain')
             WHERE id=NEW.id;
            INSERT OR IGNORE INTO jobs(kind,key,updated,payload)
            VALUES ('extract',NEW.key||':independent-water-fountain',NEW.updated,
                json_set(NEW.payload,'$.polygons',json_object('water_fountain',
                    json_extract(NEW.payload,'$.polygons.water_fountain'))));
        END
    ''')
    # Jobs that have already been claimed keep their original recorded input.
    rows = db.execute("SELECT id,key,updated,payload FROM jobs WHERE kind='extract' AND state='queued'").fetchall()
    split = 0
    for ident, key, updated, body in rows:
        payload = json.loads(body)
        polygons = payload.get('polygons', {})
        if not all(isinstance(polygons.get(area), list)
                   for area in ('eating_pad', 'water_fountain')):
            continue
        fountain = {**payload, 'polygons': {'water_fountain': polygons['water_fountain']}}
        remainder = {**payload, 'polygons': {a: p for a, p in polygons.items() if a != 'water_fountain'}}
        db.execute('UPDATE jobs SET payload=? WHERE id=?', (json.dumps(remainder), ident))
        db.execute('INSERT OR IGNORE INTO jobs(kind,key,updated,payload) VALUES (?,?,?,?)',
                   ('extract', key + ':independent-water-fountain', updated, json.dumps(fountain)))
        split += 1
    return split


def remove_queue_bridge(db):
    present = db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?", (BRIDGE,)).fetchone()
    db.execute(f'DROP TRIGGER IF EXISTS {BRIDGE}')
    db.execute(f'DROP TRIGGER IF EXISTS {FOUNTAIN_BRIDGE}')
    if present:
        row = db.execute("SELECT body FROM metadata WHERE key='classification_crop_policy'").fetchone()
        policy = json.loads(row[0]) if row else {'policy': CROP_POLICY}
        policy.update(implementation='native-media', bridge_removed_at=time.time())
        db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',
                   ('classification_crop_policy', json.dumps(policy)))
