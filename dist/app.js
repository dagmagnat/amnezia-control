'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const en={overview:'Overview',clients:'Clients',profiles:'Connections',import:'Import',settings:'Settings',help:'Help',signIn:'Sign in',localPanel:'Manage VPN on this server',username:'Username',password:'Password',administrator:'Administrator',logout:'Sign out',refresh:'Refresh',createClient:'＋ Create client',online:'Online',usage:'Traffic used',all:'All statuses',enabled:'Allowed',disabled:'Disabled',name:'Name (30 characters max.)',protocol:'Protocol',expires:'Expires',status:'Status',actions:'Actions',noClients:'No clients. Create a VPN profile and your first client.',usageNote:'Traffic is cumulative since accounting started. Online: handshake in the last 3 minutes.',profileNote:'Connections prepared automatically by the panel. Usually, just choose a protocol and generation when creating a client.',newProfile:'＋ VPN profile',profile:'VPN profile',importNote:'Add an existing client .conf from this server here. Moving from another server also requires its original server keys. Import is not needed to create new clients.',language:'Language',currentPassword:'Current password',newPassword:'New password (10+ characters)',save:'Save',access:'Panel address',accessNote:'Change the domain and port using this VPS command. It validates Nginx and preserves the previous configuration:',backup:'Save connections',backupNote:'The SQL backup contains private keys. Keep it in a secure location.',downloadBackup:'Download connection backup',fullBackup:'Full backup of database, keys and configuration:',guide:'1. Click Create client. 2. Choose WireGuard or AmneziaWG and a generation. 3. Download .conf or scan the QR. The server connection is prepared automatically.',relayNote:'Endpoints support IP:port and domain:port, including IDNs. A relay must forward UDP to the profile port. After a DNS change clients may need to reconnect: WireGuard does not guarantee continuous DNS refresh.',quotaNote:'The limit is cumulative RX + TX, not a monthly quota. Enforcement runs every 10 seconds. Extend expiry or increase quota to restore access. Reset clears the recorded usage.',versionsNote:'Generations: 1.0, 1.5, 2.0, 3.0, 3.1. No invented 2.1/2.5 versions. The installed engine validates parameters; a failed profile is not reported as created.',events:'Events',count:'Number of clients',description:'Description',quota:'Quota, GiB (0 = unlimited)',resetUsage:'Reset recorded traffic',download:'Download .conf',delete:'Delete',version:'Generation',subnet:'Subnet',advanced:'AmneziaWG parameters',autoParams:'Empty object = automatic parameters. Changing an existing profile requires reissuing client files.',confirmParams:'Change parameters and reissue client files',connected:'Connected',failed:'Connection failed',edit:'Open',unlimited:'Unlimited',never:'No expiry',expired:'Expired',quotaHit:'Quota reached',saved:'Saved',created:'Created',confirmDelete:'Delete this client and revoke VPN access?',noProfiles:'Create a VPN profile first',noEvents:'No events yet',disconnected:'Interface offline',noKey:'Private key unavailable',qrSecret:'This QR code contains a private key. Do not share it publicly.',obfuscated:'Traffic obfuscation',standard:'Standard protocol',automaticConnection:'Keys, parameters and the server connection are prepared automatically.',vpnHost:'VPN server IP or domain',vpnHostNote:'New connections use this address. The web panel address is a separate setting.',legacyNote:'Old connection without AmneziaWG obfuscation. Create a new AmneziaWG client for the selected generation.',advancedSettings:'Advanced settings',portNote:'Allow this UDP port at your VPS provider:',creating:'Preparing VPN connection…',clientLimits:'Description, traffic and expiry',createAction:'Create'};
const ru={name:'Имя',expires:'Срок действия',import:'Импорт',createAction:'Создать',profiles:'Подключения',backup:'Сохранить подключения',downloadBackup:'Скачать копию подключений',connected:'Подключено',failed:'Нет соединения',edit:'Открыть',unlimited:'Без лимита',never:'Бессрочно',expired:'Срок истёк',quotaHit:'Лимит исчерпан',saved:'Сохранено',created:'Создано',confirmDelete:'Удалить клиента и отозвать доступ к VPN?',noProfiles:'Сначала создайте VPN-профиль',noEvents:'Событий пока нет',disconnected:'Интерфейс не запущен',noKey:'Приватный ключ недоступен',qrSecret:'QR содержит приватный ключ. Не публикуйте его.',legacyNote:'Старое подключение без обфускации AmneziaWG. Для нужной версии создайте нового клиента AmneziaWG.',advancedSettings:'Дополнительные настройки',portNote:'Разрешите этот UDP-порт у провайдера VPS:',creating:'Настраиваю VPN-подключение…'};
Object.assign(en,{startupLoading:'Loading panel…',startupFailed:'Could not load the panel',startupRetry:'Retry',startupTimeout:'The server did not respond in time. Please retry.',quickExpiring:'Expiring',quickDisabled:'Disabled',quickAll:'All',name:'Name',online:'Online',offline:'Offline',expired:'Expired',disabled:'Access denied',expiring:'Expiring within 7 days',allClients:'All clients',sortName:'By name',sortExpiry:'Expiring first',sortNewest:'Newest first',sortTraffic:'By traffic',selectList:'Select all',clearSelection:'Clear selection',deleteSelected:'Delete selected',cancel:'Cancel',bulkDeleteNote:'VPN access for the selected clients will be revoked. A database snapshot with the keys is saved on the server before deletion.',noOnline:'No clients are online right now.',noMatches:'No matching clients.',selected:'Selected',selectClient:'Select client',selectAll:'Select all clients in this list',deleteDone:'Clients deleted',deleteBackup:'Database snapshot saved',accountSettings:'Account settings',vpnHostNote:'A VPN domain must resolve to this VPS IP. This is the default for new VPN profiles. For an existing connection, edit its Endpoint under Connections; device files do not update automatically.',accessNote:'This domain is for signing in to the web panel. It must resolve to this VPS. The selected TCP port remains part of the address; HTTPS is configured separately.'});
Object.assign(ru,{startupLoading:'Загрузка панели…',startupFailed:'Не удалось загрузить панель',startupRetry:'Повторить',startupTimeout:'Сервер не ответил вовремя. Попробуйте ещё раз.',quickExpiring:'Истекают',quickDisabled:'Отключены',quickAll:'Все',online:'В сети',offline:'Не в сети',expired:'Срок закончился',disabled:'Доступ запрещён',expiring:'Истекают за 7 дней',allClients:'Все клиенты',sortName:'По имени',sortExpiry:'Сначала истекающие',sortNewest:'Сначала новые',sortTraffic:'По трафику',selectList:'Выбрать всех',clearSelection:'Снять выбор',deleteSelected:'Удалить выбранных',cancel:'Отмена',noOnline:'Сейчас нет клиентов в сети.',noMatches:'Нет подходящих клиентов.',selected:'Выбрано',selectClient:'Выбрать клиента',selectAll:'Выбрать всех клиентов в этом списке',deleteDone:'Клиентов удалено',deleteBackup:'Копия базы сохранена',accountSettings:'Настройки аккаунта',vpnHostNote:'VPN-домен должен указывать на IP этого VPS. Это адрес для новых VPN-профилей. Для существующего подключения измените Endpoint в разделе «Подключения»; файлы на устройствах автоматически не обновляются.',accessNote:'Этот домен — для входа в веб-панель. Он должен указывать на IP этого VPS. Выбранный TCP-порт остаётся в адресе; HTTPS настраивается отдельно.',lastSeen:'Последняя активность',justNow:'только что',minAgo:'мин. назад',hourAgo:'ч. назад',dayAgo:'дн. назад',neverConnected:'никогда'});
Object.assign(ru,{addVersion:'Добавить версию',downloadVersion:'Версия для скачивания',versionNote:'Старые подключения продолжат работать. Новая версия — дополнительный файл полного VPN для устройства. Лимит трафика и срок остаются общими для всех версий клиента.',versionAllNote:'Если ничего не выделено, применяем ко всем клиентам. Повторное нажатие не создаёт дубликатов.',downloadVersions:'Скачать новые конфигурации ZIP'});
Object.assign(en,{addVersion:'Add generation',downloadVersion:'Download generation',versionNote:'Existing connections keep working. The new generation is an additional full VPN configuration for the device. Traffic quota and expiry are shared across all generations of a client.',versionAllNote:'With no selection, apply to all clients. Repeating this action does not create duplicates.',downloadVersions:'Download new configurations ZIP',lastSeen:'Last seen',justNow:'just now',minAgo:'min ago',hourAgo:'h ago',dayAgo:'d ago',neverConnected:'never connected'});
Object.assign(ru,{qrTitle:'QR подключения',saveQr:'Скачать QR',closeQr:'Закрыть',qrLoading:'Загрузка QR…',qrFailed:'Не удалось загрузить QR. Закройте окно и попробуйте ещё раз.'});
Object.assign(en,{qrTitle:'Connection QR',saveQr:'Download QR',closeQr:'Close',qrLoading:'Loading QR…',qrFailed:'Could not load QR. Close this window and try again.'});
Object.assign(ru,{downloadVersion:'Основная версия и скачивание',preferredVersionNote:'После сохранения эта версия будет основной для скачивания и QR. Старые файлы продолжают работать через исходное подключение.'});
Object.assign(en,{downloadVersion:'Primary and download generation',preferredVersionNote:'Save to use this generation for downloads and QR. Existing files keep using the original connection.'});
Object.assign(ru,{makePrimary:'Сделать основной для скачивания и QR'});Object.assign(en,{makePrimary:'Use as primary for downloads and QR'});
let versionClientId=0;let versionIds=[];
const selectedIds=new Set();let visibleClients=[],pendingDeleteIds=[];
const downloadIcon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12m-4-4 4 4 4-4M5 16v4h14v-4"/></svg>';
const original={}; $$('[data-i18n]').forEach(el=>{original[el.dataset.i18n]=el.textContent;});
let lang=localStorage.getItem('ac-language')||'ru', csrf='', me={}, data={clients:[],profiles:[],events:[],panel:{}}, page='overview', polling=false;
const t=k=>lang==='en'?(en[k]||k):(ru[k]||original[k]||k);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function translate(){document.documentElement.lang=lang; $$('[data-i18n]').forEach(el=>el.textContent=t(el.dataset.i18n)); $('#loginLanguage').value=lang; $('#settingsForm [name=language]').value=lang; $('#pageTitle').textContent=t(page==='servers'?'profiles':page==='imports'?'import':page==='docs'?'help':page);$('#clientForm button.primary').textContent=$('#clientForm').elements.id.value?t('save'):t('createAction');$('#logout').title=t('logout');$('#logout').setAttribute('aria-label',t('logout'));$('#accountSettings').setAttribute('aria-label',t('accountSettings'));$('#selectAll').setAttribute('aria-label',t('selectAll'));$('#search').placeholder=lang==='ru'?'Поиск по имени, описанию, IP':'Search name, description, IP';}
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;setTimeout(()=>$('#toast').hidden=true,4000);}
function error(message){$('#errorBanner').textContent=message;$('#errorBanner').hidden=!message;}
async function api(path,options={}){
 const headers={'X-CSRF-Token':csrf,...options.headers}; if(options.body && !(options.body instanceof FormData))headers['Content-Type']='application/json';
 const response=await fetch('/api/'+path,{...options,headers}); const payload=await response.json().catch(()=>({error:'Invalid server response'}));
 if(!response.ok){if(response.status===401 && path!=='login'){showLogin();}const err=Error(payload.error||response.statusText);err.status=response.status;throw err;}
 if(payload.csrf)csrf=payload.csrf; return payload;
}
function showLogin(){$('#appShell').hidden=true;window.location.replace('/');}
function showApp(){$('#startupScreen').hidden=true;$('#loginScreen').hidden=true;$('#appShell').hidden=false;$('#accountName').textContent=me.user||'';$('#accountAvatar').textContent=Array.from(me.user||'?').slice(0,2).join('').toUpperCase();}
function bytes(value){value=Number(value)||0;let n=0;const units=['B','KiB','MiB','GiB','TiB'];while(value>=1024&&n<4){value/=1024;n++;}return value.toLocaleString(lang,{maximumFractionDigits:n?1:0})+' '+units[n];}
function date(value){if(!value)return t('never');return new Date(Number(value)*1000).toLocaleString(lang,{dateStyle:'short',timeStyle:'short'});}
function dtInput(value){if(!value)return '';const d=new Date(Number(value)*1000);return new Date(d-d.getTimezoneOffset()*60000).toISOString().slice(0,16);}
function choosePage(p){const changed=page!==p;page=p;$('#clientsPage').dataset.mode=p;$$('#nav button').forEach(el=>el.classList.toggle('active',el.dataset.page===p));$('#overviewStats').hidden=p!=='overview';$('#overviewWelcome').hidden=p!=='overview';$('#overviewFilters').hidden=p!=='overview';$('#clientsPage').hidden=!['overview','clients'].includes(p);$('#openCreate').hidden=p==='imports';['servers','imports','settings','docs','statistics'].forEach(n=>$('#'+n+'Page').hidden=p!==n);if(changed){selectedIds.clear();if(['overview','clients'].includes(p)){$('#statusFilter').value=p==='overview'?'online':'all';$('#search').value='';}}translate();renderClients();if(p==='statistics')loadTraffic();}
function render(){
 renderTrafficChoices();$('#navCount').textContent=data.clients.length;$('#totalCount').textContent=data.clients.length;$('#onlineCount').textContent=data.clients.filter(c=>clientState(c)==='online').length;$('#totalUsage').textContent=bytes(data.clients.reduce((sum,c)=>sum+c.used_bytes,0));$('#profileCount').textContent=data.profiles.filter(p=>p.active).length+'/'+data.profiles.length;
 $('#appVersion').textContent=data.version||'';$('#panelAddress').textContent=location.origin;
 if(!$('#accessForm').contains(document.activeElement)){const af=$('#accessForm');af.ip.value=data.panel.ip||((/^\d+\.\d+\.\d+\.\d+$/.test(location.hostname))?location.hostname:'');af.domain.value=data.panel.domain||'';af.port.value=location.port||data.panel.port;}
 if(!$('#settingsForm').contains(document.activeElement))$('#settingsForm').vpn_host.value=data.panel.vpn_host||'';
 const choices=data.profiles.map(p=>`<option value="${p.id}">${esc(p.name)} · ${p.protocol==='wireguard'?'WireGuard':p.version} / ${p.port}</option>`).join('');
 $$('.profile-select').forEach(select=>{const previous=select.value;if(document.activeElement===select)return;select.innerHTML=choices; if([...select.options].some(o=>o.value===previous))select.value=previous;});
 $('#profileList').innerHTML=data.profiles.length?data.profiles.map(p=>`<article class="card profile-card"><span class="pill ${p.active?'':'off'}">${p.active?t('connected'):t('disconnected')}</span><h2>${esc(p.version==='legacy'?'WireGuard / '+(lang==='ru'?'совместимость':'compatibility'):p.name)}</h2>${p.version==='legacy'?`<p class="legacy-note">${t('legacyNote')}</p>`:''}<p>${esc(p.endpoint)}</p><small>${t('portNote')} <strong>${p.port}/UDP</strong></small><details><summary>${t('advancedSettings')}</summary><small>${esc(p.interface)} · ${esc(p.address)}</small><small>Public key: ${esc(p.public_key)}</small><pre>${esc(p.params==='{}'?'—':JSON.stringify(JSON.parse(p.params),null,2))}</pre><button data-edit-profile="${p.id}">${t('edit')}</button> <button type="button" data-check-endpoint="${p.id}">${t('endpointCheck')}</button></details></article>`).join(''):`<p class="empty">${t('noProfiles')}</p>`;
 $('#events').innerHTML=data.events.length?data.events.map(e=>`<div class="event">${esc(eventText(e.message))}<small>${date(e.created_at)}</small></div>`).join(''):`<p>${t('noEvents')}</p>`;
 renderClients(); translate();if(page==='statistics')loadTraffic();
}
function eventText(message){if(lang==='en')return message;if(message.startsWith('Clients deleted: '))return message.replace('Clients deleted: ','Клиенты удалены: ').replace('; backup:','; копия:');const labels={'Client created: ':'Клиент создан: ','Client updated: ':'Клиент изменён: ','Client deleted: ':'Клиент удалён: ','Client imported: ':'Клиент импортирован: ','VPN profile created: ':'Профиль VPN создан: ','VPN profile updated: ':'Профиль VPN изменён: ','Panel settings updated':'Настройки панели сохранены','Panel installed':'Панель установлена','Existing VPN adopted; server keys preserved':'Существующий VPN принят; серверные ключи сохранены'};for(const [key,value] of Object.entries(labels))if(message.startsWith(key))return value+message.slice(key.length);return message;}
function clientState(c){if(!c.enabled)return 'disabled';const now=Date.now()/1000;if(c.blocked_reason==='expired'||c.expires_at&&Number(c.expires_at)<=now)return 'expired';if(c.blocked_reason==='quota'||c.quota_bytes&&c.used_bytes>=c.quota_bytes)return 'quota';return c.online?'online':'offline';}
function matchesStatus(c,filter){const state=clientState(c);if(filter==='all')return true;if(filter==='enabled')return ['online','offline'].includes(state);if(filter==='expiring'){const end=Number(c.expires_at);return c.enabled&&end>Date.now()/1000&&end<=Date.now()/1000+7*86400;}return state===filter;}
function renderSelection(){const selected=visibleClients.filter(c=>selectedIds.has(c.id)).length;$('#selectAll').checked=visibleClients.length>0&&selected===visibleClients.length;$('#selectAll').indeterminate=selected>0&&selected<visibleClients.length;$('#selectAll').disabled=!visibleClients.length;$('#selectVisible').disabled=!visibleClients.length;$('#selectVisible').setAttribute('aria-pressed',String(visibleClients.length>0&&selected===visibleClients.length));$('#selectVisible').title=t('selectAll');$('#addVersion').disabled=!data.clients.length;$('#selectionCount').textContent=selectedIds.size?t('selected')+': '+selectedIds.size:'';$('#clearSelection').hidden=!selectedIds.size;$('#bulkDelete').hidden=!selectedIds.size;$('#openBulkActions').hidden=!selectedIds.size;$$('[data-select-client]').forEach(el=>{el.checked=selectedIds.has(Number(el.dataset.selectClient));el.closest('tr').classList.toggle('selected-row',el.checked);});}
function preferred(c){return (c.versions||[]).find(v=>v.id===(c.download_variant_id||0))||c;}
function renderClients(){
 const q=$('#search').value.toLocaleLowerCase(lang),filter=$('#statusFilter').value,sort=$('#sortOrder').value;
 const known=new Set(data.clients.map(c=>c.id));for(const id of selectedIds)if(!known.has(id))selectedIds.delete(id);
 visibleClients=data.clients.filter(c=>(c.name+' '+c.address+' '+c.description).toLocaleLowerCase(lang).includes(q)&&matchesStatus(c,filter));
 const expiry=c=>Number(c.expires_at)||Infinity;
 visibleClients.sort((a,b)=>{let n=sort==='expiry'?(expiry(a)===expiry(b)?0:expiry(a)-expiry(b)):sort==='newest'?b.created_at-a.created_at:sort==='traffic'?b.used_bytes-a.used_bytes:0;return n||a.name.localeCompare(b.name,lang,{numeric:true})||a.id-b.id;});
 $('#tableCount').textContent=visibleClients.length+' / '+data.clients.length;$('#empty').hidden=visibleClients.length>0;$('#empty').textContent=page==='overview'&&filter==='online'?t('noOnline'):data.clients.length?t('noMatches'):t('noClients');
 $$('#overviewFilters [data-quick-filter]').forEach(el=>{el.setAttribute('aria-pressed',String(el.dataset.quickFilter===filter));el.querySelector('b').textContent=data.clients.filter(c=>matchesStatus(c,el.dataset.quickFilter)).length;});
 $('#clientRows').innerHTML=visibleClients.map(c=>{const status=clientState(c),label=status==='quota'?t('quotaHit'):t(status),main=preferred(c);const lastSeen=c.handshake?(()=>{const now=Date.now()/1000,diff=now-c.handshake;if(diff<60)return t('justNow');if(diff<3600)return Math.floor(diff/60)+' '+t('minAgo');if(diff<86400)return Math.floor(diff/3600)+' '+t('hourAgo');return Math.floor(diff/86400)+' '+t('dayAgo');})():t('neverConnected');return `<tr data-row="${c.id}"><td class="select-cell"><input type="checkbox" data-select-client="${c.id}" aria-label="${t('selectClient')}: ${esc(c.name)}"></td><td class="identity-cell"><button class="client-name" data-client="${c.id}">${esc(c.name)}</button><small class="client-address">${esc(main.address)}</small>${c.description?`<p class="client-description">${esc(c.description)}</p>`:''}</td><td class="protocol-cell">${esc(main.version==='legacy'?'WireGuard / legacy':main.protocol==='wireguard'?'WireGuard':'AWG '+main.version)}${c.versions&&c.versions.length>1?`<small class="additional-versions">+ ${c.versions.filter(v=>v.id!==(c.download_variant_id||0)).map(v=>(v.protocol==='wireguard'?'WG':'AWG '+esc(v.version))).join(' · ')}</small>`:''}</td><td class="traffic-cell">${bytes(c.used_bytes)}<small>${c.quota_bytes?'/ '+bytes(c.quota_bytes):t('unlimited')}</small></td><td class="last-seen-cell"><span class="last-seen ${status==='online'?'online-indicator':''}">${lastSeen}</span></td><td class="expires-cell">${date(c.expires_at)}</td><td class="status-cell"><span class="pill status-${status}">${label}</span></td><td class="actions-cell"><div class="row-actions"><button data-client="${c.id}">${t('edit')}</button>${c.downloadable?`<a class="button icon-button download-link" href="/api/clients/${c.id}/config?variant=${c.download_variant_id||0}" download title="${t('download')}" aria-label="${t('download')}: ${esc(c.name)}">${downloadIcon}</a><button data-qr="${c.id}" aria-label="QR: ${esc(c.name)}">QR</button>`:`<small>${t('noKey')}</small>`}</div></td></tr>`;}).join('');
 renderSelection();
}
function changeFilter(){selectedIds.clear();renderClients();}
function toggleVisible(checked){visibleClients.forEach(c=>checked?selectedIds.add(c.id):selectedIds.delete(c.id));renderSelection();}
$('#selectAll').onchange=e=>toggleVisible(e.target.checked);$('#selectVisible').onclick=()=>toggleVisible(!visibleClients.length||!visibleClients.every(c=>selectedIds.has(c.id)));$('#clearSelection').onclick=()=>{selectedIds.clear();renderSelection();};
$('#clientRows').onchange=e=>{if(!e.target.matches('[data-select-client]'))return;const id=Number(e.target.dataset.selectClient);if(e.target.checked)selectedIds.add(id);else selectedIds.delete(id);renderSelection();};
$('#overviewFilters').onclick=e=>{const button=e.target.closest('[data-quick-filter]');if(!button)return;$('#statusFilter').value=button.dataset.quickFilter;if(button.dataset.quickFilter==='expiring')$('#sortOrder').value='expiry';changeFilter();};
$('#bulkDelete').onclick=()=>{pendingDeleteIds=[...selectedIds];const rows=data.clients.filter(c=>selectedIds.has(c.id));$('#bulkDeleteSummary').textContent=(lang==='ru'?'Будут удалены клиенты: ':'Clients to delete: ')+rows.length;$('#bulkDeleteNames').innerHTML=rows.map(c=>`<div><strong>${esc(c.name)}</strong><small>${esc(c.address)}</small></div>`).join('');$('#bulkDeleteError').textContent='';$('#bulkDeleteDialog').showModal();};
$('#confirmBulkDelete').onclick=async()=>{const button=$('#confirmBulkDelete');button.disabled=true;try{const result=await api('clients/bulk-delete',{method:'POST',body:JSON.stringify({ids:pendingDeleteIds})});selectedIds.clear();$('#bulkDeleteDialog').close();await load();toast(t('deleteDone')+': '+result.deleted+'. '+t('deleteBackup')+'.');}catch(err){$('#bulkDeleteError').textContent=err.message;}finally{button.disabled=false;}};
function startupFailed(err){$('#startupSpinner').hidden=true;$('#startupLabel').textContent=t('startupFailed');$('#startupError').textContent=err.name==='AbortError'?t('startupTimeout'):err.message;$('#retryStartup').hidden=false;}
async function load(signal){if(polling)return false;polling=true;try{data=await api('summary',signal?{signal}:{});error('');$('#connection').textContent=t('connected');render();showApp();return true;}catch(e){if(!$('#startupScreen').hidden)startupFailed(e);else if(!$('#loginScreen').hidden)$('#loginError').textContent=e.message;else{error(e.message);$('#connection').textContent=t('failed');}return false;}finally{polling=false;}}
$('#loginLanguage').onchange=e=>{lang=e.target.value;localStorage.setItem('ac-language',lang);translate();};
$('#loginForm').onsubmit=async e=>{e.preventDefault();const form=new FormData(e.target);try{await api('login',{method:'POST',body:JSON.stringify(Object.fromEntries(form))});me=await api('me');$('#loginError').textContent='';e.target.password.value='';await load();}catch(err){$('#loginError').textContent=err.message;}};
$('#logout').onclick=async()=>{try{await api('logout',{method:'POST'});}finally{showLogin();csrf='';me=await api('me');}};
$('#nav').onclick=e=>{const b=e.target.closest('[data-page]');if(b){choosePage(b.dataset.page);closeMenu();}};$('#refresh').onclick=()=>load();
$('#search').oninput=changeFilter;$('#statusFilter').onchange=changeFilter;$('#sortOrder').onchange=renderClients;$('#accountSettings').onclick=()=>{choosePage('settings');closeMenu();};
$$('[data-close]').forEach(b=>b.onclick=()=>$('#'+b.dataset.close).close());
function showClient(id){const form=$('#clientForm');form.reset();const c=data.clients.find(c=>c.id===id);$('#clientError').textContent='';$('#clientCreation').hidden=!!c;$('#clientExisting').hidden=!c;$('#clientDialogTitle').textContent=c?c.name:t('createClient');form.querySelector('button.primary').textContent=c?t('save'):t('createAction');form.elements.id.value=c?c.id:'';$('#clientLimits').open=false;updateClientProtocol();
 if(c){for(const k of ['name','description','endpoint'])form.elements[k].value=c[k]||'';form.quota_gb.value=c.quota_bytes/1073741824;form.expires_at.value=dtInput(c.expires_at);form.enabled.checked=!!c.enabled;$('#downloadConfig').href='/api/clients/'+id+'/config';$('#downloadConfig').hidden=!c.downloadable;$('#showQr').hidden=!c.downloadable;$('#downloadVersion').innerHTML=(c.versions||[{id:0,protocol:c.protocol,version:c.version,address:c.address}]).map(v=>`<option value="${v.id}">${esc(v.protocol==='wireguard'?'WireGuard':'AmneziaWG '+v.version)} · ${esc(v.address)}</option>`).join('');$('#downloadVersion').value=String(c.download_variant_id||0);$('#downloadVersion').onchange();$('#clientInfo').textContent='Public key: '+c.public_key+'\n'+date(c.created_at);}
 $('#clientDialog').showModal();}
