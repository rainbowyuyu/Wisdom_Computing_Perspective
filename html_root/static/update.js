async function loadVersionFromUpdate() {
  try {
    const res = await fetch('update.md');
    if (!res.ok) throw new Error('update.md not found');

    const text = await res.text();

    // 匹配所有版本号，如：v 1.2.1 / v1.2.1
    const versionMatches = [...text.matchAll(/v\s*([\d.]+)/gi)];

    if (versionMatches.length === 0) return;

    // 取最后一个版本号
    const latestVersion = 'v' + versionMatches[versionMatches.length - 1][1];

    const el = document.getElementById('version');
    if (el) el.textContent = latestVersion;

  } catch (err) {
    console.warn('Version load failed:', err);
  }
}

loadVersionFromUpdate();

