const initialClients = [
  {name:'User 12',ip:'10.8.0.12',protocol:'3.1',traffic:'18.4 ГБ',color:'violet'},
  {name:'Дизайн · MacBook',ip:'10.8.0.08',protocol:'3.1',traffic:'42.8 ГБ',color:'cyan'},
  {name:'User 07',ip:'10.8.0.07',protocol:'3.1',traffic:'31.2 ГБ',color:'orange'},
  {name:'Семья · iPhone',ip:'10.8.0.03',protocol:'WG',traffic:'8.7 ГБ',color:'green'}
];
let clients = [...initialClients];
const rows = document.getElementById('clientRows');
const renderClients = (query='') => {
  const filtered = clients.filter(c => `${c.name} ${c.ip}`.toLowerCase().includes(query.toLowerCase()));
  rows.innerHTML = filtered.map((c, i) => `<div class="client-row"><div class="client-name"><div class="client-avatar ${c.color}">${c.name.split(' ').map(x=>x[0]).join('').slice(0,2)}</div><div><strong>${c.name}</strong><span>${c.ip}</span></div></div><div class="protocol"><b>${c.protocol}</b>${c.protocol === 'WG' ? 'WireGuard' : 'AmneziaWG'}</div><div class="traffic">${c.traffic}</div><div class="row-status"><i></i>Активен</div><button class="row-more">•••</button></div>`).join('') || `<div class="empty-row">Ничего не найдено</div>`;
};
renderClients();
document.getElementById('searchInput').addEventListener('input', e => renderClients(e.target.value));
const modal = document.getElementById('createModal');
const openModal = () => { modal.classList.add('open'); modal.setAttribute('aria-hidden','false'); document.getElementById('clientCount').focus(); };
const closeModal = () => { modal.classList.remove('open'); modal.setAttribute('aria-hidden','true'); };
document.getElementById('openCreate').addEventListener('click', openModal);
document.getElementById('closeModal').addEventListener('click', closeModal);
document.getElementById('cancelCreate').addEventListener('click', closeModal);
modal.addEventListener('click', e => { if(e.target === modal) closeModal(); });
document.querySelectorAll('.protocol-card').forEach(card => card.addEventListener('click', () => { document.querySelectorAll('.protocol-card').forEach(c=>c.classList.remove('selected')); card.classList.add('selected'); }));
const toast = document.getElementById('toast');
document.getElementById('createForm').addEventListener('submit', e => {
  e.preventDefault();
  const count = Math.min(25, Math.max(1, Number(document.getElementById('clientCount').value) || 1));
  const prefix = document.getElementById('namePrefix').value.trim() || 'User';
  const protocol = document.querySelector('.protocol-card.selected').dataset.protocol;
  const p = protocol === 'WireGuard' ? 'WG' : '3.1';
  const base = clients.length + 13;
  for(let i=0;i<count;i++) clients.unshift({name:`${prefix} ${String(base+i).padStart(2,'0')}`,ip:`10.8.0.${base+i}`,protocol:p,traffic:'0 Б',color:['violet','cyan','orange','green'][i%4]});
  renderClients(); closeModal();
  document.getElementById('toastText').textContent = `${count} ${count === 1 ? 'клиент добавлен' : 'клиента добавлено'} · ${protocol}`;
  toast.classList.add('show'); setTimeout(() => toast.classList.remove('show'), 4200);
});
document.querySelectorAll('[data-section]').forEach(el => el.addEventListener('click', () => {
  const section = el.dataset.section;
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.section === section));
  const title = {overview:'Обзор',clients:'Клиенты',servers:'Серверы',imports:'Импорт',settings:'Настройки',docs:'Документация'}[section] || 'Обзор';
  document.querySelector('.breadcrumb strong').textContent = title;
  if(section === 'clients') document.querySelector('.clients-panel').scrollIntoView({behavior:'smooth', block:'center'});
  if(section === 'docs') document.querySelector('.tip-row').scrollIntoView({behavior:'smooth', block:'center'});
  if(section === 'imports') { document.getElementById('toastText').textContent = 'Импорт конфигураций скоро будет доступен.'; toast.classList.add('show'); setTimeout(() => toast.classList.remove('show'), 3500); }
}));
document.addEventListener('keydown', e => { if(e.key === 'Escape') closeModal(); if((e.ctrlKey||e.metaKey) && e.key.toLowerCase() === 'k'){e.preventDefault(); openModal();} });
const loginScreen = document.getElementById('loginScreen');
const appShell = document.getElementById('appShell');
const loginForm = document.getElementById('loginForm');
if (sessionStorage.getItem('amnezia-auth') === '1') { loginScreen.style.display = 'none'; appShell.style.display = 'flex'; }
loginForm.addEventListener('submit', e => { e.preventDefault(); const user = document.getElementById('loginUser').value.trim(); const pass = document.getElementById('loginPass').value; if (user === 'admin' && pass === 'amnezia-demo') { sessionStorage.setItem('amnezia-auth','1'); loginScreen.style.display='none'; appShell.style.display='flex'; } else { document.getElementById('loginPass').style.borderColor='#e88b8b'; document.getElementById('loginPass').value=''; document.getElementById('loginPass').placeholder='Неверный пароль'; } });
document.getElementById('togglePass').addEventListener('click', e => { const input=document.getElementById('loginPass'); input.type=input.type==='password'?'text':'password'; e.target.textContent=input.type==='password'?'Показать':'Скрыть'; });
// Production API bridge. The static demo remains usable when opened from file://.
if (location.protocol !== 'file:') {
  const apiJson = (url, options={}) => fetch(url, {headers:{'Content-Type':'application/json'}, ...options}).then(async r => ({ok:r.ok, data:await r.json().catch(()=>({}))}));
  document.addEventListener('submit', async event => {
    if (event.target.id !== 'loginForm') return;
    event.preventDefault(); event.stopImmediatePropagation();
    const {ok} = await apiJson('/api/login', {method:'POST', body:JSON.stringify({username:document.getElementById('loginUser').value, password:document.getElementById('loginPass').value})});
    if (ok) { loginScreen.style.display='none'; appShell.style.display='flex'; sessionStorage.setItem('amnezia-auth','1'); await loadProductionClients(); }
    else { const p=document.getElementById('loginPass'); p.value=''; p.placeholder='Неверный логин или пароль'; p.style.borderColor='#e88b8b'; }
  }, true);
  document.addEventListener('submit', async event => {
    if (event.target.id !== 'createForm') return;
    event.preventDefault(); event.stopImmediatePropagation();
    const selected=document.querySelector('.protocol-card.selected').dataset.protocol;
    const {ok,data}=await apiJson('/api/clients',{method:'POST',body:JSON.stringify({name:document.getElementById('namePrefix').value,description:document.getElementById('description').value,protocol:selected==='WireGuard'?'wireguard':'amneziawg',version:selected==='WireGuard'?'wg':'3.1',traffic_limit:document.getElementById('trafficLimit').value,expires_at:document.getElementById('expiry').value})});
    if(ok){ closeModal(); await loadProductionClients(); document.getElementById('toastText').textContent='Клиент создан на VPS'; toast.classList.add('show'); setTimeout(()=>toast.classList.remove('show'),3500); }
  }, true);
  async function loadProductionClients(){ const r=await fetch('/api/clients'); if(!r.ok)return; const payload=await r.json(); clients=payload.clients.map(c=>({name:c.name,ip:c.address,protocol:c.protocol==='wireguard'?'WG':c.version,traffic:c.traffic_limit||'Без лимита',color:'violet'})); renderClients(); }
  fetch('/api/me').then(r=>r.json()).then(me=>{if(me.authenticated){loginScreen.style.display='none';appShell.style.display='flex';loadProductionClients();}}).catch(()=>{});
}