$('#openCreate').onclick=()=>showClient();
function updateClientProtocol(){const value=$('#clientForm input[name=client_protocol]:checked').value;$('#clientVersionField').hidden=value==='wireguard';}
$$('#clientForm input[name=client_protocol]').forEach(el=>el.onchange=updateClientProtocol);
$('#clientRows').onclick=e=>{const open=e.target.closest('[data-client]'),qr=e.target.closest('[data-qr]');if(open)showClient(Number(open.dataset.client));if(qr)showQR(Number(qr.dataset.qr));};
function showQR(id,variant=null){
 const c=data.clients.find(c=>c.id===id);if(!c)return;if(variant===null)variant=c.download_variant_id||0;
 const v=(c.versions||[]).find(v=>v.id===variant)||c;
 const url=`/api/clients/${id}/qr?variant=${variant}`,image=$('#qrImage');
 $('#qrClientLabel').textContent=c.name+' · '+(v.protocol==='wireguard'?'WireGuard':'AmneziaWG '+v.version);
 $('#qrStatus').textContent=t('qrLoading');$('#qrStatus').hidden=false;image.hidden=true;
 image.onload=()=>{image.hidden=false;$('#qrStatus').hidden=true;};
 image.onerror=()=>{image.hidden=true;$('#qrStatus').hidden=false;$('#qrStatus').textContent=t('qrFailed');};
 image.src=url;$('#downloadQr').href=url;$('#downloadQr').download=`client-${id}${variant?'-v'+variant:''}-qr.png`;
 $('#qrDialog').showModal();
}
$('#qrDialog').addEventListener('close',()=>{const image=$('#qrImage');image.onload=null;image.onerror=null;image.removeAttribute('src');image.hidden=true;$('#downloadQr').removeAttribute('href');});
$('#showQr').onclick=()=>showQR(Number($('#clientForm').elements.id.value),Number($('#downloadVersion').value)||0);
$('#clientForm').onsubmit=async e=>{e.preventDefault();const form=e.target,id=form.elements.id.value;const payload={name:form.elements.name.value,description:form.description.value,quota_bytes:Math.round(Number(form.quota_gb.value)*1073741824),expires_at:form.expires_at.value?Math.floor(new Date(form.expires_at.value).getTime()/1000):''};
 if(id)Object.assign(payload,{endpoint:form.endpoint.value,enabled:form.enabled.checked,reset_usage:form.reset_usage.checked,download_variant_id:Number($('#downloadVersion').value)||0});else Object.assign(payload,{protocol:form.querySelector('[name=client_protocol]:checked').value,version:form.client_version.value,count:Number(form.count.value)});
 const button=form.querySelector('button.primary');button.disabled=true;if(!id)$('#clientError').textContent=t('creating');
 try{const created=await api('clients'+(id?'/'+id:''),{method:id?'PATCH':'POST',body:JSON.stringify(payload)});$('#clientDialog').close();await load();toast(id?t('saved'):t('saved')+' · '+created.endpoint+' · '+t('portNote')+' '+created.udp_port+'/UDP');}catch(err){$('#clientError').textContent=err.message;}finally{button.disabled=false;}};
