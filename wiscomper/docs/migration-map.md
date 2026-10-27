# 旧站基础生态 → Wiscomper Harness 迁移对照

盘点日期：2026-10-23。新工程独立运行，并通过明确配置的兼容层读取旧 MySQL 用户身份与角色，保留原 bcrypt 密码哈希；旧站公式、笔记和错题在确认登录归属后只读复制到新工作区。旧表不覆盖、不删改，不在启动时执行旧数据库迁移。邮箱注册、验证和密码重设直接使用兼容账户字段与验证码表，GitHub 保持独立身份。

核对来源包括旧站 `static/js/site-graph.js`、`role-graph.js`、`floating-panel.js`、`knowledge-panel.js`、`settings.js`、`settings-shell.js`、`tutorial.js`、`site-tour.js`、`formulas.js`、`wrongbook.js`、`course-packs.js`、`achievement-cards.js`，以及 `static/docs/update.md`。实际入口是 `frontend/index.html` 和 `static/index.html`，旧工程没有 `templates/` 目录。

本文中的“已有”指此前新工程已有实际实现；“已迁入”指对应界面与接口已接通，具体覆盖范围列在每一行；“独立功能”指旧站存在但当前实现尚未覆盖的能力。新个人空间由 [`web/workspace-center.js`](../web/workspace-center.js) 连接 [`server/workspace.py`](../server/workspace.py)。旧版本日志明确标记为历史来源，不用作新工程实现证明。

## 功能逐项对照

