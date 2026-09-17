# Provenance · 智算星云成就闪卡

## 设计假设

- 主题取自站点 `ACHIEVEMENT_DEFS`（13 枚星云成就）
- 画风：深空学院 / 青绿星座，非二次元、非奶油纸感
- 稀有度：target=1 珠光，中档银箔，高档烫金
- 线稿：由主体 RGBA 轮廓与边缘检测生成，保证与主体同画布对齐
- 文字层：Windows 楷体/黑体本地字体排版透明 PNG

## 生成记录

- 背景 5 张（按成就大类）：内置图像工具 `GenerateImage`
- 主体 13 张：内置图像工具 `GenerateImage`
- Alpha：`checkerboard_to_alpha` + 暗底抠图/`refine_subjects.py`
- Blender：官方便携版 4.5.13（SHA-256 校验后解压到 `tools/`）
- 展台：RuiC web-template + `gallery-extra.js` 热切换 13 套纹理

## 资产路径

- 单卡工程：`cards/<id>/assets/{subject,background,lineart,text}.png`
- 可编辑场景：`card.blend`
- 展台：`web/`（`deck/<id>/` 存各卡纹理）