$('#deleteClient').onclick=async()=>{if(!confirm(t('confirmDelete')))return;try{await api('clients/'+$('#clientForm').elements.id.value,{method:'DELETE'});$('#clientDialog').close();await load();}catch(e){$('#clientError').textContent=e.message;}};
function showProfile(id){const form=$('#profileForm');form.reset();const p=data.profiles.find(p=>p.id===id);form.elements.id.value=p?p.id:'';$('#profileError').textContent='';$('#profileCreation').hidden=!!p;$('#profileNetwork').hidden=!!p;$('#confirmParams').hidden=!p;form.params.value=p?p.params:'{}';
 if(p){form.elements.name.value=p.name;form.endpoint.value=p.endpoint;form.protocol.value=p.protocol;form.version.value=p.version;}else{let port=51820;while(data.profiles.some(p=>p.port===port))port++;form.port.value=port;form.subnet.placeholder=`10.77.${Math.max(0,...data.profiles.map(p=>p.id))+1}.0/24`;}
 renderParameters(p?JSON.parse(p.params):{});$('#advanced').hidden=form.protocol.value==='wireguard';$('#profileDialog').showModal();}
function renderParameters(current={}){const v=$('#profileForm').version.value;let names=['Jc','Jmin','Jmax','S1','S2','H1','H2','H3','H4'];if(v!=='1.0')names.push('I1','I2','I3','I4','I5');if(['2.0','3.0','3.1'].includes(v))names.push('S3','S4');if(['3.0','3.1'].includes(v))names.push('HeaderProtectionKey','ContentPaddingAddition');if(v==='3.1')names.push('RekeyAfterTime','RekeyTimeout','RejectAfterTime','KeepaliveTimeout','MaxHandshakeAttempts','RandomTrailers','DisableCookies');$('#parameterFields').innerHTML=names.map(k=>`<label>${k}<input data-param="${k}" value="${esc(current[k]||'')}" placeholder="${lang==='ru'?'Автоматически':'Automatic'}"></label>`).join('');}
function readParameters(){return Object.fromEntries($$('#parameterFields [data-param]').filter(el=>el.value.trim()).map(el=>[el.dataset.param,el.value.trim()]));}
$('#profileForm [name=version]').onchange=()=>renderParameters();
$('#newProfile').onclick=()=>showProfile();
$('#profileList').onclick=event=>{
 const edit=event.target.closest('[data-edit-profile]');
 const check=event.target.closest('[data-check-endpoint]');
 if(edit)showProfile(Number(edit.dataset.editProfile));
 if(check)showEndpointCheck(Number(check.dataset.checkEndpoint));
};
async function showEndpointCheck(id){
 const dialog=$('#endpointCheckDialog'),result=$('#endpointCheckResult');
 result.textContent=t('endpointChecking');
 dialog.showModal();
 try{
  const report=await api('profiles/'+id+'/endpoint-check');
  const resolution=report.addresses.length?report.addresses.join(', '):t('endpointDnsUnavailable');
  const location=report.local_matches===null?'':report.local_matches.length?
    t('endpointLocal')+' '+report.local_matches.join(', '):t('endpointOther');
  const port=report.listen_port===report.advertised_port?
    t('endpointListening')+' '+report.listen_port+'/UDP':t('endpointListenMismatch')+' '+(report.listen_port||'—');
  result.textContent=[report.endpoint,'DNS → '+resolution,location,port,t('endpointScopeNote')].filter(Boolean).join('\n');
 }catch(err){result.textContent=err.message;}
}
$('#profileForm [name=protocol]').onchange=e=>$('#advanced').hidden=e.target.value==='wireguard';
$('#profileForm').onsubmit=async e=>{e.preventDefault();const form=e.target,id=form.elements.id.value;let payload={name:form.elements.name.value,endpoint:form.endpoint.value};try{
 if(!id){Object.assign(payload,{protocol:form.protocol.value,version:form.version.value,port:Number(form.port.value)});if(form.subnet.value)payload.subnet=form.subnet.value;if(form.protocol.value==='amneziawg')payload.params=readParameters();}
 else if(form.confirm_regenerate.checked){payload.params=readParameters();payload.confirm_regenerate=true;}
 const button=form.querySelector('button.primary');button.disabled=true;try{await api('profiles'+(id?'/'+id:''),{method:id?'PATCH':'POST',body:JSON.stringify(payload)});$('#profileDialog').close();await load();toast(t('saved'));}finally{button.disabled=false;}
 }catch(err){$('#profileError').textContent=err.message;}};

