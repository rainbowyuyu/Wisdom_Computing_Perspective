// Math remains text until KaTeX parses it; model output never becomes HTML.
const explicitMath = /(\$\$[\s\S]*?\$\$|\$[^$\n]+\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]|<[^>\n]*>)/g;
const cache = new WeakMap();
const pending = new Map();

export function normalizeLatex(value = '') {
    let source=String(value).trim();
    for(const [left,right] of [['$$','$$'],['\\[','\\]'],['\\(','\\)'],['$','$']]) {
        if(source.startsWith(left)&&source.endsWith(right)&&source.length>=left.length+right.length){source=source.slice(left.length,-right.length).trim();break;}
    }
    // Preserve intentional row separators inside matrix/aligned environments.
    if(!/\\begin\s*\{/.test(source))source=source.replace(/\\{2}(?=[A-Za-z])/g,'\\');
    // Repair the exact separator emitted by the former quadratic solver.
    source=source.replaceAll(String.raw`\quad\mathrm{or}\quadx`,String.raw`\quad\mathrm{or}\quad x`);
    return source;
}

export function normalizeSolution(solution) {
    return {...solution,steps:solution.steps.map(step=>({...step,formula:normalizeLatex(step.formula)}))};
}

function deferRender(element,render) { pending.set(element,render); }
function retryPending() {
    for(const [element,render] of [...pending]){pending.delete(element);if(element.isConnected)render();}
}
if(typeof window!=='undefined') {
    window.addEventListener('load',retryPending);
    document.addEventListener('load',event=>{if(event.target?.tagName==='SCRIPT')retryPending();},true);
    window.addEventListener('math-renderer-ready',retryPending);
}

export function renderFormula(element,value='',options={}) {
    if(!element)return;
    const source=normalizeLatex(value);
    element.textContent=source;element.classList.remove('math-render-error');element.removeAttribute('title');
    pending.delete(element);
    if(!source)return;
    if(!window.katex){deferRender(element,()=>renderFormula(element,source,options));return;}
    try {
        window.katex.render(source,element,{...options,displayMode:options.displayMode??true,throwOnError:true,trust:false,maxExpand:1000});
    } catch {
        element.textContent=source;element.classList.add('math-render-error');
        element.title='公式格式有误，请检查 LaTeX 命令和括号。';
    }
}

export function renderMathIn(container, { detectBareMath = true } = {}) {
    if(!container)return;
    pending.delete(container);
    if(!window.renderMathInElement){deferRender(container,()=>renderMathIn(container,{detectBareMath}));return;}
    // Only visit text nodes; preserve links, controls, code and rendered formula DOM.
    const walker=document.createTreeWalker(container,NodeFilter.SHOW_TEXT,{acceptNode(node){
        return node.parentElement?.closest('pre,code,textarea,script,style,math-field,.katex,.katex-error')?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT;
    }});
    const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
    if(detectBareMath)nodes.forEach(node=>node.textContent=normalizeMathText(node.textContent));
    container.classList.remove('math-render-error');
    container.removeAttribute('title');
    window.renderMathInElement(container,{
        delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false},{left:'\\(',right:'\\)',display:false},{left:'\\[',right:'\\]',display:true}],
        preProcess:normalizeLatex,throwOnError:true,trust:false,maxExpand:1000,
        ignoredTags:['script','noscript','style','textarea','pre','code','option','math-field'],
        ignoredClasses:['katex','katex-error'],
        errorCallback:()=>{container.classList.add('math-render-error');container.title='部分公式格式有误，请检查 LaTeX 命令和括号。';}
    });
}

export function normalizeMathText(value = '') {
    return String(value).split(explicitMath).map((part, index) => {
        if (index % 2) {
            if(part.startsWith('<'))return part;
            const size=part.startsWith('$$')||part.startsWith('\\')?2:1;
            return part.slice(0,size)+normalizeLatex(part.slice(size,-size))+part.slice(-size);
        }
        // A candidate ends at prose punctuation, or non-math text outside braces.
        // Brace depth preserves Chinese in \\text{...} and nested fractions.
        let result = '', cursor = 0;
        const start = /\\[a-zA-Z]+|[a-zA-Z0-9(][a-zA-Z0-9\s'()+*/.=^_{}−-]*[=^_]/g;
        let match;
        while ((match = start.exec(part))) {
            const from = match.index;
            let to = from, depth = 0, environments = 0;
            for (; to < part.length; to++) {
                const char = part[to];
                if (part.startsWith('\\begin{', to)) environments++;
                if (part.startsWith('\\end{', to)) environments = Math.max(0, environments - 1);
                // TeX control symbols (\{ and \}) are visible delimiters, not groups.
                let slashes=0;for(let i=to-1;i>=0&&part[i]==='\\';i--)slashes++;
                const escaped=slashes%2===1;
                if (char === '{' && !escaped) depth++;
                if (char === '}' && !escaped) { if (!depth) break; depth--; }
                // A complete outer environment is its own display block. Do not
                // swallow the following explanation (including English prose).
                if(char==='}'&&!escaped&&!depth&&!environments&&part.startsWith('\\begin{',from)) {to++;break;}
                if (!depth && !environments && !/[a-zA-Z0-9\s\\{}()[\]+*/=^_.,:;!|<>−\-]/.test(char)) break;
                if (!depth && !environments && /[\n,;:]/.test(char) && part[to-1] !== '\\') break;
            }
            const raw = part.slice(from, to).trimEnd().replace(/(?<!\\right|\\left|\\)[.]+$/, '');
            // Do not guess incomplete LaTeX during typing.
            if (raw && depth === 0 && environments === 0) {
                const display=/\\begin\s*\{/.test(raw);
                result += part.slice(cursor, from) + (display?'\\[':'\\(') + normalizeLatex(raw) + (display?'\\]':'\\)');
                cursor = from + raw.length;
            }
            start.lastIndex = Math.max(to, from + 1);
        }
        return result + part.slice(cursor);
    }).join('');
}

export function textWithMath(element, value = '') {
    if (!element) return;
    const text = String(value), renderer = window.renderMathInElement;
    const previous = cache.get(element);
    if (previous?.text === text && previous?.renderer === renderer) return;
    element.textContent = renderer ? normalizeMathText(text) : text;
    renderMathIn(element);
    cache.set(element, {text, renderer});
}

if(typeof window!=='undefined')window.renderMath=renderMathIn;
