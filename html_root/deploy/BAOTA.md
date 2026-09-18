# 宝塔部署与已有数据库升级

## 1. 上传目录

将 `html_root` 上传到例如 `/www/wwwroot/wiscomper_com/html_root`。下文路径可替换为你的实际目录。网站不需要上传仓库上级的训练项目、桌面程序、论文或其他目录。

正式网页由 Python 服务提供。不要把整个 `html_root` 当作可公开下载的静态目录；Nginx 通过反向代理访问网页，只由 Python 暴露 `static` 内的资源。

## 2. 在数据库面板执行 SQL

在宝塔「数据库」中先备份 `wiscomper_com`，进入 phpMyAdmin 后：

1. 左侧选中 `wiscomper_com`，确认顶部显示「数据库：wiscomper_com」。
2. 点击「SQL」，复制 `html_root/visdom_db.sql` 全文并执行；长文件也可通过「导入」上传同一文件。
3. 末尾结果应显示 `current_database = wiscomper_com`、`total_tables = 25`（如果自行添加过其他表则更多）。`unmatched_legacy_wrongbook` 是保留在旧表、暂未归入新错题本的条数。

脚本既能初始化空库，也能升级原网站 18 张表的库。它补充完整题解、教案、课包材料、错题复习等表，补齐索引和关联，并将能精确匹配用户名的旧错题复制进新错题本；原表和内容保留。重复执行不会重复导入旧错题。

无需修改 SQL 里的库名，也无需 `CREATE DATABASE` 权限。数据库账号需要当前库的建表、改表、索引和读写权限。无需存储过程权限。使用 **MySQL 8.0+**；本次未验证 MariaDB 或 MySQL 5.7。

如果提示「没有选择数据库」，重新选中左侧数据库后执行。如果新增外键提示旧数据没有对应父记录，先核对记录归属并修复再重试；脚本不会为通过检查而删除数据或关闭外键检查。MySQL 改表会逐条提交，执行前的数据库备份是回退依据。

## 3. 安装 Python 与动画环境

在宝塔 Python 项目管理中创建 Python 3.11 或 3.12 虚拟环境，并将工作目录设置为 `html_root`。Ubuntu / Debian 的系统依赖示例：

```sh
sudo apt-get update
sudo apt-get install -y build-essential python3-dev pkg-config libcairo2-dev libpango1.0-dev ffmpeg texlive-latex-extra texlive-fonts-recommended texlive-lang-chinese dvisvgm fonts-noto-cjk
python -m pip install -r requirements.txt
```

其他 Linux 发行版使用对应的软件包管理器。这里的 `python` 应使用宝塔项目虚拟环境内的解释器。LaTeX、dvisvgm 和中文字体用于公式与中文动画，FFmpeg 用于视频输出。

## 4. 配置并启动

复制 `.env.example` 为 `.env.local`，填入当前库的连接信息：

```dotenv
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DB=wiscomper_com
MYSQL_USER=宝塔数据库用户名
MYSQL_PASSWORD=宝塔数据库密码
ALIYUN_KEY=自己的模型服务密钥
VIDEO_TOKEN_SECRET=自行生成的长随机字符串
```

环境变量优先于 `.env.local`，`.env.local` 优先于 `.env`。不给模型服务密钥时，AI 识别和生成无法调用远程服务。

宝塔启动命令设置为虚拟环境中的 **`python main.py`**；监听地址默认 `127.0.0.1:8000`。可通过环境变量 `HOST` 和 `PORT` 修改。`main.py` 会统一启动正式网页、全部 API、流式解答、播放器 WebSocket 与数据库迁移检查；无需单独启动其他 Python 文件或 Vue。旧的 `python start.py` 仍调用同一个启动函数。进程用户需要能写入 `static/avatars`、`static/videos`、教学视频存储目录和系统临时目录。

使用一个进程，**不要开启 reload 或多个 worker**：现有登录会话、渲染任务和播放器 WebSocket 房间保存在进程内。重启会要求用户重新登录；服务器重启后让宝塔自动拉起此进程。

## 5. 连接域名

将 [nginx.conf.example](nginx.conf.example) 的 location 配置合并到宝塔站点现有 `server` 块，保留域名、证书和验证文件配置，替换原有同名 `location /`，不要重复添加。移除覆盖这些路径的旧反向代理或静态缓存规则。

配置支持流式解答、WebSocket 和较长动画请求。测试配置通过后重载 Nginx。首次部署依次验证：网页打开、账户登录、保存算式、创建课包、打开错题本、生成一次短动画。

## 6. 后续更新

替换网站源码时保留服务器配置与用户媒体目录，再执行最新版 `visdom_db.sql` 或让应用按 `database/migrations` 检查升级。不要修改已经执行过的历史迁移文件。Vue 源码在 `frontend/`，当前正式静态网页无需前端构建步骤。

### 启动报 Unknown collation: utf8mb4_0900_ai_ci

这表示数据库不支持 MySQL 8 的排序规则，与报错堆栈中的 Python 3.10 无关。更新网站的 `app/database.py` 后，用 `python main.py` 重新启动。迁移会检查服务器能力：支持时保留原规则，不支持时使用 `utf8mb4_general_ci`。不需要删库、清空迁移记录或修改历史 SQL 文件；之前失败的迁移会重新执行，已存在的表和原始记录保留。

此修复针对排序规则兼容问题，不代表所有旧版 MySQL / MariaDB 功能都已完成验证。完整部署仍建议使用 MySQL 8.0+。