$('#settingsForm').onsubmit=async e=>{e.preventDefault();try{const payload=Object.fromEntries(new FormData(e.target));if(!payload.vpn_host)delete payload.vpn_host;await api('settings',{method:'PATCH',body:JSON.stringify(payload)});lang=payload.language;localStorage.setItem('ac-language',lang);e.target.password.value='';e.target.current_password.value='';translate();await load();toast(t('saved'));}catch(err){error(err.message);}};
$('#statusFilter').value='online';translate();choosePage('overview');
async function bootstrap(){
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),15000);$('#startupScreen').hidden=false;$('#loginScreen').hidden=true;$('#appShell').hidden=true;$('#startupSpinner').hidden=false;$('#startupLabel').textContent=t('startupLoading');$('#startupError').textContent='';$('#retryStartup').hidden=true;$('#retryStartup').disabled=true;
 try{me=await api('me',{signal:controller.signal});if(typeof me.authenticated!=='boolean')throw Error('Invalid server response');if(!localStorage.getItem('ac-language')){lang=me.language||'ru';translate();}if(me.authenticated)await load(controller.signal);else showLogin();}
 catch(e){if(e.status===401)showLogin();else startupFailed(e);}
 finally{clearTimeout(timeout);$('#retryStartup').disabled=false;}
}
$('#retryStartup').onclick=bootstrap;
bootstrap();
setInterval(()=>{if(!$('#appShell').hidden&&!document.querySelector('dialog[open]'))load();},15000);

$('#accessForm').onsubmit=async e=>{e.preventDefault();if(!confirm(lang==='ru'?'Изменить адрес панели? Откройте новый TCP-порт в firewall.':'Change the panel address? Open the new TCP port in your firewall.'))return;try{const payload=Object.fromEntries(new FormData(e.target));const result=await api('panel-access',{method:'PATCH',body:JSON.stringify(payload)});toast(result.url);setTimeout(()=>location.href=result.url,2000);}catch(err){error(err.message);}};

$('#mobileLogout').onclick=()=>$('#logout').click();

function closeMenu(){document.body.classList.remove('menu-open');$('#navShade').hidden=true;$('#menuToggle').setAttribute('aria-expanded','false');}
$('#menuToggle').onclick=()=>{const open=!document.body.classList.contains('menu-open');document.body.classList.toggle('menu-open',open);$('#navShade').hidden=!open;$('#menuToggle').setAttribute('aria-expanded',String(open));};
$('#navShade').onclick=closeMenu;
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeMenu();});
const importForm=$('#importForm');let importToken='';
function resetImport(){importToken='';$('#importReview').hidden=true;$('#importReview').replaceChildren();$('#importFields').hidden=false;$('#importPreview').hidden=false;$('#importApply').hidden=true;$('#importBack').hidden=true;$('#importError').textContent='';}
function updateImportMode(){const server=importForm.mode.value==='server';$('#importTarget').hidden=server;$('#importEndpoint').hidden=!server;importForm.endpoint.required=server;$('#importSource').hidden=true;importForm.server_file.replaceChildren();resetImport();}
importForm.mode.onchange=updateImportMode;importForm.files.onchange=()=>{$('#importSource').hidden=true;importForm.server_file.replaceChildren();resetImport();};
$('#importBack').onclick=resetImport;
function importMessage(message){if(lang==='en')return message;const map={
'Files or VPN state changed. Run preview again before importing.':'Файлы или настройки VPN изменились. Повторите проверку перед переносом.',
'No VPN .conf found. A panel database alone does not contain the VPN server configuration.':'В архиве нет VPN-конфигураций .conf. Одной базы панели недостаточно для переноса сервера.',
'Upload exceeds 8 MiB':'Общий размер загрузки превышает 8 МиБ.',
'Archive exceeds import limits':'Архив превышает ограничения распаковки: 24 МиБ / 4096 элементов.',
'Unsafe archive path':'В архиве обнаружен небезопасный путь.',
'Invalid or damaged archive':'Архив повреждён или имеет неверный формат.',
'Select one original server configuration':'Выберите одно серверное подключение из архива, затем повторите проверку.',
'No matching clients found':'Подходящие клиенты не найдены.',
'Original UDP port is already used by another profile':'Исходный UDP-порт уже занят другим подключением.',
'Original UDP port is already listening on this VPS':'Исходный UDP-порт уже занят на этом VPS.',
'Original subnet overlaps an existing profile':'Исходная подсеть пересекается с уже существующим подключением.',
'This server file is standard WireGuard. AmneziaWG obfuscation will not be invented; provide original AmneziaWG client files to check compatibility.':'Серверный файл использует стандартный WireGuard. Для проверки старых клиентов AmneziaWG добавьте их исходные .conf.',
'AntiZapret selective routing and its internal DNS are not restored. Client .conf files are needed to check routes and DNS before switching devices.':'Выборочная маршрутизация AntiZapret и его внутренний DNS не переносятся. Перед переключением устройств нужно проверить DNS и маршруты в клиентском .conf.',
'Endpoint port differs from ListenPort. An external UDP relay must forward it to the original server port.':'Порт внешнего адреса отличается от порта сервера. Потребуется сохранённое перенаправление UDP на исходный порт.',
'An imported client uses a different external UDP port. Preserve its existing relay/NAT mapping before switching devices.':'Клиент использует другой внешний UDP-порт. Сохраните его перенаправление UDP/NAT перед переключением устройств.',
'An imported client uses private DNS. Its DNS service must also be migrated; it is not provided by this import.':'Клиент использует внутренний DNS. Этот DNS-сервис также нужно перенести; импорт его не устанавливает.',
'Legacy AmneziaWG client with S1/S2=0 and H1-H4=1/2/3/4: its original junk/CPS fields are preserved with the standard WireGuard server.':'Старый клиент AmneziaWG совместим со стандартным WireGuard: S1/S2=0, H1–H4=1/2/3/4. Его исходные поля Junk/CPS сохраняются.'
};if(map[message])return map[message];let m;if((m=message.match(/^(\d+) clients have keys but no original/)))return m[1]+' клиентов с ключами, но без исходных .conf. При скачивании будут стандартные DNS и маршруты. Конфигурации на устройствах не меняются.';if((m=message.match(/^(\d+) clients have no private key/)))return m[1]+' клиентов без приватного ключа: доступ сохраняется, но для скачивания и QR нужны их исходные .conf.';if(message.startsWith('Server hooks and network-specific'))return 'Сетевые команды и специальные поля исходного сервера не исполняются: '+message.split(': ').slice(1).join(': ');return message;}
importForm.onsubmit=async e=>{e.preventDefault();const button=$('#importPreview');button.disabled=true;$('#importError').textContent='';try{
 const plan=await api('import/preview',{method:'POST',body:new FormData(importForm)});importToken=plan.token;
 if(plan.sources?.length){const old=importForm.server_file.value;importForm.server_file.innerHTML=plan.sources.map(s=>`<option value="${esc(s)}">${esc(s)}</option>`).join('');if(old)importForm.server_file.value=old;else if(plan.server_file)importForm.server_file.value=plan.server_file;$('#importSource').hidden=importForm.mode.value!=='server';}
 const counts=plan.counts||{}, labels=lang==='ru'?{create:'Новые',complete:'Дополнить',skip:'Уже есть'}:{create:'New',complete:'Complete',skip:'Already present'};
 $('#importReview').innerHTML=`${plan.profile?`<div class="review-profile"><span class="pill">${esc(plan.profile.protocol==='amneziawg'?'AmneziaWG '+plan.profile.version:'WireGuard')}</span><strong>${esc(plan.profile.name)}</strong><small>${esc(plan.profile.address)} · ${plan.profile.port}/UDP</small></div><div class="import-counts">${Object.keys(labels).map(k=>`<div><strong>${counts[k]||0}</strong><small>${labels[k]}</small></div>`).join('')}</div>`:''}${plan.errors.length?`<div class="review-errors">${plan.errors.map(s=>`<p>${esc(importMessage(s))}</p>`).join('')}</div>`:''}${plan.warnings.length?`<details class="review-warnings" open><summary>${lang==='ru'?'Перед переносом':'Before applying'} · ${plan.warnings.length}</summary>${plan.warnings.map(s=>`<p>${esc(importMessage(s))}</p>`).join('')}</details>`:''}${plan.clients.length?`<details class="review-clients"><summary>${lang==='ru'?'Список клиентов':'Client list'} · ${plan.clients.length}</summary><div>${plan.clients.map(c=>`<p><strong>${esc(c.name)}</strong><small>${esc(c.address)} · ${labels[c.action]}</small></p>`).join('')}</div></details>`:''}`;
 $('#importReview').hidden=false;$('#importApply').hidden=!plan.can_apply;$('#importFields').hidden=plan.can_apply;$('#importPreview').hidden=plan.can_apply;$('#importBack').hidden=!plan.can_apply;
 }catch(err){$('#importError').textContent=importMessage(err.message);}finally{button.disabled=false;}};
