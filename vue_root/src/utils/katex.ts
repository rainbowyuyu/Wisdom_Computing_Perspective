export async function renderMathIn(container: HTMLElement | null | undefined) {
  if (!container) return;
  const path = "/static/js/math-text.js";
  const math = await import(/* @vite-ignore */ path);
  math.renderMathIn(container);
}
