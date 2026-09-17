# 智能体模板：保存、列表、删除（数据库存储，登录后同步）
import asyncio
import json
import logging
from fastapi import APIRouter, Cookie, HTTPException
from fastapi.responses import JSONResponse

from ..config import get_db_connection
from ..models import AgentTemplateCreate
from .solution_library import username_for_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent_templates", tags=["agent_templates"])


def _ensure_table(cursor):
    """按需创建 agent_templates 表。"""
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_templates (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                name VARCHAR(256) NOT NULL DEFAULT '未命名',
                prompt TEXT NOT NULL,
                steps_json MEDIUMTEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    except Exception as e:
        logger.warning(f"ensure agent_templates table failed: {e}")


@router.post("/save")
async def save_agent_template(data: AgentTemplateCreate, auth_session: str | None = Cookie(None)):
    if username_for_session(auth_session) != data.username:
        raise HTTPException(status_code=403, detail="无权访问其他账户的模板")
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        _ensure_table(cursor)
        steps_json = json.dumps(data.steps or [], ensure_ascii=False)
        cursor.execute(
            "INSERT INTO agent_templates (user_id, name, prompt, steps_json) VALUES (%s, %s, %s, %s)",
            (data.username, (data.name or "未命名")[:256], data.prompt or "", steps_json),
        )
        conn.commit()
        return {"status": "success", "message": "已存为模板", "id": cursor.lastrowid}
    except Exception as e:
        logger.error(f"save_agent_template: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _list_agent_templates_sync(username: str):
    """同步执行，供 run_in_executor 调用，避免阻塞事件循环"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_table(cursor)
        cursor.execute(
            """SELECT id, user_id, name, prompt, steps_json, created_at
               FROM agent_templates WHERE user_id = %s ORDER BY created_at DESC""",
            (username,),
        )
        rows = cursor.fetchall()
        out = []
        for r in rows:
            steps = []
            try:
                steps = json.loads(r.get("steps_json") or "[]") if isinstance(r.get("steps_json"), str) else (r.get("steps_json") or [])
            except Exception:
                pass
            out.append({
                "id": str(r["id"]),
                "name": r.get("name") or "未命名",
                "prompt": r.get("prompt") or "",
                "steps": steps if isinstance(steps, list) else [],
                "createdAt": r["created_at"].timestamp() * 1000 if r.get("created_at") else None,
            })
        return {"status": "success", "data": out}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get("/list")
async def list_agent_templates(username: str, auth_session: str | None = Cookie(None)):
    if username_for_session(auth_session) != username:
        raise HTTPException(status_code=403, detail="无权访问其他账户的模板")
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _list_agent_templates_sync, username)
    except Exception as e:
        logger.error(f"list_agent_templates: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@router.get("/get")
async def get_agent_template(id: int, username: str, auth_session: str | None = Cookie(None)):
    if username_for_session(auth_session) != username:
        raise HTTPException(status_code=403, detail="无权访问其他账户的模板")
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, name, prompt, steps_json, created_at FROM agent_templates WHERE id = %s AND user_id = %s",
            (id, username),
        )
        row = cursor.fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"status": "error", "message": "未找到模板"})
        steps = []
        try:
            steps = json.loads(row.get("steps_json") or "[]")
        except Exception:
            pass
        return {
            "status": "success",
            "data": {
                "id": str(row["id"]),
                "name": row.get("name") or "未命名",
                "prompt": row.get("prompt") or "",
                "steps": steps,
                "createdAt": row["created_at"].timestamp() * 1000 if row.get("created_at") else None,
            },
        }
    except Exception as e:
        logger.error(f"get_agent_template: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.delete("/delete")
async def delete_agent_template(id: int, username: str, auth_session: str | None = Cookie(None)):
    if username_for_session(auth_session) != username:
        raise HTTPException(status_code=403, detail="无权访问其他账户的模板")
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM agent_templates WHERE id = %s AND user_id = %s", (id, username))
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"delete_agent_template: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
