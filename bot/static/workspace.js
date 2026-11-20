(() => {
  const messages = document.querySelector('.messages');
  const reply = document.querySelector('.reply textarea');
  if (!messages || !reply) return;
  const toolbar = document.createElement('div');
  toolbar.className = 'thread-tools';
  const search = document.createElement('input');
  search.type = 'search';search.placeholder = 'Поиск в переписке';
  search.setAttribute('aria-label', 'Поиск в переписке');
  const count = document.createElement('span');
  const bottom = document.createElement('button');
  bottom.className = 'ghost';bottom.type = 'button';bottom.textContent = 'К последним ↓';
  bottom.onclick = () => {search.value='';filter();messages.scrollTo({top:messages.scrollHeight,behavior:'smooth'});};
  toolbar.append(search,count,bottom);messages.before(toolbar);
  const filter = () => {
    const query = search.value.trim().toLocaleLowerCase();
    let visible=0;
    messages.querySelectorAll('.message').forEach(message => {
      const match = !query || message.textContent.toLocaleLowerCase().includes(query);
      message.hidden = !match;if(match)visible++;
    });
    count.textContent=query?`Найдено: ${visible}`:'';
  };
  search.addEventListener('input',filter);
  document.addEventListener('invenia:updated',filter);
  const hint=document.createElement('small');
  hint.className='composer-hint';hint.textContent='Ctrl / ⌘ + Enter — отправить';
  reply.after(hint);
  reply.addEventListener('input',()=>{reply.style.height='auto';reply.style.height=Math.min(reply.scrollHeight,140)+'px';});
  // Превращаем ссылки в безопасные кликабельные элементы без innerHTML из текста.
  function linkify() {
    messages.querySelectorAll('.message-text').forEach(element=>{
      if(element.querySelector('a'))return;
      const text=element.textContent;
      const pattern=/https:\/\/[^\s<>]+/g;
      let start=0;const fragment=document.createDocumentFragment();
      for(const match of text.matchAll(pattern)){
        fragment.append(document.createTextNode(text.slice(start,match.index)));
        const link=document.createElement('a');link.href=match[0];link.textContent=match[0];
        link.target='_blank';link.rel='noopener noreferrer';fragment.append(link);
        start=match.index+match[0].length;
      }
      if(start){fragment.append(document.createTextNode(text.slice(start)));element.replaceChildren(fragment);}
    });
  }
  linkify();document.addEventListener('invenia:updated',linkify);
})();