$('#importApply').onclick=async()=>{const button=$('#importApply');button.disabled=true;try{const payload=new FormData(importForm);payload.set('token',importToken);const result=await api('import/apply',{method:'POST',body:payload});resetImport();importForm.reset();updateImportMode();await load();toast((lang==='ru'?'Перенос завершён. Копия базы: ':'Import complete. Database backup: ')+result.backup);}catch(err){$('#importError').textContent=importMessage(err.message);}finally{button.disabled=false;}};
updateImportMode();

Object.assign(en,{migrationTitle:'Transfer without losing keys',migrationSubtitle:'Inspect first. Transfer the selected connection after review.',importMode:'What to transfer',moveServer:'From another server — backup / server .conf',moveClients:'Client .conf files into an existing connection',migrationEndpoint:'VPN endpoint for downloaded configurations',chooseImport:'Choose a backup and client .conf files',importFormats:'.tar.gz, .zip, .conf · 8 MiB total',sourceServer:'Connection inside the backup',migrationNote:'Original keys are preserved. Archive scripts are never executed. A database snapshot is saved before applying.',backFiles:'← Back to files',checkImport:'Check files',applyImport:'Transfer connections',localWorkspace:'YOUR VPN WORKSPACE',welcomeTitle:'Your connections, under control.',welcomeNote:'Your server. Your clients. One clear workspace.'});
translate();

Object.assign(en,{settingsGeneral:'VPN & account',settingsAccess:'Address & backups'});
$('.settings-tabs').onclick=e=>{const button=e.target.closest('[data-settings-tab]');if(!button)return;$('#settingsPage').dataset.tab=button.dataset.settingsTab;document.querySelector('[data-settings-pane='+button.dataset.settingsTab+']').scrollTop=0;$$('[data-settings-tab]').forEach(el=>el.setAttribute('aria-pressed',String(el===button)));};
translate();

$('#downloadVersion').onchange=()=>{const id=$('#clientForm').elements.id.value;$('#downloadConfig').href='/api/clients/'+id+'/config?variant='+Number($('#downloadVersion').value);const c=data.clients.find(c=>c.id===Number(id)),available=(c.versions||[]).find(v=>v.id===Number($('#downloadVersion').value))?.downloadable??c.downloadable;$('#downloadConfig').hidden=!available;$('#showQr').hidden=!available;};
$('#addVersion').onclick=()=>{versionClientId=0;versionIds=selectedIds.size?[...selectedIds]:data.clients.map(c=>c.id);$('#versionSummary').textContent=(lang==='ru'?'Клиентов: ':'Clients: ')+versionIds.length+(selectedIds.size?'':(lang==='ru'?' · все клиенты':' · all clients'));$('#versionError').classList.remove('success-text');$('#versionError').textContent='';$('#versionBundle').hidden=true;$('#confirmVersion').hidden=false;$('#targetVersion').disabled=false;$('#versionDialog').showModal();};
$('#confirmVersion').onclick=async()=>{const button=$('#confirmVersion'),version=$('#targetVersion').value;button.disabled=true;$('#versionError').classList.remove('success-text');$('#versionError').textContent=t('creating');try{const result=await api('clients/add-version',{method:'POST',body:JSON.stringify({ids:versionIds,version,set_primary:$('#versionPrimary').checked})});await load();if(versionClientId){const c=data.clients.find(c=>c.id===versionClientId),v=c.versions.find(v=>v.protocol==='amneziawg'&&v.version===version);$('#downloadVersion').innerHTML=c.versions.map(v=>`<option value="${v.id}">${esc(v.protocol==='wireguard'?'WireGuard':'AmneziaWG '+v.version)} · ${esc(v.address)}</option>`).join('');if(v)$('#downloadVersion').value=String(v.id);$('#downloadVersion').onchange();}$('#versionError').classList.add('success-text');$('#versionError').textContent=(lang==='ru'?'Добавлено: ':'Added: ')+result.created+(lang==='ru'?' · уже есть: ':' · already available: ')+result.skipped;$('#versionBundle').href='/api/clients/version-bundle?version='+encodeURIComponent(version)+'&ids='+versionIds.join(',');$('#versionBundle').hidden=false;button.hidden=true;$('#targetVersion').disabled=true;}catch(e){$('#versionError').classList.remove('success-text');$('#versionError').textContent=e.message;}finally{button.disabled=false;}};

$('#addClientVersion').onclick=()=>{const id=Number($('#clientForm').elements.id.value);$('#addVersion').onclick();versionClientId=id;versionIds=[id];$('#versionSummary').textContent=data.clients.find(c=>c.id===id).name;};

Object.assign(ru,{vpnHost:'Общий IP или домен VPN',vpnHostNote:'При сохранении адрес применяется ко всем существующим и новым подключениям, скачиваемым файлам и QR. UDP-порты и ключи сохраняются. Старые файлы на устройствах не изменяются: после смены DNS переподключите VPN. Вход в панель настраивается отдельно.'});
Object.assign(en,{vpnHost:'Shared VPN IP or domain',vpnHostNote:'Saving applies this host to existing and new connections, downloads and QR. UDP ports and keys are preserved. Files already on devices are unchanged: reconnect VPN after DNS changes. The panel login address is separate.'});

