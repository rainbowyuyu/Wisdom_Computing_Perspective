Visdom System/
├── static/                # 存放前端资源
│   ├── index.html         # (保持上一步的代码)
│   ├── css                # 样式库
│   ├── js                 # 脚本库
│   └── videos/            # 存放生成的视频
├── logic/                 # 存放业务逻辑
│   ├── __init__.py
│   └── manim_generator.py # (新增：负责生成 Manim 动画脚本)
├── main.py                # (新增：FastAPI 后端入口)
├── requirements.txt       # (新增：依赖库列表)
└── .env                   # (新增：存放 API Key)