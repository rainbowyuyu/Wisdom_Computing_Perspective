## rainbow_yu 🐋✨

![logo.png](assert/images/logo.png)

# 智算视界 (Wisdom Computing Perspective)

<div align="center">
  <h3>基于 AI 视觉识别与 Manim 动态引擎的下一代数学可视化计算平台</h3>
</div>

---

## 📖 项目简介

**智算视界 (Wiscomper)** 是一个集成了 **多模态 OCR 手写识别**、**智能体编排**、**知识图谱导航** 与 **Manim 数学动画引擎** 的下一代数学可视化平台。

用户可以通过手写或上传数学公式图片，系统将自动识别为 LaTeX 代码，并由智能体理解任务意图：是**识别公式**、**整题求解**，还是**生成可视化动画 / 教学案例脚本**。平台通过「智能体 + 工具链」自动在 **智能识别 → 动态计算 → 云端渲染工作台 → 教学案例** 等模块之间编排步骤，进一步借助知识图谱组织站内功能节点，为未来引入 **图神经网络（GNN）等图结构推理模型** 预留空间。

目前，智算视界已支持从「题目图片 / 整题文本 → LaTeX 表达 → Manim 可视化脚本 → 分阶段动画视频」的完整流水线，可用于教学演示、解题可视化、脚本创作与开发者实验等场景。

## ✨ 核心功能（按 AI 能力视角）

- **智能体与工具编排**
  - 首页与独立智能体页面支持自然语言对话，可携带题目图片与整题文本。
  - 智能体基于意图识别与站内知识图谱，自动拆解任务并调用「智能识别 / 动态计算 / 开发者工具 / 教学案例 / 我的算式 / 设置」等工具。
  - 支持多步指令（如「先帮我识别这道题并保存到我的算式，再生成可视化动画并放进云端工作台里改一版脚本」），过程以步骤树展示，可存为模板复用。