Object.assign(ru,{statistics:'Статистика',trafficHistory:'Трафик и активность',trafficDay:'24 часа',trafficWeek:'7 дней',trafficMonth:'30 дней',clientUpload:'От клиента (upload)',clientDownload:'К клиенту (download)',clientActivity:'Активные клиенты по времени',clientSpeeds:'Скорость клиентов',currentSpeed:'Сейчас ↑ / ↓',sessionAverage:'Средняя за сессию ↑ / ↓',recordSpeed:'Максимум ↑ / ↓',trafficNote:'История собирается с обновления и хранится 35 дней. Скорости — средние за интервал около 10 секунд, не тест пропускной способности. Сессия оценивается по handshake за последние 3 минуты; после перезапуска панели начинается новая оценка. Пробелы на графике — отсутствие измерений.',historyUpload:'Отправлено клиентами',historyDownload:'Скачано клиентами',currentTotal:'Текущая скорость ↑ / ↓',peakTotal:'Пик суммарной скорости',waitingTraffic:'Ожидание первых измерений…',staleTraffic:'Измерения устарели. VPN продолжает работать.',updatedTraffic:'Обновлено',partialTraffic:'Часть интерфейсов недоступна; данные неполные.'});
Object.assign(en,{statistics:'Statistics',trafficHistory:'Traffic and activity',trafficDay:'24 hours',trafficWeek:'7 days',trafficMonth:'30 days',clientUpload:'Client upload',clientDownload:'Client download',clientActivity:'Active clients over time',clientSpeeds:'Client speeds',currentSpeed:'Current ↑ / ↓',sessionAverage:'Session average ↑ / ↓',recordSpeed:'Maximum ↑ / ↓',trafficNote:'History starts after this update and is retained for 35 days. Speeds are measured averages over about 10 seconds, not a capacity test. Sessions are estimated using handshakes within 3 minutes; panel restarts begin a new estimate. Chart gaps mean missing measurements.',historyUpload:'Client uploads',historyDownload:'Client downloads',currentTotal:'Current speed ↑ / ↓',peakTotal:'Peak combined speed',waitingTraffic:'Waiting for first measurements…',staleTraffic:'Measurements are stale. VPN remains independent.',updatedTraffic:'Updated',partialTraffic:'Some interfaces are unavailable; data is incomplete.'});
const speed=v=>(Math.max(0,Number(v)||0)*8/1e6).toLocaleString(lang,{maximumFractionDigits:2})+' '+(lang==='ru'?'Мбит/с':'Mbps');
const speedPair=(up,down)=>`<span class="speed-pair"><span>↑ ${esc(speed(up))}</span><span>↓ ${esc(speed(down))}</span></span>`;
let trafficPending=false, trafficSequence=0;
function historyChart(target,points,keys,start,end,maxHeight){
 const svg=$(target),w=Math.max(300,svg.getBoundingClientRect().width),h=maxHeight,pad=48,chartW=w-pad*2,chartH=h-32;svg.setAttribute('viewBox',`0 0 ${w} ${h}`);
 const max=Math.max(0,...points.flatMap(p=>keys.map(k=>Number(p[k])||0)));
 if(!max){svg.innerHTML=`<path d="M${pad} ${chartH}H${w-pad}" class="chart-grid"/><text x="${w/2}" y="${chartH/2}" text-anchor="middle">${esc(t(keys[0]==='online_max'?'noOnline':'noPeriodTraffic'))}</text>`;return;}
 const x=ts=>pad+(ts-start)/Math.max(1,end-start)*chartW;
 const y=v=>chartH-(Number(v)||0)/max*(chartH-12);
 let html=[0,0.5,1].map(f=>`<path d="M${pad} ${y(max*f)}H${w-pad}" class="chart-grid"/><text x="2" y="${y(max*f)+4}">${keys[0]==='online_max'?Math.round(max*f):speed(max*f).split(' ')[0]}</text>`).join('');
 keys.forEach((key,ki)=>{let last=null;for(const p of points){const xx=x(p.ts),yy=y(p[key]);const color=ki?'#8bd9db':'#b49cff';html+=`<circle cx="${xx}" cy="${yy}" r="2" fill="${color}"><title>${esc(date(p.ts))}: ${esc(key==='online_max'?p[key]:speed(p[key]))}</title></circle>`;if(last&&p.ts-last.ts<=Number($('#trafficPeriod').value==='day'?300:$('#trafficPeriod').value==='week'?3600:21600)*1.5)html+=`<path d="M${last.x} ${last.y}L${xx} ${yy}" stroke="${color}" stroke-width="2.5" fill="none"/>`;last={x:xx,y:yy,ts:p.ts};}});
 svg.innerHTML=html;
}
async function loadTraffic(){
 if(trafficPending)return;trafficPending=true;const sequence=++trafficSequence,period=$('#trafficPeriod').value,client=$('#trafficClient').value;
 try{const r=await api('traffic?period='+period+(client?'&client_id='+client:''));if(sequence!==trafficSequence||period!==$('#trafficPeriod').value||client!==$('#trafficClient').value)return;
 const stale=r.stale||!r.updated_at,clients=r.clients||[],points=r.points||[];
 $('#trafficUpdated').textContent=r.updated_at?t('updatedTraffic')+': '+date(r.updated_at):t('waitingTraffic');
 $('#trafficError').textContent=stale?(r.updated_at?t('staleTraffic'):t('waitingTraffic')):points.some(p=>p.partial)?t('partialTraffic'):'';
 const up=points.reduce((s,p)=>s+p.upload,0),down=points.reduce((s,p)=>s+p.download,0),peak=Math.max(0,...points.map(p=>p.peak_total));
 const metrics=[[t(client?'singleUpload':'historyUpload'),bytes(up)],[t(client?'singleDownload':'historyDownload'),bytes(down)],[t('currentTotal'),stale?'—':speed(clients.reduce((s,c)=>s+c.upload_bps,0))+' / '+speed(clients.reduce((s,c)=>s+c.download_bps,0))],[t('peakTotal'),speed(peak)]];
 $('#trafficActivity').hidden=!!client;
 $('#onlineTimeMetrics').hidden=!client;
 const person=clients[0];
 $('#onlineTimeMetrics').innerHTML=client&&person?[[t('currentSession'),stale?'—':duration(person.session_seconds)],[t('totalOnline'),duration(person.total_online_seconds)],[t('averageSession'),duration(person.average_session_seconds)],[t('observedSessions'),person.session_count||0]].map(([label,value])=>`<div><small>${esc(label)}</small><strong>${esc(value)}</strong></div>`).join(''):'';
 $('#trafficMetrics').innerHTML=metrics.map(([label,value])=>`<div><small>${esc(label)}</small><strong>${esc(value)}</strong></div>`).join('');
 const chartPoints=points.map(p=>({...p,up:p.upload/p.seconds,down:p.download/p.seconds})),end=Date.now()/1000;
 historyChart('#trafficChart',chartPoints,['up','down'],r.since||end-86400,end,200);if(!client)historyChart('#activityChart',points,['online_max'],r.since||end-86400,end,90);
 $('#trafficChartDates').innerHTML=`<span>${esc(date(r.since||r.started_at))}</span><span>${esc(date(end))}</span>`;
 const onlineOnly=$('#trafficOnlineOnly').checked;
 const shown=onlineOnly?clients.filter(c=>!stale&&c.online):clients;
 $('#trafficClients').innerHTML=shown.length?shown.sort((a,b)=>(b.upload_bps+b.download_bps)-(a.upload_bps+a.download_bps)).map(c=>`<tr><td><button type="button" class="traffic-client-action" data-traffic-client="${c.id}">${esc(c.name)}</button><small>${stale?'—':c.online?t('online'):t('offline')}</small><small>${t('totalOnline')}: ${duration(c.total_online_seconds)}</small></td><td data-label="${esc(t('currentSpeed'))}">${stale?'—':speedPair(c.upload_bps,c.download_bps)}</td><td data-label="${esc(t('sessionAverage'))}">${stale||!c.online?'—':speedPair(c.average_upload_bps,c.average_download_bps)}</td><td data-label="${esc(t('recordSpeed'))}">${speedPair(c.peak_upload_bps,c.peak_download_bps)}</td></tr>`).join(''):`<tr><td colspan="4">${esc(t(onlineOnly&&!stale?'noOnline':'waitingTraffic'))}</td></tr>`;
 }catch(e){$('#trafficError').textContent=e.message;}finally{trafficPending=false;if((period!==$('#trafficPeriod').value||client!==$('#trafficClient').value)&&page==='statistics')loadTraffic();}
}
$('#trafficPeriod').onchange=()=>{trafficSequence++;loadTraffic();};
$('#trafficOnlineOnly').onchange=()=>loadTraffic();

Object.assign(ru,{allTraffic:'Все клиенты',currentSession:'Текущая сессия',totalOnline:'Всего онлайн',averageSession:'Средняя сессия',observedSessions:'Наблюдаемые сессии',trafficNote:'Данные хранятся 35 дней. Скорости — средние за интервал около 10 секунд. Онлайн и сессии оцениваются по handshake за последние 3 минуты. Время учитывается только при работающем сборщике; после перезапуска начинается новый сегмент сессии. Индивидуальная история и общее время собираются с версии 0.6.1. Пробелы на графике — отсутствие измерений.'});
Object.assign(en,{allTraffic:'All clients',currentSession:'Current session',totalOnline:'Total online',averageSession:'Average session',observedSessions:'Observed sessions',trafficNote:'Data is retained for 35 days. Speeds are measured averages over about 10 seconds. Online state and sessions are estimated from handshakes within 3 minutes. Only observed time is counted; a panel restart starts a new session segment. Individual history and total time start with version 0.6.1. Chart gaps mean missing measurements.'});
function duration(seconds){seconds=Math.max(0,Math.floor(Number(seconds)||0));const h=Math.floor(seconds/3600),m=Math.floor(seconds%3600/60),s=seconds%60;return h?(h+(lang==='ru'?' ч ':' h ')+m+(lang==='ru'?' мин':' min')):m?(m+(lang==='ru'?' мин ':' min ')+s+(lang==='ru'?' с':' s')):s+(lang==='ru'?' с':' s');}
function renderTrafficChoices(){const select=$('#trafficClient');if(document.activeElement===select)return;const previous=select.value;select.innerHTML=`<option value="">${esc(t('allTraffic'))}</option>`+data.clients.slice().sort((a,b)=>a.name.localeCompare(b.name,lang)).map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('');select.value=data.clients.some(c=>String(c.id)===previous)?previous:'';}
$('#trafficClient').onchange=()=>{trafficSequence++;loadTraffic();};
function openClientTraffic(id){$('#trafficClient').value=String(id);trafficSequence++;choosePage('statistics');if(page==='statistics')loadTraffic();}
$('#trafficClients').onclick=e=>{const button=e.target.closest('[data-traffic-client]');if(button)openClientTraffic(Number(button.dataset.trafficClient));};
$('#clientStatistics').onclick=()=>{const id=Number($('#clientForm').elements.id.value);$('#clientDialog').close();openClientTraffic(id);};

Object.assign(ru,{singleUpload:'Отправлено клиентом',singleDownload:'Скачано клиентом'});Object.assign(en,{singleUpload:'Client uploaded',singleDownload:'Client downloaded'});

Object.assign(ru,{noPeriodTraffic:'Нет трафика за выбранный период'});Object.assign(en,{noPeriodTraffic:'No traffic in this period'});

// Bulk operations capture explicit IDs; a later filter change cannot broaden them.
Object.assign(ru,{bulkActions:'Действия',bulkSelectionNote:'Изменения применятся только к выбранным клиентам и всем их версиям VPN.',bulkShowNames:'Посмотреть выбранных клиентов',bulkChooseAction:'Что сделать',bulkChoosePlaceholder:'Выберите действие…',bulkEnable:'Включить доступ',bulkDisable:'Отключить доступ',bulkExtend:'Продлить срок',bulkSetExpiry:'Назначить дату окончания',bulkClearExpiry:'Сделать бессрочными',bulkSetQuota:'Изменить лимит трафика',bulkResetUsage:'Обнулить учтённый трафик',bulkDays:'На сколько дней',bulkExpiry:'Новая дата окончания',bulkQuota:'Лимит, ГиБ (0 = без лимита)',bulkApply:'Применить к выбранным',bulkApplying:'Применяем…',bulkUpdated:'Изменено',bulkUnchanged:'Без изменений',bulkRestricted:'Доступ остаётся ограничен',bulkNoSelection:'Сначала выберите клиентов.',bulkNote_enable:'Снимает только ручное отключение. Истёкший срок и исчерпанная квота продолжат ограничивать доступ.',bulkNote_disable:'Доступ будет отключён во всех версиях выбранных клиентов. Ключи и конфигурации сохранятся; включить доступ можно здесь же.',bulkNote_extend:'Дни добавятся к текущему сроку, а если он истёк — к текущему времени. Бессрочные клиенты останутся без изменений. Ручное отключение и квота сохранятся.',bulkNote_set_expiry:'Одна дата окончания будет установлена для всех выбранных клиентов, включая бессрочных. Используется ваше местное время. Ручное отключение и квота сохранятся.',bulkNote_clear_expiry:'Убирает только срок окончания. Ручное отключение и лимит трафика сохранятся.',bulkNote_set_quota:'Новый общий лимит загрузки и отправки заменит прежний у каждого выбранного клиента. Расход не обнуляется. Если лимит уже исчерпан, доступ будет ограничен.',bulkNote_reset_usage:'Учтённый расход станет равен нулю. Это может восстановить доступ по квоте. Срок, ручное отключение и сами лимиты не изменятся.'});
Object.assign(en,{bulkActions:'Actions',bulkSelectionNote:'Changes affect only the selected clients and all their VPN generations.',bulkShowNames:'View selected clients',bulkChooseAction:'Action',bulkChoosePlaceholder:'Choose an action…',bulkEnable:'Enable access',bulkDisable:'Disable access',bulkExtend:'Extend expiry',bulkSetExpiry:'Set expiry date',bulkClearExpiry:'Remove expiry',bulkSetQuota:'Change traffic quota',bulkResetUsage:'Reset recorded traffic',bulkDays:'Number of days',bulkExpiry:'New expiry date',bulkQuota:'Quota, GiB (0 = unlimited)',bulkApply:'Apply to selected',bulkApplying:'Applying…',bulkUpdated:'Updated',bulkUnchanged:'Unchanged',bulkRestricted:'Access remains restricted',bulkNoSelection:'Select clients first.',bulkNote_enable:'Removes manual disabling only. Expiry and exhausted quotas still restrict access.',bulkNote_disable:'Disables all generations of the selected clients. Keys and configurations are preserved; access can be enabled here again.',bulkNote_extend:'Adds days to the current expiry, or to now if already expired. Unlimited clients remain unchanged. Manual disabling and traffic quotas are preserved.',bulkNote_set_expiry:'Sets the same expiry for every selected client, including unlimited clients. Uses your local time. Manual disabling and quotas are preserved.',bulkNote_clear_expiry:'Removes the expiry only. Manual disabling and traffic quotas remain.',bulkNote_set_quota:'Replaces the combined upload and download quota for each selected client. Recorded usage is preserved. Clients already over quota will lose access.',bulkNote_reset_usage:'Sets recorded usage to zero. This may restore access restricted by quota. Expiry, manual disabling and quota values remain unchanged.'});
let pendingBulkIds=[],bulkBusy=false;
function updateBulkActionFields(){const action=$('#bulkActionChoice').value,form=$('#bulkActionForm');for(const [id,name,type] of [['bulkDaysField','days','extend'],['bulkExpiryField','expires_at','set_expiry'],['bulkQuotaField','quota_gb','set_quota']]){const active=action===type;$('#'+id).hidden=!active;form.elements[name].disabled=!active;}
 $('#bulkActionError').textContent='';$('#bulkActionNote').hidden=!action;$('#bulkActionNote').textContent=action?t('bulkNote_'+action):'';$('#confirmBulkAction').disabled=!action;$('#confirmBulkAction').textContent=t('bulkApply');$('#confirmBulkAction').classList.toggle('danger',action==='disable');}
