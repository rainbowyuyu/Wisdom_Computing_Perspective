# 本机 GitHub 登录配置

本机地址固定使用 `http://127.0.0.1:3088`，`PUBLIC_SITE_URL` 保持为空。浏览器请统一打开这个地址；`localhost` 与 `127.0.0.1` 使用不同 Cookie，登录往返时不要切换。

后端已经实现 OAuth state、PKCE S256、一次性回调、账号归属迁移和退出。完成下面的 OAuth App 注册与本机凭据输入后，才能验证你的真实 GitHub 登录；代码和本地配置检查本身不等于已授权。

## 1. 注册本机 OAuth App

在项目目录运行：

```powershell
& .\scripts\configure-github.ps1 Guide
```

打开输出中的 `create_app_url`，它指向 GitHub 官方 OAuth App 创建页面，只包含应用名称、首页、回调和描述，不含凭据。如果 GitHub 页面没有填入这些字段，手动填写：

| 字段 | 本机值 |
| --- | --- |
| Application name | `Wiscomper Local` |
| Homepage URL | `http://127.0.0.1:3088` |
| Authorization callback URL | `http://127.0.0.1:3088/api/auth/github/callback` |
| Application description | `Wiscomper 智算视界 · Wisdom Computer Perspective 本机登录` |

创建完成后复制 Client ID，再生成 Client Secret。两者由你在本机终端输入，不要粘贴进聊天、脚本参数、截图或日志。

## 2. 隐藏输入并保存凭据

双击项目根目录的 `配置GitHub登录.cmd`，或在项目目录的 PowerShell / Windows Terminal 中运行：

```powershell
& .\scripts\configure-github.ps1 Configure
```

双击入口直接调用项目 Python，不依赖 PowerShell 脚本执行策略。若手动运行 `.ps1` 时显示「禁止运行脚本」，使用双击入口即可，无需更改系统策略。只读检查也可直接运行 `& .\.venv\Scripts\python.exe .\scripts\configure_github.py --check`。

按提示输入 Client ID 和 Client Secret；如果已保存 Client ID，可直接回车保留。终端不会显示输入字符。助手只更新本工程 `.env` 的 `GITHUB_CLIENT_ID`、`GITHUB_CLIENT_SECRET` 和空的 `PUBLIC_SITE_URL`，保留其他配置；成功后通过同目录临时文件原子替换，不生成凭据备份或日志。

如果文件已有公网地址，或进程环境设置了这三个字段的覆盖值，助手会停止，避免意外改写部署环境。配置文件变化或同时运行另一个配置助手时也会停止。异常中断后若留下 `.env.github-setup.lock`，先确认没有助手在运行，再删除该空锁文件。`.env` 是私有服务端配置，不应提交或分享。

## 3. 检查并重启

```powershell
& .\scripts\configure-github.ps1 Check
```

检查只报告字段是否存在、配置是否完整和回调地址，不显示 Client ID/Secret，不联系 GitHub。`configured: true` 仅代表本地配置完整；`remote_authorization_verified` 始终为 `false`，实际授权以浏览器完成登录为准。检查退出码：`0` 配置完整，`2` 尚未配置，`1` 本地配置无法读取或参数错误。

重启工作台服务，再打开 `http://127.0.0.1:3088`，从账号菜单选择 GitHub 登录。只请求 `read:user`，不申请仓库或邮箱权限。成功回到工作台后，应能看到 GitHub 账号信息。Secret 和 GitHub access token 不会发给工作台前端，access token 不持久保存。

已有任务正在处理时，登录会提示先完成或取消任务。成功登录会把当前匿名空间的工程、图片、版本历史和其他保存记录原子迁移到账号；退出后进入新的匿名空间。之后再次登录同一个 GitHub 账号，仍可访问该账号的作品。

## 额度与切换账号

`GET /api/auth/session` 返回 `public_mode` 和 `usage`。额度按 UTC 日期重置，每次真实模型创作保守预留 3 步，失败也计入。本机模式显示全站额度；公网模式显示当前账号额度，并以全站剩余额度限制实际可提交次数。`remaining` 是该范围的余额，`available` 是此刻实际可提交次数。本地示例、参数调整和打开已有工程不会消耗模型额度。

切换 GitHub 账号前先退出。登录回调会轮换会话和 CSRF；过期、重复、跨浏览器或被新授权替代的回调均会拒绝。登录前和回调后使用同一个浏览器与本机地址。

## 以后迁到公网

为公网地址单独注册 OAuth App，回调精确设为 `https://你的域名/api/auth/github/callback`，并使用独立服务实例和部署配置。本机与公网不要共用一个 `.env`。本机助手不会创建或自动加载 `.env.public`；现有启动入口仍读取 `.env` 和环境变量。若以后增加配置文件选择，应同时调整启动器和检查工具，不能仅放置新文件并假设已生效。

官方参考：[创建 OAuth App](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app)、[授权流程与 PKCE](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps)。
