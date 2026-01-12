// static/js/calculate.js

export async function startAnimation() {
    const container = document.getElementById('video-container');
    const method = document.getElementById('calc-method').value;
    const matA = document.getElementById('latex-code-a').value;
    const matB = document.getElementById('latex-code-b').value;

    container.innerHTML = `
        <div class="placeholder-content" style="color:var(--secondary-color)">
            <i class="fa-solid fa-circle-notch fa-spin" style="font-size: 3rem;"></i>
            <p style="margin-top:1rem;">Manim 渲染中 (约需5-10秒)...</p>
        </div>
    `;

    try {
        const response = await fetch('/api/animate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                matrixA: matA,
                matrixB: matB,
                operation: method
            })
        });
        const data = await response.json();

        if (data.status === 'success') {
            // 添加时间戳防止缓存
            const videoSrc = `${data.video_url}?t=${new Date().getTime()}`;
            container.innerHTML = `
                <video controls autoplay style="width: 100%; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.5);">
                    <source src="${videoSrc}" type="video/mp4">
                    您的浏览器不支持视频标签。
                </video>
            `;
        } else {
            container.innerHTML = `<p style="color:red; text-align:center;">生成失败: ${data.message || 'Unknown error'}</p>`;
        }
    } catch (e) {
        console.error(e);
        container.innerHTML = `<p style="color:red; text-align:center;">服务器连接错误</p>`;
    }
}