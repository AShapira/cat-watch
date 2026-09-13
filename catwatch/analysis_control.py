"""Persisted, one-attempt scheduling shared by the app and Windows controller."""
import json
import time

KINDS = ('video_description', 'detector_comparison')
ACTIVE = ('checking', 'processing', 'stage_complete')


class AnalysisControlStore:
    def analysis_status(self, session_id=None):
        with self.db() as db:
            if session_id is None:
                # An explicit attempt on older evidence takes precedence over the latest session.
                for row in db.execute('SELECT session_id,body FROM analysis_control ORDER BY session_id DESC'):
                    state=json.loads(row['body'])
                    if state['phase'] in ACTIVE or state.get('owner'):
                        session_id=row['session_id']
                        break
            session = self.investigation(session_id)
            if not session:
                return {'session_id':None,'phase':'idle','allowed_kind':None,'attempt':0,'pending':{}}
            row = db.execute('SELECT body FROM analysis_control WHERE session_id=?',(session['id'],)).fetchone()
            body = json.loads(row[0])
            pending = {kind:db.execute("SELECT count(*) FROM analysis_jobs j JOIN motions m ON m.id=j.motion_id WHERE m.session_id=? AND j.kind=? AND j.status='queued'",(session['id'],kind)).fetchone()[0] for kind in KINDS}
        return dict(body,session_id=session['id'],capture_end=session['end']+5,pending=pending,description_settings={k:v for k,v in session['settings'].items() if k.startswith('description_')})

    def update_analysis(self, updates, attempt=None, session_id=None):
        with self.db() as db:
            state = self.analysis_status(session_id)
            if state['session_id'] is None:
                raise ValueError('No investigation')
            if attempt is not None and attempt != state['attempt']:
                raise ValueError('Analysis attempt changed; refresh status')
            state.update(updates)
            sid = state.pop('session_id')
            state.pop('pending',None)
            state.pop('description_settings',None)
            state.pop('capture_end',None)
            db.execute('UPDATE analysis_control SET body=? WHERE session_id=?',(json.dumps(state),sid))
        return self.analysis_status(sid)

    def request_analysis(self, session_id=None):
        with self.db():
            current=self.analysis_status()
            latest=self.investigation()
            state = self.analysis_status(session_id)
            if state['session_id'] is None or time.time()<latest['end']+5:
                raise ValueError('Wait for capture and evidence padding to finish')
            if current['phase'] in ACTIVE or current.get('owner'):
                raise ValueError('An analysis attempt or owned service cleanup is already active')
            return self.update_analysis({'attempt':state['attempt']+1,'phase':'checking',
                'allowed_kind':None,'checked_kinds':[],'skipped':[],'retry':{},
                'message':'Checking GPU availability once'},session_id=state['session_id'])

    def control_analysis(self, body):
        allowed = {'attempt','session_id','phase','allowed_kind','message','owner','checked_kinds','skipped'}
        if set(body)-allowed or type(body.get('attempt')) is not int:
            raise ValueError('Invalid analysis control update')
        if 'session_id' in body and (type(body['session_id']) is not int or body['session_id']<=0):
            raise ValueError('Invalid investigation ID')
        if body.get('phase') not in ('checking','processing','blocked','complete'):
            raise ValueError('Invalid analysis phase')
        kind = body.get('allowed_kind')
        if kind is not None and kind not in KINDS:
            raise ValueError('Invalid analysis kind')
        for key in ('checked_kinds','skipped'):
            if key in body and (not isinstance(body[key],list) or any(not isinstance(x,str) for x in body[key])):
                raise ValueError('Invalid analysis stage list')
        if any(k not in KINDS for k in body.get('checked_kinds',[])):
            raise ValueError('Invalid checked analysis kind')
        if body.get('owner') is not None and not isinstance(body['owner'],dict):
            raise ValueError('Invalid service ownership')
        with self.db():
            state = self.analysis_status()
            if body.get('session_id',state['session_id']) != state['session_id']:
                raise ValueError('Analysis investigation changed; refresh status')
            if state['phase'] in ('waiting_capture','idle') or time.time()<state['capture_end']:
                raise ValueError('No analysis attempt is ready')
            if kind and (body['phase']!='processing' or state['phase'] not in ACTIVE):
                raise ValueError('A permit requires an active attempt')
            if body['phase']=='processing' and not kind:
                raise ValueError('Processing requires an admitted kind')
            return self.update_analysis({k:v for k,v in body.items() if k not in ('attempt','session_id')},body['attempt'],state['session_id'])

    def pause_analysis(self, message):
        return self.update_analysis({'phase':'blocked','allowed_kind':None,'message':message})

    def complete_analysis_stage(self, kind):
        with self.db():
            state = self.analysis_status()
            if state.get('allowed_kind') == kind:
                return self.update_analysis({'phase':'stage_complete','allowed_kind':None,
                    'message':kind+' finished'})

    def requeue_job(self, jid):
        with self.db() as db:
            db.execute("UPDATE analysis_jobs SET status='queued',error=NULL,updated=? WHERE id=?",(time.time(),jid))
