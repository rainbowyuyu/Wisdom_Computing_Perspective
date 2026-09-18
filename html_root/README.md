# 智算视界 · 网站部署目录

上传 **`html_root` 这一整个目录**即可部署网站，不依赖仓库外的 Python 源码或 `vue_root`。Python、MySQL、FFmpeg 和 LaTeX 等运行环境需要在服务器安装。

当前正式入口是 `static/index.html`，由 `main.py` 提供网页和接口。Vue 源码已归入 `frontend/`，用于前端开发；部署当前网站不需要 Node.js 或单独启动 Vue。

## 文件位置

```text
html_root/
├── main.py                  # 统一启动入口，单进程启动全部网页与接口
├── start.py                 # 兼容入口，调用 main.py 的同一启动函数
├── requirements.txt         # 网站全部 Python 依赖
├── .env.example             # 服务器配置模板，无真实凭据
├── visdom_db.sql            # 唯一手动执行入口：完整建表 + 原网站旧库升级
├── app/                     # 账户、课包、错题、智能体、数据库等后端功能
├── logic/                   # 识别、计算与 Manim 动画
├── static/                  # 正式网页、样式、脚本、图标、成就贴图和教学视频
├── frontend/                # Vue 源码和构建配置，原仓库外的 vue_root
├── database/                # 数据结构说明、应用自动升级记录
├── deploy/                  # 宝塔部署说明、Nginx 反向代理示例
├── scripts/                 # 维护脚本
└── tests/                   # 回归验证
```

## 宝塔部署

完整步骤见 [deploy/BAOTA.md](deploy/BAOTA.md)。数据库面板只需执行一个文件：

1. 在宝塔中备份现有数据库。
2. 打开 phpMyAdmin，左侧选中 **`wiscomper_com`**，点击「SQL」。
3. 复制本目录 **`visdom_db.sql` 全部内容**，粘贴后执行；也可以在「导入」中选择此文件。
4. 将 `.env.example` 复制为 `.env.local`，填写宝塔给出的数据库名、用户名和密码。
5. 安装依赖后，在宝塔 Python 项目中运行 `python main.py`，配置域名反向代理至 `127.0.0.1:8000`。

SQL 使用面板当前选中的数据库，保留原表和数据，补齐至 25 张业务/迁移表；不需要再复制多个迁移文件。要求 MySQL 8.0+，旧库默认排序规则可以继续使用截图中的 `utf8mb4_general_ci`。截图没有列定义，兼容范围是原网站的 18 表结构；手工改过字段或有孤儿关联的库，需要按实际报错修正后重试。

## 本地开发

```sh
python -m pip install -r requirements.txt
python main.py
```

Vue 开发可另开终端：

```sh
cd frontend
npm ci
npm run dev
```

Vue 的 `/api` 和静态资源仍代理至同一个 Python 服务；`npm run build` 在 `frontend/dist` 输出前端构建，不会把后端配置复制进去。

上传时不需要 `.venv`、`node_modules`、`__pycache__`、`.pytest_cache`、`tmp`、`tests/artifacts` 或独立宣传视频工程 `product-video`。服务器使用自己的 `.env.local`，不要用本机 `.env` / `.env.local` 覆盖服务器凭据。更新时保留 `static/avatars`、`static/videos`、`static/assets/storage` 中已经产生的用户内容。