$('#openBulkActions').onclick=()=>{pendingBulkIds=[...selectedIds];if(!pendingBulkIds.length)return;const form=$('#bulkActionForm');form.reset();$('#bulkActionSummary').textContent=t('selected')+': '+pendingBulkIds.length;$('#bulkActionNames').innerHTML=data.clients.filter(c=>selectedIds.has(c.id)).map(c=>`<div><strong>${esc(c.name)}</strong><small>${esc(c.address)}</small></div>`).join('');$('#bulkActionDialog details').open=false;form.expires_at.min=dtInput(Math.ceil(Date.now()/60000)*60);updateBulkActionFields();$('#bulkActionDialog').showModal();};
$('#bulkActionChoice').onchange=updateBulkActionFields;
$('#bulkActionDialog').addEventListener('cancel',e=>{if(bulkBusy)e.preventDefault();});
$('#bulkActionForm').onsubmit=async e=>{e.preventDefault();if(bulkBusy)return;const form=e.target,action=form.elements.action.value,button=$('#confirmBulkAction');if(!pendingBulkIds.length){$('#bulkActionError').textContent=t('bulkNoSelection');return;}const payload={ids:pendingBulkIds,action};if(action==='extend')payload.days=Number(form.days.value);if(action==='set_expiry')payload.expires_at=Math.floor(new Date(form.expires_at.value).getTime()/1000);if(action==='set_quota')payload.quota_bytes=Math.round(Number(form.quota_gb.value)*1073741824);
 bulkBusy=true;button.disabled=true;button.textContent=t('bulkApplying');$('#bulkActionError').textContent='';$$('#bulkActionDialog [data-close]').forEach(b=>b.disabled=true);$('#bulkActionChoice').disabled=true;
 try{const result=await api('clients/bulk-update',{method:'POST',body:JSON.stringify(payload)});selectedIds.clear();$('#bulkActionDialog').close();await load();toast(t('bulkUpdated')+': '+result.updated+(result.unchanged?' · '+t('bulkUnchanged')+': '+result.unchanged:'')+(result.restricted?' · '+t('bulkRestricted')+': '+result.restricted:''));}
 catch(err){$('#bulkActionError').textContent=err.message;}
 finally{bulkBusy=false;button.disabled=false;button.textContent=t('bulkApply');$$('#bulkActionDialog [data-close]').forEach(b=>b.disabled=false);$('#bulkActionChoice').disabled=false;}};

// Optional outbound WARP is independent of local VPN identities.
Object.assign(ru,{settingsWarp:'WARP',warpIntro:'Выход VPN-клиентов в интернет через Cloudflare. Подключение устройств к вашему серверу остаётся прежним.',warpClients:'VPN-клиенты',warpInternet:'Интернет',warpInstall:'Установить WARP',warpAcceptTerms:'Принимаю условия Cloudflare для регистрации этого WARP-клиента.',warpReadTerms:'Прочитать условия',warpRegister:'Зарегистрировать WARP',warpEnable:'Использовать WARP',warpEnableNote:'SSH и панель продолжат использовать обычный маршрут.',warpScope:'Какие подключения',warpSelected:'Выбранные VPN-подключения',warpAll:'Все, включая новые',warpProtocol:'Протокол до Cloudflare',warpAdvanced:'Дополнительно: DNS для WARP',warpDns:'До двух DNS IPv4 через запятую',warpDnsNote:'Пустое поле — текущие upstream DNS сервера. Настройки DNS самого сервера и клиентские конфиги не меняются.',warpPolicy:'При потере WARP выбранный трафик блокируется. Чтобы вернуть прямой выход, выключите WARP и сохраните. Уже открытые соединения могут потребовать переподключения.',warpDocs:'Официальная документация Cloudflare ↗',warpNotInstalled:'Не установлен',warpUnregistered:'Нужна регистрация',warpOff:'Выключен',warpOnline:'Подключён',warpBlocked:'Нет выхода WARP',warpBusy:'Операция выполняется…',warpReady:'Операция завершена.',warpInstallNote:'Установка официального клиента может занять несколько минут. Автоматически WARP не включается.',warpSelectionRequired:'Выберите хотя бы одно VPN-подключение.',warpTermsRequired:'Перед регистрацией примите условия Cloudflare.',warpNoProfiles:'Нет VPN-подключений.',warpStale:'Статус устарел — нажмите «Обновить».',warpConflict:'Запрос уже выполняется. Дождитесь завершения.'});
Object.assign(en,{settingsWarp:'WARP',warpIntro:'Route VPN clients to the Internet through Cloudflare. Device connections to your server stay unchanged.',warpClients:'VPN clients',warpInternet:'Internet',warpInstall:'Install WARP',warpAcceptTerms:'I accept Cloudflare terms to register this WARP client.',warpReadTerms:'Read terms',warpRegister:'Register WARP',warpEnable:'Use WARP',warpEnableNote:'SSH and the panel keep their normal Internet route.',warpScope:'VPN connections',warpSelected:'Selected VPN connections',warpAll:'All, including new connections',warpProtocol:'Protocol to Cloudflare',warpAdvanced:'Advanced: WARP DNS',warpDns:'Up to two IPv4 DNS addresses, separated by commas',warpDnsNote:'Empty uses current server upstream DNS. Host DNS and client configuration files stay unchanged.',warpPolicy:'If WARP fails, selected traffic is blocked. Disable WARP and save to restore direct egress. Existing connections may need to reconnect.',warpDocs:'Official Cloudflare documentation ↗',warpNotInstalled:'Not installed',warpUnregistered:'Registration required',warpOff:'Disabled',warpOnline:'Connected',warpBlocked:'WARP unavailable',warpBusy:'Operation in progress…',warpReady:'Operation completed.',warpInstallNote:'Installing the official client may take a few minutes. WARP is not enabled automatically.',warpSelectionRequired:'Select at least one VPN connection.',warpTermsRequired:'Accept Cloudflare terms before registration.',warpNoProfiles:'No VPN connections.',warpStale:'Status is stale. Select Refresh.',warpConflict:'An operation is already running. Wait for it to finish.'});
let warpData=null,warpDirty=false,warpLoading=false,warpSubmitting=false,warpRevision=0;
function renderWarp(){if(!warpData)return;const w=warpData,busy=warpSubmitting||['queued','running'].includes(w.task.state),cfg=w.config;$('#warpInstall').hidden=w.installed;$('#warpInstall').disabled=busy;$('#warpRefresh').disabled=busy;$('#warpRegister').disabled=busy||!$('#warpTerms').checked;$('#warpRegistration').hidden=!w.installed||w.registered;$('#warpForm').hidden=!w.installed||!w.registered;$('#warpFields').disabled=!w.installed||!w.registered||busy;$('#warpVersion').textContent=w.version||'';
 $('#warpRestore').hidden=!w.restore_pending||cfg.enabled;
 $('#warpApplyRestored').hidden=!w.installed||!w.registered;
 $('#warpApplyRestored').disabled=busy;
 const recent=w.runtime.checked_at&&Date.now()/1000-w.runtime.checked_at<90,key=!w.installed?'warpNotInstalled':!w.registered?'warpUnregistered':!cfg.enabled?'warpOff':!recent?'warpStale':w.runtime.connected?'warpOnline':'warpBlocked';$('#warpBadge').textContent=t(key);$('#warpBadge').className='pill '+(key==='warpOnline'?'status-online':key==='warpBlocked'?'status-disabled':'');
 if(!warpDirty){const f=$('#warpForm');f.enabled.checked=cfg.enabled;f.scope.value=cfg.scope;f.protocol.value=cfg.protocol;f.dns.value=cfg.dns.join(', ');$('#warpProfiles').innerHTML=data.profiles.length?data.profiles.map(p=>`<label><input type="checkbox" name="warpProfile" value="${p.id}" ${cfg.profile_ids.includes(p.id)?'checked':''}><span><strong>${esc(p.name)}</strong><small>${esc(p.interface)} · ${esc(p.protocol==='wireguard'?'WireGuard':'AWG '+p.version)}</small></span></label>`).join(''):`<p>${t('warpNoProfiles')}</p>`;}
 $('#warpProfiles').hidden=$('#warpForm').scope.value==='all';$('#warpMessage').textContent=busy?t('warpBusy')+(w.task.action==='install'?' '+t('warpInstallNote'):''):w.task.state==='done'?t('warpReady'):'';$('#warpError').textContent=w.task.state==='failed'?w.task.error:'';}