| 旧站能力及实际来源 | 新工程对应 | 状态与范围 |
|---|---|---|
| 文字、公式、图片创作；`visualize-workspace.js` | DSH 受控场景工具、`server/builders.py`、`web/app.js` | 已有。内容选择二维、三维或数学表现方式；不执行模型返回的任意脚本。 |
| 图片上传、剪贴板、拖放；`detect.js`、`recognition-flow.js` | 图片输入、服务端清理图片元数据、视觉模型理解 | 已有图片理解与标注，手写草图也可作为参考图片。独立 OCR 结果编辑尚未迁入；本轮测试不调用付费视觉模型，不能替代真实识别效果验收。 |
| 手写画板、笔/橡皮、撤销重做、清空、移动端锁定与自定义快捷键；`canvas.js`、`settings.js` | [`web/sketch-input.js`](../web/sketch-input.js) → 现有图片上传 | 已迁入画笔、橡皮、粗细、撤销重做、清空、触控书写与 PNG 上传，支持标准撤销快捷键。失败保留草图，上传不自动生成；草图仅保留在当前页面，刷新清除。旧自定义快捷键与独立触控锁定设置未迁入。 |
| 公式库、预览、编辑、备注、导入计算；`formulas.js` | `server/library.py`、`web/knowledge-workspace.js` | 已有。16 条科学内置公式、收藏、标签、CAS 编辑、可恢复归档、JSON 迁移和项目关联。 |
| LaTeX 即时编辑、复制；`devtools.js` | 公式编辑预览、复制 LaTeX、带入创作 | 已有基础功能。旧站 Word/MathML/Temml 设置与完整 MathLive 键盘是独立编辑器能力，尚不能宣称等价。 |
| 动态计算、分步推导、交互图形、完整题解；`step-tutor.js`、`solution-visual.js` | 可视化创作、过程步骤与参数模型 | 已有解释与计算场景；完整通用分步数学导师、证明检查、题解快照与题型库不是同一协议，属于独立功能。 |
| 智能体多步骤导航、后台子任务；`agent-workspace.js`、`agent-task-board.js` | 受控 DSH AgentLoop、真实任务生命周期、任务列表 | 已有创建/导出任务与取消。旧数学拆题子任务、角色工作流和用户模板需另行适配，不复制旧工具执行链。 |
| 脚本库、Monaco、任意 Manim 编辑、云端执行、自动修复；`devtools.js`、`code-assistant.js` | 固定可信渲染器与结构化场景数据 | 保留导出目的，执行边界重新设计。没有复制任意 Python 执行入口或旧脚本后台。 |
| 教学案例与按标签筛选；`examples.js`、`curriculum-ui.js` | 12 个本地示例、类别筛选、公开 `/explore` | 已有数学、力学、波动、光学、机械与过程示例。原站视频资产与高中/大学题库不是这 12 个示例的别名。 |
| 播放、暂停、进度、速度、分步导航 | 场景播放器、时间轴、过程步骤 | 已有。参数重算与视角/构件操作分开，避免把随意拖动误认为数值求解。 |
| 三维力导向知识图谱；`role-graph.js`、`site-graph.js` | `server/knowledge.py` + [`web/nebula-graph.js`](../web/nebula-graph.js) | 已迁入真实 Three.js 三维节点与连线、三轴力导向布局、旋转缩放、搜索聚焦及相邻路径导航。节点连接公式、主题、示例、私人项目和实际功能；减少动效与图谱标签跟随偏好。 |
| 角色路径、图谱邻接导航与搜索 | 实际连线、上一站、节点搜索与动作 | 已有基础关系导航；旧学生/教师/开发者角色路线需映射到新真实入口，不能保留已失效旧 URL。 |
| 悬浮球、拖动、折叠、边界约束、任务进度；`floating-panel.js`、`task-progress.js` | `web/floating-hub.js` + 个人空间偏好页 | 已迁入服务器持久化的大小、透明度、显示和归一化位置，以及学习、设置、版本与教程快捷入口。原旧球只保存本地布局，不宣称旧站原本就有所有新增偏好。 |
| 浅色/深色、输入默认项、动效；`settings.js`、`theme.js` | `GET/PUT /api/preferences` + `web/workspace-center.js` | 已迁入偏好页并接入实际界面。支持系统/浅色/深色、减少动效、默认输入、自动播放、播放倍速、图谱动效与标签；场景本身保留创作颜色。 |
| 按用户加载设置；`settings.js` | 服务器记录、偏好页与邮箱/GitHub身份归并 | 已迁入。登录后通过账户归属读取；匿名资料归并后正确选择最新设置。多标签页写入使用版本冲突检测，冲突后读取服务器新值并同步全部设置控件。 |
| 用户资料、昵称、头像；`profile.js`、`account-details.js` | 兼容旧用户名/邮箱身份与独立 GitHub OAuth | 已接入旧 users 身份和 GitHub 公开资料；新站不按同名/同邮箱自动合并。邮箱重设密码已接入；旧站昵称修改、上传头像及完整资料编辑尚未等价迁入。 |
| 新手教程、聚焦高亮、上下步、跳过、重开；`tutorial.js`、`site-tour.js` | [`web/onboarding.js`](../web/onboarding.js) + `tutorial_completed` 偏好 | 已迁入七步真实界面引导，可前后移动、跳过、完成及重开，恢复焦点与原滚动位置，缺失目标可继续。完成标记只是用户操作记录，不触发生成或虚构任务。 |
| 软件版本日志、版本跳转；`docs.js`、`static/docs/update.md` | `/api/releases` + 个人空间「版本动态」 | 已迁入可读时间线。新工程与旧站 `legacy` 记录分开标注，可转到当前作品版本历史；不承担远程升级或源码切换。 |
| 项目/内容历史 | `/api/projects/{id}/revisions`、版本回看与恢复 | 已有。恢复生成新版本；这是作品版本管理，与软件更新日志分别保留。 |
| 视频收藏；`examples.js` | `/api/learning` 的 `favorite` + 画面下方收藏按钮 | 已迁入即时收藏、学习列表、编辑、搜索与归档恢复。可关联当前作品，接口也支持内置示例或公式；重复收录同一引用返回原记录。 |
| 稍后看；`examples.js` | `/api/learning` 的 `watch_later` + 画面操作栏 | 已迁入，与收藏分开；支持筛选、编辑、归档和恢复。 |
| 时间戳笔记；`examples.js` | `/api/learning` 的 `note` + 个人空间编辑器 | 已迁入当前作品时间点采集、笔记编辑和打开作品并跳到记录时间。时间不能超过实际场景时长；便携导出清除私人项目 ID 与时间戳。 |
| 错题、错因、参考答案、标签；`wrongbook.js` | `/api/learning` 的 `wrongbook` + 学习资料页 | 已迁入题目、参考回答、笔记、标签、公式预览、搜索、编辑与归档恢复；关联自己的资料，不读取旧账号数据。未保存编辑有离开确认，保存期间保护输入。 |
| 到期复习、自报掌握、复习历史；`wrongbook.js` | `/api/learning/{id}/review` + 复习界面 | 已迁入待复习筛选、先看题再展开解答、四级自评和历史记录。again/hard/good/easy 驱动计划，保留最近100条，累计次数来自实际提交；自报掌握不等同自动评测。 |
| 错题导入导出 | `/api/learning/export`、`/import` + 学习页导入导出按钮 | 已迁入 JSON 下载与文件导入，重复内容跳过。导入从0次复习开始，不把客户端声称的旧次数计入真实成就。 |
| 有序课包、教学目标、重点、准备、过程、作业、反思；`course-packs.js` | `/api/course-packs` + 个人空间课包编辑/阅读页 | 已迁入完整教案字段、材料选择、讲解备注、上下移和移除；每包最多40项，可加入作品、公式、示例和学习资料。 |
| 收录题解/错题快照 | 课包 `snapshot` + 有序材料阅读 | 已迁入受限纯文本快照与公式展示，保留条件和笔记；不复制旧脚本或完整媒体，原项目只读取标题/提示/摘要。 |
| 课包导出与导入 | `/api/course-packs/{id}/export`、`/import` + 课包页操作 | 已迁入 JSON 下载、导入、去重及便携资料阅读。私人引用在导出时去掉，保留文本快照；示例和内置公式引用可继续打开。 |
| 成就、徽章墙、闪卡；`achievement-cards.js`、`knowledge-panel.js` | `/api/achievements` + 个人空间「探索足迹」 | 已迁入根据真实记录显示的徽章与进度。已保存项目/公式、场景类型、历史版本、成功视频、复习次数和课包可解锁；不生成虚构掌握率。旧分层艺术资产、闪卡和3D卡片没有作为完整视觉资产迁入。 |
| 全站搜索；`site-search.js` | [`server/search.py`](../server/search.py) + [`web/global-search.js`](../web/global-search.js) | 已迁入独立搜索入口及 Ctrl/⌘ K，统一检索功能、内置/私人公式、示例、作品、学习资料和课包并直接打开。支持键盘选择；输入变化立即撤销旧结果。私人记录按账户过滤，归档不展示，查询与结果数量有上限。 |
| 帮助/FAQ/更新日志；`help-center.js`、`docs.js` | 使用帮助、公开介绍、部署文档、版本日志 | 已有基础文档，本轮补迁移范围和工作台功能说明。旧服务条款/隐私政策不可直接当新运营主体协议发布。 |
| GitHub 登录 | 独立 OAuth、PKCE、state、会话轮换、私人数据归并 | 保持独立提供商ID映射，绝不因邮箱或用户名相同取得旧账户。真实授权仍需配置 GitHub OAuth App并完成本人授权；本地模拟测试不能替代外部授权成功记录。 |
| 旧用户名/邮箱密码登录 | [`server/legacy_accounts.py`](../server/legacy_accounts.py) + 账户菜单 | 已兼容旧 users/account_access，原bcrypt哈希不修改；支持邮箱或用户名登录。每次请求重新校验可信角色/停用状态与密码指纹，身份绑定数据源和数值ID，不能仅凭用户名提权。 |
| 邮箱验证码、注册、密码找回；`auth.js`、`email_service.py` | [`server/email_accounts.py`](../server/email_accounts.py) + 邮箱账户表单 | 已实现用途/账户绑定验证码、注册、验证和重设；单次消费、失败尝试、到期和持久化限流均有测试。SMTP配置可继承，邮箱模板有HTML及纯文本，本轮未发送真实邮件。 |
| 会员、配额角色、管理审计；`account-admin.js`、`admin-requests.js` | 旧 `account_access` 的 member/vip/admin、disabled、daily_limit + 新模型预算 | 可信角色和停用状态可继承；管理员不由用户名决定。VIP/admin免个人限额仍计量并受站点总预算约束。完整旧管理员控制台、管理审计UI及旧消费历史不因角色接通而视为完成迁移。 |
| 旧公式、视频笔记与错题数据 | [`server/legacy_import.py`](../server/legacy_import.py) | 登录身份确认后按旧数字ID/精确用户名只读迁入文字内容，稳定ID去重且不覆盖新站修改。超长或超容量返回提示，源记录保持完整；旧媒体ID与时间点保留为文字，不伪造新作品引用。 |
| 视频评论、弹幕、公共视频发布与站内社交；`teaching-danmaku.js`、`video-delivery.js` | 暂无公共媒体社区 | 独立业务，涉及分享权限、存储和审核；私人场景笔记不等价于公共弹幕系统。 |

