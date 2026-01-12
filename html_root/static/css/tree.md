static/  
├── css/  
│   ├── base.css       # 基础变量、重置样式、字体  
│   ├── layout.css     # 布局（导航栏、容器、Footer、Hero）  
│   ├── components.css # 卡片、按钮、输入框、Modal 等通用组件  
│   ├── pages.css      # 特定页面的样式（工作区、计算页、帮助页）  
│   └── main.css       # 入口文件（使用 @import 聚合）
└── ...

static/  
├── css/  
│   ├── base.css  
│   ├── layout.css  
│   ├── components.css  
│   ├── pages/              <-- 新增目录  
│   │   ├── home.css        # 首页 (Hero, Features)  
│   │   ├── workspace.css   # 工作区 (识别, 画板)  
│   │   ├── calculate.css   # 计算页  
│   │   ├── examples.css    # 案例页  
│   │   └── help.css        # 帮助页  
│   └── main.css            # 入口文件  