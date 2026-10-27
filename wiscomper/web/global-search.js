const LABELS={feature:'功能',hub:'入口',formula:'公式',project:'作品',learning:'学习资料','course-pack':'课包',sample:'示例'};
export function mountGlobalSearch({api,onAction,notify,canOpen=()=>true}){
  const dialog=document.createElement('dialog');dialog.className='global-search';dialog.id='global-search';dialog.setAttribute('aria-labelledby','gs-title');
  dialog.innerHTML='<header><div><h2 id="gs-title">寻找你的下一步</h2><p>搜索功能、作品、公式和学习资料</p></div><button type="button" class="icon-button gs-close" aria-label="关闭搜索">×</button></header><label class="gs-input"><span aria-hidden="true">⌕</span><input type="search" aria-label="搜索全站" maxlength="200" placeholder="试试：抛体、错题、课包……" autocomplete="off"><kbd>Esc</kbd></label><p class="gs-status" role="status"></p><div class="gs-results"></div><footer>↑ ↓ 选择 · Enter 打开 · Ctrl / ⌘ K 搜索</footer>';
  document.body.append(dialog);const input=dialog.querySelector('input'),results=dialog.querySelector('.gs-results'),status=dialog.querySelector('.gs-status');let timer,controller,sequence=0,disposed=false,selected=-1;
  function choose(index){const rows=[...results.querySelectorAll('button')];if(!rows.length)return;selected=Math.max(0,Math.min(rows.length-1,index));rows.forEach((row,i)=>row.classList.toggle('selected',i===selected));rows[selected].focus({preventScroll:true});rows[selected].scrollIntoView({block:'nearest'});}
  async function search(){clearTimeout(timer);controller?.abort();controller=new AbortController();const token=++sequence;status.textContent='正在查找…';results.replaceChildren();selected=-1;
    try{const data=await api(`/api/search?q=${encodeURIComponent(input.value.trim())}&limit=40`,{signal:controller.signal});if(token!==sequence||disposed||!dialog.open)return;
      status.textContent=data.items.length?`${data.items.length} 项结果`:'暂时没找到，试试更短的关键词。';
      for(const item of data.items){const button=document.createElement('button');button.type='button';button.className='gs-result';const badge=document.createElement('span');badge.className='gs-kind';badge.textContent=LABELS[item.kind]||'内容';const copy=document.createElement('span');copy.className='gs-copy';const title=document.createElement('strong');title.textContent=item.title;const description=document.createElement('small');description.textContent=item.description||'';copy.append(title,description);button.append(badge,copy);
        button.onclick=async()=>{dialog.close();const action=item.action;const name={navigate:action.id,project:'open-project',formula:'open-formula',sample:'sample',learning:'learning-item','course-pack':'course-pack-item'}[action.type];try{if(name)await onAction(name,action.id);}catch(error){notify(error.message,true);}};results.append(button);}
    }catch(error){if(token===sequence&&error.name!=='AbortError'){status.textContent=error.message;const retry=document.createElement('button');retry.className='button secondary';retry.textContent='重新查找';retry.onclick=search;results.append(retry);}}
  }
  function open(){if(disposed||!canOpen())return;dialog.showModal();input.focus();search();}
  input.addEventListener('input',()=>{++sequence;controller?.abort();clearTimeout(timer);results.replaceChildren();selected=-1;status.textContent='正在查找…';timer=setTimeout(search,180);});
  dialog.querySelector('.gs-close').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{++sequence;clearTimeout(timer);controller?.abort();});
  dialog.addEventListener('keydown',event=>{if(event.isComposing||event.keyCode===229)return;if(event.key==='ArrowDown'){event.preventDefault();choose(selected+1);}if(event.key==='ArrowUp'){event.preventDefault();if(selected<=0){selected=-1;input.focus();}else choose(selected-1);}if(event.key==='Enter'&&event.target===input){event.preventDefault();const first=results.querySelector('button');if(first)first.click();else search();}});
  const shortcut=event=>{if(!event.isComposing&&(event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'&&!event.altKey&&!document.querySelector('dialog[open]')){event.preventDefault();open();}};
  document.addEventListener('keydown',shortcut);
  return{open,dispose(){disposed=true;++sequence;clearTimeout(timer);controller?.abort();document.removeEventListener('keydown',shortcut);dialog.remove();}};
}
