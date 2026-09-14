"""Restartable bridge: export media, publish tasks, synchronize labels and snapshots."""
from datetime import datetime, timezone
import logging
import json
import os
from pathlib import Path
import shutil
import threading
import time
import uuid

from .client import Client
from .contracts import RESOURCES, TAXONOMY, canonical
from .media import BudgetExceeded, CaptureResumed, Corpus, sha256
from .storage import LabelingStore


class LabelingService:
    def __init__(self, store, runtime, config=None, client=None):
        self.store, self.runtime = store, runtime
        self.db = LabelingStore(store)
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.config = config
        self.corpus = self.client = None
        self.error = None
        self.last_success = self.db.get('last_success')
        self.retry_at = 0
        self.failures = 0
        self.project_id = self.db.get('project_id')
        if config:
            root = Path(config['dataset_root']).resolve()
            if root.is_relative_to(store.root.resolve()) or store.root.resolve().is_relative_to(root):
                raise ValueError('Dataset and recorder storage must be separate directories')
            self.corpus = Corpus(root, self.db.get('dataset_id'), int(config.get('cap_bytes', 100_000_000_000)),
                                 int(config.get('disk_floor_bytes', 5_000_000_000)), config.get('ffmpeg', 'ffmpeg'))
            self.client = client or Client(config.get('url', 'http://127.0.0.1:8767'), config['token_file'], config.get('token_type', 'pat'))

    @classmethod
    def from_environment(cls, store, runtime):
        path = os.environ.get('CATWATCH_LABELING_CONFIG')
        try:
            return cls(store, runtime, json.loads(Path(path).read_text()) if path else None)
        except (OSError, ValueError, KeyError, TypeError):
            service = cls(store, runtime)
            service.error = 'Labeling configuration or dataset unavailable; recorder remains operational.'
            return service

    def start(self):
        if self.config and self.thread is None:
            self.thread = threading.Thread(target=self.run, name='catwatch-labeling', daemon=True)
            self.thread.start()

    def shutdown(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=20)

    def capture_busy(self):
        if self.stop.is_set():
            return True
        session = self.store.investigation()
        return bool(self.runtime.state.get('capture_busy') or self.runtime.state.get('live_model_loaded')
                    or self.runtime.segment_queue.unfinished_tasks or self.runtime.frame_queue.unfinished_tasks
                    or (session and time.time() < session['end']+5))

    def status(self):
        tasks = self.db.tasks()
        return {'enabled': bool(self.config), 'url': self.client.url if self.client else None,
                'project_id': self.project_id, 'error': self.error, 'last_success': self.last_success,
                'retry_at': self.retry_at, 'jobs': self.db.jobs(),
                'tasks': len(tasks), 'reviewed': sum(t['state']=='reviewed' for t in tasks),
                'used_bytes': self.corpus.usage() if self.corpus else 0,
                'cap_bytes': self.corpus.cap if self.corpus else 100_000_000_000,
                'capture_busy': self.capture_busy()}

    def public_tasks(self, group_id=None):
        return [{'task_key': t['task_key'], 'group_id': t['group_id'], 'session_id': t['session_id'],
                 'state': t['state'], 'error': t['error'], 'remote_id': t['remote_id'],
                 'url': f'{self.client.url}/projects/{self.project_id}/data?task={t["remote_id"]}' if self.client and t['remote_id'] else None,
                 'annotation': t['current_annotation']} for t in self.db.tasks(group_id)]

    def require_enabled(self):
        if not self.config:
            raise ValueError('Configure and start the local Label Studio integration first')

    def queue(self, session_id):
        self.require_enabled()
        count = self.db.queue(session_id)
        self.wake.set()
        return {'groups': count}

    def retry(self):
        self.require_enabled()
        with self.store.db() as db:
            db.execute("UPDATE labeling_jobs SET state='queued',error=NULL WHERE state IN ('failed','quota','source_missing')")
            db.execute("INSERT INTO labeling_sync(remote_id,payload,created) VALUES (NULL,'{}',?)", (time.time(),))
        self.retry_at, self.failures = 0, 0
        self.wake.set()

    def webhook(self, payload):
        self.require_enabled()
        action = payload.get('action')
        if action not in ('ANNOTATION_CREATED', 'ANNOTATION_UPDATED', 'ANNOTATIONS_DELETED', 'TASKS_DELETED', 'TASK_DELETED'):
            raise ValueError('Unsupported Label Studio event')
        project = payload.get('project', {})
        project_id = project.get('id') if isinstance(project, dict) else project
        if project_id is not None and project_id != self.project_id:
            raise ValueError('Webhook belongs to a different project')
        remote_id = payload.get('annotation', {}).get('task')
        with self.store.db() as db:
            db.execute('INSERT INTO labeling_sync(remote_id,payload,created) VALUES (?,?,?)',
                       (remote_id if isinstance(remote_id, int) else None, canonical(payload), time.time()))
        self.wake.set()

    def ensure_project(self):
        self.project_id = self.client.project(self.config.get('project_id') or self.project_id,
            self.db.get('dataset_id'), (RESOURCES/'config.xml').read_text(), (RESOURCES/'guide.md').read_text())
        self.db.set('project_id', self.project_id)
        # 1.23 requires project-owned local storage even for API-created tasks.
        # Never sync this storage: the bridge alone creates stable, deduplicated tasks.
        storage_path = self.config.get('label_studio_dataset_root', str(self.corpus.root)).rstrip('/')+'/clips'
        storages = self.client.request(f'/api/storages/localfiles/?project={self.project_id}')
        if isinstance(storages, dict):
            storages = storages.get('results', [])
        if not any(s.get('path', '').rstrip('/') == storage_path for s in storages):
            self.client.request('/api/storages/localfiles/', 'POST', {
                'project': self.project_id, 'title': 'cat-watch immutable clips (do not sync)',
                'path': storage_path, 'regex_filter': '^$', 'use_blob_urls': True,
                'recursive_scan': True})
        # Register only the narrow annotation events. Full reconciliation covers deletion and outages.
        secret = Path(self.config['webhook_secret_file']).read_text().strip()
        hooks = self.client.request(f'/api/webhooks/?project={self.project_id}')
        if isinstance(hooks, dict):
            hooks = hooks.get('results', [])
        url = self.config.get('callback_url', 'http://127.0.0.1:8765/api/labeling/webhook')
        existing = [h for h in hooks if h.get('url') == url]
        body = {'project': self.project_id, 'url': url, 'is_active': True, 'send_payload': True,
                'send_for_all_actions': False, 'actions': ['ANNOTATION_CREATED', 'ANNOTATION_UPDATED', 'ANNOTATIONS_DELETED'],
                'headers': {'X-Catwatch-Labeling-Token': secret}}
        if existing:
            self.client.request(f'/api/webhooks/{existing[0]["id"]}/', 'PATCH', body)
        else:
            self.client.request('/api/webhooks/', 'POST', body)

    def task_data(self, task):
        manifest = task['manifest']
        group = self.store.motion_group_detail(task['group_id'])
        notes = '\n'.join(w['text'] for j in group['descriptions'] for w in j['windows'])[:16000]
        return {'task_key': task['task_key'], 'video': '/data/local-files/?d='+manifest['video_path'],
                'fps': manifest['fps'], 'session_id': task['session_id'], 'group_id': task['group_id'],
                'cat_detected': bool(group['samples']), 'areas': sorted({a for sample in group['samples'] for d in sample['detections'] for a in d.get('areas', [])}),
                'context': f'Investigation {task["session_id"]}, motion group {task["group_id"]}. Captured {datetime.fromtimestamp(manifest['capture_start'], timezone.utc).isoformat()}. '
                           + 'One cat. Mark full or partial coverage. '+manifest['timing_note']+' Boundaries: '+canonical(manifest['boundary_flags']),
                'model_notes': notes or 'No model description yet.',
                'diagnostics': f'<a href="http://127.0.0.1:8765/?session_id={int(task["session_id"])}&amp;group_id={int(task["group_id"])}#investigation" target="_blank" rel="noopener">Open cat-watch diagnostics</a>'}

    def reconcile(self):
        remote = list(self.client.tasks(self.project_id))
        by_key = {}
        for task in remote:
            key = task.get('data', {}).get('task_key')
            if key in by_key:
                raise ValueError('Duplicate Label Studio task key; resolve the duplicate before continuing')
            if key:
                by_key[key] = task
        for task in self.db.tasks():
            if self.stop.is_set():
                return
            key = task['task_key']
            if task['suppressed']:
                continue
            found = by_key.get(key)
            if found is None and task['remote_id']:
                self.db.ingest(task, [])
                self.db.update_task(key, state='deleted', suppressed=1)
                continue
            if found is None:
                # A lost POST response is recovered by the next complete remote listing.
                found = self.client.request('/api/tasks/', 'POST', {'project': self.project_id, 'data': self.task_data(task)})
            detail = self.client.request(f'/api/tasks/{found["id"]}/')
            if detail.get('data', {}).get('task_key') != key:
                raise ValueError('Remote task identity mismatch')
            self.db.update_task(key, remote_id=found['id'])
            self.db.ingest(task, detail.get('annotations', []), detail.get('updated_at'))
            data = self.task_data(task)
            if data != detail.get('data'):
                self.client.request(f'/api/tasks/{found["id"]}/', 'PATCH', {'data': data})
        self.last_success, self.error = time.time(), None
        self.db.set('last_success', self.last_success)

    def export_one(self):
        if self.capture_busy():
            return
        for session in self.store.sessions():
            if session['start'] >= self.db.get('auto_after'):
                current = self.store.investigation(session['id'])
                if time.time() >= current['end']+5:
                    self.db.queue(session['id'])
        job = next((j for j in self.db.jobs() if j['state'] in ('queued', 'running')), None)
        if not job:
            return
        gid = job['group_id']
        from ..analysis import evidence_lease
        group = self.store.motion_group_detail(gid)
        self.db.job_state(gid, 'running')
        try:
            with evidence_lease(self.runtime, group['start']-5, group['end']+5):
                # Re-read under lease: retention might have removed an earlier snapshot.
                group = self.store.motion_group_detail(gid)
                self.corpus.export_group(self.store, group, self.capture_busy, self.db.add_task)
            self.db.job_state(gid, 'complete')
            with self.store.db() as db:
                db.execute("INSERT INTO labeling_sync(payload,created) VALUES ('{}',?)", (time.time(),))
        except CaptureResumed:
            self.db.job_state(gid, 'queued')
        except BudgetExceeded:
            self.db.job_state(gid, 'quota', 'Dataset quota or free-space reserve reached')
        except FileNotFoundError:
            self.db.job_state(gid, 'source_missing', 'Source footage is unavailable')
        except Exception:
            logging.getLogger(__name__).exception('Clip export failed for group %s', gid)
            self.db.job_state(gid, 'failed', 'Clip export failed; inspect media and retry')

    def request_snapshot(self):
        self.require_enabled()
        ident = uuid.uuid4().hex
        with self.store.db() as db:
            db.execute("INSERT INTO dataset_exports VALUES (?,'queued',?,NULL,NULL)", (ident, time.time()))
        self.wake.set()
        return {'id': ident, 'state': 'queued'}

    def snapshot_status(self, ident):
        with self.store.db() as db:
            row = db.execute('SELECT * FROM dataset_exports WHERE id=?', (ident,)).fetchone()
        if row is None:
            raise KeyError(ident)
        return dict(row)

    def snapshot(self, ident):
        self.require_enabled()
        self.snapshot_status(ident)
        self.reconcile()  # Never export silently stale human labels.
        destination = self.corpus.root/'exports'/ident
        if destination.exists():
            saved = json.loads((destination/'manifest.json').read_text())
            if saved['id'] != ident or saved['dataset_id'] != self.db.get('dataset_id'):
                raise ValueError('Export identity mismatch')
            for name, digest in saved['files'].items():
                if Path(name).name != name or sha256(destination/name) != digest:
                    raise ValueError('Export integrity mismatch')
            with self.store.db() as db:
                db.execute("UPDATE dataset_exports SET state='complete',path=? WHERE id=?", (f'exports/{ident}', ident))
            return
        import tempfile
        with tempfile.TemporaryDirectory(dir=self.corpus.root/'temporary') as tmp:
            root = Path(tmp)
            tasks = self.db.tasks()
            report = self.db.report()
            conflicts = report['conflicts']
            rows, manifests, raw = [], [], []
            for task in tasks:
                ann = task['current_annotation']
                if task['state'] != 'reviewed' or task['suppressed'] or not ann:
                    continue
                manifest = task['manifest']
                if sha256(self.corpus.path(manifest['video_path'])) != manifest['video_hash']:
                    raise ValueError('Dataset media hash mismatch')
                manifests.append(manifest)
                with self.store.db() as db:
                    raw.extend(dict(r) for r in db.execute('SELECT * FROM labeling_revisions WHERE task_key=? ORDER BY id', (task['task_key'],)))
                from .contracts import source_intervals
                for item in ann['intervals']:
                    contested = any(max(a, x)<min(b, y) for a, b in source_intervals(manifest, item) for x, y in conflicts)
                    category = 'unclear' if item['label']=='unclear' else 'negative' if item['label']=='no_cat' else 'activity'
                    rows.append(dict(item, task_key=task['task_key'], video_path=manifest['video_path'],
                        taxonomy_version=1, annotation_id=ann['annotation_id'], completed_by=ann['completed_by'],
                        quality=ann['quality'], category=category, group_key=f'{manifest["dataset_id"]}/{task["session_id"]}',
                        supervised_eligible=ann['supervised_eligible'] and not contested and category!='unclear',
                        exclusion_reason='overlap_conflict' if contested else 'multiple_cats' if not ann['supervised_eligible'] else 'unclear' if category=='unclear' else None))
            (root/'taxonomy.json').write_text(canonical(TAXONOMY))
            shutil.copyfile(RESOURCES/'guide.md', root/'guide.md')
            for name, data in [('intervals.jsonl', rows), ('clips.jsonl', manifests), ('annotations.jsonl', raw)]:
                (root/name).write_text(''.join(canonical(row)+'\n' for row in data))
            hashes = {p.name: sha256(p) for p in root.iterdir()}
            summary = {'id': ident, 'dataset_id': self.db.get('dataset_id'), 'taxonomy_version': 1,
                       'created': time.time(), 'files': hashes, 'clips': len(manifests), 'intervals': len(rows),
                       'source_hashes': sorted({r['source_hash'] for m in manifests for r in m['mapping']}),
                       'media_root_relative_to_export': '../..', 'split_policy': 'Assign entire investigations; never split adjacent frames.'}
            for digest in summary['source_hashes']:
                if sha256(self.corpus.root/'sources'/f'{digest}.mp4') != digest:
                    raise ValueError('Dataset source hash mismatch')
            (root/'manifest.json').write_text(canonical(summary))
            self.corpus.budget()
            destination = self.corpus.root/'exports'/ident
            os.replace(root, destination)
        with self.store.db() as db:
            db.execute("UPDATE dataset_exports SET state='complete',path=? WHERE id=?", (f'exports/{ident}', ident))

    def run(self):
        next_sync = 0
        while not self.stop.is_set():
            if self.retry_at and time.time() < self.retry_at:
                self.wake.wait(1)
                self.wake.clear()
                continue
            try:
                self.export_one()
                with self.store.db() as db:
                    marker = db.execute('SELECT MAX(id) FROM labeling_sync').fetchone()[0]
                    export = db.execute("SELECT id FROM dataset_exports WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
                if marker or time.time() >= next_sync or export:
                    self.ensure_project()
                    self.reconcile()
                    if marker:
                        with self.store.db() as db:
                            db.execute('DELETE FROM labeling_sync WHERE id<=?', (marker,))
                    next_sync = time.time()+300
                if export and not self.capture_busy():
                    try:
                        self.snapshot(export[0])
                    except Exception:
                        with self.store.db() as db:
                            db.execute("UPDATE dataset_exports SET state='failed',error='Snapshot failed integrity, synchronization or quota checks' WHERE id=?", (export[0],))
                self.failures, self.retry_at = 0, 0
            except Exception:
                self.failures += 1
                delay = (30, 120, 300)[min(self.failures-1, 2)]
                self.retry_at = time.time()+delay
                self.error = 'Label Studio synchronization unavailable; retrying. Check the service, credentials and project configuration.'
            self.wake.wait(1)
            self.wake.clear()
