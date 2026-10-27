# 测试与验收

这份文档说明怎样检查当前源码。它不代表当前提交已经全部通过，也不把不同版本、不同环境的历史结果合并为一次验收。发布时应记录实际执行的命令、依赖版本、通过与跳过项；部署后还需在目标服务器验证。

以下命令均在新工作台的项目根目录执行，使用已安装依赖的 Python 虚拟环境。基础安装见[快速开始](../README.md#quick-start)。测试产物放入已忽略的 tmp/，不要上传真实用户数据、邮箱验证码或模型原始响应。

## 常规回归

	python -m pytest -q
	npm run test:runtime
	node --test tests/test_engine.mjs tests/test_interactions.mjs tests/test_floating_hub.mjs tests/test_nebula_graph.mjs

npm ci 安装本地前端依赖。浏览器测试还需要可用的 Chromium；缺少浏览器时先运行：

	python -m playwright install chromium

常规回归涵盖以下范围，具体以 tests/ 和 runtime/ 中当前测试为准：

| 范围 | 主要检查 |
| --- | --- |
| 场景与数值构建 | 输入校验、参数边界、关键帧、曲线与运动一致性 |
| 模型流程 | 工具选择、受限输出、超时、取消、配额、错误脱敏 |
| 项目与版本 | 归属校验、局部修改、历史恢复、保存冲突与迟到响应 |
| 资料与工作区 | 公式、笔记、错题、课包、搜索、设置、导入去重 |
| 账号 | 邮箱流程、GitHub 协议、会话轮换、角色变更与旧库兼容 |
| 网页 | 桌面与窄屏布局、输入、参数探索、时间轴、图谱和悬浮球 |
| 部署 | 文件清单、配置保留、预检、隔离运行环境与回滚 |

模型协议用例使用合成端点和测试凭据；账号用例使用临时 SQLite、模拟邮件和 OAuth 响应。它们能检查程序行为，但不能证明生产 SMTP、真实模型连接或外部 GitHub 授权当前可用。不要将生产 MySQL 作为测试数据库。

## 真实浏览器和视频导出

部分渲染用例需要显式启用。未启用时的 skipped 不能算作视频导出成功。浏览器导出需要 FFmpeg 和 Chromium，Manim 导出还需要可用的 Manim、LaTeX 与 dvisvgm；Linux 另需相应系统库。

<details>
<summary><strong>PowerShell</strong></summary>

    $env:RUN_REAL_EXPORT = '1'
    python -m pytest -q tests/test_export_browser.py tests/test_engine_mechanical.py tests/test_engine_interactions.py
    Remove-Item Env:RUN_REAL_EXPORT

    $env:RUN_REAL_MANIM = '1'
    python -m pytest -q tests/test_manim.py
    Remove-Item Env:RUN_REAL_MANIM

</details>

<details>
<summary><strong>Linux / macOS</strong></summary>

    RUN_REAL_EXPORT=1 python -m pytest -q tests/test_export_browser.py tests/test_engine_mechanical.py tests/test_engine_interactions.py
    RUN_REAL_MANIM=1 python -m pytest -q tests/test_manim.py

</details>

导出验收应同时检查视频能否完整解码、分辨率与帧率、中文和公式、时间轴同步，以及当前交互状态是否正确带入。仅有 HTTP 成功或输出文件存在不足以证明画面正确。

## 界面验收

用内置示例检查二维公式、三维风机、参数实验和同工程迭代。建议覆盖 1440、1080、711、390、320 像素宽度，以及浅色、深色和减少动效设置。

- 顶部菜单、设置、图谱详情、输入框和悬浮球可操作，没有横向溢出或遮挡。
- 播放、暂停、时间跳转、旋转与缩放正常；切换作品后不留下上一个作品的状态。
- 保存失败保留输入；版本冲突有提示；关闭窗口后的迟到响应不会覆盖新内容。
- 公式库、错题、教案课包和搜索只显示当前空间有权访问的记录。
- 生成和导出显示实际阶段；取消后停止相关任务；失败不替换已经完成的作品。
- 浏览器控制台和网络请求没有未处理异常。截图和日志应使用合成内容并去除私人信息。

## 上线前需要单独确认

1. 按[部署说明](../deploy/DEPLOY-PACKAGE.md)验证备份、旧配置保留、反向代理与回滚，不直接覆盖用户数据目录。
2. 确认 PUBLIC_SITE_URL、HTTPS 与 OAuth 回调一致；真实 GitHub 登录需要已配置的 Client Secret 和一次完整授权往返。
3. 在运营环境验证邮件投递、验证码注册、邮箱绑定和密码重设。配置字段完整不等于邮件能够送达。
4. 检查旧库字段、读写权限、账户角色与资料导入范围。数据库预检通过不等于所有旧业务已迁移。
5. 经运营者安排后，用明确的测试内容验证已配置模型。记录所用提供商与结果；一次成功不代表后续请求始终可用。
6. 验证公开介绍页、robots、sitemap 和分享图；私人项目、素材与接口不应进入搜索索引。

## 已知边界

通用三维场景和气流是教学示意；数值示例只在标明的假设内成立。任意公式证明、单图精确三维重建和通用工程仿真不属于已保证的能力。

旧邮箱账号、符合格式的公式、笔记和错题有兼容入口；旧视频、评论弹幕、附件及完整复习历史并未全部映射到新工作台。详见[迁移范围](legacy-accounts.md#旧学习资料)。

依赖审计与自动化测试应分别报告。测试通过不表示不存在漏洞；历史连接记录、截图或本机结果也不能替代本次发布及生产环境验收。
