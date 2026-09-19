/** Decode complete SSE frames, including split UTF-8, CRLF and multiline data. */
export async function consumeEvents(response, onEvent, signal) {
    if (!response.ok) {
        let data; try { data = await response.json(); } catch { /* Non-JSON proxy response. */ }
        const message = typeof data?.message === 'string' ? data.message : typeof data?.detail === 'string' ? data.detail : null;
        throw new Error(message || `请求失败（${response.status}），请检查输入或稍后重试。`);
    }
    if (!response.body) throw new Error('浏览器不支持流式响应。');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '', ended = false;
    const deliver = frame => {
        const data = frame.split(/\r?\n/).filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
        if (!data) return;
        const event = JSON.parse(data);
        if (event.type === 'complete' || event.type === 'error' || event.type === 'handoff') ended = true;
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
                // A terminal event completes the task even if a proxy keeps HTTP open.
                signal?.throwIfAborted();
                if (ended) return;
            }
            if (buffer.length > 2_000_000) throw new Error('响应过大，请缩短题目后重试。');
            if (done) break;
        }
        signal?.throwIfAborted();
        if (buffer.trim()) deliver(buffer);
        if (!ended) throw new Error('连接提前结束，已收到的步骤会保留，请重试。');
    } finally {
        signal?.removeEventListener('abort', abort);
        // Some transports never resolve cancellation; do not hold the UI hostage.
        reader.cancel().catch(() => {});
        reader.releaseLock();
    }
}

/** Bound both connection setup and streaming, including servers sending heartbeats forever. */
export async function requestEvents(url, options, onEvent, {
    idleTimeoutMs = 30000, totalTimeoutMs = 180000,
    timeoutMessage = '等待结果超时，任务已停止，已收到的内容保留，请重试。',
} = {}) {
    const controller = new AbortController(), signal = options?.signal;
    const abort = () => controller.abort(signal.reason);
    let idleTimer, totalTimer;
    const expire = message => controller.abort(new Error(message));
    const touch = () => {
        clearTimeout(idleTimer);
        idleTimer = setTimeout(() => expire('连接长时间没有响应，已停止等待。请检查网络后重试，已收到的内容会保留。'), idleTimeoutMs);
    };
    signal?.addEventListener('abort', abort, {once:true});
    if (signal?.aborted) abort();
    try {
        controller.signal.throwIfAborted();
        touch();
        totalTimer = setTimeout(() => expire(timeoutMessage), totalTimeoutMs);
        const response = await fetch(url, {...options, signal:controller.signal});
        await consumeEvents(response, event => {touch();onEvent(event);}, controller.signal);
    } catch (error) {
        if (controller.signal.aborted) throw controller.signal.reason;
        throw error;
    } finally {
        clearTimeout(idleTimer);clearTimeout(totalTimer);
        signal?.removeEventListener('abort', abort);
        controller.abort();
    }
}
