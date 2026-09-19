"""Bounded, asynchronous request journal. Never persist raw payloads or headers."""
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import queue
import re
import threading
import time
import uuid

from .database import transaction

logger=logging.getLogger(__name__)
request_record_id=ContextVar('request_record_id',default=None)
ROUTES={'/api/solve/stream':'calculate','/api/solve/render':'render',
        '/api/animate':'calculate','/api/animate/stream':'render',
        '/api/detect':'recognize','/api/agent/execute':'assistant',
        '/api/agent/tasks':'task','/api/devtools/edit_code':'code',
        '/api/devtools/generate_video_copy':'code','/api/devtools/run_manim':'render',
        '/api/devtools/run_manim_stream':'render','/api/devtools/render_keyframe':'render'}
STATUSES={'processing','completed','failed','rejected','cancelled','interrupted',
          'handoff','partial','needs_information','queued','planning','running','blocked'}


def clean_text(value):
    if not isinstance(value,str):return ''
    text=value[:12000]
    text=re.sub(r'(?i)\b(?:sk-[\w-]{8,}|Bearer\s+[\w.\-+/=]{8,})','[凭据已隐藏]',text)
    text=re.sub(r'(?i)((?:api[_-]?key|token|password|cookie|authorization|密码)\s*[=:：]\s*)[^\s,;，；]+',r'\1[凭据已隐藏]',text)
    text=re.sub(r'data:image/[^;]+;base64,[\w+/=]+','[图片]',text)
    return text.replace('\x00','')


def input_summary(path,body,content_type):
    if path=='/api/detect':return '',True,False
    if 'json' not in content_type:return '',False,False
    try:data=json.loads(body)
    except (ValueError,UnicodeError):return '',False,False
    if not isinstance(data,dict):return '',False,False
    # Only task text is retained. Code, history, image bytes and tool settings
    # may contain provider credentials and must never become management data.
    if path in {'/api/solve/stream','/api/agent/tasks'}:parts=[data.get('problem'),data.get('context')]
    elif path=='/api/agent/execute':parts=[data.get('prompt')]
    elif path.startswith('/api/animate'):parts=[data.get('matrixA'),data.get('matrixB'),data.get('vision_prompt')]
    elif path=='/api/solve/render':
        solution=data.get('solution') or {}
        parts=[solution.get('title'),solution.get('task_goal')] if isinstance(solution,dict) else []
    elif path=='/api/devtools/edit_code':parts=[data.get('instruction') or data.get('prompt')]
    else:parts=[]
    text='\n\n'.join(p for p in parts if isinstance(p,str))
    return clean_text(text),bool(data.get('image_base64')),len(text)>12000


def device_label(agent):
    platform=next((label for key,label in [('Android','Android'),('iPhone','iOS'),('iPad','iPadOS'),('Windows','Windows'),('Macintosh','macOS'),('Linux','Linux')] if key in agent),'其他系统')
    browser=next((label for key,label in [('Edg/','Edge'),('Firefox/','Firefox'),('Chrome/','Chrome'),('Safari/','Safari')] if key in agent),'其他浏览器')
    return platform+' / '+browser


class Journal:
    def __init__(self):
        self.queue=queue.Queue(maxsize=512)
        self.lock=threading.Lock();self.worker=None;self.stopping=False
        self.dropped=0;self.failed=0

    def put(self,kind,data):
        with self.lock:
            if self.stopping:return False
            if self.worker is None:
                self.worker=threading.Thread(target=self._run,name='request-journal',daemon=True)
                self.worker.start()
            try:self.queue.put_nowait((kind,data));return True
            except queue.Full:self.dropped+=1;return False

    def _run(self):
        last_cleanup=0
        while True:
            item=self.queue.get()
            try:
                if item is None:return
                kind,data=item
                with transaction() as (_,cur):
                    if kind=='start':
                        columns=tuple(data)
                        cur.execute('INSERT INTO request_records ('+','.join(columns)+') VALUES ('+','.join(['%s']*len(columns))+')',tuple(data.values()))
                    elif kind=='finish':
                        ident=data.pop('id');columns=tuple(data)
                        assignments=[c+'=IF(job_id IS NULL,%s,'+c+')' if c in {'status','duration_ms'}
                                     else 'job_id=COALESCE(%s,job_id)' if c=='job_id' else c+'=%s' for c in columns]
                        cur.execute('UPDATE request_records SET '+','.join(assignments)+' WHERE id=%s',(*data.values(),ident))
                    elif kind=='job':
                        cur.execute('UPDATE request_records SET status=%s,duration_ms=%s,job_id=%s WHERE job_id=%s OR id=%s',data)
                    if time.monotonic()-last_cleanup>3600:
                        cur.execute('DELETE FROM request_records WHERE created_at < UTC_TIMESTAMP() - INTERVAL 90 DAY LIMIT 500')
                        # Requests that outlive the maximum server execution window
                        # are interrupted, never silently displayed as successful.
                        cur.execute("UPDATE request_records SET status='interrupted' WHERE status IN ('processing','queued','planning','running') AND updated_at < UTC_TIMESTAMP() - INTERVAL 2 HOUR LIMIT 500")
                        last_cleanup=time.monotonic()
            except Exception as error:
                self.failed+=1
                logger.warning('Request journal write unavailable (%s)',type(error).__name__)
            finally:self.queue.task_done()

    def flush(self,timeout=5):
        end=time.monotonic()+timeout
        while self.queue.unfinished_tasks and time.monotonic()<end:time.sleep(.02)
        return not self.queue.unfinished_tasks

    def close(self):
        with self.lock:self.stopping=True
        self.flush()
        if self.worker:
            try:self.queue.put_nowait(None)
            except queue.Full:return
            self.worker.join(timeout=3)


