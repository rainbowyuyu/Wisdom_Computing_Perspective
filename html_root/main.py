# 应用入口：挂载路由与静态资源
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

import uvicorn

# Windows: asyncio 子进程必须使用 ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app):
    from app.config import db_pool
    from app.database import apply_migrations
    if db_pool:
        await asyncio.to_thread(apply_migrations)
    else:
        logger.warning('数据库不可用，账户存储功能暂不可用')
    yield

app = FastAPI(lifespan=lifespan)

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

# 静态资源
app.mount("/css", StaticFiles(directory="static/css"), name="css")
app.mount("/js", StaticFiles(directory="static/js"), name="js")
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")
app.mount("/docs", StaticFiles(directory="static/docs"), name="docs")
app.mount("/videos", StaticFiles(directory="static/videos"), name="videos")
app.mount("/static", StaticFiles(directory="static"), name="static_root")


@app.get("/")
async def read_index():
    return FileResponse("static/index.html")


@app.get("/update.md")
async def read_update_log():
    if os.path.exists("static/docs/update.md"):
        return FileResponse("static/docs/update.md")
    if os.path.exists("update.md"):
        return FileResponse("update.md")
    from fastapi import HTTPException
    raise HTTPException(status_code=404)


@app.exception_handler(404)
async def not_found_exception_handler(request, exc):
    path = request.url.path
    if path.startswith("/api/") or "." in path.split("/")[-1]:
        return JSONResponse(status_code=404, content={"message": "Not Found"})
    return FileResponse("static/index.html")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
