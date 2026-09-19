"""Persistent, atomic admission control for every provider call (including retries)."""
import asyncio
from contextvars import ContextVar
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace
import uuid
from openai import APIConnectionError

identity = ContextVar('usage_identity', default=None)
request_cancelled = ContextVar('request_cancelled', default=None)


def check_request_active():
    cancelled=request_cancelled.get()
    if cancelled is not None and cancelled.is_set():
        raise UsageDenied('请求已结束，已取消尚未开始的模型调用。',0)


def limit(name, default):
    try:
        return max(0, int(os.getenv(name, default)))
    except ValueError:
        return default


class UsageDenied(Exception):
    def __init__(self, message, retry_after=60):
        super().__init__(message)
        self.retry_after = retry_after


class UsageBusy(UsageDenied):
    """Only capacity pressure is eligible for waiting; budget errors never retry."""


class UsageLedger:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute('CREATE TABLE IF NOT EXISTS usage (bucket TEXT, period TEXT, value INTEGER NOT NULL, PRIMARY KEY(bucket, period))')
            db.execute('CREATE TABLE IF NOT EXISTS leases (id TEXT PRIMARY KEY, owner TEXT, expires REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS provider_circuit (provider TEXT PRIMARY KEY, failures INTEGER NOT NULL, last_failure REAL NOT NULL, blocked_until REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS failed_requests (digest TEXT PRIMARY KEY, retries INTEGER NOT NULL, expires REAL NOT NULL)')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def admit(self, category, who, tokens=0):
        if who is None:
            raise UsageDenied('无法确认调用来源，请刷新网页后重试。')
        ip, user = who
        digest = lambda value: hashlib.sha256(value.encode()).hexdigest()[:32]
        owner = digest('user:' + user if user else 'ip:' + ip)
        ip_key = digest(ip)
        now = time.time()
        day = time.strftime('%Y-%m-%d', time.gmtime(now))
        minute = str(int(now // 60))
        if category == 'ai':
            from . import access
            try:
                principal=access.load_principal(user)
            except UsageDenied:raise
            except Exception as error:raise UsageDenied('账户权限暂不可用，本次未调用 AI。') from error
            if limit('AI_ENABLED', 1) == 0:
                raise UsageDenied('AI 服务暂已关闭，仍可阅读例题和使用本地计算。', 3600)
            if not user and not access.feature_authorized.get():
                raise UsageDenied('请从网页开始试用，试用结束后登录可使用完整功能。', 0)
            checks = [
                ('ai:global', day, 1, limit('AI_GLOBAL_DAILY_CALLS', 300)),
                ('ai:minute:' + owner, minute, 1, limit('AI_CALLS_PER_MINUTE', 6)),
                ('ai:tokens', day, tokens, limit('AI_DAILY_TOKEN_RESERVE', 2000000)),
            ]
            if not user:
                checks.append(('ai:ip:'+ip_key,day,1,limit('AI_IP_DAILY_CALLS',80)))
            maximum = limit('AI_MAX_CONCURRENT', 4)
            per_owner = max(1, min(2, limit('AI_USER_CONCURRENT', 2)))
            ttl = 100  # provider timeout is at most 70 s; survives caller cancellation
        else:
            checks = [('request:' + ip_key, minute, 1, limit('API_REQUESTS_PER_MINUTE', 30))]
            maximum, per_owner, ttl = 12, 2, 1800  # includes bounded preview/repair/video phases
        lease = category + ':' + uuid.uuid4().hex
        try:
            with self.connection() as db:
                db.execute('DELETE FROM leases WHERE expires < ?', (now,))
                # Only daily ISO periods older than a week and old minute windows.
                old_day = time.strftime('%Y-%m-%d', time.gmtime(now - 7 * 86400))
                db.execute('DELETE FROM usage WHERE (length(period)=10 AND period LIKE ? AND period < ?) OR (period NOT LIKE ? AND CAST(period AS INTEGER) < ?)', ('____-__-__', old_day, '%-%', int(now // 60) - 2))
                active, personal = db.execute('SELECT COUNT(*), COALESCE(SUM(owner=?),0) FROM leases WHERE id LIKE ?', (owner, category + ':%')).fetchone()
                for bucket, period, cost, ceiling in checks:
                    row = db.execute('SELECT value FROM usage WHERE bucket=? AND period=?', (bucket, period)).fetchone()
                    if (row[0] if row else 0) + cost > ceiling:
                        daily = period == day
                        if category == 'ai' and not daily:
                            raise UsageBusy('正在等待账户的下一调用时段，排队不扣除额度。')
                        raise UsageDenied('今日 AI 使用额度已达上限，请稍后再来；例题和本地计算仍可使用。' if daily else '操作太频繁，请一分钟后再试。', int(86400 - now % 86400) if daily else 60)
                if active >= maximum or personal >= per_owner:
                    raise UsageBusy('正在等待生成资源，请稍后再试。')
                for bucket, period, cost, _ in checks:
                    db.execute('INSERT INTO usage VALUES (?,?,?) ON CONFLICT(bucket,period) DO UPDATE SET value=value+excluded.value', (bucket, period, cost))
                db.execute('INSERT INTO leases VALUES (?,?,?)', (lease, owner, now + ttl))
            return lease
        except (sqlite3.Error, OSError) as error:
            raise UsageDenied('额度服务暂不可用，本次未调用 AI，请稍后再试。') from error

    def release(self, lease):
        try:
            with self.connection() as db:
                db.execute('DELETE FROM leases WHERE id=?', (lease,))
        except (sqlite3.Error, OSError):
            pass  # fail closed until the lease expires

    def reserve_duplicate(self, key):
        lease='duplicate:'+key
        try:
            with self.connection() as db:
                db.execute('DELETE FROM leases WHERE expires < ?',(time.time(),))
                if db.execute('SELECT 1 FROM leases WHERE id=?',(lease,)).fetchone():
                    raise UsageDenied('相同请求正在处理中，请等待当前结果，不要重复提交。',3)
                db.execute('INSERT INTO leases VALUES(?,?,?)',(lease,key,time.time()+1800))
            return lease
        except (sqlite3.Error,OSError) as error:
            raise UsageDenied('请求保护暂不可用，本次未开始生成，请稍后重试。') from error

    def claim_failed_retry(self, digest):
        """Only server-observed failures qualify, under the duplicate lease.

        Hash-only receipts survive restarts. Two retries within 24 hours are
        free of personal quota; provider budgets and admission still apply.
        """
        try:
            with self.connection() as db:
                now=time.time()
                db.execute('DELETE FROM failed_requests WHERE expires < ?', (now,))
                row=db.execute('SELECT retries,expires FROM failed_requests WHERE digest=?', (digest,)).fetchone()
                if row is None:return False
                if row[0]>=2:
                    raise UsageDenied('本题已连续重试两次仍未完成，已暂停继续生成，未扣额外额度。请检查题目、拆分后再提交，或稍后再试。', max(1,int(row[1]-now)))
                db.execute('UPDATE failed_requests SET retries=retries+1 WHERE digest=?', (digest,))
                return True
        except (sqlite3.Error,OSError) as error:
            raise UsageDenied('重试记录暂不可用，本次未开始生成，也未扣额度，请稍后重试。') from error

    def finish_failed_retry(self, digest, failed):
        with self.connection() as db:
            if failed:
                db.execute('INSERT INTO failed_requests VALUES(?,0,?) ON CONFLICT(digest) DO NOTHING', (digest,time.time()+86400))
            else:
                db.execute('DELETE FROM failed_requests WHERE digest=?', (digest,))

    def check_provider(self,provider):
        try:
            with self.connection() as db:
                row=db.execute('SELECT blocked_until FROM provider_circuit WHERE provider=?',(provider,)).fetchone()
                if row and row[0]>time.time():
                    remaining=max(1,int(row[0]-time.time()))
                    raise UsageDenied(f'模型服务暂时不稳定，已暂停重复调用以保护额度；请约 {remaining} 秒后重试。',remaining)
        except (sqlite3.Error,OSError) as error:
            raise UsageDenied('模型保护服务暂不可用，本次未调用模型。') from error

    def provider_result(self,provider,started,error=None):
        status=getattr(error,'status_code',None)
        failure=isinstance(error,(APIConnectionError,TimeoutError)) or status in {401,403,429} or (status is not None and status>=500)
        if error is not None and not failure:return
        try:
            with self.connection() as db:
                row=db.execute('SELECT failures,last_failure,blocked_until FROM provider_circuit WHERE provider=?',(provider,)).fetchone()
                now=time.time()
                if error is None:
                    # Older in-flight successes must not clear a newer outage.
                    if row and row[1]<=started:db.execute('DELETE FROM provider_circuit WHERE provider=?',(provider,))
                    return
                failures=(row[0] if row and now-row[1]<120 else 0)+1
                cooldown=300 if status in {401,403} else 60 if status==429 else 30 if failures>=3 else 0
                until=max(row[2] if row else 0,now+cooldown if cooldown else 0)
                db.execute('INSERT INTO provider_circuit VALUES(?,?,?,?) ON CONFLICT(provider) DO UPDATE SET failures=excluded.failures,last_failure=excluded.last_failure,blocked_until=excluded.blocked_until',
                           (provider,failures,now,until))
        except (sqlite3.Error,OSError):
            pass  # Next admission checks the same database and fails closed.


ledger = UsageLedger(os.getenv('USAGE_DB_PATH', str(Path(__file__).resolve().parents[1] / 'var' / 'usage.sqlite3')))


def bounded_request(kwargs):
    """Reserve conservative text-byte + image allowance; this is not a billing meter."""
    if kwargs.get('stream') or kwargs.get('n', 1) != 1:
        raise UsageDenied('暂不支持此模型调用方式。')
    kwargs = dict(kwargs)
    cap = min(10000, limit('AI_MAX_OUTPUT_TOKENS', 7000))
    kwargs['max_tokens'] = max(1, min(int(kwargs.pop('max_completion_tokens', kwargs.get('max_tokens', cap))), cap))
    size = 0
    for message in kwargs.get('messages', []):
        content = message.get('content', '')
        if isinstance(content, list):
            for part in content:
                if part.get('type') == 'image_url':
                    url = part.get('image_url', {}).get('url', '')
                    if not url.startswith('data:image/') or len(url) > 8_000_000:
                        raise UsageDenied('请使用不超过 5 MB 的本地图片。')
                    size += 32768
                else:
                    size += len(json.dumps(part, ensure_ascii=False).encode('utf-8'))
        else:
            size += len(str(content).encode('utf-8'))
        size += 64
    if size > 160000:
        raise UsageDenied('输入过长，请拆成一道题或一个修改目标后再试。')
    return kwargs, size + kwargs['max_tokens']


class GuardedClient:
    """Only the used completion API is exposed; with_options cannot bypass limits."""
    def __init__(self, provider, asynchronous=False):
        self._provider = provider
        self.api_key, self.base_url = provider.api_key, provider.base_url
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.acreate if asynchronous else self.create))
        # Hash includes the configured credential: rotating it permits recovery,
        # without ever persisting the credential or raw provider errors.
        self._circuit_key=hashlib.sha256((str(provider.base_url)+'\0'+str(provider.api_key)).encode()).hexdigest()

    def with_options(self, **kwargs):
        return self

    def create(self, **kwargs):
        kwargs, tokens = bounded_request(kwargs)
        check_request_active()
        ledger.check_provider(self._circuit_key)
        self.authorize_feature()
        deadline = time.monotonic() + min(60, limit('AI_QUEUE_TIMEOUT', 60))
        while True:
            try:
                check_request_active()
                ledger.check_provider(self._circuit_key)
                lease = ledger.admit('ai', identity.get(), tokens)
                break
            except UsageBusy:
                if time.monotonic() >= deadline:
                    raise UsageDenied('等待 AI 资源超时，请稍后重试；排队期间未调用模型。')
                time.sleep(.5)
        started=time.time()
        try:
            check_request_active()
            result=self._provider.with_options(timeout=70, max_retries=0).chat.completions.create(**kwargs)
            ledger.provider_result(self._circuit_key,started)
            return result
        except Exception as error:
            ledger.provider_result(self._circuit_key,started,error)
            raise
        finally:
            ledger.release(lease)

    async def acreate(self, **kwargs):
        kwargs, tokens = bounded_request(kwargs)
        check_request_active()
        await asyncio.to_thread(ledger.check_provider,self._circuit_key)
        await asyncio.to_thread(self.authorize_feature)
        deadline = time.monotonic() + min(60, limit('AI_QUEUE_TIMEOUT', 60))
        while True:
            try:
                check_request_active()
                await asyncio.to_thread(ledger.check_provider,self._circuit_key)
                # Admission is a short DB transaction. Shield it so cancellation
                # cannot lose an admitted lease while its thread is still running.
                admission = asyncio.create_task(asyncio.to_thread(ledger.admit, 'ai', identity.get(), tokens))
                try:
                    lease = await asyncio.shield(admission)
                except asyncio.CancelledError:
                    try:
                        unused = await admission
                        await asyncio.to_thread(ledger.release, unused)
                    except UsageDenied:
                        pass
                    raise
                break
            except UsageBusy:
                if time.monotonic() >= deadline:
                    raise UsageDenied('等待 AI 资源超时，请稍后重试；排队期间未调用模型。')
                await asyncio.sleep(.5)
        started=time.time()
        try:
            check_request_active()
            result=await asyncio.wait_for(self._provider.with_options(timeout=70, max_retries=0).chat.completions.create(**kwargs),70)
            await asyncio.to_thread(ledger.provider_result,self._circuit_key,started)
            return result
        except asyncio.CancelledError:
            # The provider may still bill a cancelled request. Retain the short lease.
            lease = None
            raise
        except Exception as error:
            await asyncio.to_thread(ledger.provider_result,self._circuit_key,started,error)
            if isinstance(error,TimeoutError):lease=None
            raise
        finally:
            if lease:
                await asyncio.to_thread(ledger.release, lease)

    @staticmethod
    def authorize_feature():
        # Optional/background provider entry points (e.g. AI formula tagging)
        # cannot bypass daily feature quotas when no metered route admitted them.
        from . import access
        if not access.feature_authorized.get():
            who=identity.get()
            if not who or not who[1]:raise UsageDenied('请从网页开始试用，试用结束后登录可使用完整功能。')
            access.consume('assistant',who)


def run_with_context(_executor, func, *args):
    """Replacement for legacy run_in_executor, preserving the caller's quota identity."""
    return asyncio.create_task(asyncio.to_thread(func, *args))
