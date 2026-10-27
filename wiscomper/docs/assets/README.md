# Wiscomper README 配图

两张图延续智算视界的蓝紫配色与留白。README 使用 PNG，SVG 与生成脚本保留在此目录中，方便后续修改。

| 文件 | 用途 | 尺寸 |
| --- | --- | --- |
| `wiscomper-hero.png` | README 品牌封面 | 2400 × 1140 |
| `wiscomper-workflow.png` | 输入、工具选择与交互输出的流程说明 | 2400 × 975 |
| `wiscomper-hero.svg` | 封面向量源文件 | 1600 × 760 |
| `visualization-flow.svg` | 流程向量源文件 | 1600 × 650 |

封面是产品概念插画，不是运行截图。风机上的流线只表示方向，不是流场求解结果。数值方案仍以程序中各自声明的模型和假设为准，视频导出需要安装相应依赖。

Logo 的路径来自工程已有的 `web/assets/wisdom-logo.svg`，保持其原有几何形状，原始文件不变。其余构图与向量元素为本次 README 配图编排，没有使用第三方图库或调用生成 API。SVG 为自包含文件，不加载远程图片、字体或脚本。

建议替代文本：

- 中文封面：智算视界可视化工作台概念图，展示三维风机、数学曲线和知识连接。
- English cover: Wiscomper workbench concept artwork featuring a 3D fan, a mathematical curve and connected knowledge nodes.
- 中文流程：从文字、公式、图片或手绘输入，经工具选择生成可交互场景，并支持版本修改和导出。
- English flow: Text, formulas, images and sketches become interactive scenes through bounded tool selection, with project revisions and export.

在项目根目录执行以下命令可重新生成：

```sh
python docs/assets/build_artwork.py
node docs/assets/render_artwork.mjs
```

向量生成只使用 Python 标准库。PNG 渲染使用工程已有的 `sharp`，按 108 DPI 输出；机器需有中文字体（例如 Microsoft YaHei 或 Noto Sans CJK SC）。本次成品已检查中文显示和边界，无裁切。

标志归属与工程既有授权保持一致；此说明不授予整个项目新的开源许可。
