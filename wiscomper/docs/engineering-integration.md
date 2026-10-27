# 可选工程来源集成

工程导入用于展示已有、可追溯的几何来源。没有配置时，普通文字、公式、图片和教学可视化照常使用；工程导入会提示“尚未配置工程来源目录”，不会搜索其他项目或猜测来源。

配置放在服务端私有 .env.local 或进程环境中。已有配置优先级仍为进程环境 > .env.local > .env > .env.deploy，不需要复制数据库或模型凭据。配置在工程导入时读取，模块导入和普通页面启动不访问工程目录。

| 设置 | 含义 |
| --- | --- |
| WISCOMPER_ENGINEERING_WORKSPACES | 专用工程工作区绝对目录；来源结构是“目录 / 32位十六进制工作区ID / files”。 |
| WISCOMPER_ENGINEERING_NATIVE_OUTPUTS | 独立布局 JSON 的专用绝对目录；与工作区目录可分别配置。 |
| WISCOMPER_ENGINEERING_WORKSPACE_ID | 可选默认工作区 ID；显式请求中的 ID 优先。 |
| WISCOMPER_ENGINEERING_BASIS_PATH | 默认设计依据相对路径；显式请求路径优先。 |
| WISCOMPER_ENGINEERING_RELEASE_PATH | 可选阶段审核 JSON 相对路径。 |
| WISCOMPER_ENGINEERING_REVIEW_PATH | 可选审核说明文本相对路径。 |
| WISCOMPER_ENGINEERING_DEFAULT_CANDIDATE | 可选默认构型 ID；必须存在于下面的映射中。 |
| WISCOMPER_ENGINEERING_PROFILES_JSON | 构型 ID 到标签、类型、报告路径与网格路径的 JSON 映射。 |

只查看 engineering-geometry-v1/turbine_array 布局时，只需配置一个合适的来源根目录。工作区来源仅允许 files/geometry/ 下的 JSON；独立输出只允许其专用根目录内的 JSON。未配置的根目录不会获得读取权限。请求几何必须与其 SHA256 绑定文件完全一致。

平台构型导入还需要工作区、设计依据和构型映射。下面是格式示例，不是随项目发布的实际工程：

    WISCOMPER_ENGINEERING_WORKSPACES=/srv/private/engineering-workspaces
    WISCOMPER_ENGINEERING_WORKSPACE_ID=
    WISCOMPER_ENGINEERING_BASIS_PATH=inputs/design-basis.json
    WISCOMPER_ENGINEERING_DEFAULT_CANDIDATE=demo
    WISCOMPER_ENGINEERING_PROFILES_JSON='{"demo":{"label":"演示装配来源","kind":"assembly","geometry_path":"geometry/demo/report.json","mesh_path":"geometry/demo/mesh.json"}}'

映射支持 assembly 与 wet_surface，最多16项；每项必须同时给出 label、kind、geometry_path、mesh_path。候选编号、报告和网格必须匹配。相对路径仅限 geometry、inputs、reports、results、notes、references 目录；父级跳转、绝对路径及越界符号链接会拒绝。来源根目录不能设置为整个磁盘。

当前平台导入适配器仍只接收 LJ20-C1-design-basis/v1 设计依据和 ai-engineer-scene-v1 米制表面网格；配置化没有扩大其物理模型或格式范围。工程预览不等同于仿真求解或工程验收。

runtime/engineering-imports/ 保存本机的内容寻址导入副本，其中包含原工程证据，不应提交 Git。常规测试只用临时合成来源。需要检查自己的真实平台来源时，可显式设置 RUN_REAL_ENGINEERING=1；布局验收可设置 WISCOMPER_TEST_ENGINEERING_REQUEST 为本机请求 JSON 路径。两者都不调用模型或付费服务。
