# 动画脚本库：保存、列表、获取、删除、更新
import asyncio
import logging
from fastapi import APIRouter, Cookie, HTTPException
from fastapi.responses import JSONResponse

from ..config import get_db_connection
from .solution_library import username_for_session
from ..models import AnimationScriptModel, AnimationScriptUpdateModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/animation_scripts", tags=["animation_scripts"])


@router.post("/save")
def save_animation_script(data: AnimationScriptModel, auth_session: str | None = Cookie(None)):
    if username_for_session(auth_session) != data.username:
        raise HTTPException(status_code=403, detail="无权访问其他账户的脚本")
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO animation_scripts (user_id, note, code) VALUES (%s, %s, %s)",
            (data.username, data.note or "", data.code),
        )
        conn.commit()
        return {"status": "success", "message": "保存成功", "id": cursor.lastrowid}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": "服务暂不可用，请稍后重试。"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _list_animation_scripts_sync(username: str):
    """同步执行，供 run_in_executor 调用，避免阻塞事件循环"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, user_id, note, LEFT(code, 400) AS code_preview, created_at FROM animation_scripts WHERE user_id = %s ORDER BY created_at DESC",
            (username,),
        )
        rows = cursor.fetchall()
        for r in rows:
            r["created_at"] = r["created_at"].isoformat()
        return {"status": "success", "data": rows}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get("/list")
async def list_animation_scripts(username: str, auth_session: str | None = Cookie(None)):
    if username_for_session(auth_session) != username:
        raise HTTPException(status_code=403, detail="无权访问其他账户的脚本")
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _list_animation_scripts_sync, username)
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": "服务暂不可用，请稍后重试。"})


@router.get("/get")
def get_animation_script(id: int, username: str, auth_session: str | None = Cookie(None)):
    if username_for_session(auth_session) != username:
        raise HTTPException(status_code=403, detail="无权访问其他账户的脚本")
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, note, code, created_at FROM animation_scripts WHERE id = %s AND user_id = %s",
            (id, username),
        )
        row = cursor.fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"status": "error", "message": "未找到脚本"})
        row["created_at"] = row["created_at"].isoformat()
        return {"status": "success", "data": row}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": "服务暂不可用，请稍后重试。"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.delete("/delete")
def delete_animation_script(id: int, username: str, auth_session: str | None = Cookie(None)):
    if username_for_session(auth_session) != username:
        raise HTTPException(status_code=403, detail="无权访问其他账户的脚本")
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM animation_scripts WHERE id = %s AND user_id = %s", (id, username))
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": "服务暂不可用，请稍后重试。"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.put("/update")
def update_animation_script(data: AnimationScriptUpdateModel, auth_session: str | None = Cookie(None)):
    if username_for_session(auth_session) != data.username:
        raise HTTPException(status_code=403, detail="无权访问其他账户的脚本")
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE animation_scripts SET note = %s, code = %s WHERE id = %s AND user_id = %s",
            (data.note or "", data.code, data.id, data.username),
        )
        conn.commit()
        if cursor.rowcount == 0:
            cursor.execute('SELECT id FROM animation_scripts WHERE id=%s AND user_id=%s', (data.id, data.username))
            if not cursor.fetchone():
                return JSONResponse(status_code=404, content={"status": "error", "message": "未找到脚本或无权修改"})
        return {"status": "success", "message": "更新成功"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": "服务暂不可用，请稍后重试。"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
