# 全局配置：数据库连接池、OpenAI 客户端、目录等
import os
import logging
from dotenv import load_dotenv
import mysql.connector
from openai import OpenAI

# 项目根目录（html_root，与 main.py 同级）
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Local credentials override the repository defaults; deployment env vars win.
load_dotenv(os.path.join(ROOT_DIR, ".env.local"))
load_dotenv(os.path.join(ROOT_DIR, ".env"))
logger = logging.getLogger(__name__)

# MySQL
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "password")
MYSQL_DB = os.getenv("MYSQL_DB", "visdom_db")
def _int_env(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default

MYSQL_PORT = _int_env("MYSQL_PORT", 3306)

try:
    db_pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="mypool",
        pool_size=5,
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DB,
        port=MYSQL_PORT,
    )
    logger.info("MySQL connection pool created successfully")
except Exception as e:
    logger.error(f"Error creating MySQL pool: {e}")
    db_pool = None


def get_db_connection():
    if not db_pool:
        raise Exception("Database connection not initialized")
    return db_pool.get_connection()


# 大模型
from .usage_guard import GuardedClient
api_key = os.getenv("ALIYUN_KEY")
client = GuardedClient(OpenAI(
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    api_key=api_key or "sk-mock-key",
))

# 头像与视频目录（相对项目根）
AVATAR_DIR = os.path.join(ROOT_DIR, "static", "avatars")
os.makedirs(AVATAR_DIR, exist_ok=True)
ALLOWED_AVATAR_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
VIDEOS_DIR = os.path.join(ROOT_DIR, "static", "videos")
os.makedirs(VIDEOS_DIR, exist_ok=True)

# 教学案例视频存储与鉴权（storage 内视频使用签名 URL）
STORAGE_DIR = os.path.join(ROOT_DIR, "static", "assets", "storage")
VIDEO_TOKEN_SECRET = os.getenv("VIDEO_TOKEN_SECRET", "dev-secret-change-in-prod")
VIDEO_TOKEN_EXPIRES_SECONDS = 3600  # 鉴权 URL 有效期 1 小时

# 阿里云 CDN/DCDN 鉴权（可选：配置后视频走 CDN 鉴权地址，否则走本站 stream）
# 资源包示例：CDN/DCDN_ResourcePack-cn-f0g4o1vfg001gx（在控制台绑定域名即可，此处仅配置鉴权参数）
ALIYUN_CDN_RESOURCE_PACK_ID = os.getenv("ALIYUN_CDN_RESOURCE_PACK_ID", "CDN/DCDN_ResourcePack-cn-f0g4o1vfg001gx")
ALIYUN_CDN_DOMAIN = os.getenv("ALIYUN_CDN_DOMAIN", "").rstrip("/")  # 例如 https://your-cdn.example.com
ALIYUN_CDN_AUTH_KEY = os.getenv("ALIYUN_CDN_AUTH_KEY", "")           # 控制台「URL 鉴权」中配置的主 KEY
ALIYUN_CDN_AUTH_TYPE = os.getenv("ALIYUN_CDN_AUTH_TYPE", "a").lower()  # a=鉴权方式A(b 暂不实现)
ALIYUN_CDN_VIDEO_PATH = os.getenv("ALIYUN_CDN_VIDEO_PATH", "/storage").rstrip("/")  # CDN 上视频路径前缀
ALIYUN_CDN_AUTH_TTL = _int_env("ALIYUN_CDN_AUTH_TTL", 3600)  # 鉴权 URL 有效时长（秒）
# 公开 CDN 基地址（可选）：不开启 URL 鉴权时，设为与 ALIYUN_CDN_DOMAIN 相同，列表与预览将直接走 CDN 加速
ALIYUN_CDN_PUBLIC_BASE = os.getenv("ALIYUN_CDN_PUBLIC_BASE", "").rstrip("/")
# 教学案例是否走 CDN（0=本地，1=CDN；默认 0，保留 CDN 接口以便后续开启）
EXAMPLES_USE_CDN = os.getenv("EXAMPLES_USE_CDN", "0").strip() in ("1", "true", "yes")
