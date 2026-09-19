// Share the recovery-safe account check before loading protected background data.
let cached, pending, revision=0;
window.addEventListener('auth-state-change',event=>{
    revision++;pending=null;
    cached=typeof event.detail?.email_verified==='boolean'
        ? {username:event.detail.username,email_verified:event.detail.email_verified} : undefined;
});
export async function canUseAccountFeatures(){
    if(cached)return !cached.username || cached.email_verified!==false;
    if(!pending){
        const run=revision;
        const request=fetch('/api/user/me',{credentials:'include',signal:AbortSignal.timeout(10000)})
            .then(async response=>{
                if(response.status===401)return {username:null};
                if(!response.ok)throw new Error('账户信息暂不可用');
                return response.json();
            }).then(data=>{if(run===revision)cached=data;return data;})
            .catch(()=>null).finally(()=>{if(pending===request)pending=null;});
        pending=request;
    }
    const run=revision,data=await pending;
    if(run!==revision)return canUseAccountFeatures();
    return !!data && (!data.username || data.email_verified!==false);
}
