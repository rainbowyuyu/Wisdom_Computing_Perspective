"""Interactive local GitHub OAuth setup. No credential CLI flags or network.

Only writes the project's explicitly selected .env, preserves unrelated bindings,
and never prints credentials. --check and --guide are read-only and offline.
"""
from __future__ import annotations

import argparse
import codecs
from contextlib import contextmanager
import getpass
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from urllib.parse import urlencode
import warnings

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from dotenv.parser import parse_stream
from server.auth import load_config

KEYS=('GITHUB_CLIENT_ID','GITHUB_CLIENT_SECRET','PUBLIC_SITE_URL')


class SetupError(ValueError):
    """Public messages are fixed and never contain input or file contents."""


def read_env(path):
    path=Path(path)
    if path.is_symlink():raise SetupError('拒绝通过符号链接修改配置，请使用项目实际 .env 文件。')
    if not path.exists():return b'',{},[]
    if not path.is_file() or path.stat().st_size>1_048_576:raise SetupError('配置文件不可用或超过大小限制。')
    raw=path.read_bytes()
    try:bindings=list(parse_stream(io.StringIO(raw.decode('utf-8-sig'))))
    except UnicodeError:raise SetupError('配置文件须使用 UTF-8 编码。') from None
    if any(binding.error for binding in bindings):raise SetupError('现有 .env 含无法解析的配置行；请先修复，原文件未修改。')
    return raw,{b.key:b.value for b in bindings if b.key is not None},bindings


def local_urls(port=3088):
    if type(port) is not int or not 1<=port<=65535:raise SetupError('本机端口必须在 1 至 65535 之间。')
    homepage=f'http://127.0.0.1:{port}'
    callback=homepage+'/api/auth/github/callback'
    query={'oauth_application[name]':'Wiscomper Local',
        'oauth_application[url]':homepage,'oauth_application[callback_url]':callback,
        'oauth_application[description]':'Wiscomper 智算视界 · Wisdom Computer Perspective 本机登录'}
    return {'homepage':homepage,'callback_url':callback,
            'create_app_url':'https://github.com/settings/applications/new?'+urlencode(query)}


def effective_settings(values,environment=None):
    environment=os.environ if environment is None else environment
    return {**values,**environment}


def check(path,environment=None,port=None):
    _,saved,_=read_env(path)
    environment=os.environ if environment is None else environment
    values=effective_settings(saved,environment)
    config=load_config(values)
    try:port=int(port if port is not None else values.get('VISUALIZE_PORT') or 3088)
    except (ValueError,TypeError):raise SetupError('VISUALIZE_PORT 无效。') from None
    urls=local_urls(port)
    public_mode=bool(values.get('PUBLIC_SITE_URL'))
    callback=config.public_site_url+'/api/auth/github/callback' if config.public_site_url else urls['callback_url'] if not public_mode else None
    return {'configured':config.configured,
        'client_id_present':bool(values.get('GITHUB_CLIENT_ID')),
        'client_secret_present':bool(values.get('GITHUB_CLIENT_SECRET')),
        'public_mode':public_mode,'callback_url':callback,
        'environment_overrides':[key for key in KEYS if key in environment],
        'message':config.message,'remote_authorization_verified':False,'network_request':False}


def render_env(raw,bindings,values):
    """Keep every unrelated original binding byte-for-byte, including multiline."""
    text=raw.decode('utf-8-sig')
    newline='\r\n' if '\r\n' in text else '\n'
    replacements={key:key+'='+"'"+value.replace('\\','\\\\').replace("'","\\'")+"'" for key,value in values.items()}
    seen=set();parts=[]
    for binding in bindings:
        original=binding.original.string
        if binding.key not in replacements:
            parts.append(original);continue
        leading=re.match(r'\s*',original).group()
        if binding.key not in seen:
            parts.append(leading+replacements[binding.key]+newline);seen.add(binding.key)
        else:
            # Drop duplicate values, retaining their leading blank lines.
            parts.append(leading)
    output=''.join(parts)
    if output and not output.endswith(('\r','\n')):output+=newline
    output+=''.join(replacements[key]+newline for key in values if key not in seen)
    return (codecs.BOM_UTF8 if raw.startswith(codecs.BOM_UTF8) else b'')+output.encode('utf-8')


@contextmanager
def config_lock(path):
    lock=path.with_name(path.name+'.github-setup.lock')
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:raise SetupError('另一个配置操作正在进行；请待其完成。若上次意外中断，请确认后移除 .env.github-setup.lock。') from None
    try:yield
    finally:
        os.close(fd);lock.unlink(missing_ok=True)