## 新工作台后端接口

安装：`install_workspace(app, lambda: STORE, owner)`。每个入口都调用同一会话/账户归属函数；写操作继续使用应用的来源与 CSRF 校验。新工作区内容保存在本工程 `records` 表；旧账号、角色、邮箱验证表由显式账户兼容配置选择，详见 [`docs/legacy-accounts.md`](legacy-accounts.md)。MySQL连接失败不会自动切换到新的本地同名账号。

| 路径 | 请求与响应 |
|---|---|
| `GET /api/preferences` | `{preferences, revision}`；默认 revision=0 |
| `PUT /api/preferences` | `{expected_revision, preferences:{部分字段}}`；只覆盖显式字段，返回新 revision |
| `GET /api/learning` | `kind=all/favorite/watch_later/wrongbook/note`、`status=all/due/new/reviewing/mastered/archived`、`q`；返回 `{items,stats,limits}` |
| `POST /api/learning` | `{kind,title,note?,problem?,answer?,tags?,project_id?,formula_id?,sample_id?,time_sec?,archived?}`；返回 `{item,duplicate}` |
| `GET /api/learning/{id}` | 返回完整 `{item}`，含最近复习记录 |
| `PATCH /api/learning/{id}` | `{expected_revision,...部分内容字段}`；kind不可悄悄改变，归档使用archived |
| `POST /api/learning/{id}/review` | `{expected_revision,grade:'again'/'hard'/'good'/'easy',note?}`；仅未归档错题可复习 |
| `GET /api/learning/export` | `{format:'wiscomper-learning',version:1,items:[可导入内容]}` |
| `POST /api/learning/import` | 接受本导出格式；返回 `{items,imported,skipped}`，整批事务，重复内容跳过 |
| `GET /api/course-packs` | `archived=false/true`；返回摘要 `{items,limits}` |
| `POST /api/course-packs` | `{title,description?,lesson?,items?,archived?}`；返回 `{item}` |
| `GET/PATCH /api/course-packs/{id}` | 详情/版本校验修改；PATCH包含expected_revision |
| `GET /api/course-packs/{id}/export` | `{format:'wiscomper-course-pack',version:1,pack:{...}}` |
| `POST /api/course-packs/import` | 接受本导出格式；返回 `{item,imported,skipped}` |
| `GET /api/achievements` | `{metrics,items:[{id,title,description,progress,target,unlocked}],note}` |
| `GET /api/releases` | `{current,items:[{version,date,title,channel,changes,source?}]}` |
| `GET /api/search` | `q`最多200字符、`limit`为1–40（默认24）；返回 `{query,items,has_more,limit,counts}`，每项有 `{id,kind,title,description,action:{type,id}}` |

