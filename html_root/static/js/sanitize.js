import DOMPurify from './vendor/dompurify.es.mjs';

export function sanitizeMarkdownHtml(html) {
    if (!html || typeof html !== 'string') return '';
    return DOMPurify.sanitize(html, {
        USE_PROFILES: { html: true },
        FORBID_TAGS: ['style', 'form', 'input', 'button', 'select', 'textarea', 'video', 'audio', 'source'],
        FORBID_ATTR: ['style', 'srcset', 'id', 'name'],
        ALLOW_DATA_ATTR: false,
    });
}
