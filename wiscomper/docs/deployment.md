# Wiscomper 智算视界：独立公网部署与检索准备

本工程的英文名称为 **Wisdom Computer Perspective**。默认使用本机 `http://127.0.0.1:3088/`；原有 `万象世界.exe` 保留为兼容启动入口。可明确配置旧站 MySQL 以继续使用已有邮箱账号；新工作台的工程、版本和场景仍保存在自己的数据库，不覆盖旧站文件。

## 1. 域名与运行配置

先完成 [README](../README.md) 中的依赖与渲染环境安装。生产服务仍监听 `127.0.0.1`，不要改为 `0.0.0.0`。让同机 HTTPS 反向代理访问该端口；代理与应用分机时，先建立受控的私有连接或隧道，不要直接公开应用端口。

把 `.env.example` 复制为本机私有 `.env`，至少设置：

```dotenv
PUBLIC_SITE_URL=https://wiscomper.example.com
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
PUBLIC_ACCOUNT_DAILY_TASKS=3
VISUALIZE_PORT=3088
VISUALIZE_DAILY_CALLS=30
```

将 `wiscomper.example.com` 替换为你控制的真实域名。`PUBLIC_SITE_URL` 只接受 HTTPS 域名根地址；可以有末尾 `/`，标准 `:443` 会被规范化。IP、localhost、单段名称、本地域名、凭据、其他端口、路径、查询和片段都会使配置失败。校验只判断格式与明显的本机地址，不代替 DNS 归属验证。环境变量优先于 `.env`；显式空环境值会恢复本机模式，不能误以为文件中的公网值仍生效。

正式配置后应通过该 HTTPS 域名访问浏览器工作台；会话 Cookie 使用 Secure。`main.py` 保持 `proxy_headers=False`，不会信任任意 `X-Forwarded-*` 头。canonical、分享地址、结构化数据和 OAuth 公网回调始终取自配置，不根据访问者提供的 Host 拼接。

模型连接按 [runtime/README.md](../runtime/README.md) 配置。Windows 的 Qwen 继续使用当前用户 DPAPI 与全局工具；Linux 服务器读取原 `.env` 的 `ALIYUN_KEY`，也支持 `DASHSCOPE_API_KEY`，仅连接所选官方 DashScope 区域。ChatGPT/Claude 可使用服务端独立覆盖项；真实密钥只保存在部署环境中。没有可用模型时仍可使用内置示例。旧站替换请使用 [部署包说明](../deploy/DEPLOY-PACKAGE.md)，保留原配置和数据。

## 2. GitHub OAuth App

在 GitHub 的 **Settings → Developer settings → OAuth Apps** 中为这份部署单独创建 OAuth App：

| 项目 | 值 |
|---|---|
| Application name | Wiscomper 智算视界 |
| Homepage URL | `https://wiscomper.example.com/` |
| Authorization callback URL | `https://wiscomper.example.com/api/auth/github/callback` |
| Client ID | 写入服务端 `GITHUB_CLIENT_ID` |
| Client secret | 写入服务端 `GITHUB_CLIENT_SECRET`，不写入网页、文档、日志或仓库 |

回调 URL 必须与实际域名、HTTPS 和路径完全一致。开发与正式部署宜使用不同 OAuth App；本机调试使用可信 loopback 地址的同一路径，例如 `http://127.0.0.1:3088/api/auth/github/callback`，不要将它误填为正式回调。

登录只请求 `read:user`，不请求 `user:email` 或仓库权限。服务端使用 state 与 PKCE S256 处理登录流程，不持久保存 GitHub access token。OAuth code、state、Cookie、Authorization 和客户端密钥都不得进入代理访问日志或应用调试日志。不要把浏览器回调完整地址粘贴到公开问题或截图中。

公网匿名访问可阅读介绍、探索内置示例，最多保存 24 个访客项目。自行模型创作、上传图片和视频导出需要登录。支持邮箱或用户名密码登录，以及 GitHub 登录；旧邮箱账号须完成邮箱验证后才能在线发起模型任务。

