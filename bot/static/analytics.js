(() => {
  const label = document.getElementById('live-status');
  let busy = false;
  async function refresh() {
    if (busy || document.hidden) return;
    busy = true;
    try {
      const response = await fetch(location.href, {cache:'no-store'});
      if (!response.ok || new URL(response.url).pathname === '/login') throw new Error('session');
      const page = new DOMParser().parseFromString(await response.text(), 'text/html');
      const incoming = page.getElementById('analytics-content');
      const current = document.getElementById('analytics-content');
      if (!incoming) throw new Error('page');
      if (incoming.innerHTML !== current.innerHTML) current.innerHTML = incoming.innerHTML;
      label.textContent = '● Обновлено ' + new Date().toLocaleTimeString('ru-RU');
    } catch (_) {
      label.textContent = 'Нет обновления — повторяем';
    } finally {busy = false;}
  }
  setInterval(refresh, 10000);
  document.addEventListener('visibilitychange', () => {if (!document.hidden) refresh();});
})();
