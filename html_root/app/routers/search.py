# 全站搜索：个人题解、课包、错题、脚本与公开案例
import json
import os
import logging
from typing import Optional, List, Any

from fastapi import APIRouter, Query, Cookie
from fastapi.responses import JSONResponse

from ..config import ROOT_DIR, get_db_connection
from ..store import SESSION_STORE

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["search"])


def _username_from_session(auth_session: Optional[str] = None):
    if not auth_session:
        return None
    return SESSION_STORE.get(auth_session)


@router.get("")
async def search(
    q: str = Query(..., min_length=1, max_length=200),
    auth_session: Optional[str] = Cookie(None),
):
    """搜索当前账户的学习资料及公开教学案例。"""
    q = (q or "").strip()
    if not q:
        return {"status": "success", "formulas": [], "scripts": [], "examples": [], "course_packs": [], "wrongbook": []}
    username = _username_from_session(auth_session)
    like = '%' + q.replace('=', '==').replace('%', '=%').replace('_', '=_') + '%'

    formulas: List[Any] = []
    scripts: List[Any] = []
    packs, wrongbook = [], []
    if username:
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT f.id, f.user_id, f.latex, f.note, f.created_at, EXISTS(SELECT 1 FROM formula_solutions s WHERE s.formula_id=f.id) AS is_solution FROM formulas f WHERE user_id = %s AND (latex LIKE %s ESCAPE '=' OR note LIKE %s ESCAPE '=') ORDER BY created_at DESC LIMIT 20",
                (username, like, like),
            )
            rows = cursor.fetchall()
            for r in rows:
                formulas.append({
                    "id": r["id"],
                    "is_solution": bool(r.get("is_solution")),
                    "latex": r.get("latex", ""),
                    "note": r.get("note", ""),
                    "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                })
            cursor.execute(
                "SELECT id, user_id, note, LEFT(code, 300) AS code_preview, created_at FROM animation_scripts WHERE user_id = %s AND (note LIKE %s ESCAPE '=' OR code LIKE %s ESCAPE '=') ORDER BY created_at DESC LIMIT 20",
                (username, like, like),
            )
            rows = cursor.fetchall()
            for r in rows:
                scripts.append({
                    "id": r["id"],
                    "note": r.get("note", ""),
                    "code_preview": r.get("code_preview", ""),
                    "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                })
            cursor.execute("SELECT p.id,p.name FROM course_packs p LEFT JOIN course_pack_documents d ON d.pack_id=p.id WHERE p.user_id=%s AND (p.name LIKE %s ESCAPE '=' OR d.description LIKE %s ESCAPE '=' OR d.lesson_json LIKE %s ESCAPE '=') ORDER BY p.id DESC LIMIT 20", (username,like,like,like))
            packs=cursor.fetchall()
            cursor.execute("SELECT w.id,w.title,w.status FROM learning_wrongbook w JOIN users u ON u.id=w.owner_id WHERE u.username=%s AND (w.title LIKE %s ESCAPE '=' OR w.problem LIKE %s ESCAPE '=' OR w.note LIKE %s ESCAPE '=') ORDER BY w.updated_at DESC LIMIT 20", (username,like,like,like))
            wrongbook=cursor.fetchall()
        except Exception as e:
            logger.warning(f"search db: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    examples: List[Any] = []
    storage_dir = os.path.join(ROOT_DIR, "static", "assets", "storage")
    metadata_path = os.path.join(storage_dir, "metadata.json")
    meta_dict = {}
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            meta_list = raw if isinstance(raw, list) else (list(raw.values()) if isinstance(raw, dict) else [])
            for item in meta_list:
                if isinstance(item, dict) and item.get("filename"):
                    meta_dict[item["filename"]] = item
        except Exception as e:
            logger.warning(f"search metadata: {e}")
    if os.path.exists(storage_dir):
        q_lower = q.lower()
        for file in os.listdir(storage_dir):
            if not file.endswith(".mp4"):
                continue
            meta = meta_dict.get(file, {"title": file, "description": "", "tags": []})
            title = (meta.get("title") or "")
            desc = (meta.get("description") or "")
            tags = meta.get("tags") or []
            tags_str = " ".join(str(t) for t in tags)
            if q_lower not in title.lower() and q_lower not in desc.lower() and q_lower not in tags_str.lower():
                continue
            video_id = file.rsplit(".", 1)[0]
            examples.append({
                "video_id": video_id,
                "title": title or file,
                "description": desc,
            })

    return {
        "status": "success",
        "formulas": formulas,
        "scripts": scripts,
        "examples": examples,
        "course_packs": packs,
        "wrongbook": wrongbook,
    }
