# 教学案例：示例视频列表、点赞/评论/弹幕、播放器配置与鉴权（B 站风核心）
import json
import os
import logging
import time
import hmac
import hashlib
import base64
from typing import Optional, Dict, Set, List, Any
from fastapi import APIRouter, Cookie, Query, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
from pathlib import Path

from ..config import (
    ROOT_DIR,
    get_db_connection,
    STORAGE_DIR,
    VIDEO_TOKEN_SECRET,
    VIDEO_TOKEN_EXPIRES_SECONDS,
    ALIYUN_CDN_DOMAIN,
    ALIYUN_CDN_AUTH_KEY,
    ALIYUN_CDN_AUTH_TYPE,
    ALIYUN_CDN_VIDEO_PATH,
    ALIYUN_CDN_AUTH_TTL,
    ALIYUN_CDN_PUBLIC_BASE,
    EXAMPLES_USE_CDN,
)
from ..store import SESSION_STORE

logger = logging.getLogger(__name__)
router = APIRouter(tags=["examples"])

# WebSocket：每个 video_id 对应的连接集合，用于在线人数与新弹幕推送
_ws_rooms: Dict[str, Set[WebSocket]] = {}


async def _broadcast_video(video_id: str, message: dict):
    room = _ws_rooms.get(video_id)
    if not room:
        return
    text = json.dumps(message, ensure_ascii=False)
    dead = []
    for ws in list(room):
        try:
            await ws.send_text(text)
        except Exception:
            dead.append(ws)
    for ws in dead:
        room.discard(ws)


def _username_from_session(auth_session: Optional[str] = None):
    if not auth_session:
        return None
    return SESSION_STORE.get(auth_session)