普通账号默认每日 3 个模型任务，旧 `account_access.daily_limit` 非空时优先使用旧额度（0 为禁止新增模型任务）。VIP/管理员免个人日额度，所有账号仍受全站模型步骤预算约束。普通在线账号只允许 Qwen；ChatGPT/Claude 需要 VIP/管理员身份。服务端在创建任务、预留预算之前检查权限，网页选项仅用于说明。

本机例外要求：未配置 `PUBLIC_SITE_URL`、请求的实际连接与 URL 都是 loopback，且没有代理转发头。配置公网模式后，即使反向代理从 `127.0.0.1` 连接应用，也不会授予本机权限。部署公网时必须填写正式域名，不能用空配置绕过在线策略。

邮箱账号角色来自旧库 `account_access`，每次 API 请求重新读取；改密后旧会话失效。GitHub 身份按其数字 ID 隔离，不会仅因用户名或邮箱相同就自动取得旧账号数据或角色。

## 3. Nginx HTTPS 反向代理示例

以下配置假设 Nginx 是直接面对用户的入口、与应用在同一机器，并已取得真实域名的有效证书。使用自己的证书路径；Windows Nginx 需替换示例中的 Linux 文件路径，`/dev/null` 对应 Windows 的 `NUL`。先用 `nginx -t` 检查，再按部署环境的服务管理方式加载。

放在 Nginx `http {}` 内的公共配置：

```nginx
# 不记录query string、Referer、Cookie或Authorization。
log_format wiscomper '$remote_addr [$time_local] "$request_method $uri $server_protocol" '
                     '$status $body_bytes_sent $request_time';

# 只限制会创建任务、上传或执行视频导出的请求，保留交互保存的流畅度。
map "$request_method:$uri" $wiscomper_cost_key {
    default "";
    "~^POST:/api/(jobs|assets)$" $binary_remote_addr;
    "~^POST:/api/projects/[a-f0-9]{32}/export$" $binary_remote_addr;
}
limit_req_zone $wiscomper_cost_key zone=wiscomper_cost:10m rate=10r/m;
```

站点配置同样放在 `http {}` 内：

```nginx
server {
    listen 80 default_server;
    server_name _;
    access_log off;
    return 444;
}
server {
    listen 80;
    server_name wiscomper.example.com;
    access_log /var/log/nginx/wiscomper-access.log wiscomper;
    return 301 https://wiscomper.example.com$request_uri;
}
server {
    listen 443 ssl default_server;
    server_name _;
    ssl_reject_handshake on;
}
server {
    listen 443 ssl;
    server_name wiscomper.example.com;
    ssl_certificate /etc/letsencrypt/live/wiscomper.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/wiscomper.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    access_log /var/log/nginx/wiscomper-access.log wiscomper;

    client_max_body_size 7m;
    limit_req zone=wiscomper_cost burst=5 nodelay;
    limit_req_status 429;
    proxy_read_timeout 180s;
    proxy_cache off;

    # 固定Host，不把访问者提交的转发头作为应用身份依据。
    proxy_set_header Host wiscomper.example.com;
    proxy_set_header X-Forwarded-Host "";
    proxy_set_header X-Forwarded-For "";
    proxy_set_header X-Forwarded-Proto "";
    proxy_set_header X-Real-IP "";
    proxy_set_header Forwarded "";

    # 浏览器渲染页仅供应用自身通过loopback访问。
    location = /render.html { return 404; }
    location = /web/render.html { return 404; }
    location = /web/index.html { return 404; }

    location = /api/auth/github/callback {
        access_log off;
        # 回调上游失败时，普通error log也可能包含带code/state的请求行。
        error_log /dev/null;
        proxy_pass http://127.0.0.1:3088;
    }
    location / {
        proxy_pass http://127.0.0.1:3088;
    }
}
```

`ssl_reject_handshake` 需要 Nginx 1.19.4 或更新版本。配置正式域名后应用会对该域名发送一年期 HSTS（不包含子域名）；启用配置前先确保 HTTPS 和自动续证正常。不要对尚未提供 HTTPS 的子域名额外启用强制包含子域名规则。

应用会再次核对原始 Host，只接受 loopback、本机测试域名以及配置的唯一正式域名；公网域名只允许标准 HTTPS 端口。公网写操作还必须通过来源、会话和 CSRF 校验。不要为“解决 403”而放开任意 Host、Origin 或信任所有代理头。

