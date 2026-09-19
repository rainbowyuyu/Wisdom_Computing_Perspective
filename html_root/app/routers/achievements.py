# 星云成就系统：数据库存储，读写 API
import logging
from fastapi import APIRouter, Cookie
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from ..store import SESSION_STORE

from ..config import get_db_connection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/achievements", tags=["achievements"])

# 成就定义：id, label, icon, stat_key, target
# 尽量围绕现有统计维度（formulas/scripts/templates/wrongbook/tutorial），避免额外埋点
ACHIEVEMENT_DEFS = [
    # 教程相关
    {
        "id": "tutorial",
        "label": "新手教程",
        "icon": "fa-circle-check",
        "stat_key": "tutorial",
        "target": 1,
        "condition": "完成新手引导",
    },
    # 公式类：从“入门”到“收藏家”
    {
        "id": "formulas_1",
        "label": "第一条公式",
        "icon": "fa-seedling",
        "stat_key": "formulas",
        "target": 1,
        "condition": "保存你的第一条云端公式",
    },
    {
        "id": "formulas_10",
        "label": "算式积累",
        "icon": "fa-calculator",
        "stat_key": "formulas",
        "target": 10,
        "condition": "累计保存 10 条算式",
    },
    {
        "id": "formulas_30",
        "label": "公式笔记本",
        "icon": "fa-book",
        "stat_key": "formulas",
        "target": 30,
        "condition": "让云端笔记里躺满 30 条公式",
    },
    # 脚本类：鼓励多写 Manim 脚本
    {
        "id": "scripts_1",
        "label": "第一段动画脚本",
        "icon": "fa-clapperboard",
        "stat_key": "scripts",
        "target": 1,
        "condition": "在工作台中创建第一段 Manim 脚本",
    },
    {
        "id": "scripts_5",
        "label": "脚本达人",
        "icon": "fa-video",
        "stat_key": "scripts",
        "target": 5,
        "condition": "创建 5 个动画脚本",
    },
    {
        "id": "scripts_12",
        "label": "可视化导演",
        "icon": "fa-film",
        "stat_key": "scripts",
        "target": 12,
        "condition": "累计创建 12 个动画脚本",
    },
    # 模板类：引导更多使用智能体模板
    {
        "id": "templates_1",
        "label": "模板启航",
        "icon": "fa-wand-magic-sparkles",
        "stat_key": "templates",
        "target": 1,
        "condition": "保存第一个属于你的智能体模板",
    },
    {
        "id": "templates_3",
        "label": "模板就绪",
        "icon": "fa-wand-magic-sparkles",
        "stat_key": "templates",
        "target": 3,
        "condition": "保存 3 个智能体模板",
    },
    {
        "id": "templates_6",
        "label": "多角色编队",
        "icon": "fa-users-gear",
        "stat_key": "templates",
        "target": 6,
        "condition": "为不同场景准备 6 个以上智能体模板",
    },
    # 错题本：鼓励形成学习闭环
    {
        "id": "wrongbook_1",
        "label": "第一道错题",
        "icon": "fa-bookmark",
        "stat_key": "wrongbook",
        "target": 1,
        "condition": "将第一道题加入错题本，开启复盘习惯",
    },
    {
        "id": "wrongbook_5",
        "label": "错题收录",
        "icon": "fa-bookmark",
        "stat_key": "wrongbook",
        "target": 5,
        "condition": "收录 5 道错题",
    },
    {
        "id": "wrongbook_12",
        "label": "复习星轨",
        "icon": "fa-chart-line",
        "stat_key": "wrongbook",
        "target": 12,
        "condition": "错题本里累计记录 12 条学习轨迹",
    },
]


