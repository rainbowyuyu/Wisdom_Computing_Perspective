# 认证：验证码、注册、登录、登出、当前用户、用户名查重
import logging
import uuid
import bcrypt
from typing import Optional
from fastapi import APIRouter, Response, Cookie, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..config import get_db_connection
from ..store import CAPTCHA_STORE, SESSION_STORE
from ..request_origin import public_scheme
from ..models import AuthModel
from logic.captcha import generate_captcha_image_bytes

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])


@router.get("/captcha")
async def get_captcha():
    text, img_buf = generate_captcha_image_bytes()
    captcha_id = str(uuid.uuid4())
    CAPTCHA_STORE[captcha_id] = text.upper()
    if len(CAPTCHA_STORE) > 1000:
        keys = list(CAPTCHA_STORE.keys())
        for k in keys[:500]:
            del CAPTCHA_STORE[k]
    return StreamingResponse(img_buf, media_type="image/png", headers={"X-Captcha-ID": captcha_id})


@router.post("/register")
def register(data: AuthModel):
    stored_code = CAPTCHA_STORE.pop(data.captcha_id, None)
    if not stored_code:
        return JSONResponse(status_code=400, content={"status": "error", "message": "验证码已过期，请刷新"})
    if stored_code != data.captcha.upper():
        return JSONResponse(status_code=400, content={"status": "error", "message": "验证码错误"})

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE username = %s", (data.username,))
        if cursor.fetchone():
            return JSONResponse(status_code=400, content={"status": "error", "message": "用户名已存在"})
        hashed_pw = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
        cursor.execute("INSERT INTO users (username, hashed_password) VALUES (%s, %s)", (data.username, hashed_pw))
        conn.commit()
        return {"status": "success", "message": "注册成功"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "message": "账户服务暂不可用，请稍后重试。"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.post("/login")
def login(data: AuthModel, response: Response, request: Request):
    stored_code = CAPTCHA_STORE.pop(data.captcha_id, None)
    if not stored_code or stored_code != data.captcha.upper():
        return JSONResponse(status_code=400, content={"status": "error", "message": "验证码错误"})

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (data.username,))
        user = cursor.fetchone()
        if user and bcrypt.checkpw(data.password.encode(), user["hashed_password"].encode()):
            from ..access import load_principal, AccessDenied
            try:principal=load_principal(user['username'])
            except AccessDenied as error:return JSONResponse(status_code=error.status,content={'status':'error','message':str(error),'code':error.code})
            session_id = str(uuid.uuid4())
            SESSION_STORE[session_id] = user["username"]
            secure = public_scheme(request.scope, request.headers) == 'https'
            response.set_cookie(key="auth_session", value=session_id, max_age=86400, httponly=True, samesite="lax", secure=bool(secure))
            return {"status": "success", "username": user["username"],"role":principal['role']}
        return JSONResponse(status_code=401, content={"status": "error", "message": "用户名或密码错误"})
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "message": "账户服务暂不可用，请稍后重试。"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get("/user/me")
def get_current_user(auth_session: Optional[str] = Cookie(None)):
    if not auth_session:
        return JSONResponse(status_code=401, content={"status": "error", "message": "Not logged in"})
    username = SESSION_STORE.get(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "Session expired"})
    from ..access import load_principal
    principal=load_principal(username)
    return {"status": "success", "username": username,"role":principal['role']}


@router.get("/user/check-username")
async def check_username(username: str = Query(..., max_length=64)):
    raw = username.strip()
    if not raw:
        return {"available": False}
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE username = %s", (raw,))
        exists = cursor.fetchone() is not None
        return {"available": not exists}
    except Exception as e:
        return JSONResponse(status_code=500, content={"available": False, "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.post("/logout")
async def logout(response: Response, auth_session: Optional[str] = Cookie(None)):
    if auth_session and auth_session in SESSION_STORE:
        del SESSION_STORE[auth_session]
    response.delete_cookie(key="auth_session")
    return {"status": "success", "message": "Logged out"}
