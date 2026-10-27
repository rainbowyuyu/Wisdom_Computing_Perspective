<a id="top"></a>
<p align="center">
  <img src="docs/assets/wiscomper-hero.png" alt="Wiscomper 智算视界 · Wisdom Computer Perspective" width="100%">
</p>

<h1 align="center">Wiscomper · 智算视界</h1>
<p align="center"><strong>Wisdom Computer Perspective</strong><br>让想法成为可以观察、操作和继续探索的画面。</p>

<p align="center"><strong>简体中文</strong> · <a href="README.en.md">English</a></p>
<p align="center">
  <a href="#quick-start"><img src="https://img.shields.io/badge/Python-3.11%2B-4F73D9?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.11+"></a>
  <a href="#quick-start"><img src="https://img.shields.io/badge/Node.js-24_recommended-539E63?style=flat-square&amp;logo=nodedotjs&amp;logoColor=white" alt="Node.js 24 recommended"></a>
  <a href="#visual-tools"><img src="https://img.shields.io/badge/Three.js-0.180.0-6572C8?style=flat-square&amp;logo=threedotjs&amp;logoColor=white" alt="Three.js 0.180.0"></a>
  <a href="#export"><img src="https://img.shields.io/badge/Manim-0.22.0_optional-9766D6?style=flat-square" alt="Manim 0.22.0 optional"></a>
  <a href="#models-and-accounts"><img src="https://img.shields.io/badge/Qwen-default-6652C8?style=flat-square" alt="Qwen default model"></a>
</p>
<p align="center">
  <a href="https://www.wiscomper.com/">智算视界官网</a> · <a href="#quick-start">开始使用</a> · <a href="#features">功能一览</a> · <a href="#deployment">部署迁移</a> · <a href="#documentation">文档导航</a>
</p>

---

Wiscomper 是一个交互可视化工作台。从一段话或一道公式开始，也可以上传图片、画一张草图。工作台根据内容选择表现方式，生成后可以旋转观察、调整参数，再描述想修改的部分。

界面沿用智算视界的蓝紫色调。公式库与知识图谱连接作品和学习资料，同一个工程可以持续迭代，保留历史版本，最终导出视频或场景数据。

<a id="features"></a>
## 把想法放进画面

| 想做的事 | 工作台里的方式 |
| --- | --- |
| 看懂结构与运动 | 三维构件、旋转缩放，以及场景定义的角度、拆解或联动控制 |
| 把数学过程讲清楚 | LaTeX、曲线与数值示例；Manim 导出支持公式对应变形 |
| 继续完善同一个作品 | 描述局部修改，选择对象，回看或恢复历史版本 |
| 积累学习资料 | 公式库、关系图谱、错题记录、时间点笔记与教案课包 |
| 快速找到入口 | `Ctrl / ⌘ K` 搜索、悬浮任务球和可重播的新手教程 |
| 保存或分享结果 | 场景 JSON、公式库 JSON，以及配置渲染环境后的 MP4 |

内置 12 个示例，可从风机、函数、单摆、折射或排队过程开始。本地示例和参数探索不调用模型。

<p align="center"><img src="docs/assets/wiscomper-workflow.png" alt="输入想法，选择表达工具，交互探索，继续迭代并保存结果" width="100%"></p>

<a id="visual-tools"></a>
### 画面由内容决定

| 内容 | 使用方式 |
| --- | --- |
| 空间结构、机械运动 | **Three.js** 三维场景，可旋转观察和调整有界自由度 |
| 公式与二维几何 | 网页数学预览，使用 **Manim** 导出符号对应变形 |
| 流程、图片标注与二维关系 | **Canvas 2D** 图层、路径与关键帧 |
| 函数和物理示例 | 固定 Python 构建器计算结果，改变参数后重新计算 |

你可以明确要求二维或三维。自定义交互使用受限数据绑定，模型输出不会作为任意 Python 或 JavaScript 执行。

<a id="quick-start"></a>
## 开始使用

需要 **Python 3.11+**，推荐 **Node.js 24**。Node 支持范围为 `^22.19.0 || >=24.0.0`，即 22 系列的 22.19.0 及以上，或 24 及以上版本。Windows 启动器另需 PowerShell 7。

```bash
git clone https://github.com/rainbowyuyu/Wisdom_Computing_Perspective.git
cd Wisdom_Computing_Perspective/wiscomper
```

仓库中的 `html_root/` 保留旧站，新工作台位于 `wiscomper/`。以下命令均在新工作台目录执行。

<details open>
<summary><strong>Windows · 本机启动</strong></summary>

```powershell
py -3 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
npm ci
pwsh -NoProfile -File ./Start.ps1
```

启动后打开 `http://127.0.0.1:3088/`。已有环境也可使用根目录的 `万象世界.exe`；该名称保留为兼容入口。EXE 读取外部脚本，更新网页无需重编启动器。

停止由启动器管理的服务：`pwsh -NoProfile -File ./Stop.ps1`。手动启动的服务由原终端停止。

</details>

