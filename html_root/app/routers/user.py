# 用户：设置、资料、修改用户名/密码、头像上传
import json
import logging
import os
import re
import uuid
import bcrypt
from typing import Optional
from fastapi import APIRouter, Cookie, File, UploadFile
from fastapi.responses import JSONResponse

from ..config import get_db_connection, AVATAR_DIR, ALLOWED_AVATAR_EXT
from ..store import SESSION_STORE
from ..models import UserSettingsModel, UserProfileModel, ChangeUsernameModel, ChangePasswordModel
from ..email_service import mask_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/user", tags=["user"])


def _username_from_session(auth_session: Optional[str] = None):
    if not auth_session:
        return None
    return SESSION_STORE.get(auth_session)


@router.get('/stats')
def user_stats(auth_session: Optional[str] = Cookie(None)):
    """One small account-owned response instead of four full content lists."""
    username=_username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401,content={'status':'error','message':'请先登录'})
    from ..database import transaction
    with transaction() as (_,cursor):
        cursor.execute('''SELECT
            (SELECT COUNT(*) FROM formulas WHERE user_id=%s) AS formulas,
            (SELECT COUNT(*) FROM animation_scripts WHERE user_id=%s) AS scripts,
            (SELECT COUNT(*) FROM agent_templates WHERE user_id=%s) AS templates,
            (SELECT COUNT(*) FROM learning_wrongbook WHERE owner_id=(SELECT id FROM users WHERE username=%s)) AS wrongbook''',
            (username,username,username,username))
        return {'status':'success','data':cursor.fetchone()}