async function loadWarp(){
 if(warpLoading||warpSubmitting||$('#appShell').hidden)return;
 const revision=warpRevision;
 warpLoading=true;
 try{
  const result=await api('warp');
  if(revision===warpRevision){warpData=result;renderWarp();}
 }catch(e){if(revision===warpRevision)$('#warpError').textContent=e.message;}
 finally{warpLoading=false;}
}
async function warpAction(action,payload={}){
 if(warpSubmitting)return;
 warpSubmitting=true;
 warpRevision++;
 renderWarp();
 let failure='';
 try{
  await api('warp/'+action,{method:'POST',body:JSON.stringify(payload)});
  if(action==='save')warpDirty=false;
  if(warpData)warpData.task={state:'queued',action};
 }catch(e){failure=e.message;}
 finally{warpSubmitting=false;renderWarp();}
 if(failure){$('#warpError').textContent=failure;return;}
 await loadWarp();
}
$('#warpInstall').onclick=()=>warpAction('install');$('#warpRefresh').onclick=()=>warpData?.config.enabled?warpAction('check'):loadWarp();$('#warpTerms').onchange=()=>renderWarp();$('#warpRegister').onclick=()=>{if(!$('#warpTerms').checked){$('#warpError').textContent=t('warpTermsRequired');return;}warpAction('register',{accept_terms:true});};
$('#warpForm').oninput=()=>{warpDirty=true;$('#warpProfiles').hidden=$('#warpForm').scope.value==='all';};
$('#warpApplyRestored').onclick=()=>{
 if(!warpData?.registered)return;
 const form=$('#warpForm');
 form.enabled.checked=true;
 form.requestSubmit();
};
$('#warpForm').onsubmit=e=>{e.preventDefault();const f=e.target,ids=$$('#warpProfiles input:checked').map(el=>Number(el.value));if(f.enabled.checked&&f.scope.value==='selected'&&!ids.length){$('#warpError').textContent=t('warpSelectionRequired');return;}warpAction('save',{enabled:f.enabled.checked,scope:f.scope.value,profile_ids:ids,protocol:f.protocol.value,dns:f.dns.value.split(',').map(v=>v.trim()).filter(Boolean)});};
$('.settings-tabs').addEventListener('click',e=>{if(e.target.closest('[data-settings-tab="warp"]'))loadWarp();});
setInterval(()=>{if(page==='settings'&&$('#settingsPage').dataset.tab==='warp'&&!$('#appShell').hidden)loadWarp();},4000);

Object.assign(ru, {
 settingsAddress:'Адрес', settingsBackup:'Копии', settingsVpnHeading:'VPN и язык',
 settingsVpnAddressHelp:'Адрес для подключений, новых файлов и QR. Сохранённые на устройствах файлы остаются прежними.',
 warpIntro:'Выход клиентов VPN в интернет через Cloudflare.',
 warpRefreshStatus:'Проверить статус', warpScope:'Профили VPN для WARP',
 warpAll:'Все VPN-профили, включая новые', warpMasque:'MASQUE (по умолчанию)',
 warpPolicy:'При сбое WARP выбранные подключения теряют доступ в интернет. Отключите WARP для прямого выхода.',
 settingsAccountHeading:'Пароль администратора', panelDomain:'Домен', panelTcpPort:'Порт TCP',
 settingsConsole:'Настройка из консоли сервера', portableDownload:'Резервная копия',
 endpointCheck:'Проверить DNS и порт', endpointChecking:'Проверяем адрес и порт…',
 endpointDnsUnavailable:'домен не разрешился', endpointLocal:'IP назначен этому VPS',
 endpointOther:'IP не найден среди адресов VPS. Проверьте DNS или настройки ретранслятора.',
 endpointListening:'Локально слушается', endpointListenMismatch:'Локальный UDP-порт отличается или недоступен',
 endpointScopeNote:'Проверка не измеряет доступность VPN из сети клиента.',
 warpRestorePending:'Настройки WARP перенесены. На новом VPS установите и зарегистрируйте WARP, затем включите перенесённые настройки.',
 warpApplyRestored:'Включить перенесённый WARP',
 portableContents:'Клиенты, их версии, ключи, порты, лимиты и настройки VPN в одном файле.',
 portableDownloadAction:'Скачать копию',
 portableSecret:'Файл содержит приватные ключи. Используйте HTTPS и храните его в защищённом месте.',
 portableOtherCopies:'Другие способы резервного копирования', portableSql:'Скачать прежнюю копию SQL',
 portableRestore:'Восстановление', portableRestoreNote:'Для чистой установки. Выберите файл, чтобы посмотреть, что будет восстановлено.',
 portableFile:'Файл резервной копии', portableReview:'Проверить копию', portableApply:'Восстановить',
 portableWarp:'Параметры WARP перенесутся. На новом сервере зарегистрируйте и включите WARP.',
 portableBusy:'Восстанавливаем подключения…', portableDone:'Восстановлено клиентов',
 portableClean:'Для восстановления нужна чистая установка без клиентов с выключенным WARP.',
 portableVariants:'Дополнительные версии', portablePorts:'Порты UDP',
 portableTarget:'Логин, пароль и адрес панели сохранятся. Убедитесь, что VPN-домен указывает на новый сервер.',
 trafficOnlineOnly:'Только в сети'
});
Object.assign(en, {
 settingsAddress:'Address', settingsBackup:'Backups', settingsVpnHeading:'VPN and language',
 settingsVpnAddressHelp:'Address for connections, new files and QR codes. Files already saved on devices keep their address.',
 warpIntro:'Send VPN clients’ internet traffic through Cloudflare.',
 warpRefreshStatus:'Check status', warpScope:'VPN profiles for WARP',
 warpAll:'All VPN profiles, including new ones', warpMasque:'MASQUE (default)',
 warpPolicy:'If WARP fails, selected connections lose internet access. Disable WARP to restore direct access.',
 settingsAccountHeading:'Administrator password', panelDomain:'Domain', panelTcpPort:'TCP port',
 settingsConsole:'Server console setup', portableDownload:'Backup',
 endpointCheck:'Check DNS and port', endpointChecking:'Checking address and port…',
 endpointDnsUnavailable:'DNS returned no addresses', endpointLocal:'IP assigned to this VPS',
 endpointOther:'No VPS address matches. Check DNS or the relay configuration.',
 endpointListening:'Local listener', endpointListenMismatch:'Local UDP port differs or is unavailable',
 endpointScopeNote:'This check does not measure VPN reachability from a client network.',
 warpRestorePending:'WARP settings were restored. Install and register WARP on this VPS, then enable the restored settings.',
 warpApplyRestored:'Enable restored WARP',
 portableContents:'Clients, variants, keys, ports, limits and VPN settings in one file.',
 portableDownloadAction:'Download backup',
 portableSecret:'The file contains private keys. Use HTTPS and keep it in a secure location.',
 portableOtherCopies:'Other backup options', portableSql:'Download legacy SQL backup',
 portableRestore:'Restore', portableRestoreNote:'For a fresh installation. Select a backup to see what it contains.',
 portableFile:'Backup file', portableReview:'Preview backup', portableApply:'Restore',
 portableWarp:'WARP preferences will be copied. Register and enable WARP on the new server.',
 portableBusy:'Restoring connections…', portableDone:'Clients restored',
 portableClean:'Restore requires a fresh installation with no clients and WARP disabled.',
 portableVariants:'Additional versions', portablePorts:'UDP ports',
 portableTarget:'The destination sign-in and panel address stay in place. Make sure the VPN domain points to this server.',
 trafficOnlineOnly:'Online only'
});

let restoreSelection=null,restoreBusy=false;
const restoreDialog=$('#restoreDialog');
$('#restoreClose').onclick=()=>restoreDialog.close();
restoreDialog.addEventListener('cancel',event=>{if(restoreBusy)event.preventDefault();});
restoreDialog.addEventListener('close',()=>{
 restoreSelection=null;
 $('#restoreApplyForm').reset();
 $('#restoreApplyError').textContent='';
});
$('#restoreFile').onchange=()=>{$('#restorePreviewError').textContent='';};
$('#restorePreviewForm').onsubmit=async event=>{
 event.preventDefault();
 const form=event.currentTarget,file=form.elements.backup.files[0],button=$('#restorePreviewButton');
 if(!file||button.disabled)return;
 button.disabled=true;
 $('#restorePreviewError').textContent='';
 const upload=new FormData();
 upload.set('backup',file);
 try{
  const info=await api('restore/preview',{method:'POST',body:upload});
  if(!info.can_restore){$('#restorePreviewError').textContent=t('portableClean');return;}
  restoreSelection={file,digest:info.digest};
  $('#restoreDetails').textContent=[
   t('clients')+' '+info.clients,t('profiles')+' '+info.profiles,
   t('portableVariants')+' '+info.variants,
   info.ports.length?t('portablePorts')+' '+info.ports.join(', '):''
  ].filter(Boolean).join(' · ');
  $('#restoreDestination').textContent=(info.vpn_host?info.vpn_host+' · ':'')+t('portableTarget');
  $('#restoreWarpNote').hidden=!info.warp_was_enabled;
  restoreDialog.showModal();
 }catch(err){$('#restorePreviewError').textContent=err.message;}
 finally{button.disabled=false;}
};
$('#restoreApplyForm').onsubmit=async event=>{
 event.preventDefault();
 if(!restoreSelection||restoreBusy)return;
 const form=event.currentTarget,button=$('#restoreApplyButton'),upload=new FormData(form);
 upload.set('backup',restoreSelection.file);
 upload.set('digest',restoreSelection.digest);
 form.reset();
 restoreBusy=true;
 button.disabled=true;
 $('#restoreClose').disabled=true;
 $('#restoreApplyError').textContent='';
 button.textContent=t('portableBusy');
 try{
  const result=await api('restore',{method:'POST',body:upload});
  restoreDialog.close();
  $('#restorePreviewForm').reset();
  lang=result.language;
  localStorage.setItem('ac-language',lang);
  await load();
  translate();
  toast(t('portableDone')+' '+result.clients);
 }catch(err){$('#restoreApplyError').textContent=err.message;}
 finally{
  restoreBusy=false;
  button.disabled=false;
  $('#restoreClose').disabled=false;
  button.textContent=t('portableApply');
 }
};

translate();
