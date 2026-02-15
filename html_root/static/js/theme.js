// static/js/theme.js

export function initTheme() {
    // 1. 优先读取用户之前的选择 (localStorage)
    const savedTheme = localStorage.getItem('theme');

    // 2. 获取系统当前的偏好 (浏览器深色模式)
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

    // 3. 决策：如果有缓存用缓存，否则用系统偏好
    if (savedTheme === 'dark' || (!savedTheme && systemPrefersDark)) {
        document.documentElement.setAttribute('data-theme', 'dark');
    } else {
        document.documentElement.setAttribute('data-theme', 'light');
    }

    // 4. 监听系统变化 (当用户在系统设置里切换深色模式时，网页实时响应)
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
        // 只有当用户没有手动覆盖过主题时，才跟随系统
        if (!localStorage.getItem('theme')) {
            const newTheme = e.matches ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            window.dispatchEvent(new CustomEvent('theme-change', { detail: newTheme }));
        }
    });

    updateThemeIcon();
}

export function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme); // 记住用户的选择
    updateThemeIcon();
    // 派发主题切换事件，供画板等模块同步更新
    window.dispatchEvent(new CustomEvent('theme-change', { detail: newTheme }));
}

function updateThemeIcon() {
    const icon = document.getElementById('theme-toggle-icon');
    if (icon) {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        // 切换图标：月亮代表深色，太阳代表浅色
        icon.className = isDark ? 'fa-solid fa-moon' : 'fa-solid fa-sun';
        // 可选：更新 title 提示
        icon.parentElement.title = isDark ? "切换浅色模式" : "切换深色模式";
    }
}