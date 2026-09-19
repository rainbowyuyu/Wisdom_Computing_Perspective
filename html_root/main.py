# 应用入口：挂载路由与静态资源
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

import uvicorn

# Windows: asyncio 子进程必须使用 ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parent
STATIC_DIR = ROOT_DIR / "static"

@asynccontextmanager
async def lifespan(app):
    from app.config import db_pool
    from app.database import apply_migrations
    if db_pool:
        await asyncio.to_thread(apply_migrations)
    else:
        logger.warning('数据库不可用，账户存储功能暂不可用')
    from app.math_jobs import manager
    try:
        yield
    finally:
        await manager.close()
        from app.request_records import journal
        await asyncio.to_thread(journal.close)

app = FastAPI(lifespan=lifespan)
from app.static_compression import StaticCompression
app.add_middleware(StaticCompression)

@app.middleware("http")
async def revalidate_site_code(request, call_next):
    response = await call_next(request)
    path = request.url.path
    # Revalidate first-party code after deployment without disabling media caching.
    if path == '/' or path.startswith(('/js/', '/css/', '/static/js/', '/static/css/')):
        response.headers['Cache-Control'] = 'no-cache'
    if path.startswith(('/api/search', '/api/wrongbook', '/api/examples/course-packs', '/api/formulas/solutions')):
        response.headers['Cache-Control'] = 'private, no-store'
    return response


# 注册路由（各功能模块在 app 包内）
from app.routers import auth, user, formulas, animation_scripts, detect, examples, devtools, agent, agent_templates, achievements, wrongbook, search
from app.routers import solve
from app.routers import solution_library

app.include_router(auth.router, prefix="/api")
app.include_router(user.router, prefix="/api")
app.include_router(formulas.router, prefix="/api")
app.include_router(animation_scripts.router, prefix="/api")
app.include_router(detect.router, prefix="/api")
app.include_router(examples.router, prefix="/api")
app.include_router(devtools.router, prefix="/api")
app.include_router(agent.router, prefix="/api")
app.include_router(agent_templates.router, prefix="/api")
app.include_router(achievements.router, prefix="/api")
app.include_router(wrongbook.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(solve.router, prefix="/api")
app.include_router(solution_library.router, prefix="/api")
from app.routers import course_packs
app.include_router(course_packs.router, prefix="/api")
from app.routers import math_tasks
app.include_router(math_tasks.router, prefix="/api")
from app.request_guard import RequestGuard
app.add_middleware(RequestGuard)
from app.routers import accounts
app.include_router(accounts.router,prefix='/api')
from app.access import AccessDenied

@app.exception_handler(AccessDenied)
async def access_error(request,exc):
    return JSONResponse(status_code=exc.status,content={'status':'error','message':str(exc),'code':exc.code},headers={'Cache-Control':'private, no-store','X-Wisdom-Access':exc.code})

# 静态资源
for name in ("css", "js", "assets", "docs", "videos"):
    app.mount(f"/{name}", StaticFiles(directory=STATIC_DIR / name), name=name)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static_root")


@app.get("/")
async def read_index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/update.md")
async def read_update_log():
    if (STATIC_DIR / "docs/update.md").exists():
        return FileResponse(STATIC_DIR / "docs/update.md")
    from fastapi import HTTPException
    raise HTTPException(status_code=404)


@app.exception_handler(404)
async def not_found_exception_handler(request, exc):
    path = request.url.path
    if path.startswith("/api/") or "." in path.split("/")[-1]:
        return JSONResponse(status_code=404, content={"message": "Not Found"})
    return FileResponse(STATIC_DIR / "index.html")


def run():
    """Start every website route from the same application and working directory."""
    os.chdir(ROOT_DIR)
    # Sessions, rendering tasks and WebSocket rooms share this single process.
    # Passing the app avoids importing main a second time and creating another DB pool.
    uvicorn.run(app, host=os.getenv("HOST", "127.0.0.1"),
                port=int(os.getenv("PORT", "8000")), workers=1, reload=False, proxy_headers=False)


if __name__ == "__main__":
    run()