偏好字段：`theme`、`autoplay`、`reduced_motion`、`default_speed`、`default_input`、`graph_motion`、`graph_labels`、`floating_visible`、`floating_size`、`floating_opacity`、`floating_x`、`floating_y`、`tutorial_completed`。悬浮位置为0到1的归一化值，`null`表示使用界面默认位置；尺寸44–96，透明度0.35–1，播放倍速0.25–2。布局实现仍须将位置约束在实际可见窗口内。

课包材料为 `{kind:'project'/'formula'/'sample'/'learning',id?,note?,snapshot?}`。有 id 时服务器验证引用归属，并读取可信源生成文本快照；无 id 时必须提供受限 `snapshot`，它是可阅读的迁移内容，不成为可以打开别人的项目的凭据。快照字段为 title/note/latex/problem/answer/prompt/tags，不能包含代码、URL或执行工具字段。

教案字段为 `audience`、`duration`（分钟）、`objectives`、`key_points`、`preparation`、`procedure`、`exercises`、`reflection`。课程材料引用的源记录保留，不会因课包归档而被删除。

容量：学习记录最多300条（含归档），课包最多40个，每包40份材料；标题120字符，标签最多8个且每个24字符，题目/答案/笔记各4000字符。查询最多200字符。学习导入最多5 MB，课包导入最多1.5 MB；未知字段、非法引用和无效数值都拒绝。CAS冲突为409，外会话引用统一404，格式错误422。错误和导出中不泄露owner或数据库文件位置。

