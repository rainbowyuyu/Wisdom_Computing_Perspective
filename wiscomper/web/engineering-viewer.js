/* Original Wiscomper engineering mesh plugin; host supplies a verified local mesh URL. */
(function(global){
  'use strict';
  const STYLE='wiscomper-engineering-style';
  function el(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;}
  function style(){if(document.getElementById(STYLE))return;const s=el('style');s.id=STYLE;s.textContent='.wcev{position:relative;border:1px solid #dbe5f1;border-radius:14px;overflow:hidden;background:#f4f7fb;color:#365271;font-family:system-ui,sans-serif}.wcev-header{display:flex;justify-content:space-between;gap:14px;align-items:center;padding:15px 18px;background:#fff;border-bottom:1px solid #e4ebf4}.wcev-title{font-size:14px;font-weight:650}.wcev-tag{font-size:10px;padding:5px 8px;border-radius:5px;background:#eaf1fc;color:#476c9f}.wcev-viewport{height:490px;position:relative;min-width:0}.wcev-viewport canvas{width:100%;height:100%;display:block;touch-action:none}.wcev-loading{position:absolute;inset:0;display:grid;place-items:center;font-size:12px;padding:25px;text-align:center;color:#798ca4}.wcev-tools{display:flex;gap:8px;align-items:center;padding:12px 15px;background:#fff;border-top:1px solid #e3ebf5;flex-wrap:wrap}.wcev-tools button{border:1px solid #d9e4f2;padding:6px 11px;border-radius:7px;background:#f9fbfe;color:#4b6d96;font-size:11px;cursor:pointer}.wcev-tools button[aria-pressed=true]{background:#e8f0fe;border-color:#b9cdee}.wcev-tools span{font-size:10px;color:#8395ad;margin-left:auto}.wcev-note{font-size:11px;line-height:1.8;padding:11px 16px;margin:0;background:#f8fafd;color:#7f90a6}.wcev-error{color:#ad594c;background:#fff4f1}.wcev-coordinate{position:absolute;bottom:13px;left:15px;font-size:10px;line-height:1.7;background:#ffffffdf;border:1px solid #e3eaf3;padding:7px 10px;border-radius:7px;color:#7187a3;pointer-events:none}@media(max-width:600px){.wcev-viewport{height:350px}.wcev-header{align-items:flex-start;padding:13px}.wcev-title{font-size:12px}.wcev-tag{font-size:9px}.wcev-tools span{width:100%;margin:0}.wcev-note{font-size:10px}}';document.head.append(s);}
  function mount(container,{design,meshUrl}={}){
    style();let disposed=false,renderer=null,scene=null,camera=null,mesh=null,geometry=null,material=null,axes=null,observer=null,frame=0,drag=null,wireframe=false;
    const abort=new AbortController(),root=el('section','wcev'),header=el('div','wcev-header'),view=el('div','wcev-viewport'),tools=el('div','wcev-tools');
    header.append(el('span','wcev-title',design?.title||'原工程构型'),el('span','wcev-tag','源文件精确网格 · 未绑定仿真'));
    const loading=el('div','wcev-loading','正在核对并读取原工程网格…');view.append(loading);root.append(header,view,tools);
    const note=el('p','wcev-note','平台本体局部坐标，单位 m、z 轴向上。拖动旋转，滚轮缩放。几何导入不表示工程验收或动力学计算完成。');root.append(note);container.replaceChildren(root);
    const reset=el('button','','适合视图'),front=el('button','','正视'),top=el('button','','俯视'),wire=el('button','','显示网格');
    [reset,front,top,wire].forEach(b=>b.type='button');wire.setAttribute('aria-pressed','false');tools.append(reset,front,top,wire);
    let azimuth=.7,elevation=.3,radius=15,target=null,initialRadius=15;
    function draw(){if(disposed||!renderer||!camera)return;camera.position.set(target.x+radius*Math.cos(elevation)*Math.sin(azimuth),target.y+radius*Math.sin(elevation),target.z+radius*Math.cos(elevation)*Math.cos(azimuth));camera.lookAt(target);renderer.render(scene,camera);}
    function schedule(){if(frame||disposed)return;frame=requestAnimationFrame(()=>{frame=0;draw();});}
    reset.addEventListener('click',()=>{azimuth=.7;elevation=.3;radius=initialRadius;schedule();});
    front.addEventListener('click',()=>{azimuth=0;elevation=0;schedule();});
    top.addEventListener('click',()=>{elevation=Math.PI/2-.01;azimuth=0;schedule();});
    wire.addEventListener('click',()=>{wireframe=!wireframe;wire.setAttribute('aria-pressed',String(wireframe));wire.textContent=wireframe?'隐藏网格':'显示网格';if(material){material.wireframe=wireframe;schedule();}});
    view.addEventListener('pointerdown',event=>{if(!renderer)return;drag={x:event.clientX,y:event.clientY};view.setPointerCapture(event.pointerId);});
    view.addEventListener('pointermove',event=>{if(!drag)return;azimuth-=(event.clientX-drag.x)*.006;elevation=Math.max(-1.5,Math.min(1.5,elevation+(event.clientY-drag.y)*.006));drag={x:event.clientX,y:event.clientY};schedule();});
    const stop=()=>{drag=null;};view.addEventListener('pointerup',stop);view.addEventListener('pointercancel',stop);
    view.addEventListener('wheel',event=>{event.preventDefault();radius=Math.max(initialRadius*.15,Math.min(initialRadius*8,radius*Math.exp(event.deltaY*.001)));schedule();},{passive:false});
    const ready=(async()=>{
      try{
        if(!design?.engineering_mesh||!meshUrl)throw Error('没有声明精确网格来源；请使用明确标注的坐标预览。');
        const url=new URL(meshUrl,location.href);if(url.origin!==location.origin)throw Error('工程网格必须来自当前工作台的验证接口。');
        const [THREE,response]=await Promise.all([import('/vendor/three/three.module.js'),fetch(url.href,{signal:abort.signal,headers:{Accept:'application/json'}})]);
        if(!response.ok)throw Error('网格接口返回 '+response.status);const raw=await response.arrayBuffer();
        if(disposed)return;if(raw.byteLength>32*1024*1024)throw Error('网格超过允许大小。');
        if(global.crypto?.subtle){const bytes=new Uint8Array(await crypto.subtle.digest('SHA-256',raw)),hash=[...bytes].map(x=>x.toString(16).padStart(2,'0')).join('');if(hash!==design.engineering_mesh.source.sha256)throw Error('源网格哈希已变化，请重新导入当前构型。');}
        const data=JSON.parse(new TextDecoder().decode(raw));
        if(data.schema!=='ai-engineer-scene-v1'||data.units?.length!=='m'||!Array.isArray(data.nodes)||!Array.isArray(data.elements)||!Array.isArray(data.types))throw Error('网格契约或单位不匹配。');
        if(data.nodes.length!==design.engineering_mesh.node_count||data.elements.length!==design.engineering_mesh.element_count)throw Error('网格数量与导入记录不一致。');
        if(!data.nodes.length||data.nodes.length>250000||data.elements.length>500000)throw Error('网格规模超出安全显示限制。');
        const low=[Infinity,Infinity,Infinity],high=[-Infinity,-Infinity,-Infinity];
        for(const p of data.nodes){if(!Array.isArray(p)||p.length!==3||!p.every(Number.isFinite))throw Error('网格坐标无效。');for(let j=0;j<3;j++){low[j]=Math.min(low[j],p[j]);high[j]=Math.max(high[j],p[j]);}}
        const center=low.map((v,i)=>(v+high[i])/2),span=Math.max(...low.map((v,i)=>high[i]-v));if(!(span>0))throw Error('网格包围范围无效。');
        const scale=10/span,positions=new Float32Array(data.nodes.length*3);data.nodes.forEach((p,i)=>{positions[i*3]=(p[0]-center[0])*scale;positions[i*3+1]=(p[2]-center[2])*scale;positions[i*3+2]=-(p[1]-center[1])*scale;});
        const indices=[];data.elements.forEach((a,i)=>{if(!Array.isArray(a)||!a.every(v=>Number.isInteger(v)&&v>=0&&v<data.nodes.length))throw Error('网格索引无效。');if(data.types[i]===5&&a.length===3)indices.push(...a);else if(data.types[i]===9&&a.length===4)indices.push(a[0],a[1],a[2],a[0],a[2],a[3]);else throw Error('不支持的表面单元类型。');});
        if(disposed)return;scene=new THREE.Scene();scene.background=new THREE.Color('#f4f7fb');camera=new THREE.PerspectiveCamera(38,1,.01,200);
        renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));renderer.outputColorSpace=THREE.SRGBColorSpace;view.append(renderer.domElement);renderer.domElement.setAttribute('aria-label','原工程 '+data.nodes.length+' 个节点精确三维网格');
        geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));geometry.setIndex(indices);geometry.computeVertexNormals();geometry.computeBoundingSphere();
        material=new THREE.MeshStandardMaterial({color:'#8faed3',metalness:.12,roughness:.61,side:THREE.DoubleSide});mesh=new THREE.Mesh(geometry,material);scene.add(mesh);
        scene.add(new THREE.HemisphereLight('#ffffff','#8b9caf',2.2));const key=new THREE.DirectionalLight('#ffffff',2.4);key.position.set(6,10,7);scene.add(key);const rim=new THREE.DirectionalLight('#d0e1ff',1.6);rim.position.set(-8,4,-5);scene.add(rim);
        axes=new THREE.AxesHelper(1.2);axes.position.set(-5,-4.5,0);scene.add(axes);target=new THREE.Vector3(0,0,0);initialRadius=geometry.boundingSphere.radius/Math.sin(camera.fov*Math.PI/360)*1.14;radius=initialRadius;
        const coordinate=el('div','wcev-coordinate','原坐标：x/y 水平，z ↑；SWL = 0\n仅统一缩放与坐标轴转换，保留全部表面单元');coordinate.style.whiteSpace='pre-line';view.append(coordinate);
        tools.append(el('span','',data.nodes.length.toLocaleString()+' 节点 · '+data.elements.length.toLocaleString()+' 源单元'));
        observer=new ResizeObserver(()=>{if(disposed||!renderer)return;const bounds=view.getBoundingClientRect();renderer.setSize(Math.max(1,bounds.width),Math.max(1,bounds.height),false);camera.aspect=Math.max(1,bounds.width)/Math.max(1,bounds.height);camera.updateProjectionMatrix();schedule();});observer.observe(view);loading.remove();schedule();
      }catch(error){if(disposed)return;loading.classList.add('wcev-error');loading.textContent='精确构型未加载：'+error.message+'。未用示例几何替代。';tools.querySelectorAll('button').forEach(b=>b.disabled=true);}
    })();
    return {ready,dispose(){if(disposed)return;disposed=true;abort.abort();observer?.disconnect();cancelAnimationFrame(frame);geometry?.dispose();material?.dispose();axes?.geometry?.dispose();if(axes?.material)axes.material.dispose();renderer?.dispose();renderer?.forceContextLoss();root.remove();}};
  }
  global.WiscomperEngineeringViewer={mount};
})(window);
