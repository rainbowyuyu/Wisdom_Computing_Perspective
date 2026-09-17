export const escapeText = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const palette = ['#3b82f6', '#8b5cf6', '#0891b2', '#d97706', '#f43f5e', '#10b981'];
const n = value => Number.isFinite(Number(value)) ? Number(value) : 0;
const pt = p => [n(p[0]), n(p[1])];

export function visualMarkup(visual, progress = 1) {
    progress = Math.max(0, Math.min(1, n(progress)));
    const v = visual || {kind:'reasoning'};
    if (v.kind === 'reasoning') return `<div class="tutor-reasoning"><span>∴</span><p>${escapeText(v.caption || '跟随左侧步骤，理解条件、推理与结论之间的关系。')}</p></div>`;
    let curves = (v.curves || []).map(c => ({label:c.label, points:c.points.map(pt)}));
    let marked = (v.points || []).map(pt);
    const labels = v.labels || [];
    if (v.kind === 'geometry') curves = Array.isArray(v.segments)
        ? v.segments.map(([a,b])=>({label:`${labels[a] || a+1}–${labels[b] || b+1}`,points:[marked[a],marked[b]]}))
        : [{label:'几何关系', points:marked}];
    if (v.kind === 'matrix') {
        const m = v.matrix;
        const corners = [[0,0],[1,0],[1,1],[0,1],[0,0]];
        const transform = ([x,y], t) => [(1-t)*x+t*(m[0][0]*x+m[0][1]*y), (1-t)*y+t*(m[1][0]*x+m[1][1]*y)];
        curves = [{label:'单位正方形',points:corners}, {label:'变换后',points:corners.map(p=>transform(p,progress))},
            {label:'基向量 e₁',points:[[0,0],transform([1,0],progress)]}, {label:'基向量 e₂',points:[[0,0],transform([0,1],progress)]}];
        marked = corners.map(p=>transform(p,1)); // final bounds keep the camera stable during transformation
    }
    const all = curves.flatMap(c=>c.points).concat(marked);
    if (!all.length) return '<p>本步骤暂无可绘制的坐标数据。</p>';
    let xmin=Math.min(0,...all.map(p=>p[0])), xmax=Math.max(0,...all.map(p=>p[0]));
    let ymin=Math.min(0,...all.map(p=>p[1])), ymax=Math.max(0,...all.map(p=>p[1]));
    let dx=Math.max(xmax-xmin,1), dy=Math.max(ymax-ymin,1);
    xmin-=dx*.1; xmax+=dx*.1; ymin-=dy*.1; ymax+=dy*.1;
    // Geometry and matrix scenes use equal units on both axes.
    if (v.kind !== 'plot') {
        const scale=Math.max((xmax-xmin)/540,(ymax-ymin)/290);
        const cx=(xmin+xmax)/2, cy=(ymin+ymax)/2;
        xmin=cx-scale*270; xmax=cx+scale*270; ymin=cy-scale*145; ymax=cy+scale*145;
    }
    const sx=x=>50+(x-xmin)/(xmax-xmin)*540, sy=y=>330-(y-ymin)/(ymax-ymin)*290;
    const xy=([x,y])=>`${sx(x).toFixed(2)},${sy(y).toFixed(2)}`;
    let svg=`<svg viewBox="0 0 640 380" role="img" aria-label="${escapeText(v.caption || '数学交互图形')}"><title>${escapeText(v.caption || '数学交互图形')}</title>`;
    for(let i=0;i<=6;i++) {
        const x=xmin+(xmax-xmin)*i/6, y=ymin+(ymax-ymin)*i/6;
        svg+=`<path d="M${sx(x)} 40V330 M50 ${sy(y)}H590" stroke="#718096" stroke-opacity=".16"/><text x="${sx(x)}" y="352" text-anchor="middle">${Number(x.toPrecision(3))}</text><text x="42" y="${sy(y)+4}" text-anchor="end">${Number(y.toPrecision(3))}</text>`;
    }
    svg+=`<path d="M50 ${sy(0)}H590 M${sx(0)} 40V330" stroke="#94a3b8" stroke-opacity=".7"/><text x="605" y="${Math.min(335,Math.max(50,sy(0)-8))}">x</text><text x="${sx(0)+10}" y="28">y</text>`;
    if(v.area && curves[0]) {
        const shown=curves[0].points.slice(0,1+Math.floor(progress*(curves[0].points.length-1)));
        const area=[[shown[0][0],0],...shown,[shown[shown.length-1][0],0]];
        svg+=`<polygon points="${area.map(xy).join(' ')}" fill="#3b82f6" fill-opacity=".2"/>`;
    }
    if(v.tangent && curves.length===2) {
        const index=Math.floor(progress*(curves[0].points.length-1));
        const p=curves[0].points[index], derivative=curves[1].points[index];
        if(derivative && Math.abs(p[0]-derivative[0])<1e-6) {
            const slope=derivative[1], span=Math.min((xmax-xmin)*.12,(ymax-ymin)*.15/(Math.abs(slope)||1));
            svg+=`<line x1="${sx(p[0]-span)}" y1="${sy(p[1]-slope*span)}" x2="${sx(p[0]+span)}" y2="${sy(p[1]+slope*span)}" stroke="#8b5cf6" stroke-width="2" stroke-dasharray="6 4"/>`;
        }
    }
    curves.forEach((curve,i)=> {
        let visible=curve.points;
        if(v.kind==='geometry'&&progress<1) {
            const position=progress*(curve.points.length-1),index=Math.floor(position),fraction=position-index;
            const a=curve.points[index],b=curve.points[index+1];
            visible=curve.points.slice(0,index+1);
            if(b)visible.push([a[0]+(b[0]-a[0])*fraction,a[1]+(b[1]-a[1])*fraction]);
        }
        svg+=`<polyline points="${visible.map(xy).join(' ')}" fill="${v.kind==='matrix'&&i<2?palette[i]:'none'}" fill-opacity=".12" stroke="${palette[i%6]}" stroke-width="2.7" stroke-linejoin="round"/>`;
    });
    if(v.kind==='plot'||v.kind==='geometry') {
        curves.forEach((c,i)=> {
            const p=c.points[Math.min(c.points.length-1,Math.floor(progress*(c.points.length-1)))];
            if(v.kind==='plot') svg+=`<circle cx="${sx(p[0])}" cy="${sy(p[1])}" r="5" fill="${palette[i%6]}"/><text x="${60+i%2*270}" y="${18+Math.floor(i/2)*14}" fill="${palette[i%6]}">${escapeText(c.label)} (${p[0].toFixed(2)}, ${p[1].toFixed(2)})</text>`;
        });
    }
    if(v.kind!=='matrix') marked.forEach((p,i)=> {
        if(marked.slice(0,i).some(q=>q[0]===p[0]&&q[1]===p[1]))return;
        svg+=`<circle cx="${sx(p[0])}" cy="${sy(p[1])}" r="5" fill="#8b5cf6"/><text x="${sx(p[0])+8}" y="${sy(p[1])-10}">${escapeText(labels[i] || `(${Number(p[0].toPrecision(3))}, ${Number(p[1].toPrecision(3))})`)}</text>`;
    });
    return svg+'</svg><div class="tutor-legend">'+curves.map((c,i)=>`<span><i style="background:${palette[i%6]}"></i>${escapeText(c.label)}</span>`).join('')+'</div>';
}
