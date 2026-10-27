"""Real email routes with a synthetic mail sink and isolated legacy database."""
from test_model_access import web,login  # noqa: F401


def mail_sink(accounts):
    delivered=[]
    accounts.get_settings().update(SMTP_HOST='smtp.test.invalid',SMTP_USERNAME='test@example.com',
                             SMTP_PASSWORD='synthetic-only',SMTP_FROM='test@example.com',EMAIL_CODE_SECRET='test-only-'*8)
    accounts.sender=lambda email,code,purpose:delivered.append((email,code,purpose))
    return delivered


def test_register_logout_and_reset_use_single_use_codes_and_rotated_sessions(web):
    api,accounts,client,headers,_=web
    delivered=mail_sink(accounts)
    send=client.post('/api/auth/email/send-code',headers=headers,json={'email':'new@example.com','purpose':'register'})
    assert send.status_code==200,send.text
    assert len(delivered)==1
    old_sid=client.cookies.get(api.COOKIE)
    response=client.post('/api/auth/email/register',headers=headers,json={'username':'new-reader','password':'test-only-password',
                        'email':'new@example.com','code':delivered[-1][1]})
    assert response.status_code==200,response.text
    data=response.json();headers['x-csrf-token']=data['csrf']
    assert data['authenticated'] and data['user']['email_verified'] and data['user']['role']=='member'
    assert '_credential_version' not in response.text and 'SMTP' not in response.text
    assert api.STORE.session_identity(old_sid) is None
    signed_sid=client.cookies.get(api.COOKIE)
    # A second existing device session must be revoked when the password resets.
    identity=api.STORE.session_identity(signed_sid)
    api.STORE.create_session('synthetic-second-device','second-csrf',owner=identity['owner'],account_id=identity['account_id'])
    response=client.post('/api/auth/logout',headers=headers,json={})
    assert response.status_code==200,response.text
    headers['x-csrf-token']=response.json()['csrf']
    # Advance just the synthetic mailbox's cooldown, without wall-clock sleeps.
    with accounts.transaction(write=True) as cur:
        cur.execute('UPDATE account_email_limits SET window_start=%s',('2000-01-01 00:00:00',))
    response=client.post('/api/auth/email/send-code',headers=headers,json={'email':'new@example.com','purpose':'reset'})
    assert response.status_code==200,response.text
    reset={'email':'new@example.com','new_password':'new-test-only-password','code':delivered[-1][1]}
    response=client.post('/api/auth/email/reset',headers=headers,json=reset)
    assert response.status_code==200,response.text
    assert api.STORE.session_identity('synthetic-second-device') is None
    assert client.post('/api/auth/email/reset',headers=headers,json=reset).status_code==400
    assert accounts.authenticate('new@example.com','new-test-only-password')['username']=='new-reader'


def test_existing_account_can_fill_empty_email_and_verify_without_fetch_recursion(web):
    _,accounts,client,headers,uid=web
    delivered=mail_sink(accounts)
    with accounts.transaction(write=True) as cur:
        cur.execute('UPDATE users SET email=NULL,email_verified=0 WHERE id=%s',(uid,))
    response=client.post('/api/auth/email/login',headers=headers,json={'identifier':'old-user','password':'test-only-password'})
    assert response.status_code==200,response.text
    data=response.json();headers['x-csrf-token']=data['csrf']
    assert data['user']['email']=='' and not data['user']['email_verified']
    response=client.post('/api/auth/email/send-code',headers=headers,json={'email':'bound@example.com','purpose':'verify'})
    assert response.status_code==200,response.text
    response=client.post('/api/auth/email/verify',headers=headers,json={'email':'bound@example.com','code':delivered[-1][1]})
    assert response.status_code==200,response.text
    assert response.json()['user']['email_verified'] and response.json()['model_access']['allowed']==['qwen']
    assert client.get('/api/auth/session').json()['user']['email']=='bound@example.com'