def configure(path,client_id,client_secret,*,environment=None):
    """Called only after hidden terminal input; arguments never reach argv/logs."""
    path=Path(path).absolute()
    if not path.parent.is_dir():raise SetupError('配置文件所在目录不存在。')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',client_id or ''):
        raise SetupError('Client ID 格式无效，请复制 GitHub OAuth App 的 Client ID。')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,1024}',client_secret or ''):
        raise SetupError('Client Secret 格式无效，请复制 GitHub OAuth App 新生成的 Secret。')
    write_local_fields(path,{'GITHUB_CLIENT_ID':client_id,'GITHUB_CLIENT_SECRET':client_secret,'PUBLIC_SITE_URL':''},environment=environment)


def save_client_id(path,client_id,*,environment=None):
    """Save an already authorized public Client ID without altering other fields."""
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',client_id or ''):
        raise SetupError('Client ID 格式无效，请复制 GitHub OAuth App 的 Client ID。')
    write_local_fields(path,{'GITHUB_CLIENT_ID':client_id},environment=environment)


def write_local_fields(path,fields,*,environment=None):
    path=Path(path).absolute()
    if not path.parent.is_dir():raise SetupError('配置文件所在目录不存在。')
    environment=os.environ if environment is None else environment
    if any(key in environment for key in KEYS):
        raise SetupError('当前进程存在 GitHub 或站点配置覆盖；请先从终端环境移除这些覆盖，再运行本机配置。')
    with config_lock(path):
        raw,saved,bindings=read_env(path)
        if saved.get('PUBLIC_SITE_URL'):
            raise SetupError('当前文件配置了公网地址；本机助手不会覆盖公网环境，请使用独立的本机配置。')
        changed=render_env(raw,bindings,fields)
        staged=None
        try:
            fd,name=tempfile.mkstemp(prefix='.'+path.name+'.github-',suffix='.tmp',dir=path.parent)
            staged=Path(name)
            with os.fdopen(fd,'wb') as stream:
                stream.write(changed);stream.flush();os.fsync(stream.fileno())
            if path.exists():os.chmod(staged,stat.S_IMODE(path.stat().st_mode))
            if path.is_symlink() or (path.read_bytes() if path.exists() else b'')!=raw:
                raise SetupError('配置文件在操作期间发生变化，已取消覆盖；请重新运行。')
            os.replace(staged,path)
        finally:
            if staged is not None:staged.unlink(missing_ok=True)


def hidden_input(prompt):
    if not sys.stdin.isatty():raise SetupError('请在本机交互终端运行配置；不要把密钥放到命令行参数或管道。')
    with warnings.catch_warnings():
        warnings.simplefilter('error',getpass.GetPassWarning)
        try:return getpass.getpass(prompt)
        except getpass.GetPassWarning:raise SetupError('终端不支持隐藏输入，已停止；请改用 PowerShell 或 Windows Terminal。') from None


def main(argv=None):
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description='Wiscomper 本机 GitHub OAuth 安全配置（无网络请求）')
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--check',action='store_true',help='只报告字段存在、配置状态与回调地址')
    group.add_argument('--guide',action='store_true',help='输出本机 OAuth App 注册链接，不修改配置')
    parser.add_argument('--env-file',type=Path,default=ROOT/'.env',help='显式配置文件；默认本工程 .env')
    parser.add_argument('--port',type=int,default=None,help='仅检查/指南显示的本机端口，默认读取配置或3088')
    args=parser.parse_args(argv)
    try:
        if args.guide:
            status=check(args.env_file,port=args.port)
            if status['public_mode']:raise SetupError('当前配置为公网模式；本机指南不会改写公网地址。')
            port=urlsplit_port(status['callback_url'])
            print(json.dumps(local_urls(port),ensure_ascii=False,indent=2));return 0
        if args.check:
            status=check(args.env_file,port=args.port)
            print(json.dumps(status,ensure_ascii=False,indent=2));return 0 if status['configured'] else 2
        if args.port is not None:raise SetupError('--port 仅用于 --check 或 --guide；修改服务端口请显式编辑 VISUALIZE_PORT。')
        _,saved,_=read_env(args.env_file)
        existing_id=saved.get('GITHUB_CLIENT_ID') or ''
        client_id=hidden_input('GitHub Client ID（隐藏输入，回车保留已保存值）: ' if existing_id else 'GitHub Client ID（隐藏输入）: ')
        if not client_id:client_id=existing_id
        client_secret=hidden_input('GitHub Client Secret（隐藏输入）: ')
        configure(args.env_file,client_id,client_secret)
        print('GitHub 本机配置已原子保存，其他配置保持原样。请重启工作台，然后从页面完成 GitHub 授权。')
        print('本次仅保存本地配置；没有请求 GitHub，也没有验证实际授权。')
        return 0
    except (SetupError,KeyboardInterrupt,EOFError) as error:
        print(str(error) if isinstance(error,SetupError) else '配置已取消。',file=sys.stderr);return 1
    except Exception:
        print('配置未完成，请检查文件权限与终端环境。未输出密钥或原始错误。',file=sys.stderr);return 1


def urlsplit_port(url):
    from urllib.parse import urlsplit
    return urlsplit(url).port or 3088


if __name__=='__main__':raise SystemExit(main())
