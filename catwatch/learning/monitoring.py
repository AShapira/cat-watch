"""Coverage-aware summaries, shadow qualification, and a durable Telegram outbox."""
from collections import defaultdict
from datetime import datetime, timedelta
import json
import os
import time
from zoneinfo import ZoneInfo

import httpx

from .contracts import CARE, LABELS, canonical, digest, merge_spans

ZONE = ZoneInfo('Asia/Jerusalem')


def coverage(store, start, end, model_id=None):
    if end <= start:
        return {'fraction': 0., 'seconds': 0., 'largest_gap': 0.}
    with store.db() as db:
        rows = (db.execute('SELECT * FROM model_coverage WHERE model_id=? AND end>? AND start<?', (model_id, start, end))
                if model_id else db.execute('SELECT * FROM coverage WHERE good=1 AND end>? AND start<?', (start, end)))
        spans = merge_spans((max(start, r['start']), min(end, r['end'])) for r in rows)
    seconds = sum(b-a for a, b in spans)
    edges = [[start, start], *spans, [end, end]]
    return {'fraction': seconds/(end-start), 'seconds': seconds,
            'largest_gap': max(b[0]-a[1] for a, b in zip(edges, edges[1:]))}


def events(store, start, end, *, qualified=False, model_id=None):
    with store.db() as db:
        rows = db.execute('SELECT * FROM events WHERE end>? AND start<? AND (?=0 OR qualified=1) AND (? IS NULL OR model_id=?) ORDER BY start',
                          (start, end, int(qualified), model_id, model_id)).fetchall()
    return [dict(r, body=json.loads(r['body'])) for r in rows]


def bouts(rows, label, start, end):
    return merge_spans(((max(start, r['start']), min(end, r['end'])) for r in rows if r['label'] == label), gap=5)


def presentation_events(store, start, end):
    rows = events(store, start, end)
    selected = store.inference_models()
    preferred = selected[0]['id'] if selected else None
    rows = [r for r in rows if r['source'] == 'human' or r['model_id'] == preferred]
    # Human intervals replace overlapping machine claims, including corrected
    # no-cat and non-care decisions. Never count both as separate observations.
    human = [r for r in rows if r['source'] == 'human']
    out = list(human)
    for row in rows:
        if row['source'] == 'human':
            continue
        spans = [(row['start'], row['end'])]
        for h in human:
            spans = [(x, y) for a, b in spans for x, y in
                     ([(a, b)] if h['end'] <= a or h['start'] >= b else [(a, min(b, h['start'])), (max(a, h['end']), b)]) if y > x]
        out.extend(dict(row, start=a, end=b) for a, b in spans)
    return sorted(out, key=lambda r: r['start'])


def summary(store, start, end):
    rows = presentation_events(store, start, end)
    classes = {}
    for label in CARE:
        spans = bouts(rows, label, start, end)
        verified = bouts([r for r in rows if r['source'] == 'human' or r['qualified']], label, start, end)
        classes[label] = {'episodes': len(spans), 'observed_seconds': sum(b-a for a, b in spans),
                          'qualified_episodes': len(verified), 'last_observed': spans[-1][1] if spans else None}
    cov = coverage(store, start, end)
    text = ['Cat-watch daily summary', datetime.fromtimestamp(start, ZONE).strftime('%d %b %H:%M')+' – '+
            datetime.fromtimestamp(end, ZONE).strftime('%d %b %H:%M'),
            f"Analysis coverage: {cov['fraction']:.0%}. Gaps are unobserved time."]
    for label, counts in classes.items():
        text.append(f"{label.replace('_', ' ').capitalize()}: {counts['episodes']} observed episodes "
                    f"({counts['qualified_episodes']} confirmed or qualified).")
    text.append('Observations describe this camera view. Uncertain classifications remain provisional.')
    queue = store.review_queue()
    text.append(f"Decisions waiting: {queue['pending']}; today's queue: {len(queue['items'])}.")
    evidence = next((r['clip_id'] for r in reversed(rows) if r['clip_id'] and r['label'] in CARE), None)
    return {'start': start, 'end': end, 'classes': classes, 'coverage': cov, 'text': '\n'.join(text), 'clip_id': evidence}


