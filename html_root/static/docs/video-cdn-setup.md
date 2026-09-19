# 视频加速配置说明（CDN + Nginx）

教学案例视频加载慢时，可通过以下方式加速。

---

## 一、启用阿里云 CDN（推荐）

项目已支持阿里云 CDN，配置后视频将走 CDN 加速，显著提升加载速度。

### 1. 前置准备

- 已购买 CDN 资源包（如 50GB 中国大陆下行流量）
- 已创建 OSS Bucket，并将视频上传至 `storage/` 路径
- CDN 加速域名已添加并完成 CNAME 解析

### 2. 环境变量配置

在项目根目录 `.env` 中增加：

```env
# 阿里云 CDN 鉴权（用于播放）
ALIYUN_CDN_DOMAIN=https://cdn.wiscomper.com
ALIYUN_CDN_AUTH_KEY=你的主KEY
ALIYUN_CDN_VIDEO_PATH=/storage
ALIYUN_CDN_AUTH_TTL=3600

# 公开 CDN 基地址（可选：不开启 URL 鉴权时设置，可加速列表预览）
ALIYUN_CDN_PUBLIC_BASE=https://cdn.wiscomper.com
```

- **ALIYUN_CDN_DOMAIN**：CDN 加速域名（如 `https://cdn.wiscomper.com`）
- **ALIYUN_CDN_AUTH_KEY**：CDN 控制台「URL 鉴权」中配置的主 KEY，与鉴权方式 A 一致
- **ALIYUN_CDN_VIDEO_PATH**：CDN 上视频路径前缀，需与 OSS 中路径对应
- **ALIYUN_CDN_PUBLIC_BASE**：若未启用 URL 鉴权，设为与 `ALIYUN_CDN_DOMAIN` 相同，列表和预览也会走 CDN

### 3. OSS 与 CDN 配置要点

- OSS 中视频路径示例：`storage/AStarVisualization2.mp4`
- CDN 源站选择 OSS 域名，如 `rainbow-yu.oss-cn-shanghai.aliyuncs.com`
- 若启用 URL 鉴权，在 CDN 控制台配置鉴权方式 A，主 KEY 与 `ALIYUN_CDN_AUTH_KEY` 一致

---

## 二、Nginx 优化（本地回源时）

当视频仍走本站时，建议在宝塔面板中配置 Nginx，以支持 Range 请求和合理缓冲。

本站播放器接口 `/api/v1/player/stream/{video_id}` 已内置单段 Range、ETag、Last-Modified 和 1 小时缓存头；无需额外改 Python 配置即可边下边播和拖动进度。Nginx 只需要把请求保持为 HTTP/1.1 并允许回源流式传输。

### 1. 打开 Nginx 配置

宝塔 → 网站 → 选择站点 → 设置 → 配置文件

### 2. 添加/检查以下配置

在 `location /` 或对应的 `proxy_pass` 块内添加：

```nginx
# 视频 Range 请求支持（拖拽进度、分片加载）
proxy_http_version 1.1;
proxy_set_header Connection "";

# 代理缓冲，避免大文件被截断
proxy_buffer_size 128k;
proxy_buffers 4 256k;
proxy_busy_buffers_size 256k;
proxy_temp_file_write_size 256k;
proxy_request_buffering off;

# 超时与大小
proxy_connect_timeout 300;
proxy_send_timeout 300;
proxy_read_timeout 300;
client_max_body_size 500m;
```

### 3. 静态资源直接由 Nginx 提供（可选）

若 `/assets/` 由本站提供，可增加：

```nginx
location /assets/ {
    alias /www/wwwroot/你的项目/html_root/static/assets/;
    add_header Cache-Control "public, max-age=86400";
    add_header Accept-Ranges bytes;
}
```

---

## 三、配置检查清单

| 项目 | 说明 |
|------|------|
| CDN 域名解析 | CNAME 指向 CDN 提供的地址 |
| OSS 视频路径 | 与 `ALIYUN_CDN_VIDEO_PATH` 对应 |
| .env 配置 | `ALIYUN_CDN_DOMAIN`、`ALIYUN_CDN_AUTH_KEY` 已填写 |
| 加速区域 | 选择「仅中国内地」以匹配资源包 |
| Nginx Range | 本地回源时需支持 `Accept-Ranges` |

---

## 四、验证

1. 打开教学案例页，播放视频，观察加载速度
2. 浏览器开发者工具 → Network，确认视频请求的域名是否为 CDN 域名
3. 若有 `Accept-Ranges: bytes`，表示支持 Range 请求，拖拽进度条可正常使用

## 五、视频文件建议

上传前建议统一为 H.264 视频 + AAC 音频，并使用 `faststart` 将索引移到文件开头。这样浏览器拿到开头的小段数据即可显示时长和开始播放，不必等待整个文件下载：

```bash
ffmpeg -i input.mp4 -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k -movflags +faststart output.mp4
```

教学案例卡片采用按需预览：首屏只加载封面或元数据，鼠标移入单个卡片后才请求视频，打开播放器后再使用鉴权分段地址。没有 CDN 时会自动使用本站流；CDN 回源失败时播放器会切换到本站地址。