def _sign_video_token(video_id: str) -> tuple[str, int]:
    """生成视频鉴权 token，返回 (token_b64, expires_ts)。"""
    expires = int(time.time()) + VIDEO_TOKEN_EXPIRES_SECONDS
    raw = f"{video_id}:{expires}"
    sig = hmac.new(
        VIDEO_TOKEN_SECRET.encode("utf-8"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    token = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    return token, expires


def _verify_video_token(video_id: str, token: str, expires: str) -> bool:
    """校验视频鉴权 token。"""
    try:
        exp = int(expires)
        if exp < int(time.time()):
            return False
        raw = f"{video_id}:{exp}"
        sig = hmac.new(
            VIDEO_TOKEN_SECRET.encode("utf-8"),
            raw.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        expected = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
        return hmac.compare_digest(expected, (token or "").strip())
    except (ValueError, TypeError):
        return False


def _aliyun_cdn_signed_url(video_id: str) -> Optional[str]:
    """
    生成阿里云 CDN 鉴权方式 A 的签名 URL。
    控制台需开启 URL 鉴权并配置与 ALIYUN_CDN_AUTH_KEY 一致的主 KEY。
    """
    if not ALIYUN_CDN_DOMAIN or not ALIYUN_CDN_AUTH_KEY:
        return None
    if ALIYUN_CDN_AUTH_TYPE != "a":
        return None
    import secrets
    filename = video_id + ".mp4"
    uri = f"{ALIYUN_CDN_VIDEO_PATH}/{filename}"
    if not uri.startswith("/"):
        uri = "/" + uri
    timestamp = int(time.time()) + ALIYUN_CDN_AUTH_TTL
    rand = (secrets.token_hex(16) or "0").replace("-", "")[:32]
    uid = "0"
    sstring = f"{uri}-{timestamp}-{rand}-{uid}-{ALIYUN_CDN_AUTH_KEY}"
    md5hash = hashlib.md5(sstring.encode("utf-8")).hexdigest()
    auth_key = f"{timestamp}-{rand}-{uid}-{md5hash}"
    return f"{ALIYUN_CDN_DOMAIN}{uri}?auth_key={auth_key}"


def _ensure_tables(cursor):
    """创建/补齐教学案例相关表，单步失败不影响后续步骤。"""
    def run(sql, params=None):
        try:
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
        except Exception as e:
            logger.warning(f"_ensure_tables step failed: {e}")
    run("""
        CREATE TABLE IF NOT EXISTS example_video_likes (
            video_id VARCHAR(128) NOT NULL,
            user_id VARCHAR(64) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (video_id, user_id)
        )
    """)
    run("""
        CREATE TABLE IF NOT EXISTS example_video_comments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            video_id VARCHAR(128) NOT NULL,
            user_id VARCHAR(64) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    run("""
        CREATE TABLE IF NOT EXISTS example_video_danmaku (
            id INT AUTO_INCREMENT PRIMARY KEY,
            video_id VARCHAR(128) NOT NULL,
            user_id VARCHAR(64) NOT NULL,
            text VARCHAR(80) NOT NULL,
            time DOUBLE NOT NULL,
            color INT DEFAULT 16777215,
            mode SMALLINT DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        cursor.execute("SELECT color FROM example_video_danmaku LIMIT 1")
        cursor.fetchone()  # 必须消费结果，否则下一句 execute 会报 Unread result found
    except Exception:
        try:
            cursor.execute("ALTER TABLE example_video_danmaku ADD COLUMN color INT DEFAULT 16777215")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE example_video_danmaku ADD COLUMN mode SMALLINT DEFAULT 1")
        except Exception:
            pass
    run("""
        CREATE TABLE IF NOT EXISTS example_play_history (
            user_id VARCHAR(64) NOT NULL,
            video_id VARCHAR(128) NOT NULL,
            progress DOUBLE NOT NULL DEFAULT 0,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, video_id)
        )
    """)
    run("""
        CREATE TABLE IF NOT EXISTS user_favorites (
            user_id VARCHAR(64) NOT NULL,
            video_id VARCHAR(128) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, video_id)
        )
    """)
    run("""
        CREATE TABLE IF NOT EXISTS watch_later (
            user_id VARCHAR(64) NOT NULL,
            video_id VARCHAR(128) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, video_id)
        )
    """)
    run("""
        CREATE TABLE IF NOT EXISTS example_video_notes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            video_id VARCHAR(128) NOT NULL,
            time_sec DOUBLE NOT NULL DEFAULT 0,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    run("""
        CREATE TABLE IF NOT EXISTS course_packs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            name VARCHAR(128) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    run("""
        CREATE TABLE IF NOT EXISTS course_pack_videos (
            pack_id INT NOT NULL,
            video_id VARCHAR(128) NOT NULL,
            sort_order INT DEFAULT 0,
            PRIMARY KEY (pack_id, video_id)
        )
    """)


@router.get("/examples/health")
async def examples_health():
    """
    诊断接口：不依赖 Cookie，返回列表或详细错误（便于排查 500）。
    正常后请勿依赖此接口，使用 GET /api/examples。
    """
    try:
        storage_dir = os.path.join(ROOT_DIR, "static", "assets", "storage")
        metadata_path = os.path.join(storage_dir, "metadata.json")
        videos = []
        meta_dict = {}
        if os.path.exists(metadata_path):
            with open(metadata_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            meta_list = raw if isinstance(raw, list) else (list(raw.values()) if isinstance(raw, dict) else [])
            for item in meta_list:
                if isinstance(item, dict) and item.get("filename"):
                    meta_dict[item["filename"]] = item
        if os.path.exists(storage_dir):
            for file in os.listdir(storage_dir):
                if file.endswith(".mp4"):
                    meta = meta_dict.get(file, {"title": file, "description": "暂无简介", "poster": ""})
                    video_id = file.rsplit(".", 1)[0]
                    high_energy = meta.get("high_energy") or []
                    if not isinstance(high_energy, list):
                        high_energy = []
                    he_list = [int(x) for x in high_energy if isinstance(x, (int, float))][:200]
                    videos.append({
                        "video_id": video_id,
                        "title": meta.get("title", file),
                        "filename": file,
                    })
        db_ok = True
        db_error = None
        try:
            conn = get_db_connection()
            conn.close()
        except Exception as db_err:
            db_ok = False
            db_error = str(db_err)
        return {
            "status": "ok",
            "videos_count": len(videos),
            "db_ok": db_ok,
            "db_error": db_error,
            "storage_dir": storage_dir,
            "storage_exists": os.path.exists(storage_dir),
        }
    except Exception as e:
        import traceback
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e),
                "type": type(e).__name__,
                "traceback": traceback.format_exc(),
            },
        )


@router.get("/examples")
async def get_examples(
    request: Request,
    tag: Optional[str] = Query(None, max_length=64),
    filter_mode: Optional[str] = Query(None, description="all|favorites|watch_later"),
):
    try:
        auth_session = request.cookies.get("auth_session") if request else None
        username = _username_from_session(auth_session)
        storage_dir = os.path.join(ROOT_DIR, "static", "assets", "storage")
        metadata_path = os.path.join(storage_dir, "metadata.json")
        videos = []
        meta_dict = {}
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                meta_list = raw if isinstance(raw, list) else (list(raw.values()) if isinstance(raw, dict) else [])
                for item in meta_list:
                    if not isinstance(item, dict):
                        continue
                    fn = item.get("filename")
                    if fn:
                        meta_dict[fn] = item
            except Exception as e:
                logger.error(f"Metadata load error: {e}")

        if os.path.exists(storage_dir):
            try:
                for file in os.listdir(storage_dir):
                    if file.endswith(".mp4"):
                        meta = meta_dict.get(file, {"title": file, "description": "暂无简介", "poster": ""})
                        video_id = file.rsplit(".", 1)[0]
                        duration_sec = meta.get("duration_sec")
                        high_energy = meta.get("high_energy")
                        if not isinstance(high_energy, list):
                            high_energy = []
                        try:
                            sprite_cols = meta.get("sprite_cols", 10)
                            sprite_rows = meta.get("sprite_rows", 10)
                            if not isinstance(sprite_cols, (int, float)):
                                sprite_cols = 10
                            if not isinstance(sprite_rows, (int, float)):
                                sprite_rows = 10
                            he_list = [int(x) for x in high_energy if isinstance(x, (int, float))][:200]
                        except (TypeError, ValueError):
                            sprite_cols, sprite_rows, he_list = 10, 10, []
                        tags_raw = meta.get("tags")
                        tags_list = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []
                        # 默认本地；EXAMPLES_USE_CDN=1 时走 CDN（保留 CDN 接口）
                        cdn_base = (ALIYUN_CDN_PUBLIC_BASE or "").strip() if EXAMPLES_USE_CDN else ""
                        video_url = f"{cdn_base.rstrip('/')}{ALIYUN_CDN_VIDEO_PATH}/{file}" if cdn_base else f"/assets/storage/{file}"
                        videos.append({
                            "filename": file,
                            "video_id": video_id,
                            "title": meta.get("title", file),
                            "description": meta.get("description", "暂无简介"),
                            "url": video_url,
                            "poster": meta.get("poster", ""),
                            "duration_sec": duration_sec,
                            "sprite_url": meta.get("sprite_url", ""),
                            "sprite_cols": int(sprite_cols),
                            "sprite_rows": int(sprite_rows),
                            "hls_url": meta.get("hls_url", ""),
                            "mask_url": meta.get("mask_url", ""),
                            "high_energy": he_list,
                            "tags": tags_list,
                        })
            except OSError as e:
                logger.warning(f"Storage listdir error: {e}")

        if tag:
            tag_lower = tag.strip().lower()
            videos = [v for v in videos if tag_lower in [str(t).lower() for t in v.get("tags", [])]]

        conn = None
        cursor = None
        fav_ids: Set[str] = set()
        watch_later_ids: Set[str] = set()
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            _ensure_tables(cursor)
            if username:
                cursor.execute("SELECT video_id FROM user_favorites WHERE user_id = %s", (username,))
                fav_ids = {row["video_id"] for row in cursor.fetchall()}
                cursor.execute("SELECT video_id FROM watch_later WHERE user_id = %s", (username,))
                watch_later_ids = {row["video_id"] for row in cursor.fetchall()}
                if filter_mode == "favorites":
                    videos = [v for v in videos if v["video_id"] in fav_ids]
                elif filter_mode == "watch_later":
                    videos = [v for v in videos if v["video_id"] in watch_later_ids]
                elif filter_mode == "courseware":
                    # 教师：我的课件包（从 course_pack_videos 筛选）
                    pack_video_ids = set()
                    try:
                        cursor.execute(
                            "SELECT cpv.video_id FROM course_pack_videos cpv "
                            "INNER JOIN course_packs cp ON cp.id = cpv.pack_id AND cp.user_id = %s",
                            (username or "",),
                        )
                        pack_video_ids = {row["video_id"] for row in cursor.fetchall()}
                    except Exception:
                        pass
                    videos = [v for v in videos if v["video_id"] in pack_video_ids]
            for v in videos:
                vid = v["video_id"]
                cursor.execute("SELECT COUNT(*) AS c FROM example_video_likes WHERE video_id = %s", (vid,))
                row = cursor.fetchone()
                v["like_count"] = row.get("c", row.get("C", 0)) if row else 0
                v["user_has_liked"] = False
                if username:
                    cursor.execute("SELECT 1 FROM example_video_likes WHERE video_id = %s AND user_id = %s", (vid, username))
                    v["user_has_liked"] = cursor.fetchone() is not None
                v["user_favorited"] = vid in fav_ids
                v["user_watch_later"] = vid in watch_later_ids
        except Exception as e:
            logger.warning(f"Examples likes query: {e}")
            for v in videos:
                v["like_count"] = v.get("like_count", 0)
                v["user_has_liked"] = v.get("user_has_liked", False)
                v["user_favorited"] = v.get("video_id") in fav_ids
                v["user_watch_later"] = v.get("video_id") in watch_later_ids
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

        return {"status": "success", "data": videos}
    except Exception as e:
        logger.exception("get_examples failed")
        # 始终返回 200，避免前端只看到 500 无法展示错误信息
        return {"status": "success", "data": [], "error": str(e)}


# ========== v1 播放器核心 API（鉴权 URL、续播、弹幕分段、心跳） ==========

@router.get("/v1/player/config/{video_id}")
async def get_player_config(
    video_id: str,
    request: Request,
    auth_session: Optional[str] = Cookie(None),
):
    """播放器初始化：返回鉴权后的视频 URL、续播进度、弹幕池 ID。"""
    video_id = (video_id or "").strip()[:128]
    if not video_id:
        return JSONResponse(
            status_code=400,
            content={"code": -1, "message": "缺少 video_id"},
        )
    storage_dir = os.path.join(ROOT_DIR, "static", "assets", "storage")
    metadata_path = os.path.join(storage_dir, "metadata.json")
    meta_dict = {}
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                meta_list = json.load(f)
                for item in meta_list:
                    fn = item.get("filename", "")
                    meta_dict[fn.rsplit(".", 1)[0] if "." in fn else fn] = item
        except Exception as e:
            logger.error(f"Metadata load error: {e}")
    filename = video_id + ".mp4"
    file_path = os.path.join(storage_dir, filename)
    if not os.path.isfile(file_path):
        return JSONResponse(
            status_code=404,
            content={"code": -1, "message": "视频不存在"},
        )
    # 默认本地；EXAMPLES_USE_CDN=1 时优先 CDN（保留 CDN 接口），并返回 fallback_src 供前端切换
    # 使用相对路径（与列表页缩略图一致），浏览器按当前页 origin 解析，反向代理环境下可正常播放
    token, expires = _sign_video_token(video_id)
    local_src = f"/api/v1/player/stream/{video_id}?token={token}&expires={expires}"
    video_src = _aliyun_cdn_signed_url(video_id) if EXAMPLES_USE_CDN else None
    if not video_src:
        video_src = local_src
        fallback_src = None
    else:
        fallback_src = local_src
    last_play_time = 0.0
    username = _username_from_session(auth_session)
    if username:
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            _ensure_tables(cursor)
            cursor.execute(
                "SELECT progress FROM example_play_history WHERE user_id = %s AND video_id = %s",
                (username, video_id),
            )
            row = cursor.fetchone()
            if row and row.get("progress") is not None:
                last_play_time = float(row["progress"])
        except Exception as e:
            logger.warning(f"play_history query: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
    data = {
        "video_src": video_src,
        "format": "mp4",
        "last_play_time": last_play_time,
        "danmaku_id": video_id,
    }
    if fallback_src:
        data["fallback_src"] = fallback_src
    return {"code": 0, "data": data}


@router.get("/v1/player/stream/{video_id}")
async def stream_video(
    video_id: str,
    token: str = Query(""),
    expires: str = Query(""),
):
    """鉴权视频流：仅在校验 token 通过后返回 storage 内 MP4 文件。"""
    video_id = (video_id or "").strip()[:128]
    if not _verify_video_token(video_id, token, expires):
        return JSONResponse(
            status_code=403,
            content={"code": -1, "message": "鉴权失败或链接已过期"},
        )
    filename = video_id + ".mp4"
    file_path = os.path.join(STORAGE_DIR, filename)
    if not os.path.isfile(file_path):
        return JSONResponse(status_code=404, content={"code": -1, "message": "视频不存在"})
    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=filename,
    )


@router.get("/v1/danmaku/list")
async def get_danmaku_list(
    video_id: str = Query(..., max_length=128),
    segment_index: Optional[int] = Query(None, ge=0),
):
    """
    弹幕列表，DPlayer/Xgplayer 格式 [time, type, color, author, content]。
    支持 segment_index 分片：每片 6 分钟，segment_index=0 为 0~360s，1 为 360~720s…
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        if segment_index is not None:
            t_start = segment_index * 360.0
            t_end = t_start + 360.0
            cursor.execute(
                """SELECT id, video_id, user_id, text, time, COALESCE(color, 16777215) AS color, COALESCE(mode, 1) AS mode
                   FROM example_video_danmaku
                   WHERE video_id = %s AND time >= %s AND time < %s
                   ORDER BY time ASC, id ASC""",
                (video_id, t_start, t_end),
            )
        else:
            cursor.execute(
                """SELECT id, video_id, user_id, text, time, COALESCE(color, 16777215) AS color, COALESCE(mode, 1) AS mode
                   FROM example_video_danmaku
                   WHERE video_id = %s
                   ORDER BY time ASC, id ASC""",
                (video_id,),
            )
        rows = cursor.fetchall()
        # DPlayer 格式: [time, type, color, author, content]
        out: List[List[Any]] = []
        for r in rows:
            out.append([
                float(r.get("time", 0)),
                int(r.get("mode", 1)),
                int(r.get("color", 16777215)),
                (r.get("user_id") or "").strip(),
                (r.get("text") or "").strip(),
                r['id'],
            ])
        return {"code": 0, "data": out}
    except Exception as e:
        logger.error(f"get_danmaku_list: {e}")
        return JSONResponse(status_code=500, content={"code": -1, "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


class DanmakuCreateV1(BaseModel):
    video_id: str
    text: str
    time: float = Field(ge=0, le=86400, allow_inf_nan=False)
    color: int = Field(default=16777215, ge=0, le=16777215)
    mode: int = 1  # 1=滚动 4=底部 5=顶部


@router.post("/v1/danmaku/send")
async def post_danmaku_v1(body: DanmakuCreateV1, auth_session: Optional[str] = Cookie(None)):
    """发送弹幕（鉴权用户），写入 DB 并 WebSocket 推送。"""
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"code": -1, "message": "请先登录"})
    text = (body.text or "").strip()
    if not text or len(text) > 80:
        return JSONResponse(status_code=400, content={"code": -1, "message": "弹幕内容 1～80 字"})
    video_id = (body.video_id or "").strip()[:128]
    if not video_id:
        return JSONResponse(status_code=400, content={"code": -1, "message": "缺少 video_id"})
    if Path(video_id).name!=video_id or not (Path(STORAGE_DIR)/(video_id+'.mp4')).is_file():
        return JSONResponse(status_code=404,content={"code":-1,"message":"视频不存在"})
    t = max(0, float(body.time))
    color = int(body.color) if body.color is not None else 16777215
    mode = int(body.mode) if body.mode is not None else 1
    if mode not in (1, 4, 5):
        mode = 1
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        cursor.execute(
            "INSERT INTO example_video_danmaku (video_id, user_id, text, time, color, mode) VALUES (%s, %s, %s, %s, %s, %s)",
            (video_id, username, text, t, color, mode),
        )
        conn.commit()
        payload = {"code": 0, "data": {"id":cursor.lastrowid,"video_id": video_id, "username": username, "text": text, "time": t,"color":color,"mode":mode}}
        await _broadcast_video(video_id, {"type": "new_danmaku", "data": payload["data"]})
        return payload
    except Exception as e:
        logger.error(f"post_danmaku_v1: {e}")
        return JSONResponse(status_code=500, content={"code": -1, "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


class HeartbeatBody(BaseModel):
    video_id: str
    progress: float = Field(ge=0, le=86400, allow_inf_nan=False)


@router.delete('/v1/danmaku/{ident}')
async def delete_danmaku(ident: int, auth_session: Optional[str] = Cookie(None)):
    username=_username_from_session(auth_session)
    if not username: return JSONResponse(status_code=401,content={'code':-1,'message':'请先登录'})
    conn=get_db_connection();cursor=conn.cursor(dictionary=True)
    try:
        _ensure_tables(cursor)
        cursor.execute('SELECT video_id FROM example_video_danmaku WHERE id=%s AND user_id=%s',(ident,username));row=cursor.fetchone()
        if not row: return JSONResponse(status_code=404,content={'code':-1,'message':'弹幕不存在或无权删除'})
        cursor.execute('DELETE FROM example_video_danmaku WHERE id=%s AND user_id=%s',(ident,username));conn.commit()
        await _broadcast_video(row['video_id'],{'type':'delete_danmaku','id':ident})
        return {'code':0}
    finally:
        cursor.close();conn.close()


@router.post("/v1/player/heartbeat")
async def post_heartbeat(
    body: HeartbeatBody,
    auth_session: Optional[str] = Cookie(None),
):
    """每 30 秒上报一次，更新播放进度并异步增加播放量（防刷）。"""
    video_id = (body.video_id or "").strip()[:128]
    progress = max(0, float(body.progress))
    username = _username_from_session(auth_session)
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        if username:
            cursor.execute(
                """INSERT INTO example_play_history (user_id, video_id, progress, last_active)
                   VALUES (%s, %s, %s, NOW())
                   ON DUPLICATE KEY UPDATE progress = VALUES(progress), last_active = NOW()""",
                (username, video_id, progress),
            )
            conn.commit()
        # 播放量防刷：同一用户同视频在短时间内的多次心跳只计一次（可选：按 last_active 间隔判断）
        # 此处简化：仅更新进度，不在此处自增 views；若需 views 可另表或异步任务
        return {"code": 0}
    except Exception as e:
        logger.error(f"heartbeat: {e}")
        return JSONResponse(status_code=500, content={"code": -1, "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# --- 点赞 ---
class LikeBody(BaseModel):
    video_id: str
    action: str  # "like" | "unlike"


@router.get("/examples/likes")
async def get_likes(video_id: str = Query(..., max_length=128), auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        cursor.execute("SELECT COUNT(*) AS c FROM example_video_likes WHERE video_id = %s", (video_id,))
        count = cursor.fetchone()["c"]
        user_has_liked = False
        if username:
            cursor.execute("SELECT 1 FROM example_video_likes WHERE video_id = %s AND user_id = %s", (video_id, username))
            user_has_liked = cursor.fetchone() is not None
        return {"status": "success", "like_count": count, "user_has_liked": user_has_liked}
    except Exception as e:
        logger.error(f"get_likes: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.post("/examples/like")
async def post_like(body: LikeBody, auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "请先登录"})
    video_id = (body.video_id or "").strip()[:128]
    if not video_id:
        return JSONResponse(status_code=400, content={"status": "error", "message": "缺少 video_id"})
    action = (body.action or "").strip().lower()
    if action not in ("like", "unlike"):
        return JSONResponse(status_code=400, content={"status": "error", "message": "action 为 like 或 unlike"})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        if action == "like":
            cursor.execute(
                "INSERT IGNORE INTO example_video_likes (video_id, user_id) VALUES (%s, %s)",
                (video_id, username),
            )
        else:
            cursor.execute(
                "DELETE FROM example_video_likes WHERE video_id = %s AND user_id = %s",
                (video_id, username),
            )
        conn.commit()
        cursor.execute("SELECT COUNT(*) AS c FROM example_video_likes WHERE video_id = %s", (video_id,))
        count = cursor.fetchone()["c"]
        cursor.execute("SELECT 1 FROM example_video_likes WHERE video_id = %s AND user_id = %s", (video_id, username))
        user_has_liked = cursor.fetchone() is not None
        return {"status": "success", "like_count": count, "user_has_liked": user_has_liked}
    except Exception as e:
        logger.error(f"post_like: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# --- 收藏 / 稍后看 / 笔记 ---
class VideoIdBody(BaseModel):
    video_id: str


class NoteCreate(BaseModel):
    video_id: str
    time_sec: float
    content: str


@router.get("/examples/favorites")
async def get_favorites(auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return {"status": "success", "data": []}
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        cursor.execute("SELECT video_id, created_at FROM user_favorites WHERE user_id = %s ORDER BY created_at DESC", (username,))
        rows = cursor.fetchall()
        out = [{"video_id": r["video_id"], "created_at": time.mktime(r["created_at"].timetuple()) if r.get("created_at") and hasattr(r["created_at"], "timetuple") else None} for r in rows]
        return {"status": "success", "data": out}
    except Exception as e:
        logger.error(f"get_favorites: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.post("/examples/favorites")
async def post_favorite(body: VideoIdBody, auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "请先登录"})
    video_id = (body.video_id or "").strip()[:128]
    if not video_id:
        return JSONResponse(status_code=400, content={"status": "error", "message": "缺少 video_id"})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        cursor.execute("INSERT IGNORE INTO user_favorites (user_id, video_id) VALUES (%s, %s)", (username, video_id))
        conn.commit()
        return {"status": "success", "user_favorited": True}
    except Exception as e:
        logger.error(f"post_favorite: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.delete("/examples/favorites")
async def delete_favorite(video_id: str = Query(..., max_length=128), auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "请先登录"})
    video_id = (video_id or "").strip()[:128]
    if not video_id:
        return JSONResponse(status_code=400, content={"status": "error", "message": "缺少 video_id"})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        cursor.execute("DELETE FROM user_favorites WHERE user_id = %s AND video_id = %s", (username, video_id))
        conn.commit()
        return {"status": "success", "user_favorited": False}
    except Exception as e:
        logger.error(f"delete_favorite: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get("/examples/watch-later")
async def get_watch_later(auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return {"status": "success", "data": []}
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        cursor.execute("SELECT video_id, created_at FROM watch_later WHERE user_id = %s ORDER BY created_at DESC", (username,))
        rows = cursor.fetchall()
        out = [{"video_id": r["video_id"], "created_at": time.mktime(r["created_at"].timetuple()) if r.get("created_at") and hasattr(r["created_at"], "timetuple") else None} for r in rows]
        return {"status": "success", "data": out}
    except Exception as e:
        logger.error(f"get_watch_later: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.post("/examples/watch-later")
async def post_watch_later(body: VideoIdBody, auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "请先登录"})
    video_id = (body.video_id or "").strip()[:128]
    if not video_id:
        return JSONResponse(status_code=400, content={"status": "error", "message": "缺少 video_id"})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        cursor.execute("INSERT IGNORE INTO watch_later (user_id, video_id) VALUES (%s, %s)", (username, video_id))
        conn.commit()
        return {"status": "success", "user_watch_later": True}
    except Exception as e:
        logger.error(f"post_watch_later: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.delete("/examples/watch-later")
async def delete_watch_later(video_id: str = Query(..., max_length=128), auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "请先登录"})
    video_id = (video_id or "").strip()[:128]
    if not video_id:
        return JSONResponse(status_code=400, content={"status": "error", "message": "缺少 video_id"})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        cursor.execute("DELETE FROM watch_later WHERE user_id = %s AND video_id = %s", (username, video_id))
        conn.commit()
        return {"status": "success", "user_watch_later": False}
    except Exception as e:
        logger.error(f"delete_watch_later: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# --- 课件包（教师：我的课件） ---
@router.post("/examples/course-pack/add")
async def add_to_course_pack(body: VideoIdBody, auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "请先登录"})

    video_id = (body.video_id or "").strip()[:128]
    if not video_id:
        return JSONResponse(status_code=400, content={"status": "error", "message": "缺少 video_id"})

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)

        # 获取或创建当前用户的默认课件包
        cursor.execute(
            "SELECT id FROM course_packs WHERE user_id = %s ORDER BY id ASC LIMIT 1",
            (username,),
        )
        row = cursor.fetchone()
        pack_id = row["id"] if row else None
        if not pack_id:
            cursor.execute(
                "INSERT INTO course_packs (user_id, name) VALUES (%s, %s)",
                (username, "我的课件包"),
            )
            pack_id = cursor.lastrowid

        # 将视频加入课件包（忽略重复）
        cursor.execute(
            "INSERT IGNORE INTO course_pack_videos (pack_id, video_id, sort_order) VALUES (%s, %s, %s)",
            (pack_id, video_id, 0),
        )
        conn.commit()
        return {"status": "success", "in_course_pack": True}
    except Exception as e:
        logger.error(f"add_to_course_pack: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.get("/examples/notes")
async def get_notes(video_id: str = Query(..., max_length=128), auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return {"status": "success", "data": []}
    video_id = (video_id or "").strip()[:128]
    if not video_id:
        return JSONResponse(status_code=400, content={"status": "error", "message": "缺少 video_id"})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        cursor.execute(
            "SELECT id, video_id, time_sec, content, created_at FROM example_video_notes WHERE user_id = %s AND video_id = %s ORDER BY time_sec ASC",
            (username, video_id),
        )
        rows = cursor.fetchall()
        out = []
        for r in rows:
            created = r.get("created_at")
            out.append({
                "id": r["id"],
                "video_id": r["video_id"],
                "time_sec": float(r.get("time_sec", 0)),
                "content": r.get("content", ""),
                "created_at": time.mktime(created.timetuple()) if created and hasattr(created, "timetuple") else None,
            })
        return {"status": "success", "data": out}
    except Exception as e:
        logger.error(f"get_notes: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.post("/examples/notes")
async def post_note(body: NoteCreate, auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "请先登录"})
    video_id = (body.video_id or "").strip()[:128]
    if not video_id:
        return JSONResponse(status_code=400, content={"status": "error", "message": "缺少 video_id"})
    content = (body.content or "").strip()
    if not content or len(content) > 2000:
        return JSONResponse(status_code=400, content={"status": "error", "message": "笔记内容 1～2000 字"})
    time_sec = max(0, float(body.time_sec))
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        cursor.execute(
            "INSERT INTO example_video_notes (user_id, video_id, time_sec, content) VALUES (%s, %s, %s, %s)",
            (username, video_id, time_sec, content),
        )
        conn.commit()
        nid = cursor.lastrowid
        return {"status": "success", "data": {"id": nid, "video_id": video_id, "time_sec": time_sec, "content": content}}
    except Exception as e:
        logger.error(f"post_note: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.delete("/examples/notes/{note_id}")
async def delete_note(note_id: int, auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "请先登录"})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        cursor.execute("DELETE FROM example_video_notes WHERE id = %s AND user_id = %s", (note_id, username))
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"delete_note: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# --- 评论 ---
class CommentCreate(BaseModel):
    video_id: str
    content: str


@router.get("/examples/comments")
async def get_comments(video_id: str = Query(..., max_length=128)):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        cursor.execute(
            "SELECT id, video_id, user_id AS username, content, created_at FROM example_video_comments WHERE video_id = %s ORDER BY id ASC",
            (video_id,),
        )
        rows = cursor.fetchall()
        for r in rows:
            if r.get("created_at"):
                r["created_at"] = time.mktime(r["created_at"].timetuple()) if hasattr(r["created_at"], "timetuple") else r["created_at"]
        return {"status": "success", "data": rows}
    except Exception as e:
        logger.error(f"get_comments: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.post("/examples/comments")
async def post_comment(body: CommentCreate, auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "请先登录"})
    content = (body.content or "").strip()
    if not content or len(content) > 2000:
        return JSONResponse(status_code=400, content={"status": "error", "message": "评论内容 1～2000 字"})
    video_id = (body.video_id or "").strip()[:128]
    if not video_id:
        return JSONResponse(status_code=400, content={"status": "error", "message": "缺少 video_id"})
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        cursor.execute(
            "INSERT INTO example_video_comments (video_id, user_id, content) VALUES (%s, %s, %s)",
            (video_id, username, content),
        )
        conn.commit()
        cid = cursor.lastrowid
        cursor.execute(
            "SELECT id, video_id, user_id AS username, content, created_at FROM example_video_comments WHERE id = %s",
            (cid,),
        )
        row = cursor.fetchone()
        if row and row.get("created_at"):
            row["created_at"] = time.mktime(row["created_at"].timetuple())
        return {"status": "success", "data": row}
    except Exception as e:
        logger.error(f"post_comment: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# --- 弹幕 ---
class DanmakuCreate(BaseModel):
    video_id: str
    text: str
    time: float


@router.websocket("/examples/ws/{video_id}")
async def websocket_video_room(websocket: WebSocket, video_id: str):
    video_id = (video_id or "").strip()[:128]
    if not video_id:
        await websocket.close(code=4000)
        return
    await websocket.accept()
    room = _ws_rooms.setdefault(video_id, set())
    room.add(websocket)
    count = len(room)
    await _broadcast_video(video_id, {"type": "viewer_count", "count": count})
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}, ensure_ascii=False))
            except (json.JSONDecodeError, TypeError):
                pass
    except WebSocketDisconnect:
        pass
    finally:
        room.discard(websocket)
        if not room:
            _ws_rooms.pop(video_id, None)
        else:
            await _broadcast_video(video_id, {"type": "viewer_count", "count": len(room)})


@router.get("/examples/danmaku")
async def get_danmaku(video_id: str = Query(..., max_length=128)):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        cursor.execute(
            "SELECT id, video_id, user_id AS username, text, time, created_at FROM example_video_danmaku WHERE video_id = %s ORDER BY time ASC, id ASC",
            (video_id,),
        )
        rows = cursor.fetchall()
        out = []
        for r in rows:
            out.append({
                "video_id": r.get("video_id"),
                "username": r.get("username"),
                "text": r.get("text"),
                "time": float(r.get("time", 0)),
                "created_at": time.mktime(r["created_at"].timetuple()) if r.get("created_at") and hasattr(r["created_at"], "timetuple") else r.get("created_at"),
            })
        return {"status": "success", "data": out}
    except Exception as e:
        logger.error(f"get_danmaku: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@router.post("/examples/danmaku")
async def post_danmaku(body: DanmakuCreate, auth_session: Optional[str] = Cookie(None)):
    username = _username_from_session(auth_session)
    if not username:
        return JSONResponse(status_code=401, content={"status": "error", "message": "请先登录"})
    text = (body.text or "").strip()
    if not text or len(text) > 80:
        return JSONResponse(status_code=400, content={"status": "error", "message": "弹幕内容 1～80 字"})
    video_id = (body.video_id or "").strip()[:128]
    if not video_id:
        return JSONResponse(status_code=400, content={"status": "error", "message": "缺少 video_id"})
    t = max(0, float(body.time))
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        cursor.execute(
            "INSERT INTO example_video_danmaku (video_id, user_id, text, time) VALUES (%s, %s, %s, %s)",
            (video_id, username, text, t),
        )
        conn.commit()
        payload = {"status": "success", "data": {"video_id": video_id, "username": username, "text": text, "time": t}}
        await _broadcast_video(video_id, {"type": "new_danmaku", "data": payload["data"]})
        return payload
    except Exception as e:
        logger.error(f"post_danmaku: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
