// Keep the original request and personal-quota receipt throughout recovery.
export function requestFailure(message, details={}, status=0) {
    return Object.assign(new Error(message),{status,code:details?.code,retryable:details?.retryable});
}

export function canRecover(error) {
    if(error?.name==='AbortError'||error?.retryable===false)return false;
    if(error?.status>=400&&error.status<500)return false;
    return !['retry_unavailable','access_denied','email_verification_required','invalid_input'].includes(error?.code);
}

export function recoveryDelay(ms, signal) {
    return new Promise((resolve,reject)=>{
        let timer;
        const cleanup=()=>{clearTimeout(timer);signal?.removeEventListener('abort',abort);};
        const abort=()=>{cleanup();reject(signal.reason||new DOMException('已停止','AbortError'));};
        signal?.addEventListener('abort',abort,{once:true});
        if(signal?.aborted){abort();return;}
        timer=setTimeout(()=>{cleanup();resolve();},ms);
    });
}

export async function recoverRequest(run,{signal,onRetry=()=>{},maxRetries=2,delay=recoveryDelay}={}) {
    for(let attempt=0;;attempt++){
        signal?.throwIfAborted();
        try{return await run(attempt);}
        catch(error){
            if(signal?.aborted||attempt>=maxRetries||!canRecover(error)){
                if(attempt&&error&&typeof error==='object')error.autoRetryCount=attempt;
                throw error;
            }
            onRetry(attempt+1,error);
            // Also gives the server time to finish cleanup and persist its receipt.
            await delay(1000*(attempt+1),signal);
        }
    }
}