为保证自己导出的内容可以重新导入，整份学习资料的可移植文本预算为4.5 MB，每个课包为1.3 MB（含两空格缩进的JSON）。超过预算会拒绝本次保存，事务内不留下半条记录。列表与导出不加载每条资料的全部复习历史；历史只在读取单条详情时提供。

统一搜索由 `install_search(app, lambda: STORE, owner)` 安装。搜索词按空白拆分并全部匹配，大小写使用 Unicode casefold；用户输入不拼接进 SQL。SQL 内完成归属、归档与文本命中检查，再按标题匹配和更新时间返回少量摘要；不读取完整场景、课包材料或复习历史。空搜索预留功能入口，并优先显示最近私人记录。搜索接口返回纯 JSON 文本，前端使用 `textContent` 展示。

## 验证与实际边界

`tests/test_workspace.py` 验证偏好默认值与局部更新、并发冲突、会话隔离、GitHub归并后的所有权、材料引用、时间戳边界、归档恢复、复习计划、导入事务、课包顺序、跨会话便携导出以及真实成就计数。项目资料与成就统计不得读取每个项目的完整scene。

`tests/test_workspace_browser.py` 使用独立数据目录和本地示例验证偏好跨刷新、主题/播放/悬浮球应用、真实偏好冲突恢复、错题时间点与复习、编辑/归档恢复、草稿离开确认、保存期间输入保护、课包材料顺序及导出再导入、关闭面板时错误提示、纯文本/XSS边界、统一搜索直接跳转和输入竞态。`tests/test_search.py` 验证所有搜索来源、账户隔离、归档排除、SQL字面查询、旧记录检索、摘要和数量上限，并阻止搜索加载完整记录。

图谱、悬浮球、教程和画板分别由 `tests/test_nebula_graph.mjs`、`tests/test_ecosystem_browser.py`、`tests/test_floating_browser.py`、`tests/test_onboarding_browser.py`、`tests/test_sketch_browser.py` 覆盖布局或交互；实际账号、教程和画板上传接线由 `tests/test_account_onboarding_integration.py` 覆盖。原作品回看与恢复仍由 `tests/test_browser.py` 检查。各套件的本次运行结果以执行记录为准；列出测试文件本身不是通过证明。

账户兼容由 `tests/test_legacy_accounts.py` 额外覆盖旧bcrypt、实时角色撤销、用途/账户绑定验证码、并发消费、重设撤销会话、来源隔离与只读资料复制。2026-10-23 本机只读检查确认旧 MySQL 5个用户及必要字段/表兼容，必要配置已安全追加到新工程，未修改旧库或发送真实邮件。

本轮没有进行真实 GitHub 外部授权、SMTP投递、付费模型识别或公开部署验收。公共视频社区、完整旧管理控制台、通用数学导师、完整题库、任意脚本执行和旧视觉资产不在上述已迁入范围内。已接通邮箱登录、密码恢复和可信会员角色，不能据此宣称所有旧账户管理业务完整迁入。

旧日志节选保留版本号和日期：0.3.6（2026-02-20，设置与多步骤智能体）、0.4.1（2026-02-27，图谱与星云）、0.4.3（2026-03-06，成就）、0.4.4（2026-09-17，课包与错题）、0.4.7（2026-09-19，旧账户服务）。内容经过摘要，未宣称复制原部署或全部旧业务。
