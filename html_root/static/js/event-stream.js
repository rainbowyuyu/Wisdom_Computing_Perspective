/** Decode complete SSE frames, including split UTF-8, CRLF and multiline data. */
export async function consumeEvents(response, onEvent, signal) {
    if (!response.ok) throw new Error(`请求失败（${response.status}），请检查输入或稍后重试。`);
    if (!response.body) throw new Error('浏览器不支持流式响应。');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '', ended = false;
    const deliver = frame => {
        const data = frame.split(/\r?\n/).filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
        if (!data) return;
        const event = JSON.parse(data);
        if (event.type === 'complete' || event.type === 'error') ended = true;
        onEvent(event);
    };
    const abort = () => { reader.cancel().catch(() => {}); };
    signal?.addEventListener('abort', abort, { once: true });
    try {
        while (true) {
            signal?.throwIfAborted();
            const { done, value } = await reader.read();
            buffer += decoder.decode(value, { stream: !done });
            let match;
            while ((match = /\r?\n\r?\n/.exec(buffer))) {
                deliver(buffer.slice(0, match.index));
                buffer = buffer.slice(match.index + match[0].length);
            }
            if (buffer.length > 2_000_000) throw new Error('响应过大，请缩短题目后重试。');
            if (done) break;
        }
        signal?.throwIfAborted();
        if (buffer.trim()) deliver(buffer);
        if (!ended) throw new Error('连接提前结束，已收到的步骤会保留，请重试。');
    } finally {
        signal?.removeEventListener('abort', abort);
        await reader.cancel().catch(() => {});
        reader.releaseLock();
    }
}
