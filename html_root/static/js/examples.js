// static/js/examples.js
import { toggleModal } from './ui.js';

export async function loadExamples() {
    const grid = document.getElementById('examples-grid');
    if (!grid) return;

    grid.innerHTML = '<div style="grid-column:1/-1; text-align:center;"><i class="fa-solid fa-spinner fa-spin"></i> 加载案例中...</div>';

    try {
        const res = await fetch('/api/examples');
        const data = await res.json();

        if (data.status === 'success') {
            renderExampleCards(data.data);
        } else {
            grid.innerHTML = '<div style="text-align:center;">加载失败</div>';
        }
    } catch (e) {
        console.error(e);
        grid.innerHTML = '<div style="text-align:center;">网络错误</div>';
    }
}

function renderExampleCards(videos) {
    const grid = document.getElementById('examples-grid');
    if (videos.length === 0) {
        grid.innerHTML = '<div style="text-align:center;">暂无视频案例</div>';
        return;
    }

    grid.innerHTML = videos.map(v => `
        <div class="video-card" onclick="playExample('${v.url}', '${v.title}')">
            <div class="thumbnail video-preview-container">
                <!-- 
                    使用 video 标签作为封面 
                    muted: 静音 (浏览器策略要求自动播放必须静音)
                    loop: 循环
                    playsinline: 移动端内联播放
                -->
                <video 
                    src="${v.url}#t=1" 
                    muted 
                    loop 
                    playsinline 
                    preload="metadata"
                    onmouseover="this.play()" 
                    onmouseout="this.pause();"
                    style="width:100%; height:100%; object-fit:cover;"
                ></video>
                
                <!-- 播放图标覆盖层 -->
                <div class="play-overlay">
                    <i class="fa-solid fa-play-circle"></i>
                </div>
            </div>
            <div class="info">
                <h4>${v.title}</h4>
                <p>${v.description}</p>
            </div>
        </div>
    `).join('');
}

export function playExample(videoSrc, title) {
    const player = document.getElementById('example-video-player');
    const titleEl = document.getElementById('video-modal-title');

    if (player) {
        player.src = videoSrc;
        player.load();
        player.play().catch(e => console.log("Autoplay blocked"));
    }

    if (titleEl) {
        titleEl.innerText = title;
    }

    toggleModal('video-modal', true);
}

export function closeVideoModal() {
    const player = document.getElementById('example-video-player');
    if (player) {
        player.pause();
        player.currentTime = 0;
        player.src = "";
    }
    toggleModal('video-modal', false);
}