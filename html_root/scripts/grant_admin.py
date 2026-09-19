"""Provision an administrator using a verified password, never a public signup flag."""
import argparse
import getpass
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bcrypt
from app.database import apply_migrations,transaction


def grant(username,password,create=False):
    apply_migrations()
    with transaction() as (_,cur):
        cur.execute('SELECT id,username,hashed_password FROM users WHERE username=%s FOR UPDATE',(username,))
        user=cur.fetchone()
        if user:
            if user['username']!=username or not bcrypt.checkpw(password.encode(),user['hashed_password'].encode()):
                raise ValueError('账户或密码校验失败，未修改任何权限。')
            ident=user['id']
        else:
            if not create:raise ValueError('账户不存在。需要创建时显式使用 --create。')
            cur.execute('INSERT INTO users(username,hashed_password) VALUES(%s,%s)',(username,bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode()))
            ident=cur.lastrowid
        cur.execute("INSERT INTO account_access(user_id,role) VALUES(%s,'admin') ON DUPLICATE KEY UPDATE role='admin',disabled=0",(ident,))
        cur.execute('INSERT INTO access_audit(actor_id,target_id,action,details) VALUES(%s,%s,%s,%s)',(ident,ident,'provision_admin',json.dumps({'source':'server_cli'})))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username',required=True);parser.add_argument('--create',action='store_true')
    args=parser.parse_args()
    grant(args.username,getpass.getpass('Account password: '),args.create)
    print('Administrator account verified and enabled.')