def baseline(store, now, model_id=None):
    end = datetime.fromtimestamp(now, ZONE).replace(hour=0, minute=0, second=0, microsecond=0)
    valid = []
    for n in range(1, 31):
        a, b = (end-timedelta(days=n)).timestamp(), (end-timedelta(days=n-1)).timestamp()
        c = coverage(store, a, b, model_id)
        if c['fraction'] >= .95 and c['largest_gap'] <= 300:
            valid.append((a, b, events(store, a, b, model_id=model_id) if model_id else events(store, a, b, qualified=True)))
        if len(valid) >= 14:
            break
    if len(valid) < 14:
        return {'ready': False, 'valid_days': len(valid), 'classes': {}}
    out = {}
    for label in CARE:
        spans = merge_spans([s for a, b, rows in valid for s in bouts(rows, label, a, b)], gap=5)
        # Use within-day intervals only; gaps between accepted days are not routine.
        gaps, hourly = [], []
        for a, b, rows in valid:
            visits = bouts(rows, label, a, b)
            gaps.extend(y[0]-x[1] for x, y in zip(visits, visits[1:]))
            for hour in range(int((b-a)//3600)):
                hourly.append(sum(a+hour*3600 <= x < a+(hour+1)*3600 for x, _ in visits))
        if len(spans) >= 30 and len(gaps) >= 14:
            gaps.sort(); hourly.sort()
            out[label] = {'absence_seconds': max(gaps[min(len(gaps)-1, int(.95*len(gaps)))]*1.5, 3600),
                          'frequent_per_hour': max(3, hourly[min(len(hourly)-1, int(.99*len(hourly)))]+2)}
    return {'ready': True, 'valid_days': len(valid), 'classes': out}


def tick(store, runtime, now=None):
    now = time.time() if now is None else now
    cfg = store.config()
    previous = store.meta('health_tick', now)
    # Detection coverage alone cannot establish behavior-analysis coverage.
    healthy = (runtime.state.get('camera') == 'connected' and runtime.state.get('detector') == 'ready'
               and now-(runtime.state.get('detection_stamp') or 0) < 20
               and now-(store.meta('inference_stamp', 0) or 0) < 30)
    if cfg['continuous'] and not healthy and 0 < now-previous <= 30:
        with store.db() as db:
            last = db.execute('SELECT * FROM coverage ORDER BY start DESC LIMIT 1').fetchone()
            if last and last['good'] == int(healthy) and previous-last['end'] < 1:
                db.execute('UPDATE coverage SET end=? WHERE start=?', (now, last['start']))
            else:
                db.execute('INSERT OR IGNORE INTO coverage VALUES (?,?,?)', (previous, now, int(healthy)))
    store.set_meta('health_tick', now)
    bad_since = store.meta('bad_since')
    if cfg['continuous']:
        if not healthy and bad_since is None:
            store.set_meta('bad_since', now)
        elif healthy:
            store.set_meta('bad_since', None)
        elif bad_since is not None and now-bad_since >= 300:
            store.notice('outage:'+str(int(bad_since)), 'system', {'text': 'Cat-watch camera or behavior analysis has been unavailable for over five minutes. Absence alerts are paused.', 'since': bad_since})
    local = datetime.fromtimestamp(now, ZONE)
    due = local.replace(hour=cfg['summary_hour'], minute=0, second=0, microsecond=0)
    if cfg['continuous'] and local >= due:
        a, b = (due-timedelta(days=1)).timestamp(), due.timestamp()
        store.notice('summary:'+due.date().isoformat(), 'summary', summary(store, a, b))
    if not cfg['continuous']:
        return
    selected = store.inference_models()
    base = baseline(store, now, selected[0]['id'] if selected else None)
    store.set_meta('baseline', base)
    for model in selected:
        if model['state'] not in ('shadow', 'active'):
            continue
        body = model['body']
        qualified = body.get('qualified_classes', [])
        base = baseline(store, now, model['id'])
        if model['state'] == 'shadow':
            if base['ready'] and not body.get('shadow_alert_since'):
                body['shadow_alert_since'] = now
                store.save_model(model['id'], 'shadow', body)
            since = body.get('shadow_alert_since', now)
            notices = [n for n in store.notices(all_rows=True) if n['body'].get('model_id') == model['id'] and n['kind'] == 'behavior']
            adjudicated = all('correct' in n['body'] for n in notices)
            false = sum(n['body'].get('correct') is False for n in notices)
            if false > 1:
                store.save_model(model['id'], 'rejected', {**body, 'rejection': 'More than one assessed false alert in shadow monitoring'})
                continue
            cov = coverage(store, since, now, model['id'])
            if qualified and base['ready'] and now-since >= 7*86400 and cov['fraction'] >= .95 and adjudicated and false <= 1:
                old = cfg['active_model']
                store.save_model(model['id'], 'active', body)
                store.configure({'active_model': model['id'], 'previous_model': old}, internal=True)
                if old and old != model['id']:
                    prior = store.model(old)
                    store.save_model(old, 'retired', prior['body'])
                model['state'] = 'active'
                with store.db() as db:
                    for label in qualified:
                        db.execute('UPDATE events SET qualified=1 WHERE model_id=? AND label=?', (model['id'], label))
        if not base['ready']:
            continue
        for label in qualified:
            rule = base['classes'].get(label)
            if not rule:
                continue
            window = rule['absence_seconds']
            cov = coverage(store, now-window, now, model['id'])
            if cov['fraction'] < .95 or cov['largest_gap'] > 300:
                continue
            rows = events(store, now-window, now, model_id=model['id'])
            seen = bouts(rows, label, now-window, now)
            message = None
            if not seen:
                message = f"{label.replace('_', ' ').capitalize()} has not been observed here for {window/3600:.1f} hours, longer than the established routine."
            elif len(bouts(rows, label, now-3600, now)) > rule['frequent_per_hour']:
                message = f"More {label.replace('_', ' ')} episodes than usual in the last hour. Review the evidence."
            if message:
                recent = [n for n in store.notices(all_rows=True) if n['kind'] == 'behavior' and n['body'].get('label') == label
                          and n['body'].get('model_id') == model['id'] and
                          (now-n['created'] < 6*3600 or n['snoozed_until'] > now)]
                if not recent:
                    store.notice(digest([model['id'], label, int(now//21600)]), 'behavior',
                                 {'text': message, 'label': label, 'model_id': model['id'], 'coverage': cov,
                                  'clip_id': next((r['clip_id'] for r in reversed(rows) if r['clip_id']), None)},
                                 shadow=model['state'] != 'active')


def acknowledge(store, ident, body):
    if set(body)-{'correct', 'snooze_hours'}:
        raise ValueError('Supply alert assessment or snooze duration')
    if 'correct' in body and type(body['correct']) is not bool:
        raise ValueError('Alert correctness must be true or false')
    hours = body.get('snooze_hours', 0)
    if type(hours) not in (int, float) or not 0 <= hours <= 168:
        raise ValueError('Snooze must be 0–168 hours')
    with store.db() as db:
        row = db.execute('SELECT body FROM notices WHERE id=?', (ident,)).fetchone()
        if row is None:
            raise KeyError(ident)
        value = json.loads(row[0])
        if 'correct' in body:
            value['correct'] = body['correct']
        db.execute('UPDATE notices SET acknowledged=1,snoozed_until=?,body=? WHERE id=?',
                   (time.time()+hours*3600, canonical(value), ident))


def deliver_one(store, *, transport=None):
    cfg = store.config()
    token = os.environ.get('CATWATCH_TELEGRAM_TOKEN')
    if not cfg['telegram_enabled'] or not token or not cfg['telegram_chat_id']:
        return False
    now = time.time()
    with store.db() as db:
        db.execute("UPDATE notices SET state='expired' WHERE state='queued' AND created<?", (now-86400,))
        row = db.execute("SELECT * FROM notices WHERE state='queued' AND next_at<=? AND snoozed_until<=? AND acknowledged=0 ORDER BY created LIMIT 1", (now, now)).fetchone()
        if row is None:
            return False
        db.execute("UPDATE notices SET state='sending',attempts=attempts+1 WHERE id=?", (row['id'],))
    body = json.loads(row['body'])
    if row['kind'] == 'behavior':
        try:
            model = store.model(body['model_id'])
            eligible = model['state'] == 'active' and body.get('label') in model['body'].get('qualified_classes', [])
        except KeyError:
            eligible = False
        if not eligible:
            with store.db() as db:
                db.execute("UPDATE notices SET state='cancelled' WHERE id=?", (row['id'],))
            return True
    text = body['text'][:3800]
    try:
        # Token is never stored in SQLite or returned by APIs/logs.
        url = 'https://api.telegram.org/bot'+token
        with httpx.Client(timeout=30, follow_redirects=False, transport=transport) as client:
            payload = {'chat_id': cfg['telegram_chat_id'], 'text': text, 'protect_content': True}
            from .media import jpeg, outbound_crop, sample
            clip = store.clip(body['clip_id']) if body.get('clip_id') else None
            if cfg['telegram_evidence'] and clip and outbound_crop(clip['manifest']):
                photo = jpeg(sample(store, clip, count=1)[0][1])
                # One outbound request per notice avoids half-delivered multipart messages.
                response = client.post(url+'/sendPhoto', data={'chat_id': cfg['telegram_chat_id'],
                    'caption': text[:1000], 'protect_content': 'true'}, files={'photo': ('cat.jpg', photo, 'image/jpeg')})
            else:
                response = client.post(url+'/sendMessage', json=payload)
        result = response.json()
        if response.status_code == 429 and row['attempts'] < 3:
            state, retry = 'queued', now+min(3600, max(30, result.get('parameters', {}).get('retry_after', 60)))
        elif response.is_success and result.get('ok'):
            state, retry = 'sent', 0
        else:
            state, retry = 'failed', 0
    except Exception:
        # A timeout may have delivered the message. Retrying could duplicate an alert.
        state, retry = 'unknown', 0
    with store.db() as db:
        db.execute('UPDATE notices SET state=?,next_at=? WHERE id=?', (state, retry, row['id']))
    return True