@router.get("/settings")
def get_user_settings(auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "Not logged in"})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT settings_json FROM user_settings WHERE user_id = %s", (username,))
        row = cursor.fetchone()
        out = {}
        if row and row.get("settings_json"):
            try:
                out = json.loads(row["settings_json"]) if isinstance(row["settings_json"], str) else (row["settings_json"] or {})
            except Exception:
                pass
        return {"status": "success", "settings": out}
    except Exception as e:
        logger.error("get_user_settings: %s", type(e).__name__)
        return JSONResponse(status_code=500, content={"status": "error", "message": "服务暂不可用，请稍后重试。"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.put("/settings")
def put_user_settings(data: UserSettingsModel, auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "Not logged in"})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        js = json.dumps(data.settings, ensure_ascii=False)
        cursor.execute(
            """INSERT INTO user_settings (user_id, settings_json, updated_at)
               VALUES (%s, %s, CURRENT_TIMESTAMP)
               ON DUPLICATE KEY UPDATE settings_json = VALUES(settings_json), updated_at = CURRENT_TIMESTAMP""",
            (username, js),
        )
        conn.commit()
        return {"status": "success", "message": "Settings saved"}
    except Exception as e:
        logger.error("put_user_settings: %s", type(e).__name__)
        return JSONResponse(status_code=500, content={"status": "error", "message": "服务暂不可用，请稍后重试。"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get("/profile")
def get_user_profile(auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "Not logged in"})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''SELECT p.avatar_url, p.nickname, u.email, u.email_verified, u.email_verified_at
            FROM users u LEFT JOIN user_profiles p ON p.user_id = u.username
            WHERE u.username = %s''', (username,))
        row = cursor.fetchone()
        out = {"username": username, "avatar_url": None, "nickname": None,
               "email": '', "email_verified": False, "email_verified_at": None}
        if row:
            out["avatar_url"] = row.get("avatar_url")
            out["nickname"] = row.get("nickname")
            out["email"] = mask_email(row.get("email"))
            # 当前账户本人使用，便于设置页直接发起邮箱验证；页面展示仍使用脱敏值。
            out["email_address"] = row.get("email") or ''
            out["email_verified"] = bool(row.get("email_verified"))
            out["email_verified_at"] = row.get("email_verified_at")
        return {"status": "success", "profile": out}
    except Exception as e:
        logger.error("get_user_profile: %s", type(e).__name__)
        return JSONResponse(status_code=500, content={"status": "error", "message": "服务暂不可用，请稍后重试。"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.put("/profile")
def put_user_profile(data: UserProfileModel, auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "Not logged in"})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        nickname = (data.nickname or "").strip()[:128] if data.nickname else None
        avatar_url = (data.avatar_url or "").strip()[:512] if data.avatar_url else None
        if avatar_url:
            # Avatar ownership is established only by the upload transaction.
            # A profile edit cannot point at somebody else's file or a tracking URL.
            cursor.execute('SELECT avatar_url FROM user_profiles WHERE user_id=%s', (username,))
            current = cursor.fetchone()
            if not current or current[0] != avatar_url:
                return JSONResponse(status_code=400, content={'status':'error','message':'请通过上传图片更换头像。'})
        cursor.execute(
            """INSERT INTO user_profiles (user_id, avatar_url, nickname, updated_at)
               VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
               ON DUPLICATE KEY UPDATE
               avatar_url = COALESCE(VALUES(avatar_url), avatar_url),
               nickname = COALESCE(VALUES(nickname), nickname),
               updated_at = CURRENT_TIMESTAMP""",
            (username, avatar_url, nickname),
        )
        conn.commit()
        return {"status": "success", "message": "资料已更新"}
    except Exception as e:
        logger.error("put_user_profile: %s", type(e).__name__)
        return JSONResponse(status_code=500, content={"status": "error", "message": "服务暂不可用，请稍后重试。"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.put("/username")
def change_username(data: ChangeUsernameModel, auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "Not logged in"})
    from ..access import load_principal, is_owner
    if is_owner(load_principal(username)):
        return JSONResponse(status_code=403,content={'status':'error','message':'主管理员账号名受保护，请保留当前账号名。'})
    new_username = (data.new_username or "").strip()[:64]
    if not new_username or new_username == username:
        return JSONResponse(status_code=400, content={"status": "error", "message": "新用户名无效或未变更"})
    if len(data.password.encode()) > 72:
        return JSONResponse(status_code=400, content={'status':'error','message':'密码不能超过 72 字节。'})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, hashed_password FROM users WHERE username = %s FOR UPDATE", (username,))
        user = cursor.fetchone()
        if not user or not bcrypt.checkpw(data.password.encode(), user["hashed_password"].encode()):
            return JSONResponse(status_code=401, content={"status": "error", "message": "当前密码错误"})
        cursor.execute("SELECT id FROM users WHERE username = %s", (new_username,))
        if cursor.fetchone():
            return JSONResponse(status_code=400, content={"status": "error", "message": "该用户名已被占用"})
        cursor.execute("UPDATE users SET username = %s WHERE username = %s", (new_username, username))
        # FK-backed tables cascade. Legacy username-owned tables must move in the
        # same transaction; the new notebook's numeric owner_id stays stable.
        for table in ('formulas','animation_scripts','agent_templates','user_profiles','user_settings',
                      'formula_topics','user_achievements','user_wrongbook','course_packs',
                      'example_play_history','example_video_comments','example_video_danmaku',
                      'example_video_likes','example_video_notes','user_favorites','watch_later'):
            cursor.execute('SELECT COUNT(*) AS n FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s',(table,))
            if cursor.fetchone()['n']:
                cursor.execute(f'UPDATE `{table}` SET user_id=%s WHERE user_id=%s',(new_username,username))
        for token,name in list(SESSION_STORE.items()):
            if name==username:SESSION_STORE[token]=new_username
        conn.commit()
        return {"status": "success", "username": new_username, "message": "用户名已修改"}
    except Exception as e:
        if conn:conn.rollback()
        logger.error("change_username: %s", type(e).__name__)
        return JSONResponse(status_code=500, content={"status": "error", "message": "服务暂不可用，请稍后重试。"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.put("/password")
def change_password(data: ChangePasswordModel, auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "Not logged in"})
    if len(data.new_password) < 6 or max(len(data.new_password.encode()),len(data.current_password.encode())) > 72:
        return JSONResponse(status_code=400, content={"status": "error", "message": "密码至少 6 位，且不能超过 72 字节。"})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT hashed_password FROM users WHERE username = %s FOR UPDATE", (username,))
        row = cursor.fetchone()
        if not row or not bcrypt.checkpw(data.current_password.encode(), row["hashed_password"].encode()):
            return JSONResponse(status_code=401, content={"status": "error", "message": "当前密码错误"})
        hashed = bcrypt.hashpw(data.new_password.encode(), bcrypt.gensalt()).decode()
        cursor.execute("UPDATE users SET hashed_password = %s WHERE username = %s", (hashed, username))
        # Login and password-reset lock the same account row. Revoke while held
        # so a concurrent login cannot retain a session made with the old hash.
        SESSION_STORE.remove_value(username)
        conn.commit()
        return {"status": "success", "message": "密码已修改，所有设备已退出，请重新登录。", "reauthenticate": True}
    except Exception as e:
        logger.error("change_password: %s", type(e).__name__)
        return JSONResponse(status_code=500, content={"status": "error", "message": "服务暂不可用，请稍后重试。"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.post("/avatar")
def upload_avatar(file: UploadFile = File(...), auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "Not logged in"})
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_AVATAR_EXT:
        return JSONResponse(status_code=400, content={"status": "error", "message": "仅支持 PNG/JPG/GIF/WEBP"})
    conn = cursor = path = None
    committed = False
    old_name = None
    try:
        from ..avatar_image import sanitize_avatar
        content = sanitize_avatar(file.file.read(2 * 1024 * 1024 + 1))
        safe_name = re.sub(r"[^\w\-]", "_", username)[:32]
        fname = f"{safe_name}_{uuid.uuid4().hex}.png"
        conn = get_db_connection()
        cursor = conn.cursor()
        # Serialize replacement so concurrent uploads cannot orphan every file.
        cursor.execute('SELECT id FROM users WHERE username=%s FOR UPDATE', (username,))
        cursor.fetchone()
        cursor.execute('SELECT avatar_url FROM user_profiles WHERE user_id=%s', (username,))
        old_row = cursor.fetchone()
        old_url = (old_row[0] or '') if isinstance(old_row, (tuple, list)) and old_row else ''
        candidate = old_url.removeprefix('/static/avatars/') if isinstance(old_url, str) else ''
        if (isinstance(old_url,str) and old_url.startswith('/static/avatars/') and
                re.fullmatch(re.escape(safe_name)+r'_[a-f0-9]{32}\.(?:png|jpg|jpeg|gif|webp)', candidate)):
            old_name = candidate
        path = os.path.join(AVATAR_DIR, fname)
        with open(path, "wb") as f:
            f.write(content)
        url = f"/static/avatars/{fname}"
        cursor.execute(
            """INSERT INTO user_profiles (user_id, avatar_url, updated_at) VALUES (%s, %s, CURRENT_TIMESTAMP)
               ON DUPLICATE KEY UPDATE avatar_url = VALUES(avatar_url), updated_at = CURRENT_TIMESTAMP""",
            (username, url),
        )
        conn.commit()
        committed = True
        if old_name:
            try: os.remove(os.path.join(AVATAR_DIR, old_name))
            except OSError: pass
        return {"status": "success", "avatar_url": url, "message": "头像已更新"}
    except ValueError as e:
        return JSONResponse(status_code=400, content={'status':'error','message':str(e)})
    except Exception as e:
        logger.error("upload_avatar: %s", type(e).__name__)
        return JSONResponse(status_code=500, content={"status": "error", "message": "服务暂不可用，请稍后重试。"})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
        if path and not committed:
            try: os.remove(path)
            except OSError: pass
