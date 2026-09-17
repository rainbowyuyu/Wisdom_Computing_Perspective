# 智算星云 · 成就闪卡（已迁入 html_root）

站点内成就面板与解锁弹窗使用分层闪卡；独立 3D 展台由静态目录托管。

## 位置

| 内容 | 路径 |
|---|---|
| 成就面板用分层图 | `html_root/static/assets/achievement-cards/` |
| 3D 展台 | `html_root/static/achievement-holo/` |
| 分层源文件 | `html_root/static/assets/achievement-cards/layers/` |
| 重建脚本 | `html_root/scripts/achievement-holo/` |

## 打开展台

启动站点后访问：`/static/achievement-holo/`

## 重建（可选）

```bash
python html_root/scripts/achievement-holo/prepare_all_cards.py
python html_root/scripts/achievement-holo/fix_and_export_site.py
python html_root/scripts/achievement-holo/assemble_gallery.py
```