journal=Journal()


class RequestRecord:
    def __init__(self,path,principal,body,content_type,agent):
        self.id=uuid.uuid4().hex;self.path=path;self.started=time.monotonic()
        problem,image,truncated=input_summary(path,body,content_type)
        self.status='processing';self.code=None;self.sse=False;self.buffer=b'';self.overflow=False
        self.problem=problem;self.job_id=None;self.finished=False
        self.saved=journal.put('start',dict(id=self.id,owner_id=principal.get('id') if principal else None,
            username=principal.get('username') or '' if principal else '',role=principal.get('role','guest') if principal else 'guest',
            feature=ROUTES[path],endpoint=path,problem=problem,has_image=image,content_truncated=truncated,
            device=device_label(agent),created_at=datetime.now(timezone.utc).replace(tzinfo=None)))

    def observe_data(self,data):
        if not isinstance(data,dict):return
        kind=data.get('type') or data.get('status')
        if kind=='error':self.status='failed'
        elif kind=='handoff':self.status='handoff'
        elif kind in {'complete','success'}:
            solution=data.get('solution') or {}
            completion=solution.get('completion') if isinstance(solution,dict) else None
            self.status=completion if completion in {'partial','needs_information'} else 'completed'
        if self.path=='/api/detect' and kind=='success':self.problem=clean_text(data.get('problem_text') or data.get('latex'))
        if self.path=='/api/agent/tasks' and isinstance(data.get('id'),str) and re.fullmatch('[a-f0-9]{32}',data['id']):
            self.job_id=data['id'];self.status=data.get('status') if data.get('status') in STATUSES else 'queued'

    def observe(self,message):
        if message['type']=='http.response.start':
            self.code=message['status']
            self.sse=any(k.lower()==b'content-type' and b'text/event-stream' in v for k,v in message.get('headers',[]))
        elif message['type']=='http.response.body':
            # Stop retaining an overlong frame until its next boundary. Never
            # buffer an entire video, stream, response or traceback in memory.
            for part in message.get('body',b'').splitlines(keepends=True) if self.sse else [message.get('body',b'')]:
                if not self.overflow:self.buffer+=part
                if len(self.buffer)>1_000_000:self.buffer=b'';self.overflow=True
                if self.sse and part.strip()==b'':
                    if not self.overflow:
                        for line in self.buffer.splitlines():
                            if line.startswith(b'data:'):
                                try:self.observe_data(json.loads(line[5:]))
                                except (ValueError,UnicodeError):pass
                    self.buffer=b'';self.overflow=False
            if not message.get('more_body',False):
                if not self.sse and not self.overflow:
                    try:self.observe_data(json.loads(self.buffer))
                    except (ValueError,UnicodeError):pass
                self.finished=True

    def finish(self):
        if not self.saved:return
        if self.code and self.code>=400:self.status='rejected' if self.code<500 else 'failed'
        elif not self.finished:self.status='cancelled'
        elif self.status=='processing':self.status='interrupted' if self.sse else 'completed'
        journal.put('finish',dict(id=self.id,status=self.status,http_status=self.code,
            duration_ms=min(int((time.monotonic()-self.started)*1000),4294967295),job_id=self.job_id,problem=self.problem))


def job_progress(job):
    status={'done':'completed','error':'failed'}.get(job['status'],job['status'])
    if status not in STATUSES:return
    journal.put('job',(status,min(max(0,int((time.time()-job['created'])*1000)),4294967295),job['id'],job['id'],job.get('journal_id')))
