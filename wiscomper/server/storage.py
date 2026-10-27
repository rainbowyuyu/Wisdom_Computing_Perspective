import json
import re
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class RevisionConflict(ValueError):
    """A newer saved scene must not be overwritten by an older operation."""


class ProjectMissing(ValueError):
    pass


class SessionExpired(ValueError):
    pass


class LoginBusy(ValueError):
    pass


ACTIVE_JOB_STATUSES = ('queued','planning','validating','building','rendering','cancelling')
ANONYMOUS_SESSION_TTL = 365 * 86400
ACCOUNT_SESSION_TTL = 30 * 86400

class Store:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock()
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,csrf TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS records(kind TEXT NOT NULL,id TEXT PRIMARY KEY,owner TEXT NOT NULL,updated REAL NOT NULL,payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS records_owner ON records(owner,kind,updated);
            CREATE INDEX IF NOT EXISTS records_request_key ON records(owner,json_extract(payload,'$.request_key')) WHERE kind='job';
            CREATE INDEX IF NOT EXISTS records_project_revision ON records(owner,json_extract(payload,'$.project_id'),json_extract(payload,'$.revision')) WHERE kind='revision';
            CREATE TABLE IF NOT EXISTS budget(day TEXT PRIMARY KEY,reserved INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS account_budget(day TEXT NOT NULL,owner TEXT NOT NULL,reserved INTEGER NOT NULL,PRIMARY KEY(day,owner));
            CREATE TABLE IF NOT EXISTS accounts(owner TEXT PRIMARY KEY,github_id TEXT UNIQUE NOT NULL,profile TEXT NOT NULL,updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS oauth_states(state_hash TEXT PRIMARY KEY,session_id TEXT NOT NULL,verifier TEXT NOT NULL,redirect_uri TEXT NOT NULL,expires REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS oauth_session ON oauth_states(session_id);
            CREATE TABLE IF NOT EXISTS retired_owners(owner TEXT PRIMARY KEY);
            ''')
            columns={row[1] for row in db.execute('PRAGMA table_info(sessions)')}
            for name,kind in [('owner','TEXT'),('account_id','TEXT'),('expires','REAL'),('kind',"TEXT NOT NULL DEFAULT 'browser'"),('scope','TEXT'),('oauth_flow','TEXT'),('credential_version','TEXT')]:
                if name not in columns:db.execute(f'ALTER TABLE sessions ADD COLUMN {name} {kind}')
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()
    def put(self,kind,value):
        with self.lock,self.connect() as db:
            self._write(db,kind,value)
    def _write(self,db,kind,value):
        if db.execute('SELECT 1 FROM retired_owners WHERE owner=?',(value['owner'],)).fetchone():
            raise SessionExpired('登录状态已变化，请刷新工作台后重试。')
        result=db.execute('INSERT INTO records VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated=excluded.updated,payload=excluded.payload WHERE records.kind=excluded.kind AND records.owner=excluded.owner',(kind,value['id'],value['owner'],value.get('updated',time.time()),json.dumps(value,ensure_ascii=False)))
        if result.rowcount!=1:raise ValueError('记录身份不匹配。')
    def create_project(self,project,completed_job):
        with self.lock,self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._write(db,'project',project)
            self._write(db,'job',completed_job)
    def get(self,kind,ident,owner):
        with self.connect() as db:
            row=db.execute('SELECT payload FROM records WHERE kind=? AND id=? AND owner=?',(kind,ident,owner)).fetchone()
        return json.loads(row[0]) if row else None
    def list(self,kind,owner=None,limit=100):
        with self.connect() as db:
            query='SELECT payload FROM records WHERE kind=?';params=[kind]
            if owner:query+=' AND owner=?';params.append(owner)
            rows=db.execute(query+' ORDER BY updated DESC LIMIT ?',(*params,limit)).fetchall()
        return [json.loads(row[0]) for row in rows]
    def session(self,ident):
        value=self.session_identity(ident)
        return value['csrf'] if value else None
    def _identity(self,db,ident,now):
        row=db.execute('SELECT id,csrf,COALESCE(owner,id),account_id,COALESCE(expires,created+?),kind,scope,owner,credential_version FROM sessions WHERE id=?',
                       (ANONYMOUS_SESSION_TTL,ident)).fetchone()
        if not row or row[4]<=now:return None
        value=dict(zip(('id','csrf','owner','account_id','expires','kind','scope'),row))
        value['legacy_cookie']=row[7] is None
        value['credential_version']=row[8]
        value['scope']=json.loads(value['scope']) if value['scope'] else {}
        value['user']=None
        if value['account_id']:
            account=db.execute('SELECT profile FROM accounts WHERE owner=?',(value['account_id'],)).fetchone()
            if not account or value['owner']!=value['account_id']:return None
            value['user']=json.loads(account[0])
        return value
    def session_identity(self,ident):
        if not isinstance(ident,str) or not ident or len(ident)>128:return None
        with self.connect() as db:return self._identity(db,ident,time.time())
    def session_owner(self,ident):
        value=self.session_identity(ident)
        return value['owner'] if value else None
    def _insert_session(self,db,ident,csrf,*,owner=None,account_id=None,expires=None,kind='browser',scope=None):
        now=time.time()
        credential_version=None
        if account_id:
            account=db.execute('SELECT profile FROM accounts WHERE owner=?',(account_id,)).fetchone()
            if account:credential_version=json.loads(account[0]).get('_credential_version')
        # Freeze the credential version at sign-in for this device. A later
        # sign-in must not refresh another device's password validation stamp.
        db.execute('INSERT INTO sessions(id,csrf,created,owner,account_id,expires,kind,scope,credential_version) VALUES (?,?,?,?,?,?,?,?,?)',
                   (ident,csrf,now,owner or ident,account_id,expires or now+ANONYMOUS_SESSION_TTL,kind,json.dumps(scope) if scope else None,credential_version))
    def create_session(self,ident,csrf,**options):
        with self.lock,self.connect() as db:self._insert_session(db,ident,csrf,**options)
    def revoke_session(self,ident):
        with self.lock,self.connect() as db:
            db.execute('DELETE FROM oauth_states WHERE session_id=?',(ident,))
            db.execute('DELETE FROM sessions WHERE id=?',(ident,))
    def _active_jobs(self,db,owner):
        return bool(db.execute("SELECT 1 FROM records WHERE kind='job' AND owner=? AND json_extract(payload,'$.status') IN (?,?,?,?,?,?) LIMIT 1",
                               (owner,*ACTIVE_JOB_STATUSES)).fetchone())
    def has_active_jobs(self,owner):
        with self.connect() as db:return self._active_jobs(db,owner)
    def begin_oauth(self,sid,state_hash,verifier,redirect_uri,expires):
        with self.lock,self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            identity=self._identity(db,sid,time.time())
            if not identity or identity['kind']!='browser':raise SessionExpired('页面会话已失效，请刷新后重新登录。')
            if identity['account_id']:raise ValueError('请先退出当前账号，再切换 GitHub 账号。')
            if self._active_jobs(db,identity['owner']):raise LoginBusy('请先等待当前任务完成或取消任务，再登录。')
            db.execute('DELETE FROM oauth_states WHERE session_id=? OR expires<=?',(sid,time.time()))
            db.execute('INSERT INTO oauth_states VALUES (?,?,?,?,?)',(state_hash,sid,verifier,redirect_uri,expires))
            db.execute('UPDATE sessions SET owner=COALESCE(owner,id),oauth_flow=? WHERE id=?',(state_hash,sid))
    def consume_oauth(self,sid,state_hash):
        with self.lock,self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            identity=self._identity(db,sid,time.time())
            if not identity or identity['kind']!='browser':return None
            row=db.execute('SELECT verifier,redirect_uri,expires FROM oauth_states WHERE state_hash=? AND session_id=?',(state_hash,sid)).fetchone()
            if not row:return None
            db.execute('DELETE FROM oauth_states WHERE state_hash=? AND session_id=?',(state_hash,sid))
            return {'verifier':row[0],'redirect_uri':row[1]} if row[2]>time.time() else None
    def login_github(self,sid,github_id,profile,new_sid,new_csrf,*,expected_flow=None):
        """Move the anonymous namespace and rotate the session in one transaction.

        Call while holding the application's mutation lock as well, so queued
        jobs and the cache cannot race this transaction.
        """
        with self.lock,self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            identity=self._identity(db,sid,time.time())
            if not identity or identity['kind']!='browser' or identity['account_id']:
                raise SessionExpired('页面会话已失效，请刷新后重新登录。')
            if expected_flow is not None:
                flow=db.execute('SELECT oauth_flow FROM sessions WHERE id=?',(sid,)).fetchone()
                if not flow or not secrets.compare_digest(flow[0] or '',expected_flow):
                    raise SessionExpired('登录流程已更新，请完成最新一次授权。')
            old_owner=identity['owner']
            if self._active_jobs(db,old_owner):raise LoginBusy('请先等待当前任务完成或取消任务，再登录。')
            row=db.execute('SELECT owner FROM accounts WHERE github_id=?',(str(github_id),)).fetchone()
            account=row[0] if row else 'account:'+uuid.uuid4().hex
            db.execute('INSERT INTO accounts VALUES (?,?,?,?) ON CONFLICT(github_id) DO UPDATE SET profile=excluded.profile,updated=excluded.updated',
                       (account,str(github_id),json.dumps(profile,ensure_ascii=False),time.time()))
            def rewrite(value):
                if isinstance(value,list):return [rewrite(item) for item in value]
                if isinstance(value,dict):return {key:(account if key=='owner' and item==old_owner else rewrite(item)) for key,item in value.items()}
                return value
            moved_preferences=bool(db.execute("SELECT 1 FROM records WHERE kind='preferences' AND owner=? LIMIT 1",(old_owner,)).fetchone())
            rows=db.execute('SELECT id,payload FROM records WHERE owner=?',(old_owner,)).fetchall()
            for ident,payload in rows:
                db.execute('UPDATE records SET owner=?,payload=? WHERE id=? AND owner=?',
                           (account,json.dumps(rewrite(json.loads(payload)),ensure_ascii=False),ident,old_owner))
            if moved_preferences:
                preferences=db.execute("SELECT id,payload,updated FROM records WHERE kind='preferences' AND owner=? ORDER BY updated DESC,id DESC",(account,)).fetchall()
                if len(preferences)>1:
                    # Merging two namespaces must invalidate stale account tabs,
                    # even when both sources happen to have the same revision.
                    latest=json.loads(preferences[0][1])
                    latest['revision']=max(int(json.loads(item[1]).get('revision',0)) for item in preferences)+1
                    latest['updated']=max(time.time(),preferences[0][2]+0.000001)
                    db.execute("UPDATE records SET updated=?,payload=? WHERE kind='preferences' AND id=? AND owner=?",
                               (latest['updated'],json.dumps(latest,ensure_ascii=False),latest['id'],account))
            for day,reserved in db.execute('SELECT day,reserved FROM account_budget WHERE owner=?',(old_owner,)).fetchall():
                db.execute('INSERT INTO account_budget VALUES (?,?,?) ON CONFLICT(day,owner) DO UPDATE SET reserved=reserved+excluded.reserved',(day,account,reserved))
            db.execute('DELETE FROM account_budget WHERE owner=?',(old_owner,))
            db.execute('DELETE FROM oauth_states WHERE session_id IN (SELECT id FROM sessions WHERE COALESCE(owner,id)=?)',(old_owner,))
            db.execute('DELETE FROM sessions WHERE COALESCE(owner,id)=?',(old_owner,))
            db.execute('INSERT OR IGNORE INTO retired_owners VALUES (?)',(old_owner,))
            self._insert_session(db,new_sid,new_csrf,owner=account,account_id=account,expires=time.time()+ACCOUNT_SESSION_TTL)
            return old_owner,account,self._identity(db,new_sid,time.time())
    def logout_session(self,sid,new_sid,new_csrf):
        with self.lock,self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            identity=self._identity(db,sid,time.time())
            if not identity or identity['kind']!='browser':raise SessionExpired('页面会话已失效，请刷新后重试。')
            db.execute('DELETE FROM oauth_states WHERE session_id=?',(sid,))
            db.execute('DELETE FROM sessions WHERE id=?',(sid,))
            # Anonymous logout preserves its local namespace; account logout gets
            # a new empty anonymous namespace and never moves account records.
            owner=new_sid if identity['account_id'] else identity['owner']
            self._insert_session(db,new_sid,new_csrf,owner=owner)
            return self._identity(db,new_sid,time.time())
    def login_legacy(self,sid,user_id,profile,new_sid,new_csrf,*,namespace):
        """Use a namespaced stable database ID, never a username/email match.

        accounts.github_id is the existing unique external-key column. Real
        GitHub subjects are numeric strings; the legacy prefix is disjoint.
        Existing GitHub accounts and workspace IDs remain untouched.
        """
        if not isinstance(namespace,str) or not re.fullmatch(r'[a-f0-9]{24}',namespace):
            raise ValueError('账户来源无效。')
        if type(user_id) is not int or user_id<=0 or profile.get('id')!=user_id or profile.get('auth_provider')!='email':
            raise ValueError('账户身份无效。')
        return self.login_github(sid,f'legacy:{namespace}:{user_id}',profile,new_sid,new_csrf)
    def get_legacy_user_id(self,owner,*,namespace):
        with self.connect() as db:
            row=db.execute('SELECT github_id FROM accounts WHERE owner=?',(owner,)).fetchone()
        prefix=f'legacy:{namespace}:'
        if not row or not row[0].startswith(prefix):return None
        ident=row[0][len(prefix):]
        return int(ident) if ident.isascii() and ident.isdigit() and int(ident)>0 else None
    def revoke_legacy_sessions(self,user_id,*,namespace):
        """Invalidate browser/render sessions for a reset or disabled identity."""
        with self.lock,self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT owner FROM accounts WHERE github_id=?',(f'legacy:{namespace}:{user_id}',)).fetchone()
            if not row:return 0
            owner=row[0]
            db.execute('DELETE FROM oauth_states WHERE session_id IN (SELECT id FROM sessions WHERE COALESCE(owner,id)=?)',(owner,))
            return db.execute('DELETE FROM sessions WHERE COALESCE(owner,id)=?',(owner,)).rowcount
    def render_session(self,owner,job_id,asset_ids,ttl=900):
        sid=secrets.token_hex(32)
        with self.lock,self.connect() as db:
            job=db.execute("SELECT payload FROM records WHERE kind='job' AND id=? AND owner=?",(job_id,owner)).fetchone()
            if not job or json.loads(job[0]).get('kind')!='export':raise ProjectMissing('导出任务不存在。')
            self._insert_session(db,sid,secrets.token_hex(32),owner=owner,kind='render',
                expires=time.time()+min(900,max(1,ttl)),scope={'job_id':job_id,'asset_ids':list(set(asset_ids))})
        return sid
    def find_request(self,owner,request_key):
        with self.connect() as db:
            row=db.execute("SELECT payload FROM records WHERE kind='job' AND owner=? AND json_extract(payload,'$.request_key')=? ORDER BY updated DESC LIMIT 1",(owner,request_key)).fetchone()
        return json.loads(row[0]) if row else None
    def active_project_job(self,owner,project_id):
        with self.connect() as db:
            row=db.execute("""SELECT payload FROM records WHERE kind='job' AND owner=?
                AND json_extract(payload,'$.kind')='create'
                AND json_extract(payload,'$.target_project_id')=?
                AND json_extract(payload,'$.status') IN ('queued','planning','validating','building','rendering')
                ORDER BY updated DESC LIMIT 1""",(owner,project_id)).fetchone()
        return json.loads(row[0]) if row else None
    def revisions(self,project_id,owner):
        """Filter in SQL before loading metadata, including histories over 100 rows."""
        with self.connect() as db:
            rows=db.execute("""SELECT json_extract(payload,'$.revision'),json_extract(payload,'$.title'),
                json_extract(payload,'$.prompt'),json_extract(payload,'$.change_summary'),
                json_extract(payload,'$.action'),json_extract(payload,'$.updated'),
                json_extract(payload,'$.restored_from') FROM records
                WHERE kind='revision' AND owner=? AND json_extract(payload,'$.project_id')=?
                ORDER BY CAST(json_extract(payload,'$.revision') AS INTEGER) DESC,updated DESC""",(owner,project_id)).fetchall()
        result=[];seen=set()
        for row in rows:
            if row[0] in seen:continue
            seen.add(row[0]);item=dict(zip(('revision','title','prompt','change_summary','action','updated','restored_from'),row))
            item['action']=item['action'] or 'recompute'
            item['change_summary']=item['change_summary'] or (item['prompt'] or '')[:240]
            item['is_current']=False;result.append(item)
        return result
    def revision(self,project_id,revision,owner):
        with self.connect() as db:
            row=db.execute("""SELECT payload FROM records WHERE kind='revision' AND owner=?
                AND json_extract(payload,'$.project_id')=? AND json_extract(payload,'$.revision')=?
                ORDER BY updated DESC LIMIT 1""",(owner,project_id,revision)).fetchone()
        if not row:return None
        value=json.loads(row[0]);value['id']=project_id
        value.pop('project_id',None)
        return value
    def _change_project(self,project_id,owner,expected_revision,transform,versioned,completed_job=None):
        with self.lock,self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT payload FROM records WHERE kind='project' AND id=? AND owner=?",(project_id,owner)).fetchone()
            if not row:raise ProjectMissing('项目不存在或不属于当前会话。')
            current=json.loads(row[0])
            if current.get('revision',1)!=expected_revision:
                raise RevisionConflict('项目已有新版本，请刷新后继续；本次修改没有覆盖当前作品。')
            # The transformer receives the latest exploration, even when a model
            # was working from an older immutable input snapshot.
            changed=transform(json.loads(row[0]))
            if changed.get('id')!=project_id or changed.get('owner')!=owner:
                raise ValueError('记录身份不匹配。')
            changed['created']=current.get('created',changed.get('created',time.time()))
            changed['revision']=expected_revision+1 if versioned else expected_revision
            changed['updated']=time.time()
            encoded=json.dumps(changed,ensure_ascii=False)
            if versioned:
                snapshot={**current,'id':uuid.uuid4().hex,'project_id':project_id}
                db.execute('INSERT INTO records VALUES (?,?,?,?,?)',('revision',snapshot['id'],owner,snapshot.get('updated',time.time()),json.dumps(snapshot,ensure_ascii=False)))
            db.execute("UPDATE records SET updated=?,payload=? WHERE kind='project' AND id=? AND owner=?",(changed['updated'],encoded,project_id,owner))
            if completed_job is not None:self._write(db,'job',completed_job)
        return changed
    def commit_project(self,project_id,owner,expected_revision,transform,*,completed_job=None):
        """Archive the former head and publish its successor in one transaction."""
        return self._change_project(project_id,owner,expected_revision,transform,True,completed_job)
    def update_project_state(self,project_id,owner,expected_revision,transform):
        """Save exploration against the scene revision without creating history spam."""
        return self._change_project(project_id,owner,expected_revision,transform,False)
    def reserve(self,amount,limit,*,owner=None,owner_limit=None):
        # Conservatively reserve the full per-turn step budget, even on failure.
        day=time.strftime('%Y-%m-%d',time.gmtime())
        with self.lock,self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT reserved FROM budget WHERE day=?',(day,)).fetchone();used=row[0] if row else 0
            if used+amount>limit:raise ValueError('今日模型调用预算已用完；仍可使用本地示例、参数推演和已有作品。')
            if owner is not None:
                row=db.execute('SELECT reserved FROM account_budget WHERE day=? AND owner=?',(day,owner)).fetchone()
                account_used=row[0] if row else 0
                if owner_limit is not None and account_used+amount>owner_limit:raise ValueError('今日账号模型额度已用完；仍可使用本地示例、参数推演和已有作品。')
                db.execute('INSERT INTO account_budget VALUES (?,?,?) ON CONFLICT(day,owner) DO UPDATE SET reserved=excluded.reserved',(day,owner,account_used+amount))
            db.execute('INSERT INTO budget VALUES (?,?) ON CONFLICT(day) DO UPDATE SET reserved=excluded.reserved',(day,used+amount))
    def usage(self,owner):
        """Read both counters from one snapshot without reserving any budget."""
        now=time.time();day=time.strftime('%Y-%m-%d',time.gmtime(now))
        reset=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime((int(now)//86400+1)*86400))
        with self.connect() as db:
            db.execute('BEGIN')
            row=db.execute('SELECT reserved FROM budget WHERE day=?',(day,)).fetchone()
            total=row[0] if row else 0
            row=db.execute('SELECT reserved FROM account_budget WHERE day=? AND owner=?',(day,owner)).fetchone()
            account=row[0] if row else 0
        return {'day':day,'reset_at':reset,'site_reserved':total,'account_reserved':account}

def public(value): return {k:v for k,v in dict(value).items() if not k.startswith('_') and k not in {'owner','request_key','digest','export_scene'}}