- **👁️ 多模态智能识别 (OCR + 大模型)**
  - 集成 Qwen-VL 多模态大模型与自研 OCR 逻辑，支持手写公式、教材截图等复杂场景。
  - 输出自动清洗为适配 MathLive 的 LaTeX，统一移除 ```latex、`$$ $$`、`\[ \]` 等包裹。
  - 对于积分等典型题型强化提示词，提升逐符号抄写的鲁棒性，看不清位置使用占位符而非「自作聪明」猜测。

- **🎬 动态计算与可视化解题引擎**
  - 支持「计算」「可视化」「计算 + 可视化（通用模式）」等模式，并在动态计算前**先返回文字版解题步骤**。
  - 解题步骤以 Markdown 流式输出，支持标题、列表与公式高亮。
  - 动画生成采用 Manim 社区版，渲染日志与脚本预览并行展示，错误会自动回传给大模型做多轮纠错（最多三次），再重新渲染。

- **🧠 知识图谱与智算星云**
  - 全站功能以知识图谱形式组织：智能体、智能识别、动态计算、开发者工具、教学案例、成就、设置等均为图谱节点。
  - 首页提供 3D 力导向图 +「智算星云」导航，将功能视作「站点」，支持站点式浏览与子页面历史（返回 / 前进）。
  - 知识图谱作为图结构骨干，既用于前端可视化，也用于智能体工具选择决策，为后续引入 **图神经网络（GNN）在图上的推理与策略学习** 提供天然载体。

- **💾 我的算式与脚本资产库**
  - 提供云端算式库，支持创建、重命名、编辑与规范化显示（自动去除多余的 $$ 包裹等）。
  - 支持从智能识别一键入库、从库导入到动态计算或开发者工具。
  - 云端渲染工作台可保存渲染脚本，配合 Monaco 编辑器与 rainbow_extend_manim 拓展库，形成可复用的代码资产库。

- **🧑‍🏫 教学案例与视频播放系统**
  - 内置教学案例列表，支持标签筛选、收藏、稍后看等「学习闭环」能力。
  - 播放页支持时间戳笔记、续看位置、带时间的分享链接，以及基于 WebSocket 的弹幕与互动。
  - 教学案例与题目练习可通过智能体串联：从视频中的时间戳笔记一键生成同类型练习题，反向链接回原视频。

- **👨‍💻 开发者工具与 AI 编辑助手**
  - Manim 云端工作台整合 Monaco + Pylance，支持在线编辑、实时类型提示与代码高亮。
  - 内置 AI 编辑助手，可用自然语言增删改 Manim 代码；未登录会提示先登录以确认身份。
  - 支持从拓展组件库一键载入示例、从算式库导入公式、从教学案例导出发布包（含弹幕与元信息）。

- **🎮 交互式画板与多端适配**
  - HTML5 画板支持笔 / 橡皮大小独立调节、快捷键与 Alt+右键拖动调整笔刷半径。
  - 画板锁定逻辑与手机端触摸事件进行了专门优化，避免滚动 / 书写误触。
  - 移动端重点承担「采集器 + 播放器」角色：专注拍照识别、查看题解和回看视频，开发者工具等重工作台引导在桌面端使用。

- **🌊 流式反馈与状态可视化**
  - 动画生成全程采用 SSE 流式反馈，实时展示提示词、脚本生成、纠错与渲染进度。
  - 动态计算页顶部配有阶段式状态栏（理解题目 → 生成脚本 → 自动纠错 → 渲染视频），进度条与日志同步更新。

---

## 🛠️ 技术栈

- **后端与基础设施**
  - 语言与框架：Python 3.10+、FastAPI、Uvicorn\[standard]
  - 配置与环境：`python-dotenv` 读取 `.env`，按环境变量配置 MySQL、Aliyun 视频鉴权、CDN 等
  - 数据库访问：`mysql-connector-python` 连接池（`MySQLConnectionPool`），集中封装在 `app/config.py::get_db_connection`
  - 配置 & 日志：标准 `logging` 体系，统一入口 `main.py` 负责挂载所有 API 路由与静态资源目录
  - 文件与视频：后端维护本地 `static/videos` 与 `static/assets/storage` 目录，用于 Manim 渲染产物与教学案例资源

- **AI、智能体与多模态能力**
  - 大模型接入：使用 OpenAI 官方 Python SDK 指向阿里云 DashScope 兼容接口（`base_url=https://dashscope.aliyuncs.com/compatible-mode/v1`），核心模型为 **Qwen-VL** 多模态（图片 + 文本）
  - 智能体服务：后端 `/api/agent/execute` + 前端 `agent.js`，基于「用户对话 + 上下文 + 知识图谱」生成结构化 `steps`，驱动前端自动跳转与工具调用
  - 工具编排：借助 `site-graph.js` 中的全站知识图谱（节点 NODES / 边 EDGES），智能体将自然语言意图解析为站内工具节点（如智能识别、动态计算、开发者工具、教学案例等），形成可视化的步骤树并支持「从模板运行」
  - AI 代码编辑：`/api/devtools/edit_code` 提供 Manim 脚本编辑服务，前端 `devtools.js` 中的 AI 编辑助手可根据自然语言指令、渲染日志自动修改代码并生成关键帧预览
  - 智能识别：多模态大模型 + 自研 OCR 管线，统一通过 `sanitize_latex_for_mathlive` 等函数将输出清洗为 MathLive 友好的 LaTeX，并在后端 `/api/detect` 层面对积分、极限等算子做鲁棒性约束

- **数学编辑、渲染与可视化**
  - 数学输入：前端集成 **MathLive** 作为主输入组件，计算页与开发者工具的 LaTeX 编辑器均基于统一的 MathLive 封装
  - LaTeX 渲染：全站统一使用 **KaTeX**，通过 `renderMath(container)` 入口对文档、智能体回复、动态解题步骤等内容进行二次渲染
  - 可视化动画：后端使用 **Manim Community Edition**，通过子进程调用 `manim` 命令并解析日志；动画生成与渲染过程通过 **SSE (Server-Sent Events)** 流式回传给前端（`/api/animate/stream`、`/api/devtools/run_manim_stream`）
  - 扩展组件：整合 `rainbow_extend_manim` 拓展库，前端 `rainbow_data.js` 与 `devtools.js` 将其封装为「可复用动画组件卡片」，支持一键载入到 Manim 云端工作台
  - Word/MathML 导出：开发者工具内接入 **Temml**（CDN 加载），将 LaTeX 转为 MathML/FlatMML，配合 `navigator.clipboard` 写入 HTML/Text，方便粘贴到 Word/PowerPoint
  - 代码高亮：前端通过 **highlight.js** 为 Python/Markdown 代码块着色，用于解题步骤、Manim 代码预览等场景

