import os
"""我的算式：保存、列表、删除、更新 + 主题标签与知识概览"""
import asyncio
import logging
from typing import List, Tuple

from fastapi import APIRouter, Cookie
from ..store import SESSION_STORE
from .solution_library import ensure_solution_table, username_for_session
from fastapi.responses import JSONResponse

from ..config import get_db_connection, client, api_key
from ..models import FormulaModel, FormulaUpdateModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/formulas", tags=["formulas"])


def _ensure_topics_tables(cursor) -> None:
    """按需创建公式主题标签表，用于知识星云与掌握度统计。"""
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS formula_topics (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(64) NOT NULL,
                formula_id INT NOT NULL,
                tag VARCHAR(64) NOT NULL,
                weight FLOAT DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_tag (user_id, tag),
                INDEX idx_formula (formula_id)
            )
            """
        )
    except Exception as e:
        logger.warning(f"ensure formula_topics table failed: {e}")


def _heuristic_tags(latex: str) -> List[str]:
    """基于简单规则的主题识别，在未配置大模型或解析失败时兜底使用。"""
    s = (latex or "").replace(" ", "").lower()
    tags = set()
    if not s:
        return []
    # 微积分 / 极限
    if "\\int" in s or "dx" in s or "dy" in s:
        tags.add("微积分")
        tags.add("积分")
    if "\\lim" in s:
        tags.add("极限")
        tags.add("微积分")
    if "\\sum" in s or "\\prod" in s:
        tags.add("级数")
    # 线性代数 / 矩阵 / 特征值
    if "\\begin{bmatrix}" in s or "\\begin{pmatrix}" in s or "matrix" in s:
        tags.add("线性代数")
        tags.add("矩阵")
    if "det" in s or "\\det" in s:
        tags.add("行列式")
        tags.add("线性代数")
    if "\\lambda" in s and ("a-\\lambda i" in s or "λ" in s):
        tags.add("特征值")
        tags.add("线性代数")
    # 复变 / 复数
    if "e^{i" in s or "e^{\\mathrm{i}" in s or "\\arg" in s:
        tags.add("复变函数")
        tags.add("复数")
    # 概率统计
    if "\\mathbb{p}" in s or "\\mathbb{e}" in s or "\\operatorname{var}" in s or "n!" in s:
        tags.add("概率统计")
    # 函数图像 / 解析几何
    if "\\sin" in s or "\\cos" in s or "\\tan" in s:
        tags.add("三角函数")
        tags.add("函数图像")
    if "x^2" in s or "y^2" in s:
        tags.add("解析几何")
    return list(tags)


def _infer_formula_topics(latex: str, note: str = "") -> List[Tuple[str, float]]:
    """
    基于 LaTeX 与备注推断该算式的知识主题标签。
    - 优先调用大模型给出 1～4 个标签；若未配置或解析失败，退化为本地启发式规则。
    - 返回 [(tag, weight), ...]，weight 暂时统一为 1，便于未来扩展不同权重。
    """
    base_tags = _heuristic_tags(latex)
    # 未配置大模型：直接返回启发式标签
    if not api_key or os.getenv("AI_FORMULA_TAGGING", "0") != "1":
        return [(t, 1.0) for t in base_tags]

    try:
        prompt = (
            "你是一名为数学公式打知识标签的助手。请阅读下面的 LaTeX 公式及其备注，"
            "从常见大学数学/高中数学知识模块中选出 1～4 个最相关的标签，输出 JSON：\n"
            '{ "tags": ["微积分","极限","线性代数"] }\n\n'
            "公式（LaTeX）：\n"
            f"{latex}\n\n"
            f"备注（可为空）：{note or ''}\n\n"
            "常见标签示例（可选其一部分，也可以补充相近的，但请保持中文短语）：\n"
            "微积分, 极限, 导数, 积分, 级数, 线性代数, 矩阵, 特征值, 行列式, 解析几何, 函数图像, 概率统计, 复变函数, 复数, 代数, 方程, 初等函数\n\n"
            "要求：\n"
            "- 只输出一个 JSON 对象，不要任何解释；\n"
            "- tags 为字符串数组，每个元素是一个中文短标签；\n"
            "- 标签数量不超过 4 个。"
        )
        completion = client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": prompt}],
        )
        raw = completion.choices[0].message.content.strip()
        if "```" in raw:
            parts = raw.split("```")
            if len(parts) >= 2:
                raw = parts[1].replace("json", "").strip()
        data = {}
        try:
            import json as _json

            data = _json.loads(raw)
        except Exception:
            data = {}
        tags = data.get("tags") or []
        tags = [str(t).strip() for t in tags if str(t).strip()]
        if not tags and base_tags:
            tags = base_tags
        # 去重并保留顺序
        seen = set()
        uniq = []
        for t in tags:
            if t not in seen:
                seen.add(t)
                uniq.append(t)
        return [(t, 1.0) for t in uniq]
    except Exception as e:
        logger.warning(f"infer formula topics via LLM failed: {e}")
        return [(t, 1.0) for t in base_tags]


@router.post("/save")
def save_formula(data: FormulaModel, auth_session: str | None = Cookie(None)):
    if username_for_session(auth_session) != data.username:
        return JSONResponse(status_code=403, content={"status":"error","message":"无权修改其他账户的算式"})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO formulas (user_id, latex, note) VALUES (%s, %s, %s)",
            (data.username, data.latex, data.note),
        )
        formula_id = cursor.lastrowid

        # 在同一事务中为该算式生成知识标签，写入 formula_topics，供知识星云使用
        try:
            topics = _infer_formula_topics(data.latex, data.note)
            if topics and formula_id:
                topics_cursor = conn.cursor()
                _ensure_topics_tables(topics_cursor)
                topics_cursor.executemany(
                    "INSERT INTO formula_topics (user_id, formula_id, tag, weight) VALUES (%s, %s, %s, %s)",
                    [(data.username, int(formula_id), tag, float(weight)) for tag, weight in topics],
                )
                topics_cursor.close()
        except Exception as e:
            logger.warning(f"save_formula topics failed: {e}")

        conn.commit()
        return {"status": "success", "message": "保存成功"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _list_formulas_sync(username: str, include_solutions: bool = False):
    """同步执行，供 run_in_executor 调用，避免阻塞事件循环（渲染时可并发加载算式库）"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_solution_table(cursor)
        cursor.execute("SELECT f.*, s.title AS solution_title, s.step_count, s.video_url FROM formulas f LEFT JOIN formula_solutions s ON s.formula_id=f.id WHERE f.user_id = %s " + ("" if include_solutions else "AND s.formula_id IS NULL ") + "ORDER BY f.created_at DESC, f.id DESC", (username,))
        formulas = cursor.fetchall()
        for f in formulas:
            f["created_at"] = f["created_at"].isoformat()
        return {"status": "success", "data": formulas}
    except Exception as e:
        raise e
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get("/list")
async def list_formulas(username: str, auth_session: str | None = Cookie(None)):
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _list_formulas_sync, username, SESSION_STORE.get(auth_session or '') == username)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@router.get('/list/me')
def list_my_formulas(auth_session: str | None = Cookie(None)):
    return _list_formulas_sync(username_for_session(auth_session), True)


