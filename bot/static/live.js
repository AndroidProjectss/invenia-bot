// Обновляем только данные: введённый ответ и положение прокрутки сохраняются.
(() => {
  const status = document.createElement('span');
  status.className = 'live-status';
  status.textContent = '● Обновляется';
  document.querySelector('.topbar').append(status);
  let busy = false;
  async function refresh() {
    if (busy || document.hidden) return;
    busy = true;
    try {
      const url = new URL(location.href);
      const active = document.querySelector('.chat-item.active');
      if (active) url.searchParams.set('chat', new URL(active.href).searchParams.get('chat'));
      const response = await fetch(url, {cache: 'no-store', headers: {'X-Live-Update': '1'}});
      if (!response.ok || new URL(response.url).pathname === '/login') {
        throw new Error('session');
      }
      const next = new DOMParser().parseFromString(await response.text(), 'text/html');
      for (const selector of ['.stats', '.chat-list', '.conversation-head', '.messages']) {
        const current = document.querySelector(selector);
        const incoming = next.querySelector(selector);
        if (!current || !incoming || (current.dataset.serverHtml || current.innerHTML) === incoming.innerHTML) continue;
        const top = current.scrollTop;
        const atBottom = current.scrollHeight - current.clientHeight - top < 80;
        const openDetails = [...current.querySelectorAll('details')].map((detail,index)=>detail.open?index:-1);
        current.innerHTML = incoming.innerHTML;
        current.dataset.serverHtml = incoming.innerHTML;
        current.querySelectorAll('details').forEach((detail,index)=>{detail.open=openDetails.includes(index);});
        current.scrollTop = selector === '.messages' && atBottom ? current.scrollHeight : top;
      }
      // Первый чат появился после открытия пустой панели.
      if (!document.querySelector('.reply') && next.querySelector('.reply')) location.reload();
      status.textContent = '● На связи';
      document.dispatchEvent(new Event('invenia:updated'));
    } catch (_) {
      status.textContent = '● Нет обновлений — повторяем';
    } finally {
      busy = false;
    }
  }
  setInterval(refresh, 2500);
  document.addEventListener('visibilitychange', () => {if (!document.hidden) refresh();});
})();