def _ensure_table(cursor):
    """按需创建 user_achievements 表。"""
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_achievements (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                achievement_id VARCHAR(64) NOT NULL,
                progress INT NOT NULL DEFAULT 0,
                unlocked TINYINT(1) NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_user_ach (user_id, achievement_id)
            )
            """
        )
    except Exception as e:
        logger.warning("ensure user_achievements table failed: %s", type(e).__name__)


def _get_db_progress(cursor, user_id):
    """从数据库读取用户成就进度。"""
    cursor.execute(
        """SELECT achievement_id, progress, unlocked FROM user_achievements WHERE user_id = %s""",
        (user_id,),
    )
    rows = cursor.fetchall()
    return {r[0]: {"progress": r[1], "unlocked": bool(r[2])} for r in rows}


def _compute_achievements(stats, db_progress):
    """合并 stats 与 db 计算成就列表。"""
    out = []
    for defn in ACHIEVEMENT_DEFS:
        aid = defn["id"]
        stat_key = defn["stat_key"]
        target = defn["target"]
        db = db_progress.get(aid)
        # 基于当前统计的进度（本次会话）
        if stat_key == "tutorial":
            stat_progress = 1 if stats.get("tutorialDone") else 0
        else:
            stat_progress = min(int(stats.get(stat_key) or 0), target)
        # DB 中已保存的历史进度与解锁状态
        db_progress_value = int(db.get("progress") or 0) if db else 0
        db_unlocked = bool(db.get("unlocked")) if db else False
        # 进度取“历史记录”和“当前统计”的较大值，避免回退
        progress = max(stat_progress, db_progress_value)
        # 是否解锁：一旦 DB 中标记为已解锁则永久解锁；否则依据进度判断
        unlocked = db_unlocked or (progress >= target)
        out.append({
            "id": aid,
            "label": defn["label"],
            "icon": defn["icon"],
            "condition": defn["condition"],
            "target": target,
            "progress": progress,
            "unlocked": unlocked,
            "db_unlocked": db_unlocked,
        })
    return out


@router.get("/list")
def list_achievements(formulas: int = 0, scripts: int = 0, templates: int = 0, wrongbook: int = 0, tutorial_done: bool = False, username: str = "", auth_session: str | None = Cookie(None)):
    """
    获取用户成就列表。
    前端传入 stats（formulas/scripts/templates/wrongbook/tutorial_done），
    服务端合并 DB 中的 tutorial 等状态后返回成就列表。
    """
    owner = SESSION_STORE.get(auth_session or '')
    if username and username != owner:
        return JSONResponse(status_code=403 if owner else 401, content={'status':'error','message':'只能读取自己的成就。'})
    username = owner or ''
    conn = None
    cursor = None
    try:
        stats = {
            "formulas": formulas,
            "scripts": scripts,
            "templates": templates,
            "wrongbook": wrongbook,
            "tutorialDone": tutorial_done,
        }
        db_progress = {}
        if username:
            conn = get_db_connection()
            cursor = conn.cursor()
            _ensure_table(cursor)
            db_progress = _get_db_progress(cursor, username)
            # tutorial 优先用 DB 中的状态
            if "tutorial" in db_progress:
                stats["tutorialDone"] = bool(db_progress["tutorial"].get("unlocked"))
        data = _compute_achievements(stats, db_progress)
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error("list_achievements: %s", type(e).__name__)
        return JSONResponse(status_code=500, content={"status": "error", "message": "服务暂不可用，请稍后重试。"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


class AchievementUpsert(BaseModel):
    username: str = Field(max_length=64)
    achievement_id: str = Field(max_length=64)
    progress: int = Field(default=0, ge=0, le=1000000)
    unlocked: bool = False


@router.post("/upsert")
def upsert_achievement(data: AchievementUpsert, auth_session: str | None = Cookie(None)):
    """写入/更新成就进度到数据库。"""
    owner = SESSION_STORE.get(auth_session or '')
    if not owner or data.username != owner:
        return JSONResponse(status_code=403 if owner else 401, content={'status':'error','message':'只能修改自己的成就。'})
    if data.achievement_id not in {item['id'] for item in ACHIEVEMENT_DEFS}:
        return JSONResponse(status_code=422, content={'status':'error','message':'成就类型不正确。'})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        _ensure_table(cursor)
        cursor.execute(
            """
            INSERT INTO user_achievements (user_id, achievement_id, progress, unlocked)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE progress = VALUES(progress), unlocked = VALUES(unlocked)
            """,
            (owner, data.achievement_id, data.progress, 1 if data.unlocked else 0),
        )
        conn.commit()
        return {"status": "success", "message": "已更新成就"}
    except Exception as e:
        logger.error("upsert_achievement: %s", type(e).__name__)
        return JSONResponse(status_code=500, content={"status": "error", "message": "服务暂不可用，请稍后重试。"})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