- **前端架构与交互**
  - 技术栈：原生 ES Modules + HTML5 + CSS3 单页应用；`static/index.html` 为唯一入口，所有页面（智能体、智能识别、动态计算、开发者工具、教学案例等）由 `main.js` 与 `ui.js` 管理路由与显示
  - UI 组件：自研组件体系（布局、组件、页面级 CSS），配合 CSS 变量与 data-theme 实现浅色/深色模式与高对比度细节；图标体系基于 Font Awesome
  - 代码编辑：云端 Manim 工作台通过 **Monaco Editor**（CDN 加载）提供 VS Code 级编辑体验，内置 Manim 相关智能补全（`Scene`、`Circle`、`MathTex`、`self.play` 等）
  - 效果与动效：`main.js` 提供 Hero 文字交互、知识星云拖拽、右键菜单、键盘快捷键（Undo/Redo、画笔切换、画板锁定等）等复杂交互逻辑
  - 多端适配：统一的 `isMobileDevice` 逻辑控制画板锁定按钮、智能体侧边栏、云端工作台入口，移动端突出「采集器 + 播放器」角色，桌面端负责重度编辑与渲染

- **知识图谱、3D 可视化与未来 GNN 方向**
  - 知识图谱建模：`site-graph.js` 将全站功能（section、子工具、角色入口、设置项等）抽象为有向图，节点携带类型、图标、关键词等信息，边刻画从「智能体 → 工具 → 设置/案例」的路径
  - 3D 可视化：`role-graph.js` 使用 **three.js + ForceGraph3D + SpriteText** 以 3D 力导向图展示知识图谱，支持节点高亮、相机飞行、角色推荐路径与「智算星云」视图
  - 角色流转：通过 ROLE_FLOWS 将「学生 / 教师 / 创作者 / 开发者」四类角色与图谱节点绑定，驱动首页「按角色快速开始」与智能体角色模板
  - 研究与扩展：当前知识图谱已完整以图结构表达站内工具及其关系，为未来在此图上引入 **图神经网络（GNN）** 做路径规划、推荐策略、个性化学习路线打下数据与结构基础

- **数据存储与账号体系**
  - 关系型数据库：MySQL 持久化用户、密码（`bcrypt` 哈希）、算式库、动画脚本库、智能体模板、成就系统、教学案例元数据与标签等
  - 会话与验证码：当前版本使用内存字典（`store.py` 中的 `CAPTCHA_STORE` / `SESSION_STORE`），生产环境建议替换为 Redis 等外部缓存
  - 元数据与配置：教学案例、Rainbow 拓展组件等使用结构化 JSON（如 `static/assets/storage/metadata.json`）描述，前端按需加载并渲染

- **实时通信与多媒体**
  - 流式 API：大量使用 **SSE**（服务器推送事件）流式返回日志、代码、进度与状态文本，前端通过 `ReadableStream` + 自定义解析器增量更新 UI
  - WebSocket：教学案例视频播放器结合 **WebSocket** 实现点赞弹幕与心跳上报，记录用户观看进度与互动行为，用于后续学习闭环统计
  - 视频处理：后端依赖 **FFmpeg** 进行视频合成/转码；教学案例支持本地源与阿里云 CDN 加速双通路，CDN 路径由环境变量控制
  - 视频鉴权：通过 `VIDEO_TOKEN_SECRET` 与 Aliyun CDN URL 鉴权参数生成短期有效的播放链接（支持本地直链与 CDN 域名切换）

- **安全与健壮性**
  - Markdown 安全：`sanitizeMarkdownHtml` 在前端统一清理站内 Markdown 渲染结果（文档、智能体回复、开发者工具文案等），移除 `<script>`、内联 `on*` 事件、`javascript:` 链接，降低 XSS 风险
  - 公式渲染安全：KaTeX 渲染集中由 `renderMath(container)` 负责，避免在 Markdown 中内联任意 HTML 的同时保持公式显示效果
  - 渲染容错：动态计算与开发者工具均实现「渲染失败 → 自动读取错误日志 → 回传给大模型纠错 → 重试渲染」的闭环，并在前端明确展示错误原因与重试情况
  - 冷却与限流：统一的渲染冷却控制（`render-cooldown.js`），限制连续 Manim 渲染频率，前端按钮展示倒计时与禁用状态，保护服务器资源