@router.delete("/delete")
async def delete_formula(id: int, username: str, auth_session: str | None = Cookie(None)):
    if username_for_session(auth_session) != username:
        return JSONResponse(status_code=403, content={"status":"error","message":"无权删除其他账户的算式"})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM formulas WHERE id = %s AND user_id = %s", (id, username))
        try:
            topics_cursor = conn.cursor()
            _ensure_topics_tables(topics_cursor)
            topics_cursor.execute(
                "DELETE FROM formula_topics WHERE formula_id = %s AND user_id = %s",
                (id, username),
            )
            topics_cursor.close()
        except Exception as e:
            logger.warning(f"delete_formula topics cleanup failed: {e}")
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.put("/update")
def update_formula(data: FormulaUpdateModel, auth_session: str | None = Cookie(None)):
    if username_for_session(auth_session) != data.username:
        return JSONResponse(status_code=403, content={"status":"error","message":"无权修改其他账户的算式"})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_solution_table(cursor)
        cursor.execute('SELECT formula_id FROM formula_solutions WHERE formula_id=%s', (data.id,))
        if cursor.fetchone():
            return JSONResponse(status_code=409, content={"status":"error","message":"请在可视化页面修改题目并重新解题，避免已保存的步骤与题目不一致。"})
        cursor.execute(
            "UPDATE formulas SET latex = %s, note = %s WHERE id = %s AND user_id = %s",
            (data.latex, data.note, data.id, data.username),
        )
        # 更新成功时，同步重建该算式的知识标签
        if cursor.rowcount > 0:
            try:
                topics_cursor = conn.cursor()
                _ensure_topics_tables(topics_cursor)
                topics_cursor.execute(
                    "DELETE FROM formula_topics WHERE formula_id = %s AND user_id = %s",
                    (data.id, data.username),
                )
                topics = _infer_formula_topics(data.latex, data.note)
                if topics:
                    topics_cursor.executemany(
                        "INSERT INTO formula_topics (user_id, formula_id, tag, weight) VALUES (%s, %s, %s, %s)",
                        [(data.username, int(data.id), tag, float(weight)) for tag, weight in topics],
                    )
                topics_cursor.close()
            except Exception as e:
                logger.warning(f"update_formula topics failed: {e}")

        conn.commit()
        if cursor.rowcount == 0:
            return JSONResponse(status_code=404, content={"status": "error", "message": "未找到算式或无权修改"})
        return {"status": "success", "message": "更新成功"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get("/knowledge")
async def knowledge_summary(username: str):
    """
    基于用户已保存的算式，统计各知识标签的数量与粗略掌握度估计，
    供前端渲染「知识星云」与进度条。
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_topics_tables(cursor)

        # 先看是否已有主题标签记录
        cursor.execute(
            "SELECT tag, COUNT(*) AS cnt, COALESCE(SUM(weight), 0) AS score "
            "FROM formula_topics WHERE user_id = %s GROUP BY tag",
            (username,),
        )
        rows = cursor.fetchall() or []

        # 若用户已有算式但尚未生成任何主题标签，则按需为其批量补打标签（兼容上线前已保存的数据）
        if not rows:
            cursor.execute(
                "SELECT id, latex, note FROM formulas WHERE user_id = %s ORDER BY created_at DESC LIMIT 200",
                (username,),
            )
            formulas = cursor.fetchall() or []
            if formulas:
                topics_cursor = conn.cursor()
                _ensure_topics_tables(topics_cursor)
                bulk_values = []
                for f in formulas:
                    fid = f.get("id")
                    latex = f.get("latex", "")
                    note = f.get("note", "")
                    topics = _infer_formula_topics(latex, note)
                    for tag, weight in topics:
                        bulk_values.append((username, int(fid), tag, float(weight)))
                if bulk_values:
                    topics_cursor.executemany(
                        "INSERT INTO formula_topics (user_id, formula_id, tag, weight) VALUES (%s, %s, %s, %s)",
                        bulk_values,
                    )
                topics_cursor.close()
                conn.commit()

                # 重新聚合
                cursor.execute(
                    "SELECT tag, COUNT(*) AS cnt, COALESCE(SUM(weight), 0) AS score "
                    "FROM formula_topics WHERE user_id = %s GROUP BY tag",
                    (username,),
                )
                rows = cursor.fetchall() or []

        if not rows:
            return {"status": "success", "total": 0, "topics": []}

        total = sum(int(r.get("cnt", 0) or 0) for r in rows)
        max_cnt = max(int(r.get("cnt", 0) or 0) for r in rows) or 1
        topics = []
        for r in rows:
            cnt = int(r.get("cnt", 0) or 0)
            # 简单掌握度估计：同一标签做得越多，占比越高，百分比越大；每个标签上限 100%
            mastery = int(round(min(100.0, (cnt / max_cnt) * 100.0)))
            topics.append(
                {
                    "tag": r.get("tag") or "",
                    "count": cnt,
                    "mastery": mastery,
                }
            )
        # 依掌握度/数量降序
        topics.sort(key=lambda x: (-x["mastery"], -x["count"], x["tag"]))
        return {"status": "success", "total": total, "topics": topics}
    except Exception as e:
        logger.error(f"knowledge_summary failed: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