<details>
<summary><strong>Linux · 独立本机运行</strong></summary>

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm ci
.venv/bin/python main.py
```

默认监听 `127.0.0.1:3088`。公网使用前需配置正式 HTTPS 域名与反向代理，见 [公网部署](docs/deployment.md)。替换宝塔旧站请使用 [保留数据的部署流程](deploy/DEPLOY-PACKAGE.md)。

</details>

首次运行可以先体验内置示例。创建自己的内容前，参考 [.env.example](.env.example) 配置模型；已有 `.env` 请保留，避免覆盖。

<a id="models-and-accounts"></a>
## 模型与登录

| 使用场景 | 可用模型 |
| --- | --- |
| 普通在线用户 | Qwen；仍需登录、完成适用的邮箱验证，并符合站点额度 |
| VIP / 管理员 | 已配置的 Qwen、ChatGPT 和 Claude；仍受全站预算限制 |
| 直接访问本机工作台 | 全部已配置模型；启用公网模式后不再适用本机例外 |

**Qwen 是默认模型。** Windows 使用本机全局 Qwen 工具与当前用户 DPAPI 凭据；Linux 可读取服务器私有配置中的 `ALIYUN_KEY` 或 `DASHSCOPE_API_KEY`。ChatGPT / Claude 支持本机服务配置或独立服务器配置。字段和连接边界见 [Runtime](runtime/README.md)。

**邮箱入口**支持用户名或邮箱密码登录，以及验证码注册、绑定验证和找回密码；验证码流程需要 SMTP。**GitHub 登录**需要 OAuth App 和匹配的回调地址，Client Secret 未配置时不能完成登录。GitHub 身份不会因同名而自动合并旧邮箱账号。

[旧账号接入](docs/legacy-accounts.md) · [本机 GitHub 配置](docs/github-local-setup.md) · [公网 OAuth 与 HTTPS](docs/deployment.md)

<a id="export"></a>
## 从交互预览到视频

场景 JSON 可直接导出。MP4 支持 1280 × 720、15 / 24 fps，额外需要渲染环境：

- **二维 / 三维浏览器导出**：FFmpeg 与可用的 Chrome、Edge 或 Playwright Chromium。
- **Manim 二维导出**：安装 `requirements-manim.txt`，准备 FFmpeg、LaTeX 和 dvisvgm；Linux 还需对应 Cairo/Pango 等系统库。

参数和观察视角会随作品保存。视频使用固定渲染器，不额外调用模型；后端依赖未就绪时会提示。安装命令及导出细节见 [完整使用说明](docs/guide.zh-CN.md#视频导出)。

<a id="deployment"></a>
## 更新程序，保留已有内容

部署包支持覆盖前检查、备份与回滚。旧 `.env`、`.env.local` 和 MySQL 保留，上传文件留在原位置；新工作台数据默认存入独立的 `var/wiscomper-harness/`。安装程序不执行数据库建表或删表 SQL。

按 [部署包说明](deploy/DEPLOY-PACKAGE.md) 上传并解压，在宝塔停止原服务后，从包目录执行：

```bash
python3 deploy.py install --target /www/wwwroot/wiscomper.com
```

入口仍为 `python main.py`。首次部署还需检查 Nginx 代理、运行用户和系统依赖。已有本机隔离测试；生产服务器尚需实机验收，官网链接也不表示此版本已经上线。

旧账号可沿用原库，公式、笔记和错题支持迁入。旧视频和课包等内容会保留，但并非全部已映射到新界面，详见 [迁移范围](docs/legacy-accounts.md#旧学习资料)。

<a id="documentation"></a>
## 文档导航

| 想了解 | 入口 |
| --- | --- |
| 完整操作、启动器与存储 | [中文使用手册](docs/guide.zh-CN.md) |
| 模型如何选工具和检查场景 | [Runtime](runtime/README.md) · [场景契约](docs/contract.md) |
| 交互绑定与探索状态 | [交互说明](docs/interaction-contract.md) |
| 邮箱、旧库与学习资料 | [账号兼容](docs/legacy-accounts.md) |
| HTTPS、OAuth 与部署回滚 | [公网部署](docs/deployment.md) · [部署包](deploy/DEPLOY-PACKAGE.md) |
| 已执行的测试与适用范围 | [验证记录](docs/verification.md) |

<details>
<summary><strong>开发检查与目录</strong></summary>

```bash
# 在项目虚拟环境中运行
python -m pytest -q
npm run test:runtime
```

`server/` 管理 API 与数据；`runtime/` 负责受限模型流程；`web/` 提供工作台。`tests/` 保存回归测试，`deploy/` 与 `tools/` 提供部署辅助。浏览器测试和视频导出需要相应环境。

真实 `.env`、数据库、用户作品和日志留在运行环境中，不提交到 Git；密钥仅保存在服务端。任务有调用次数与时间限制，权限和归属由服务端校验。

</details>

## 使用范围

“让万物动起来”是可视化表达的方向。通用三维结构与气流属于示意，单张图片不能可靠恢复真实尺寸或完整三维模型。数值示例只在标明的假设内解释规律，公式展示也不等于自动证明。重要结果请结合原题、单位与适用条件复核。

<p align="center"><a href="#top">↑ 回到顶部</a> · <a href="README.en.md">Read in English</a> · <a href="https://www.wiscomper.com/">Wiscomper</a></p>
