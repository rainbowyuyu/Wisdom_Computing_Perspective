const pending=new Map();
export function loadScript(url,ready){
    if(ready())return Promise.resolve();
    if(pending.has(url))return pending.get(url);
    const promise=new Promise((resolve,reject)=>{
        const script=document.createElement('script');script.src=url;script.async=true;
        const timer=setTimeout(()=>fail(),15000);
        function fail(){clearTimeout(timer);script.remove();pending.delete(url);reject(new Error('资源加载超时，请重试'));}
        script.onload=()=>{clearTimeout(timer);if(ready())resolve();else fail();};script.onerror=fail;document.head.append(script);
    });
    pending.set(url,promise);return promise;
}
export async function loadGraphAssets(){
    window.process??={env:{NODE_ENV:'production'}};
    await loadScript('https://cdn.jsdelivr.net/npm/three@0.152.0/build/three.min.js',()=>!!window.THREE);
    await loadScript('https://cdn.jsdelivr.net/npm/3d-force-graph@1.79.1/dist/3d-force-graph.min.js',()=>!!window.ForceGraph3D);
}
