import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeMathText, normalizeLatex, normalizeSolution } from '../static/js/math-text.js';

test('legacy separators, doubled commands and formula wrappers normalize consistently',()=>{
  const broken=String.raw`x-2=0\quad\mathrm{or}\quadx-3=0`;
  const fixed=String.raw`x-2=0\quad\mathrm{or}\quad x-3=0`;
  assert.equal(normalizeLatex(broken),fixed);
  assert.equal(normalizeLatex(broken.replaceAll('\\','\\\\')),fixed);
  assert.equal(normalizeMathText(`结果 $${broken}$。`),`结果 $${fixed}$。`);
  assert.equal(normalizeLatex(String.raw`\[\\frac{1}{2}\]`),String.raw`\frac{1}{2}`);
  const matrix=String.raw`\begin{bmatrix}a&b\\c&d\end{bmatrix}`;
  assert.equal(normalizeLatex(matrix),matrix);
  assert.equal(normalizeLatex(String.raw`\unknown{x}`),String.raw`\unknown{x}`);
  const original={steps:[{formula:broken}]};assert.equal(normalizeSolution(original).steps[0].formula,fixed);
  assert.equal(original.steps[0].formula,broken);
});

test('bare nested LaTeX in Chinese prose is normalized without changing delimited math', () => {
  assert.equal(normalizeMathText(String.raw`结果为 \frac{11}{6}。`), String.raw`结果为 \(\frac{11}{6}\)。`);
  assert.equal(normalizeMathText(String.raw`由 $x=2$ 得 \sqrt{\frac{1}{2}}，成立。`), String.raw`由 $x=2$ 得 \(\sqrt{\frac{1}{2}}\)，成立。`);
  assert.equal(normalizeMathText(String.raw`面积 \int_0^1 x^{2}+3x\,dx`), String.raw`面积 \(\int_0^1 x^{2}+3x\,dx\)`);
  assert.equal(normalizeMathText(String.raw`说明 \text{有向面积}=\frac{1}{3}`), String.raw`说明 \(\text{有向面积}=\frac{1}{3}\)`);
});

test('matrices retain row breaks; incomplete input and HTML-like text stay literal', () => {
  const matrix=String.raw`\begin{bmatrix}1&2\\0&1\end{bmatrix}`;
  assert.equal(normalizeMathText(matrix), String.raw`\[${matrix}\]`);
  assert.equal(normalizeMathText(String.raw`结果为 \frac{1}{`), String.raw`结果为 \frac{1}{`);
  const injection='条件 $x > 2$，<img src=x onerror=alert(1)>';
  assert.equal(normalizeMathText(injection), injection);
});

test('aligned systems with visible braces render as one display block and preserve prose',()=>{
  const system=String.raw`\begin{aligned}&(3)\left\{\begin{array}{l}x_{1}-5x_{3}=1\\-x_{1}+x_{2}+6x_{3}=3\\2x_{1}+3x_{2}-7x_{3}=15\end{array}\right.\\&(5)\left\{\begin{array}{l}x_{1}+x_{2}+x_{3}+x_{4}=1\\2x_{1}+3x_{2}+4x_{3}+x_{4}=3\\3x_{1}+x_{2}-x_{3}+5x_{4}=1\end{array}\right.\end{aligned}`;
  const text=system+'\n本次子目标：代入原方程验证。';
  const normalized=String.raw`\[${system}\]`+'\n本次子目标：代入原方程验证。';
  assert.equal(normalizeMathText(text),normalized);
  assert.equal(normalizeMathText(normalized),normalized);
  assert.equal(normalizeMathText(system+' Verify the result.'),String.raw`\[${system}\]`+' Verify the result.');
  const set=String.raw`\left\{x\mid x>0\right\}`;
  assert.equal(normalizeMathText(set),String.raw`\(${set}\)`);
  const bare=String.raw`\left\{\begin{array}{l}x=1\\y=2\end{array}\right.`;
  assert.equal(normalizeMathText(bare),String.raw`\[${bare}\]`);
  const incomplete=String.raw`\begin{aligned}x&=\frac{1}{`;
  assert.equal(normalizeMathText(incomplete),incomplete);
});