---

## 🚀 本地与宝塔部署

网站全部源码和部署资源均在 **`html_root/`**，只上传这个目录即可。Vue 源码已从仓库外的 `vue_root` 移入 `html_root/frontend/`；正式网页由 Python 直接提供，无需启动 Vue。

- [网站目录与快速启动](html_root/README.md)
- [宝塔部署、环境配置与反向代理](html_root/deploy/BAOTA.md)
- [单文件数据库安装与升级](html_root/visdom_db.sql)

在宝塔 / phpMyAdmin 中先备份并选中现有数据库（例如 `wiscomper_com`），点击「SQL」，粘贴 `visdom_db.sql` 全文执行。脚本使用当前选中的库，支持空库建表和原网站 18 表升级至 25 表，保留原数据，支持重复执行。要求 MySQL 8.0+。

配置 `html_root/.env.local` 后，在网站目录启动：

```sh
cd html_root
python -m pip install -r requirements.txt
python main.py
```

Manim 的系统依赖、服务器数据库凭据和域名设置按部署文档配置；服务器使用自己的虚拟环境，不上传本机环境目录或凭据文件。

## 📂 代码结构概览（html_root）

```text
html_root/
├── main.py                  # 后端入口 (FastAPI)
├── requirements.txt         # 依赖列表
├── .env                     # 环境变量配置文件
├── logic/                   # 核心业务逻辑
│   ├── __init__.py
│   ├── manim_generator.py   # Manim 动画生成脚本构建器
│   └── prompt.py            # AI 提示词管理
└── static/                  # 前端静态资源
    ├── index.html           # 前端单页应用入口
    ├── css/                 # 样式文件 (模块化 + 各页面独立样式)
    │   ├── main.css
    │   ├── layout.css
    │   ├── components.css
    │   └── pages/
    │       ├── home.css         # 首页与智算星云
    │       ├── agent.css        # 智能体页面
    │       ├── calculate.css    # 动态计算与解题可视化
    │       ├── workspace.css    # 云端渲染工作台
    │       ├── help.css         # 帮助与文档
    │       ├── examples.css     # 教学案例
    │       ├── devtools.css     # 开发者工具
    │       ├── mathlive.css     # 公式编辑界面
    │       └── ...              # 其他页面样式
    ├── js/                  # 前端脚本 (ES Modules)
    │   ├── main.js          # 应用入口与路由
    │   ├── ui.js            # UI 交互与弹窗管理
    │   ├── canvas.js        # 画板与手写逻辑
    │   ├── detect.js        # 智能识别页逻辑
    │   ├── calculate.js     # 动态计算与动画生成
    │   ├── formulas.js      # 算式库 CRUD
    │   ├── auth.js          # 登录注册与权限
    │   ├── agent.js         # 智能体对话与工具调用
    │   ├── role-graph.js    # 角色导航与知识图谱视图
    │   ├── site-graph.js    # 全站知识图谱 3D 力导向图
    │   ├── devtools.js      # 云端工作台与 AI 编辑助手
    │   └── ...              # 其他辅助脚本（主题、右键菜单、教程等）
    ├── assets/              # 图标、Logo 与案例封面
    ├── docs/                # Markdown 文档 (隐私政策、服务条款、API 文档、更新日志等)
    │   ├── update.md        # 详细更新日志（功能 / 智能体 / 知识图谱 / 成就等）
    │   ├── api_doc.md
    │   ├── privacy.md
    │   ├── terms.md
    │   └── SECURITY.md
    └── proto/               # 协议文件（如弹幕等）
```

---

## 🤝 贡献与反馈

欢迎提交 Issue 或 Pull Request 来改进本项目。

- **作者**: rainbow_yu
- **网站**: [智算视界](https://wiscomper.com/)
- **Email**: rainbowyu619@gmail.com 

---

## 📜 许可证

本项目仅供学习与交流使用，后端核心渲染逻辑保留所有权。

Copyright © 2026 Wisdom Computing Perspective.
