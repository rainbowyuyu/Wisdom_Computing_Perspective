// Position bullets from media time so pausing, seeking and playback speed stay in sync.
export function createTeachingDanmaku({getOpacity,getFontSize}) {
    let opts={},canvas,frame=0,observer,items=[],cachedList=null,cachedSize=0,width=0,height=0,player,bindings;
    function schedule(){
        const list=opts.getList?.()||[],size=getFontSize();
        if(list===cachedList&&size===cachedSize)return;cachedList=list;cachedSize=size;
        const ctx=canvas.getContext('2d');ctx.font=`600 ${size}px sans-serif`;
        const lanes=Math.max(1,Math.floor(height/(size+14))),free=Array.from({length:lanes},()=>({entry:-Infinity,end:-Infinity,mode:0}));
        const speed=Math.max(70,width/6);items=[];
        for(const d of [...list].sort((a,b)=>a.time-b.time)){
            const mode=[4,5].includes(Number(d.mode))?Number(d.mode):1;
            const textWidth=ctx.measureText(d.text||'').width,time=Number(d.time);
            const order=Array.from({length:lanes},(_,i)=>mode===4?lanes-i-1:i);
            const lane=order.find(i=>(mode===1&&free[i].mode===1?free[i].entry:free[i].end)<=time);if(lane===undefined)continue;
            const duration=mode===1?(width+textWidth)/speed:3;
            free[lane]={mode,entry:time+(textWidth+28)/speed,end:time+duration};
            items.push({...d,mode,time,lane,textWidth,speed,end:time+duration});
        }
    }
    function draw(){
        if(!canvas||!canvas.isConnected)return;
        const ctx=canvas.getContext('2d');ctx.clearRect(0,0,width,height);
        if(!opts.getVisible?.())return;
        schedule();const t=opts.getTime?.()||0,size=getFontSize();ctx.font=`600 ${size}px sans-serif`;ctx.textBaseline='middle';ctx.lineWidth=3;ctx.strokeStyle='#000a';ctx.globalAlpha=getOpacity();
        for(const item of items){if(item.time>t)break;if(item.end<=t)continue;
            const x=item.mode===1?width-(t-item.time)*item.speed:(width-item.textWidth)/2;
            const y=(item.lane+.5)*(size+14);
            ctx.fillStyle='#'+Math.max(0,Math.min(16777215,Number(item.color??16777215))).toString(16).padStart(6,'0');
            ctx.strokeText(item.text,x,y);ctx.fillText(item.text,x,y);
        }
        ctx.globalAlpha=1;
    }
    function tick(){frame=0;draw();if(player&&!player.paused&&!player.ended&&!document.hidden)frame=requestAnimationFrame(tick);}
    function wake(){if(frame)cancelAnimationFrame(frame);frame=0;tick();}
    function resize(){if(!canvas||!opts.container)return;const r=opts.container.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2);width=r.width;height=r.height;canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);canvas.style.width=width+'px';canvas.style.height=height+'px';canvas.getContext('2d').setTransform(dpr,0,0,dpr,0,0);cachedList=null;draw();}
    function stop(){cancelAnimationFrame(frame);frame=0;observer?.disconnect();bindings?.abort();}
    return {
        init(options){stop();opts=options;canvas=opts.canvas;player=document.getElementById('example-video-player');cachedList=null;bindings=new AbortController();const signal=bindings.signal;
            for(const event of ['play','pause','timeupdate','seeked','ratechange','loadedmetadata'])player?.addEventListener(event,wake,{signal});
            document.addEventListener('visibilitychange',wake,{signal});observer=new ResizeObserver(resize);if(opts.container)observer.observe(opts.container);resize();},
        start:wake,stop,resize,setMask(){},
        setGetList(fn){opts.getList=fn;cachedList=null;wake();},setShownCountRef(){},emit(){cachedList=null;wake();}
    };
}