代理端的限流使用实际连接来源 `$binary_remote_addr`。如果以后接入 CDN，先明确可信 CDN 网段与真实 IP 恢复策略；不要直接把任意客户端提供的 X-Forwarded-For 当成来源。当前应用自身对 `POST /api/jobs`、`POST /api/assets`、项目视频导出按**直连对端 IP 每分钟 60 次**限流。它不信任 XFF；同机代理时应用看到同一个代理 IP，这一层相当于该代理入口的合计保护，Nginx 的按用户 IP 限流是另一层。阅读、参数调整、取消和保存不进入这一昂贵请求限额。

## 4. 公开内容和私有数据边界

可检索内容为 `/`、`/about` 和 `/explore`。介绍页由服务端直接输出 HTML，不要求搜索引擎先运行工作台脚本或创建会话。12 个示例介绍只来自固定目录，并写明模型用途和局限；没有读取用户场景、公式笔记或任务记录。

首页与介绍页包含固定配置生成的 canonical、Open Graph、Twitter 卡片，以及 WebSite、SoftwareApplication 和 WebPage JSON-LD。不生成虚构评价、价格、评分或不存在的站内搜索接口。分享素材为 `web/assets/wiscomper-share.svg` 与对应的 1200×630 PNG，通过 `/site-share.svg` 和 `/site-share.png` 提供；社交元数据使用兼容性更广的 PNG。标志来自工程已有的本地 SVG，没有对外调用图像生成服务。

以下资源不进入 sitemap：个人项目、素材、公式、任务、导出文件、认证回调、渲染页面和静态首页副本。`robots.txt` 禁止抓取 API 与私有入口，相关响应使用 `X-Robots-Tag: noindex`。CSS、JavaScript 和公开品牌图片仍可被正常请求，以便页面渲染。**robots 与 noindex 是检索指令，不是权限控制**；私有数据仍须依靠服务端的会话、账户和归属校验。

只代理应用端口，不把项目目录、`.env`、`data/`、日志、数据库或用户配置目录作为 Nginx 静态根目录。代理默认不缓存私有 API 响应，不应覆盖应用的 `private, no-store`。数据库与上传文件保存在部署服务端；真实模型任务才把本次相关输入发送给所选提供商。公开页面不意味着个人创作会公开发布。

## 5. 上线前验证与站长平台提交

先在测试域名或同等代理配置下运行代码检查：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_site.py tests/test_auth.py tests/test_api.py tests/test_library.py -q
```

正式域名生效后，用浏览器或 `curl` 检查：

```sh
curl -D - -o /dev/null https://wiscomper.example.com/
curl https://wiscomper.example.com/robots.txt
curl https://wiscomper.example.com/sitemap.xml
curl -D - -o /dev/null https://wiscomper.example.com/about
curl -D - -o /dev/null https://wiscomper.example.com/explore
curl -D - -o /dev/null https://wiscomper.example.com/site-share.png
```

上面的命令检查 GET 响应；Windows 命令行可将 `/dev/null` 换成 `NUL`。

验证结果应满足：HTTPS 证书匹配；三个公开页面 GET 200；页面源代码中 canonical 都属于同一正式域名；robots 包含正式 sitemap 地址；sitemap 恰好包含三个公开页面；分享 PNG 可访问且尺寸为 1200×630；本机空配置下 robots 为 `Disallow: /`、sitemap 无 URL，页面为 `noindex`。登录测试需覆盖正确回调、取消登录、无效或复用 state；跨会话访问项目和素材应被拒绝。用另一台设备检查移动页面和登录返回路径。

通过 DNS TXT 验证域名归属后，可在 Google Search Console、Bing Webmaster Tools、百度搜索资源平台中提交 `https://wiscomper.example.com/sitemap.xml`。先查看抓取诊断和 URL 检查，再根据实际错误调整；无需批量伪造页面或反复提交未变化的链接。结构化数据可用相应平台的公开校验工具检查，但不应向第三方上传私有项目、图片或配置文件。

提交 sitemap、提供结构化数据和可访问页面只是检索准备，不保证收录时间、排名或社交平台展示形式。本说明不会代为验证域名、创建 OAuth App、提交站长平台或部署任何现有公网站点。
