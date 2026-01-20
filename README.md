## rainbow_yu 🐋✨

![logo.png](assert/images/logo.png)

# 智算视界 (Wisdom Computing Perspective)

<div align="center">
  <h3>基于 AI 视觉识别与 Manim 动态引擎的下一代数学可视化计算平台</h3>
</div>

---

## 📖 项目简介

**智算视界 (Visdom)** 是一个集成了 **OCR 手写识别**、**大模型语义理解**与 **Manim 数学动画引擎** 的 Web 应用。

用户可以通过手写或上传数学公式图片，系统将自动识别为 LaTeX 代码。随后，用户可以对公式进行编辑、存储，并一键生成高质量的数学推演动画（如矩阵变换、行列式计算过程），帮助学生和研究者直观地理解抽象的数学概念。

## ✨ 核心功能

- **👁️ 智能识别 (OCR)**：集成 Qwen-VL 多模态大模型， 以及OCR技术，精准识别手写矩阵、积分及复杂代数公式。
- **🎬 动态推演**: 基于 Python Manim 引擎，实时生成数学运算的可视化视频（MP4）。
- **💾 云端算式库**: 支持用户注册/登录，将常用公式保存至 MySQL 数据库，随时复用。
- **✏️ 交互式画板**: 内置 HTML5 画板与 MathLive 编辑器，支持手写输入与所见即所得的公式修改。
- **🌊 流式反馈**: 动画生成过程采用 SSE (Server-Sent Events) 技术，实时展示代码生成与渲染进度。

---

## 🛠️ 技术栈

- **后端**: Python, FastAPI, Uvicorn
- **前端**: HTML5, CSS3, JavaScript (原生模块化开发), MathLive, Driver.js
- **AI 模型**: 阿里云 Qwen-VL / OpenAI 兼容接口
- **视觉模型**: Mamba-YOLOv11模型
- **渲染引擎**: Manim Community Edition
- **数据库**: MySQL
- **工具**: FFmpeg, LaTeX (TeXLive/MiKTeX)

---

## 🚀 本地部署指南

### 1. 环境准备

确保您的系统已安装 **Python 3.10+**。

由于 Manim 的渲染依赖底层系统库，请务必先配置以下环境：

1.  **FFmpeg**: 用于视频合成。
    *   下载并配置环境变量：[FFmpeg 官网](https://ffmpeg.org/)
    *   验证：终端输入 `ffmpeg -version`
2.  **LaTeX 环境**: 用于渲染数学公式。
    *   推荐安装 [MiKTeX](https://miktex.org/) (Windows) 或 [TeX Live](https://tug.org/texlive/) (Linux/macOS)。
    *   验证：终端输入 `latex --version`

### 2. 安装 Python 依赖

在项目根目录下运行：

```bash
pip install -r requirements.txt
```

### 3. 配置数据库 (MySQL)

1.  确保本地或远程 MySQL 服务已启动。
2.  创建一个新的数据库（例如命名为 `wiscomper_db`）。
3.  执行以下 SQL 初始化表结构：

```sql
CREATE DATABASE IF NOT EXISTS wiscomper_db;
USE wiscomper_db;

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 算式表
CREATE TABLE IF NOT EXISTS formulas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    latex TEXT NOT NULL,
    note VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(username) ON DELETE CASCADE
);
```

### 4. 配置环境变量 (.env)

在项目根目录下创建 `.env` 文件，填入您的配置：

```ini
# 阿里云 DashScope API Key (用于 OCR 和代码生成)
ALIYUN_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# MySQL 数据库配置
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DB=wiscomper_db
MYSQL_PORT=3306
```

### 5. 启动项目

使用 Python 直接运行入口文件：

```bash
python main.py
```

或者使用 Uvicorn 命令行：

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

启动成功后，访问浏览器：`http://localhost:8000`

---

## 📂 文件结构

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
    ├── index.html           # 单页应用入口
    ├── update.md            # 更新日志
    ├── css/                 # 样式文件 (模块化)
    │   ├── main.css
    │   ├── layout.css
    │   ├── components.css
    │   └── pages/           # 各页面独立样式
    ├── js/                  # 脚本文件 (ES6 Modules)
    │   ├── main.js          # 前端入口
    │   ├── ui.js            # UI 交互与路由
    │   ├── canvas.js        # 画板逻辑
    │   ├── detect.js        # 识别与 MathLive 交互
    │   ├── calculate.js     # 动画生成与 SSE 处理
    │   ├── formulas.js      # 算式库 CRUD
    │   └── auth.js          # 登录注册逻辑
    ├── assets/              # 图标与 Logo
    ├── docs/                # Markdown 文档 (隐私政策等)
    └── videos/              # 存放生成的 MP4 视频
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

Copyright © 2026 Visdom Computing Perspective.