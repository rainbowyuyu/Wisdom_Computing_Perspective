# 智算视界 · 新工作台部署包

这份包用于把原宝塔网站切换到新的可视化工作台。默认网站目录是 `/www/wwwroot/wiscomper.com`，正式网址是 `https://www.wiscomper.com`，仍通过 `python main.py` 启动，端口仍为 `8000`。

## 保留的内容

- 服务器的 `.env`、`.env.local` 原样保留，不带入开发电脑上的密钥。
- MySQL 原库、账号、密码、权限和资料保留；安装程序不执行建表、删表或数据迁移 SQL。
- 原来的 `var/`、`data/`、`storage/`、上传文件和视频保留。
- 新项目、版本、素材和会话单独保存在 `var/wiscomper-harness/`。以后更新或回滚也不删除这里。

旧邮箱账号直接使用原数据库登录。公式、笔记和错题可按当前迁入功能导入；旧课包和视频仍保留在原库与文件目录中，**不代表它们已经全部出现在新工作台里**。本包不包含你电脑上的项目、用户库或视频。

## 上传与安装

1. 在宝塔备份一次原数据库。把整个 ZIP 上传到 **站点目录以外**，例如 `/www/deploy/`，解压后进入与 ZIP 同名的文件夹。构建器默认按北京时间日期命名，也可用 `--release-name` 指定。不要直接把 ZIP 解压覆盖到网站根目录。
2. 在宝塔停止原 Python 项目。终端需要 **Python 3.11 或更新版本、Node.js 24**（也兼容 Node 22.19+ 的 22 系列）。宝塔里安装了 Node 后，还需把它的 `bin` 目录加入当前终端 `PATH`。
3. 使用宝塔的 Python 3.11+ 执行下面一条命令。若 `python3` 版本过旧，就将它替换为宝塔所选 Python 的绝对路径：

```bash
python3 deploy.py install --target /www/wwwroot/wiscomper.com
```

程序会校验包、准备独立 Python/npm 依赖、只读检查旧库、下载 Chromium，再备份并替换代码。下载或配置检查失败时不会切换旧站代码。不会改动原 Python 环境。需要服务器能访问 Python/npm/Playwright 的下载地址，首次执行可能需要几分钟。文件按清单逐个替换，安装和回滚期间应始终保持原项目停止。

默认按网站目录所有者准备可写数据目录。如果宝塔 Python 项目使用的是另一个运行用户，请显式指定，例如：

```bash
python3 deploy.py install --target /www/wwwroot/wiscomper.com --service-user www
```

安装会首次创建 `.env.deploy`，只放正式网址、端口、新数据目录及旧库选择，**不含密钥**。配置优先级是：进程环境变量 → `.env.local` → `.env` → `.env.deploy`。如果原配置已有冲突网址、空的 `PUBLIC_SITE_URL`、其他端口或数据库选择，预检会说明并停止；请在服务器确认正确设置后重试，不会自动覆盖你的原值。

4. 按包内 `nginx-harness.conf.example` 修改宝塔现有 HTTPS 站点的代理部分，再检查配置并重新加载 Nginx。保留证书和域名验证配置。**替换旧规则，不要重复追加 `location /`**：新 `/web/`、`/vendor/` 必须进入 Python 服务，不能被旧 JS/CSS 静态缓存规则拦截。代理 Host 使用 `www.wiscomper.com`。不要把整个工程或 `var/` 当成公开静态目录。
5. 在宝塔重启原 Python 项目，启动命令仍为 `python main.py`。旧的 `python start.py` 也可继续调用该入口。新入口会使用这次准备的独立环境；不要另开第二个 worker。若旧项目配置的是 `main:app`，需改成 `python main.py` 命令启动。

安装器只负责文件与环境，不修改宝塔面板、Nginx、证书或自动停止/启动服务。

## 上线后检查

```bash
curl --fail http://127.0.0.1:8000/healthz
curl --fail https://www.wiscomper.com/healthz
curl --fail -I https://www.wiscomper.com/web/brand.css
curl --fail -I https://www.wiscomper.com/vendor/three/three.module.js
```

打开网站，检查首页样式、旧邮箱登录、公式库和一个内置三维示例。登录会话需要重新建立。随后再提交一次自己的 Qwen 创作；这一步会正常调用模型并占用额度。预检和安装本身不会调用模型或发送邮件。

服务器已有的 `MYSQL_*`、`ALIYUN_KEY`、`SOLVER_MODEL` 和 `SMTP_*` 配置会继续读取。`AI_ENABLED=0` 仍保持停用。普通在线用户仅开放 Qwen；ChatGPT/Claude 需要 VIP/管理员身份且服务器已配置相应服务。本机 CC Switch 和 DPAPI 密钥不会被打包上传。

GitHub 登录需要为正式域名单独配置 OAuth App：回调为 `https://www.wiscomper.com/api/auth/github/callback`。现有本机 OAuth App 不适用于正式站；没有配置正式 Client ID/Secret 时，邮箱登录仍可使用。

## 视频导出与 Manim

交互场景可在浏览器里使用，不依赖视频导出环境。浏览器导出额外需要 FFmpeg 与 Chromium 系统库；安装脚本会下载 Chromium，但不会自动更改服务器的系统软件。检查 `ffmpeg -version`，并按服务器发行版安装 Playwright 所需库；可用本次环境执行 `.venv-wiscomper/bin/python -m playwright install-deps chromium`（需要系统安装权限）。

如服务器已有 Cairo/Pango、LaTeX、dvisvgm、FFmpeg，可在首次安装命令增加 `--with-manim`，把 Manim 一起装入独立 Python 环境。它不会沿用旧 Python 环境里安装的 Manim。缺少这些条件时网页仍可使用，未准备好的视频导出入口会提示依赖未就绪。只准备交互工作台可加 `--skip-browser` 跳过 Chromium 下载。

## 回滚

安装完成时会打印具体备份目录，形如：

```text
/www/wwwroot/wiscomper.com.deploy-backups/日期-随机编号
```

在宝塔停止 Python 项目后，从部署包目录执行，替换为实际路径：

```bash
python3 deploy.py rollback --backup /www/wwwroot/wiscomper.com.deploy-backups/实际备份目录
```

它会恢复被覆盖的程序及原依赖入口，删除这次新增且未改动的程序文件，保留 `.env`、MySQL 与所有新旧用户内容。更新后手动改过的程序文件会阻止回滚，避免覆盖新修改；请先保存这些改动。然后恢复此前的 Nginx 代理设置并重启旧项目。

备份与独立运行环境都在站点同级目录，不通过网页提供下载。不要在验收前删除 `.deploy-backups`、`.deploy-runtimes`。保留原数据库备份；代码回滚不回滚上线期间用户正常修改的账号、密码等数据库记录。

高级用法：`python3 install.py dry-run --target /www/wwwroot/wiscomper.com` 可只预览源码变化；`install.py` 不准备依赖，首次安装请使用上面的 `deploy.py`。

## 这份包的验证范围

已在本机隔离环境验证 ZIP 清单、源码覆盖、配置保留、备份回滚、错误中断及账号/模型权限回归。测试使用模拟数据库、邮箱和模型，没有对你的服务器执行部署或发送真实请求。Linux 独立环境与符号链接分支有模拟测试；Windows 当前没有创建目录符号链接的权限，3 个真实链接测试跳过，尚未在宝塔实机完成安装验收。首次上服务器仍需按上面的步骤验证依赖、代理和服务用户权限。

`SHA256SUMS.txt` 与 ZIP 旁的 `.sha256` 文件用于检查传输是否完整，不是发布者签名。部署包应从本次提供的文件获取。
