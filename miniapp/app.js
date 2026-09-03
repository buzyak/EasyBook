const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

const content = document.getElementById('content');
const nav = document.getElementById('bottomNav');
const toastEl = document.getElementById('toast');
const brandEl = document.getElementById('brand');
const avatarEl = document.getElementById('avatar');
const themeToggleEl = document.getElementById('themeToggle');
const themeMetaEl = document.getElementById('themeMeta');
let manualThemeForSession = null;

function telegramTheme() {
  return tg?.colorScheme === 'dark' ? 'dark' : 'light';
}

function applyTheme(theme, manual = false) {
  const next = theme === 'dark' ? 'dark' : 'light';
  if (manual) manualThemeForSession = next;
  document.documentElement.dataset.theme = next;
  const bg = next === 'dark' ? '#11130f' : '#f6f3ec';
  const header = next === 'dark' ? '#11130f' : '#f6f3ec';
  if (themeMetaEl) themeMetaEl.setAttribute('content', bg);
  try { tg?.setHeaderColor?.(header); tg?.setBackgroundColor?.(bg); } catch (_) {}
}

applyTheme(telegramTheme());
themeToggleEl?.addEventListener('click', () => {
  const current = document.documentElement.dataset.theme || telegramTheme();
  applyTheme(current === 'dark' ? 'light' : 'dark', true);
});
try {
  tg?.onEvent?.('themeChanged', () => {
    if (!manualThemeForSession) applyTheme(telegramTheme());
  });
} catch (_) {}

const state = {
  me: null,
  page: null,
  booking: { serviceIds: [], staffId: null, date: null, slot: null },
};

const WEEKDAYS = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (tg?.initData) headers['X-Telegram-Init-Data'] = tg.initData;
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let text = await response.text();
    try { text = JSON.parse(text).detail || text; } catch (_) {}
    throw new Error(text);
  }
  if (response.status === 204) return null;
  return response.json();
}

function esc(value = '') {
  return String(value).replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}

function toast(message) {
  toastEl.textContent = message;
  toastEl.classList.remove('hidden');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toastEl.classList.add('hidden'), 2600);
}

function money(value) {
  if (value == null || value === '') return '';
  const currency = state.me?.business?.currency;
  return `${Number(value).toLocaleString('ru-RU')}${currency ? ` ${currency}` : ''}`;
}

function businessTime(iso) {
  const tz = state.me?.business?.timezone || 'Europe/Moscow';
  return new Intl.DateTimeFormat('ru-RU', {hour:'2-digit', minute:'2-digit', hourCycle:'h23', timeZone:tz}).format(new Date(iso));
}

function businessDateTime(iso) {
  const tz = state.me?.business?.timezone || 'Europe/Moscow';
  return new Intl.DateTimeFormat('ru-RU', {day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23',timeZone:tz}).format(new Date(iso));
}

function statusLabel(status) {
  return ({
    temporary_hold:'Ожидает подтверждения', pending:'Ожидает подтверждения', confirmed:'Подтверждена',
    completed:'Завершена', cancelled_admin:'Отменена', cancelled_client:'Отменена', expired:'Бронь истекла'
  })[status] || status;
}

function setNav(items, active) {
  nav.innerHTML = items.map(item => `
    <button class="nav-btn ${active === item.id ? 'active' : ''}" data-nav="${item.id}">
      <i>${item.icon}</i><span>${item.label}</span>
    </button>`).join('');
  nav.className = `bottom-nav cols-${items.length}`;
  nav.querySelectorAll('[data-nav]').forEach(btn => btn.onclick = () => route(btn.dataset.nav));
}

function setBack(handler) {
  try {
    tg?.BackButton?.show();
    tg?.BackButton?.offClick?.(state.backHandler);
    state.backHandler = handler;
    tg?.BackButton?.onClick(handler);
  } catch (_) {}
}

function clearBack() {
  try {
    if (state.backHandler) tg?.BackButton?.offClick?.(state.backHandler);
    tg?.BackButton?.hide();
  } catch (_) {}
  state.backHandler = null;
}

function pageTitle(title, subtitle = '') {
  return `<div class="title-row"><h2>${esc(title)}</h2></div>${subtitle ? `<p class="muted">${esc(subtitle)}</p>` : ''}`;
}

function dateYMD(d) {
  return d.toISOString().slice(0,10);
}

function nextDates(count) {
  const tz=state.me?.business?.timezone||'Europe/Moscow';
  const parts=new Intl.DateTimeFormat('en-US',{timeZone:tz,year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const map=Object.fromEntries(parts.map(p=>[p.type,p.value]));
  const base=new Date(Date.UTC(Number(map.year),Number(map.month)-1,Number(map.day),12));
  const out=[];
  for(let i=0;i<count;i++)out.push(new Date(base.getTime()+i*86400000));
  return out;
}

function dayLabel(d) {
  return new Intl.DateTimeFormat('ru-RU',{weekday:'short',timeZone:'UTC'}).format(d);
}

function monthLabel(d) {
  return new Intl.DateTimeFormat('ru-RU',{month:'short',timeZone:'UTC'}).format(d);
}

function timeOptions(selected = '09:00', step = 30) {
  const out = [];
  for (let minutes = 0; minutes < 24 * 60; minutes += step) {
    const hh = String(Math.floor(minutes / 60)).padStart(2, '0');
    const mm = String(minutes % 60).padStart(2, '0');
    const value = `${hh}:${mm}`;
    out.push(`<option value="${value}" ${value === selected ? 'selected' : ''}>${value}</option>`);
  }
  return out.join('');
}

function timezoneLabel(value) {
  if (value === 'Europe/Moscow') return 'Москва';
  return value?.replace('_', ' ') || 'Москва';
}

function setButtonBusy(button, busy, busyText = 'Сохраняем…') {
  if (!button) return;
  if (busy) {
    button.dataset.originalText = button.textContent;
    button.disabled = true;
    button.textContent = busyText;
  } else {
    button.disabled = false;
    if (button.dataset.originalText) button.textContent = button.dataset.originalText;
  }
}

async function init() {
  state.me = await api('/api/me');
  brandEl.textContent = state.me.business.name || 'EasyBook';
  const name = state.me.user.full_name || 'EB';
  avatarEl.textContent = name.split(/\s+/).slice(0,2).map(x=>x[0]).join('').toUpperCase() || 'EB';

  if (!state.me.business.is_onboarded) {
    if (state.me.user.role !== 'owner') return renderNotConfigured();
    return renderSetup();
  }
  route(homeForRole());
}

function homeForRole() {
  if (['owner','admin'].includes(state.me.user.role)) return 'dashboard';
  if (state.me.user.role === 'performer') return 'performer-bookings';
  return 'book';
}

async function route(page) {
  state.page = page;
  clearBack();
  try {
    if (['owner','admin'].includes(state.me.user.role)) {
      setNav([
        {id:'dashboard',icon:'⌂',label:'Главная'},
        {id:'bookings',icon:'▣',label:'Записи'},
        {id:'staff',icon:'◎',label:'Команда'},
        {id:'settings',icon:'⚙',label:'Ещё'},
      ], page);
      if (page === 'dashboard') return renderDashboard();
      if (page === 'bookings') return renderAdminBookings();
      if (page === 'staff') return renderStaff();
      if (page === 'services') return renderServices();
      if (page === 'settings') return renderSettings();
    }
    if (state.me.user.role === 'performer') {
      setNav([
        {id:'performer-bookings',icon:'▣',label:'Записи'},
        {id:'performer-schedule',icon:'◷',label:'График'},
        {id:'my-bookings',icon:'☺',label:'Мои записи'},
      ], page);
      if (page === 'performer-bookings') return renderAdminBookings(true);
      if (page === 'performer-schedule') return renderSchedule(state.me.staff_id, true);
      if (page === 'my-bookings') return renderMyBookings();
    }
    if (state.me.user.role === 'client') {
      setNav([
        {id:'book',icon:'＋',label:'Записаться'},
        {id:'my-bookings',icon:'▣',label:'Мои записи'},
        {id:'profile',icon:'☺',label:'Профиль'},
      ], page);
      if (page === 'book') return renderBookServices();
      if (page === 'my-bookings') return renderMyBookings();
      if (page === 'profile') return renderProfile();
    }
  } catch (err) { renderError(err); }
}

function renderNotConfigured() {
  nav.classList.add('hidden');
  content.innerHTML = `<section class="empty"><div class="emoji">🛠️</div><h3>EasyBook ещё настраивается</h3><p>Владелец пока не завершил первоначальную настройку.</p></section>`;
}

function renderSetup() {
  nav.classList.add('hidden');
  content.innerHTML = `<div class="page">
    <section class="hero card"><span class="badge accent">Первый запуск</span><div><h2>Настроим EasyBook</h2><p class="muted" style="margin-top:8px">Одна установка — один бизнес. Всё остальное добавишь после запуска.</p></div></section>
    <section class="form-card card">
      <form id="setupForm">
        <div class="field"><label>Название</label><input name="name" placeholder="Например, Barber Place" required></div>
        <div class="field"><label>Часовой пояс</label><input name="timezone" value="Europe/Moscow" required></div>
        <div class="field"><label>Валюта, необязательно</label><input name="currency" placeholder="RUB"></div>
        <button class="primary">Создать пространство</button>
      </form>
    </section>
  </div>`;
  document.getElementById('setupForm').onsubmit = async e => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target).entries());
    if (!data.currency) data.currency = null;
    await api('/api/setup',{method:'POST',body:JSON.stringify(data)});
    state.me = await api('/api/me');
    brandEl.textContent = state.me.business.name;
    route('dashboard');
  };
}

async function renderDashboard() {
  const bookings = await api('/api/bookings');
  const now = new Date();
  const todayKey = new Intl.DateTimeFormat('en-CA',{timeZone:state.me.business.timezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
  const today = bookings.filter(b => b.local_start.slice(0,10) === todayKey && !b.status.startsWith('cancelled') && b.status !== 'expired');
  const pending = bookings.filter(b => ['temporary_hold','pending'].includes(b.status));
  content.innerHTML = `<div class="page">
    <section class="hero card">
      <span class="badge accent">Сегодня · ${esc(timezoneLabel(state.me.business.timezone))}</span>
      <div class="hero-row"><div><p class="muted">Записей на сегодня</p><div class="metric">${today.length}</div></div><div class="badge ${pending.length?'warn':''}">${pending.length} ${pending.length===1?'ожидает':'ожидают'}</div></div>
    </section>
    <div class="grid">
      <button class="tile" id="quickServices"><span class="tile-icon">✨</span><div><strong>Услуги</strong><span>Настроить каталог</span></div></button>
      <button class="tile" id="quickStaff"><span class="tile-icon">👤</span><div><strong>Исполнители</strong><span>Команда и графики</span></div></button>
    </div>
    <div class="section-head"><h3>Сегодня</h3><button class="back" id="allBookings">Все записи</button></div>
    <div class="list">${today.length ? today.sort((a,b)=>a.start_at.localeCompare(b.start_at)).map(bookingCard).join('') : emptyHtml('☕','На сегодня записей нет','Свободный день или всё ещё впереди.')}</div>
  </div>`;
  document.getElementById('quickServices').onclick=()=>route('services');
  document.getElementById('quickStaff').onclick=()=>route('staff');
  document.getElementById('allBookings').onclick=()=>route('bookings');
  bindBookingButtons();
}

function bookingCard(b, admin=true) {
  const services=b.services.map(s=>s.name).join(' + ');
  const pending=['temporary_hold','pending'].includes(b.status);
  return `<article class="booking-card card" data-booking="${b.id}">
    <div class="booking-top"><div><div class="booking-time">${businessTime(b.start_at)}</div><div class="muted small">${businessDateTime(b.start_at).split(',')[0]}</div></div><span class="badge status-${b.status}">${statusLabel(b.status)}</span></div>
    <div><strong>${esc(admin ? b.client.full_name : b.staff.display_name)}</strong><p class="muted small" style="margin-top:3px">${esc(services)}${admin ? ` · ${esc(b.staff.display_name)}`:''}</p></div>
    ${admin && b.client.phone ? `<div class="chip">📞 ${esc(b.client.phone)}</div>`:''}
    ${admin && pending ? `<div class="actions"><button class="primary confirm-booking" data-id="${b.id}">Подтвердить</button><button class="secondary cancel-booking" data-id="${b.id}">Отклонить</button></div>`:''}
    ${admin && b.status==='confirmed' ? `<div class="actions"><button class="secondary complete-booking" data-id="${b.id}">Завершить</button><button class="secondary move-booking" data-id="${b.id}">Перенести</button></div><button class="danger-btn cancel-booking" data-id="${b.id}">Отменить запись</button>`:''}
    ${!admin && ['temporary_hold','pending','confirmed'].includes(b.status) ? `<div class="actions">${state.me.business.allow_client_reschedule?`<button class="secondary client-move" data-id="${b.id}">Перенести</button>`:''}${state.me.business.allow_client_cancel?`<button class="danger-btn client-cancel" data-id="${b.id}">Отменить</button>`:''}</div>`:''}
  </article>`;
}

function bindBookingButtons() {
  document.querySelectorAll('.confirm-booking').forEach(x=>x.onclick=async()=>{await api(`/api/bookings/${x.dataset.id}/confirm`,{method:'POST'});toast('Запись подтверждена');route(state.page)});
  document.querySelectorAll('.cancel-booking').forEach(x=>x.onclick=async()=>{if(!confirm('Отменить эту запись?'))return;await api(`/api/bookings/${x.dataset.id}/cancel`,{method:'POST'});toast('Запись отменена');route(state.page)});
  document.querySelectorAll('.complete-booking').forEach(x=>x.onclick=async()=>{await api(`/api/bookings/${x.dataset.id}/complete`,{method:'POST'});toast('Готово');route(state.page)});
  document.querySelectorAll('.move-booking').forEach(x=>x.onclick=async()=>{const all=await api('/api/bookings');const b=all.find(i=>i.id===Number(x.dataset.id));if(b)renderMoveBooking(b,true)});
  document.querySelectorAll('.client-cancel').forEach(x=>x.onclick=async()=>{if(!confirm('Отменить запись?'))return;await api(`/api/my-bookings/${x.dataset.id}/cancel`,{method:'POST'});toast('Запись отменена');renderMyBookings()});
  document.querySelectorAll('.client-move').forEach(x=>x.onclick=async()=>{const all=await api('/api/my-bookings');const b=all.find(i=>i.id===Number(x.dataset.id));if(b)renderMoveBooking(b,false)});
}

async function renderAdminBookings(performer=false) {
  const bookings=await api('/api/bookings');
  const live=bookings.filter(b=>!['cancelled_admin','cancelled_client','expired'].includes(b.status));
  content.innerHTML=`<div class="page">${pageTitle(performer?'Мои рабочие записи':'Записи','Последние и предстоящие бронирования')}
    ${performer?'':'<button class="primary" id="manualBooking">+ Добавить запись вручную</button>'}
    <div class="chips"><span class="chip">Всего: ${bookings.length}</span><span class="chip">Активных: ${live.length}</span></div>
    <div class="list">${bookings.length?bookings.map(b=>bookingCard(b,true)).join(''):emptyHtml('📭','Записей пока нет','Когда клиенты начнут записываться, они появятся здесь.')}</div>
  </div>`;
  bindBookingButtons();
  if(!performer)document.getElementById('manualBooking').onclick=renderManualServices;
}

async function renderStaff() {
  const staff=await api('/api/staff?active_only=false');
  content.innerHTML=`<div class="page">${pageTitle('Исполнители','Каждому — свои услуги, длительность и график')}
    <button class="primary" id="addStaff">+ Добавить исполнителя</button>
    <div class="list">${staff.length?staff.map(s=>`<button class="list-item" data-staff="${s.id}"><div class="list-main"><strong>${esc(s.display_name)}</strong><span>${esc(s.description||'Без описания')}${s.is_active?'':' · скрыт'}</span></div><span class="chev">›</span></button>`).join(''):emptyHtml('👤','Команда пока пустая','Добавь первого исполнителя.')}</div>
    <button class="secondary" id="servicesFromStaff">✨ Перейти к услугам</button>
  </div>`;
  document.getElementById('addStaff').onclick=renderAddStaff;
  document.getElementById('servicesFromStaff').onclick=()=>route('services');
  document.querySelectorAll('[data-staff]').forEach(x=>x.onclick=()=>renderStaffDetail(Number(x.dataset.staff)));
}

function renderAddStaff() {
  setBack(()=>route('staff'));
  content.innerHTML=`<div class="page">${pageTitle('Новый исполнитель','Telegram ID нужен только для личного кабинета сотрудника')}
    <section class="form-card card"><form id="staffForm">
      <div class="field"><label>Имя</label><input name="display_name" required placeholder="Артём"></div>
      <div class="field"><label>Описание</label><input name="description" placeholder="Барбер, мастер маникюра…"></div>
      <div class="field"><label>Telegram ID, необязательно</label><input name="telegram_id" inputmode="numeric" placeholder="123456789"></div>
      <label class="switch-row"><input type="checkbox" name="can_manage_schedule"> Может менять свой график</label>
      <button class="primary">Добавить</button>
    </form></section></div>`;
  document.getElementById('staffForm').onsubmit=async e=>{
    e.preventDefault();const fd=new FormData(e.target);const d=Object.fromEntries(fd.entries());
    d.can_manage_schedule=fd.has('can_manage_schedule');
    if(d.telegram_id)d.telegram_id=Number(d.telegram_id);else delete d.telegram_id;
    await api('/api/staff',{method:'POST',body:JSON.stringify(d)});toast('Исполнитель добавлен');route('staff');
  };
}

async function renderStaffDetail(staffId) {
  const staff=(await api('/api/staff?active_only=false')).find(x=>x.id===staffId);
  if(!staff)return route('staff');
  setBack(()=>route('staff'));
  content.innerHTML=`<div class="page">${pageTitle(staff.display_name,staff.description||'Исполнитель')}
    <div class="grid">
      <button class="tile" id="staffSchedule"><span class="tile-icon">◷</span><div><strong>График</strong><span>Дни и часы</span></div></button>
      <button class="tile" id="staffBlocks"><span class="tile-icon">⊘</span><div><strong>Закрыть время</strong><span>День или интервал</span></div></button>
    </div>
    <section class="form-card card"><h3>Профиль</h3><form id="staffEdit">
      <div class="field"><label>Имя</label><input name="display_name" value="${esc(staff.display_name)}"></div>
      <div class="field"><label>Описание</label><input name="description" value="${esc(staff.description||'')}"></div>
      <label class="switch-row"><input type="checkbox" name="is_active" ${staff.is_active?'checked':''}> Показывать для записи</label>
      <label class="switch-row"><input type="checkbox" name="can_manage_schedule" ${staff.can_manage_schedule?'checked':''}> Может менять свой график</label>
      <button class="primary">Сохранить</button>
    </form></section>
  </div>`;
  document.getElementById('staffSchedule').onclick=()=>renderSchedule(staffId,false);
  document.getElementById('staffBlocks').onclick=()=>renderBlocks(staffId);
  document.getElementById('staffEdit').onsubmit=async e=>{e.preventDefault();const fd=new FormData(e.target);const d=Object.fromEntries(fd.entries());d.is_active=fd.has('is_active');d.can_manage_schedule=fd.has('can_manage_schedule');await api(`/api/staff/${staffId}`,{method:'PATCH',body:JSON.stringify(d)});toast('Сохранено');renderStaffDetail(staffId)};
}

async function renderSchedule(staffId, performerMode=false) {
  const rows=await api(`/api/staff/${staffId}/schedule`);
  const map=Object.fromEntries(rows.map(r=>[r.weekday,r]));
  if(!performerMode)setBack(()=>renderStaffDetail(staffId));
  content.innerHTML=`<div class="page">${pageTitle('Рабочая неделя','Настройте обычный график. Отдельные даты можно изменить ниже.')}
    <section class="panel card"><form id="scheduleForm">
      <div class="schedule-list">${WEEKDAYS.map((name,i)=>{
        const r=map[i]||{};
        const active=!!r.is_working_day;
        const start=(r.start_time?.slice(0,5)||'09:00');
        const end=(r.end_time?.slice(0,5)||'18:00');
        return `<div class="schedule-day">
          <div class="schedule-day-top">
            <span class="schedule-name">${name}</span>
            <label class="toggle">
              <input type="checkbox" data-work="${i}" ${active?'checked':''}>
              <span class="toggle-ui"></span><span class="toggle-label"></span>
            </label>
          </div>
          <div class="schedule-hours" data-hours="${i}">
            <select aria-label="Начало рабочего дня" data-start="${i}" ${active?'':'disabled'}>${timeOptions(start,15)}</select>
            <span class="dash">—</span>
            <select aria-label="Конец рабочего дня" data-end="${i}" ${active?'':'disabled'}>${timeOptions(end,15)}</select>
          </div>
        </div>`;
      }).join('')}</div>
      <button class="primary" style="margin-top:4px">Сохранить график</button>
    </form></section>
    ${performerMode?'':`<button class="secondary" id="exceptionsBtn">Особые дни и выходные</button>`}
  </div>`;
  document.querySelectorAll('[data-work]').forEach(cb=>cb.onchange=()=>{
    const i=cb.dataset.work;
    document.querySelector(`[data-start="${i}"]`).disabled=!cb.checked;
    document.querySelector(`[data-end="${i}"]`).disabled=!cb.checked;
  });
  document.getElementById('scheduleForm').onsubmit=async e=>{
    e.preventDefault();
    const submit=e.submitter;
    const data={rows:WEEKDAYS.map((_,i)=>{
      const active=document.querySelector(`[data-work="${i}"]`).checked;
      return {weekday:i,is_working_day:active,start_time:active?document.querySelector(`[data-start="${i}"]`).value:null,end_time:active?document.querySelector(`[data-end="${i}"]`).value:null};
    })};
    try{setButtonBusy(submit,true,'Сохраняем…');await api(`/api/staff/${staffId}/schedule`,{method:'PUT',body:JSON.stringify(data)});toast('График сохранён');}
    catch(err){toast(err.message)}finally{setButtonBusy(submit,false)}
  };
  if(!performerMode)document.getElementById('exceptionsBtn').onclick=()=>renderExceptions(staffId);
}

async function renderExceptions(staffId) {
  const rows=await api(`/api/staff/${staffId}/exceptions`);
  setBack(()=>renderSchedule(staffId,false));
  content.innerHTML=`<div class="page">${pageTitle('Особые дни','Закрыть дату полностью или задать другой рабочий интервал')}
    <section class="form-card card"><form id="exceptionForm">
      <div class="field"><label>Дата</label><input name="target_date" type="date" required></div>
      <label class="switch-row"><input type="checkbox" name="is_closed" checked id="closedToggle"> Полностью закрыть день</label>
      <div class="inline-form" id="exceptionHours"><div class="field"><label>С</label><select name="start_time" disabled>${timeOptions('09:00',15)}</select></div><div class="field"><label>До</label><select name="end_time" disabled>${timeOptions('18:00',15)}</select></div></div>
      <button class="primary">Добавить исключение</button>
    </form></section>
    <div class="list">${rows.length?rows.map(x=>`<div class="list-item"><div class="list-main"><strong>${x.target_date}</strong><span>${x.is_closed?'Закрыто':`${x.start_time?.slice(0,5)}–${x.end_time?.slice(0,5)}`}</span></div><button class="back del-exception" data-id="${x.id}">Удалить</button></div>`).join(''):emptyHtml('📅','Исключений нет','Работает обычный недельный график.')}</div>
  </div>`;
  const toggle=document.getElementById('closedToggle');toggle.onchange=()=>document.querySelectorAll('#exceptionHours select').forEach(i=>i.disabled=toggle.checked);
  document.getElementById('exceptionForm').onsubmit=async e=>{e.preventDefault();const fd=new FormData(e.target);const closed=fd.has('is_closed');const d={target_date:fd.get('target_date'),is_closed:closed,start_time:closed?null:fd.get('start_time'),end_time:closed?null:fd.get('end_time')};await api(`/api/staff/${staffId}/exceptions`,{method:'POST',body:JSON.stringify(d)});toast('Добавлено');renderExceptions(staffId)};
  document.querySelectorAll('.del-exception').forEach(x=>x.onclick=async()=>{await api(`/api/staff/${staffId}/exceptions/${x.dataset.id}`,{method:'DELETE'});renderExceptions(staffId)});
}

async function renderBlocks(staffId) {
  const rows=await api(`/api/staff/${staffId}/blocks`);
  setBack(()=>renderStaffDetail(staffId));
  content.innerHTML=`<div class="page">${pageTitle('Закрыть время','Подходит для обеда, личного дела или любого перерыва')}
    <section class="form-card card"><form id="blockForm">
      <div class="field"><label>Начало</label><input name="start_at" type="datetime-local" required></div>
      <div class="field"><label>Конец</label><input name="end_at" type="datetime-local" required></div>
      <div class="field"><label>Причина, необязательно</label><input name="reason" placeholder="Обед"></div>
      <button class="primary">Закрыть интервал</button>
    </form></section>
    <div class="list">${rows.length?rows.map(x=>`<div class="list-item"><div class="list-main"><strong>${businessDateTime(x.start_at)} — ${businessTime(x.end_at)}</strong><span>${esc(x.reason||'Закрыто вручную')}</span></div><button class="back del-block" data-id="${x.id}">Открыть</button></div>`).join(''):emptyHtml('◷','Закрытых интервалов нет','Исполнитель доступен по обычному графику.')}</div>
  </div>`;
  document.getElementById('blockForm').onsubmit=async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(e.target).entries());await api(`/api/staff/${staffId}/blocks`,{method:'POST',body:JSON.stringify(d)});toast('Время закрыто');renderBlocks(staffId)};
  document.querySelectorAll('.del-block').forEach(x=>x.onclick=async()=>{await api(`/api/staff/${staffId}/blocks/${x.dataset.id}`,{method:'DELETE'});renderBlocks(staffId)});
}

async function renderServices() {
  const [services,staff]=await Promise.all([api('/api/services?active_only=false'),api('/api/staff')]);
  setBack(()=>route('dashboard'));
  content.innerHTML=`<div class="page">${pageTitle('Услуги','Клиент может выбрать несколько услуг одной записью')}
    <button class="primary" id="addService">+ Добавить услугу</button>
    <div class="list">${services.length?services.map(s=>`<button class="list-item" data-service="${s.id}"><div class="list-main"><strong>${esc(s.name)}</strong><span>${s.default_duration_minutes} мин${s.default_price!=null?` · ${money(s.default_price)}`:''}${s.is_active?'':' · скрыта'}</span></div><span class="chev">›</span></button>`).join(''):emptyHtml('✨','Услуг пока нет','Создай первую услугу и назначь исполнителей.')}</div>
  </div>`;
  document.getElementById('addService').onclick=()=>renderAddService(staff);
  document.querySelectorAll('[data-service]').forEach(x=>x.onclick=()=>renderServiceDetail(Number(x.dataset.service),staff));
}

function renderAddService(staff) {
  setBack(()=>renderServices());
  content.innerHTML=`<div class="page">${pageTitle('Новая услуга','Цена необязательна. Длительность можно переопределить для конкретного исполнителя.')}
    <section class="form-card card"><form id="serviceForm">
      <div class="field"><label>Название</label><input name="name" required placeholder="Стрижка"></div>
      <div class="field"><label>Длительность, минут</label><input name="default_duration_minutes" type="number" min="5" step="5" value="60" required></div>
      <div class="field"><label>Цена, необязательно</label><input name="default_price" type="number" step="0.01"></div>
      <div class="field"><label>Кто выполняет</label><div class="list">${staff.length?staff.map(s=>`<label class="list-item"><div class="list-main"><strong>${esc(s.display_name)}</strong></div><input style="width:auto" type="checkbox" name="staff_id" value="${s.id}"></label>`).join(''):'<p class="muted">Сначала добавь исполнителя.</p>'}</div></div>
      <button class="primary" ${staff.length?'':'disabled'}>Создать услугу</button>
    </form></section></div>`;
  document.getElementById('serviceForm').onsubmit=async e=>{e.preventDefault();const fd=new FormData(e.target);const d={name:fd.get('name'),default_duration_minutes:Number(fd.get('default_duration_minutes')),staff_ids:fd.getAll('staff_id').map(Number)};if(fd.get('default_price'))d.default_price=Number(fd.get('default_price'));await api('/api/services',{method:'POST',body:JSON.stringify(d)});toast('Услуга создана');renderServices()};
}

async function renderServiceDetail(serviceId, staff) {
  const services=await api('/api/services?active_only=false');const service=services.find(x=>x.id===serviceId);if(!service)return renderServices();
  const linked=await api(`/api/services/${serviceId}/staff`);const linkMap=Object.fromEntries(linked.map(x=>[x.staff_id,x]));
  setBack(()=>renderServices());
  content.innerHTML=`<div class="page">${pageTitle(service.name,'Настройки услуги и исполнители')}
    <section class="form-card card"><form id="serviceEdit">
      <div class="field"><label>Название</label><input name="name" value="${esc(service.name)}"></div>
      <div class="field"><label>Базовая длительность</label><input name="default_duration_minutes" type="number" min="5" step="5" value="${service.default_duration_minutes}"></div>
      <div class="field"><label>Базовая цена</label><input name="default_price" type="number" step="0.01" value="${service.default_price??''}"></div>
      <label class="switch-row"><input type="checkbox" name="is_active" ${service.is_active?'checked':''}> Доступна для записи</label>
      <button class="primary">Сохранить</button>
    </form></section>
    <section class="form-card card"><h3>Исполнители</h3><p class="muted small">Если поля пустые — используются базовые длительность и цена.</p><form id="linksForm">
      ${staff.map(s=>{const l=linkMap[s.id];return `<div class="panel" style="background:var(--surface-2)"><label class="switch-row"><input type="checkbox" data-link="${s.id}" ${l?'checked':''}><strong>${esc(s.display_name)}</strong></label><div class="inline-form" style="margin-top:9px"><input type="number" min="5" step="5" data-duration="${s.id}" placeholder="${service.default_duration_minutes} мин" value="${l?.duration_minutes??''}"><input type="number" step="0.01" data-price="${s.id}" placeholder="${service.default_price??'Цена'}" value="${l?.price??''}"></div></div>`}).join('')}
      <button class="primary">Сохранить исполнителей</button>
    </form></section>
  </div>`;
  document.getElementById('serviceEdit').onsubmit=async e=>{e.preventDefault();const fd=new FormData(e.target);const d={name:fd.get('name'),default_duration_minutes:Number(fd.get('default_duration_minutes')),default_price:fd.get('default_price')?Number(fd.get('default_price')):null,is_active:fd.has('is_active')};await api(`/api/services/${serviceId}`,{method:'PATCH',body:JSON.stringify(d)});toast('Сохранено');renderServiceDetail(serviceId,staff)};
  document.getElementById('linksForm').onsubmit=async e=>{e.preventDefault();const links=staff.filter(s=>document.querySelector(`[data-link="${s.id}"]`).checked).map(s=>{const dv=document.querySelector(`[data-duration="${s.id}"]`).value;const pv=document.querySelector(`[data-price="${s.id}"]`).value;return {staff_id:s.id,duration_minutes:dv?Number(dv):null,price:pv?Number(pv):null,is_active:true}});await api(`/api/services/${serviceId}/staff`,{method:'PUT',body:JSON.stringify({links})});toast('Исполнители обновлены');renderServiceDetail(serviceId,staff)};
}

async function renderSettings() {
  const b=state.me.business;
  content.innerHTML=`<div class="page">${pageTitle('Настройки','Правила записи для всего бизнеса')}
    <button class="secondary" id="settingsServices">✨ Услуги</button>
    <section class="form-card card"><form id="settingsForm">
      <div class="field"><label>Название</label><input name="name" value="${esc(b.name)}"></div>
      <div class="field"><label>Часовой пояс</label><input name="timezone" value="${esc(b.timezone)}"><span class="muted small">По умолчанию — Москва (Europe/Moscow)</span></div>
      <div class="field"><label>Валюта</label><input name="currency" value="${esc(b.currency||'')}"></div>
      <div class="field"><label>Подтверждение записи</label><select name="booking_confirmation_mode"><option value="manual" ${b.booking_confirmation_mode==='manual'?'selected':''}>Администратором</option><option value="auto" ${b.booking_confirmation_mode==='auto'?'selected':''}>Автоматически</option></select></div>
      <div class="field"><label>Временная бронь, минут</label><input name="hold_minutes" type="number" min="1" value="${b.hold_minutes}"></div>
      <div class="field"><label>Шаг начала записи, минут</label><input name="slot_step_minutes" type="number" min="5" step="5" value="${b.slot_step_minutes}"></div>
      <div class="field"><label>Запись вперёд, дней</label><input name="booking_horizon_days" type="number" min="1" value="${b.booking_horizon_days}"></div>
      <label class="switch-row"><input type="checkbox" name="allow_client_cancel" ${b.allow_client_cancel?'checked':''}> Клиент может отменять запись</label>
      <div class="field"><label>Отмена не позднее, часов</label><input name="cancel_before_hours" type="number" min="0" value="${b.cancel_before_hours}"></div>
      <label class="switch-row"><input type="checkbox" name="allow_client_reschedule" ${b.allow_client_reschedule?'checked':''}> Клиент может переносить запись</label>
      <div class="field"><label>Перенос не позднее, часов</label><input name="reschedule_before_hours" type="number" min="0" value="${b.reschedule_before_hours}"></div>
      <button class="primary">Сохранить настройки</button>
    </form></section>
  </div>`;
  document.getElementById('settingsServices').onclick=()=>route('services');
  document.getElementById('settingsForm').onsubmit=async e=>{e.preventDefault();const fd=new FormData(e.target);const d=Object.fromEntries(fd.entries());['hold_minutes','slot_step_minutes','booking_horizon_days','cancel_before_hours','reschedule_before_hours'].forEach(k=>d[k]=Number(d[k]));d.allow_client_cancel=fd.has('allow_client_cancel');d.allow_client_reschedule=fd.has('allow_client_reschedule');if(!d.currency)d.currency=null;await api('/api/business/settings',{method:'PATCH',body:JSON.stringify(d)});state.me=await api('/api/me');brandEl.textContent=state.me.business.name;toast('Настройки сохранены');renderSettings()};
}

async function renderBookServices() {
  state.booking={serviceIds:[],staffId:null,date:null,slot:null};
  const services=await api('/api/services');
  content.innerHTML=`<div class="page">${pageTitle('Выберите услуги','Можно выбрать несколько услуг для одного визита')}
    <div class="list" id="serviceList">${services.length?services.map(s=>`<button class="list-item service-pick" data-id="${s.id}"><span class="check">✓</span><div class="list-main"><strong>${esc(s.name)}</strong><span>${s.default_duration_minutes} мин${s.default_price!=null?` · от ${money(s.default_price)}`:''}</span></div></button>`).join(''):emptyHtml('✨','Запись пока недоступна','Администратор ещё не добавил услуги.')}</div>
    ${services.length?'<button class="primary" id="continueServices" disabled>Выбрать исполнителя</button>':''}
  </div>`;
  document.querySelectorAll('.service-pick').forEach(btn=>btn.onclick=()=>{const id=Number(btn.dataset.id);if(state.booking.serviceIds.includes(id))state.booking.serviceIds=state.booking.serviceIds.filter(x=>x!==id);else state.booking.serviceIds.push(id);btn.classList.toggle('selected');document.getElementById('continueServices').disabled=!state.booking.serviceIds.length});
  if(services.length)document.getElementById('continueServices').onclick=renderBookStaff;
}

async function renderBookStaff() {
  setBack(renderBookServices);
  const ids=state.booking.serviceIds.join(',');
  const staff=await api(`/api/staff/eligible?service_ids=${encodeURIComponent(ids)}`);
  content.innerHTML=`<div class="page">${pageTitle('Выберите исполнителя','Доступны специалисты, которые выполняют все выбранные услуги')}
    <div class="list">${staff.length?staff.map(s=>`<button class="list-item staff-pick" data-id="${s.id}"><div class="list-main"><strong>${esc(s.display_name)}</strong><span>${esc(s.description||'Исполнитель')}</span></div><span class="chev">›</span></button>`).join(''):emptyHtml('🙈','Нет подходящего исполнителя','Никто не выполняет весь выбранный набор услуг. Попробуйте убрать одну из услуг.')}</div>
  </div>`;
  document.querySelectorAll('.staff-pick').forEach(btn=>btn.onclick=()=>{state.booking.staffId=Number(btn.dataset.id);renderBookDate()});
}

async function renderBookDate() {
  setBack(renderBookStaff);
  const count=Math.min(Number(state.me.business.booking_horizon_days||60),30);
  const dates=nextDates(count);
  content.innerHTML=`<div class="page">${pageTitle('Дата и время','Свободные слоты учитывают весь выбранный набор услуг')}
    <div class="days" id="days">${dates.map((d,i)=>`<button class="day" data-date="${dateYMD(d)}"><span>${i===0?'Сегодня':dayLabel(d)}</span><strong>${d.getUTCDate()}</strong><span>${monthLabel(d)}</span></button>`).join('')}</div>
    <div id="slotsBox" class="empty"><div class="emoji">◷</div><h3>Выберите дату</h3><p>Покажем всё доступное время.</p></div>
  </div>`;
  document.querySelectorAll('.day').forEach(btn=>btn.onclick=async()=>{document.querySelectorAll('.day').forEach(x=>x.classList.remove('selected'));btn.classList.add('selected');state.booking.date=btn.dataset.date;state.booking.slot=null;const box=document.getElementById('slotsBox');box.className='empty';box.innerHTML='<div class="spinner" style="margin:0 auto"></div><p style="margin-top:8px">Ищем свободное время…</p>';const result=await api(`/api/availability?staff_id=${state.booking.staffId}&service_ids=${state.booking.serviceIds.join(',')}&target_date=${state.booking.date}`);if(!result.slots.length){box.className='empty';box.innerHTML='<div class="emoji">🗓️</div><h3>На этот день мест нет</h3><p>Выберите другую дату.</p>';return}box.className='slots';box.innerHTML=result.slots.map(s=>`<button class="slot" data-start="${s.start_at}">${businessTime(s.start_at)}</button>`).join('');box.querySelectorAll('.slot').forEach(s=>s.onclick=()=>{box.querySelectorAll('.slot').forEach(x=>x.classList.remove('selected'));s.classList.add('selected');state.booking.slot=s.dataset.start;renderBookConfirm()})});
}

async function renderBookConfirm() {
  const [services,staff]=await Promise.all([api('/api/services'),api('/api/staff')]);
  const selectedServices=services.filter(s=>state.booking.serviceIds.includes(s.id));
  const selectedStaff=staff.find(s=>s.id===state.booking.staffId);
  setBack(renderBookDate);
  content.innerHTML=`<div class="page">${pageTitle('Подтверждение','Проверьте запись перед отправкой')}
    <section class="summary card">
      <div class="summary-row"><span>Услуги</span><span>${selectedServices.map(s=>esc(s.name)).join(' + ')}</span></div>
      <div class="summary-row"><span>Исполнитель</span><span>${esc(selectedStaff?.display_name||'')}</span></div>
      <div class="summary-row"><span>Дата и время</span><span>${businessDateTime(state.booking.slot)}</span></div>
      <div class="summary-row"><span>Подтверждение</span><span>${state.me.business.booking_confirmation_mode==='auto'?'Автоматическое':`Администратором, бронь ${state.me.business.hold_minutes} мин`}</span></div>
    </section>
    <section class="form-card card"><form id="bookingForm">
      <div class="field"><label>Телефон для связи</label><input name="phone" type="tel" value="${esc(state.me.user.phone||'')}" placeholder="+7 999 123-45-67" required></div>
      <button class="primary">Записаться</button>
    </form></section>
  </div>`;
  document.getElementById('bookingForm').onsubmit=async e=>{e.preventDefault();const fd=new FormData(e.target);try{const result=await api('/api/bookings',{method:'POST',body:JSON.stringify({staff_id:state.booking.staffId,service_ids:state.booking.serviceIds,start_at:state.booking.slot,phone:fd.get('phone')||null})});renderBookingSuccess(result)}catch(err){toast(err.message);setTimeout(renderBookDate,700)}};
}

function renderBookingSuccess(b) {
  clearBack();
  content.innerHTML=`<div class="page"><section class="hero card"><span class="badge accent">Готово</span><div><h2>${b.status==='confirmed'?'Запись подтверждена':'Время временно забронировано'}</h2><p class="muted" style="margin-top:8px">${b.status==='confirmed'?'Ждём вас в выбранное время.':`Администратор должен подтвердить запись. Слот удерживается ${state.me.business.hold_minutes} минут.`}</p></div></section><section class="summary card"><div class="summary-row"><span>Исполнитель</span><span>${esc(b.staff.display_name)}</span></div><div class="summary-row"><span>Дата</span><span>${businessDateTime(b.start_at)}</span></div><div class="summary-row"><span>Услуги</span><span>${b.services.map(s=>esc(s.name)).join(' + ')}</span></div></section><button class="primary" id="successBookings">Мои записи</button><button class="secondary" id="successAgain">Записаться ещё</button></div>`;
  document.getElementById('successBookings').onclick=()=>route('my-bookings');document.getElementById('successAgain').onclick=()=>route('book');
}

async function renderMoveBooking(booking, adminMode=false) {
  const serviceIds=booking.services.map(s=>s.id);
  const count=Math.min(Number(state.me.business.booking_horizon_days||60),30);
  const dates=nextDates(count);
  setBack(()=>adminMode?route('bookings'):renderMyBookings());
  content.innerHTML=`<div class="page">${pageTitle('Перенести запись',`${booking.staff.display_name} · ${booking.services.map(s=>s.name).join(' + ')}`)}
    <section class="summary card">
      <div class="summary-row"><span>Сейчас</span><span>${businessDateTime(booking.start_at)}</span></div>
      <div class="summary-row"><span>Исполнитель</span><span>${esc(booking.staff.display_name)}</span></div>
    </section>
    <div class="days" id="moveDays">${dates.map((d,i)=>`<button class="day" data-date="${dateYMD(d)}"><span>${i===0?'Сегодня':dayLabel(d)}</span><strong>${d.getUTCDate()}</strong><span>${monthLabel(d)}</span></button>`).join('')}</div>
    <div id="moveSlots" class="empty"><div class="emoji">◷</div><h3>Выберите новую дату</h3><p>Старая запись останется на месте, пока перенос не будет успешно подтверждён.</p></div>
    <div id="moveConfirm"></div>
  </div>`;

  document.querySelectorAll('#moveDays .day').forEach(btn=>btn.onclick=async()=>{
    document.querySelectorAll('#moveDays .day').forEach(x=>x.classList.remove('selected'));
    btn.classList.add('selected');
    const confirmBox=document.getElementById('moveConfirm');
    confirmBox.innerHTML='';
    const box=document.getElementById('moveSlots');
    box.className='empty';
    box.innerHTML='<div class="spinner" style="margin:0 auto"></div><p style="margin-top:8px">Ищем свободное время…</p>';
    try{
      const result=await api(`/api/availability?staff_id=${booking.staff.id}&service_ids=${serviceIds.join(',')}&target_date=${btn.dataset.date}&exclude_booking_id=${booking.id}`);
      if(!result.slots.length){box.className='empty';box.innerHTML='<div class="emoji">🗓️</div><h3>Свободных мест нет</h3><p>Попробуйте другой день.</p>';return}
      box.className='slots';
      box.innerHTML=result.slots.map(slot=>`<button class="slot" data-start="${slot.start_at}">${businessTime(slot.start_at)}</button>`).join('');
      box.querySelectorAll('.slot').forEach(slot=>slot.onclick=()=>{
        box.querySelectorAll('.slot').forEach(x=>x.classList.remove('selected'));
        slot.classList.add('selected');
        renderMoveConfirmation(booking, slot.dataset.start, adminMode);
      });
    }catch(err){
      box.className='empty';
      box.innerHTML=`<div class="emoji">⚠️</div><h3>Не удалось загрузить время</h3><p>${esc(err.message)}</p>`;
    }
  });
}

function renderMoveConfirmation(booking, newStart, adminMode=false) {
  const confirmBox=document.getElementById('moveConfirm');
  if(!confirmBox)return;
  confirmBox.innerHTML=`<section class="reschedule-confirm">
    <div><span class="badge accent">Новое время</span></div>
    <div class="new-time">${businessDateTime(newStart)}</div>
    <p class="muted small">Текущая запись изменится только после успешного ответа сервера.</p>
    <div id="moveError" class="inline-error hidden"></div>
    <button class="primary" id="confirmMove">Подтвердить перенос</button>
  </section>`;
  const button=document.getElementById('confirmMove');
  button.onclick=async()=>{
    const errorBox=document.getElementById('moveError');
    errorBox.classList.add('hidden');
    const endpoint=adminMode?`/api/bookings/${booking.id}/move`:`/api/my-bookings/${booking.id}/reschedule`;
    try{
      setButtonBusy(button,true,'Переносим…');
      const updated=await api(endpoint,{method:'POST',body:JSON.stringify({start_at:newStart})});
      content.innerHTML=`<div class="page">
        <section class="hero card"><span class="badge accent">Готово</span><div><h2>Запись перенесена</h2><p class="muted" style="margin-top:8px">Новое время сохранено.</p></div></section>
        <section class="summary card"><div class="summary-row"><span>Исполнитель</span><span>${esc(updated.staff.display_name)}</span></div><div class="summary-row"><span>Новая дата</span><span>${businessDateTime(updated.start_at)}</span></div><div class="summary-row"><span>Статус</span><span>${statusLabel(updated.status)}</span></div></section>
        <button class="primary" id="moveDone">${adminMode?'К записям':'Мои записи'}</button>
      </div>`;
      toast('Запись успешно перенесена');
      document.getElementById('moveDone').onclick=()=>adminMode?route('bookings'):renderMyBookings();
    }catch(err){
      setButtonBusy(button,false);
      errorBox.textContent=err.message||'Не удалось перенести запись';
      errorBox.classList.remove('hidden');
      toast('Не удалось перенести запись');
    }
  };
}

async function renderManualServices() {
  state.manual={serviceIds:[],staffId:null,date:null,slot:null};
  const services=await api('/api/services');
  setBack(()=>route('bookings'));
  content.innerHTML=`<div class="page">${pageTitle('Ручная запись','Для клиента, который записался по телефону или в переписке')}
    <div class="list">${services.map(s=>`<button class="list-item manual-service" data-id="${s.id}"><span class="check">✓</span><div class="list-main"><strong>${esc(s.name)}</strong><span>${s.default_duration_minutes} мин</span></div></button>`).join('')}</div>
    <button class="primary" id="manualNext" disabled>Далее</button>
  </div>`;
  document.querySelectorAll('.manual-service').forEach(btn=>btn.onclick=()=>{const id=Number(btn.dataset.id);if(state.manual.serviceIds.includes(id))state.manual.serviceIds=state.manual.serviceIds.filter(x=>x!==id);else state.manual.serviceIds.push(id);btn.classList.toggle('selected');document.getElementById('manualNext').disabled=!state.manual.serviceIds.length});
  document.getElementById('manualNext').onclick=renderManualStaff;
}

async function renderManualStaff() {
  setBack(renderManualServices);
  const staff=await api(`/api/staff/eligible?service_ids=${state.manual.serviceIds.join(',')}`);
  content.innerHTML=`<div class="page">${pageTitle('Исполнитель','Кто будет выполнять запись')}<div class="list">${staff.length?staff.map(s=>`<button class="list-item manual-staff" data-id="${s.id}"><div class="list-main"><strong>${esc(s.display_name)}</strong><span>${esc(s.description||'Исполнитель')}</span></div><span class="chev">›</span></button>`).join(''):emptyHtml('🙈','Нет подходящего исполнителя','Проверьте назначение услуг исполнителям.')}</div></div>`;
  document.querySelectorAll('.manual-staff').forEach(btn=>btn.onclick=()=>{state.manual.staffId=Number(btn.dataset.id);renderManualDate()});
}

async function renderManualDate() {
  setBack(renderManualStaff);
  const dates=nextDates(Math.min(Number(state.me.business.booking_horizon_days||60),30));
  content.innerHTML=`<div class="page">${pageTitle('Дата и время','Показываются только свободные интервалы')}<div class="days" id="manualDays">${dates.map((d,i)=>`<button class="day" data-date="${dateYMD(d)}"><span>${i===0?'Сегодня':dayLabel(d)}</span><strong>${d.getUTCDate()}</strong><span>${monthLabel(d)}</span></button>`).join('')}</div><div id="manualSlots" class="empty"><div class="emoji">◷</div><h3>Выберите дату</h3><p>Найдём свободный слот.</p></div></div>`;
  document.querySelectorAll('#manualDays .day').forEach(btn=>btn.onclick=async()=>{document.querySelectorAll('#manualDays .day').forEach(x=>x.classList.remove('selected'));btn.classList.add('selected');const box=document.getElementById('manualSlots');box.className='empty';box.innerHTML='<div class="spinner" style="margin:0 auto"></div>';const result=await api(`/api/availability?staff_id=${state.manual.staffId}&service_ids=${state.manual.serviceIds.join(',')}&target_date=${btn.dataset.date}`);if(!result.slots.length){box.className='empty';box.innerHTML='<div class="emoji">🗓️</div><h3>Нет свободного времени</h3><p>Выберите другой день.</p>';return}box.className='slots';box.innerHTML=result.slots.map(slot=>`<button class="slot" data-start="${slot.start_at}">${businessTime(slot.start_at)}</button>`).join('');box.querySelectorAll('.slot').forEach(slot=>slot.onclick=()=>{state.manual.slot=slot.dataset.start;renderManualClient()})});
}

function renderManualClient() {
  setBack(renderManualDate);
  content.innerHTML=`<div class="page">${pageTitle('Клиент','Последний шаг ручной записи')}<section class="form-card card"><form id="manualClientForm"><div class="field"><label>Имя клиента</label><input name="client_name" required placeholder="Анна"></div><div class="field"><label>Телефон</label><input name="phone" type="tel" required placeholder="+7 999 123-45-67"></div><div class="summary-row"><span>Время</span><span>${businessDateTime(state.manual.slot)}</span></div><button class="primary">Создать запись</button></form></section></div>`;
  document.getElementById('manualClientForm').onsubmit=async e=>{e.preventDefault();const fd=new FormData(e.target);await api('/api/bookings/manual',{method:'POST',body:JSON.stringify({client_name:fd.get('client_name'),phone:fd.get('phone'),staff_id:state.manual.staffId,service_ids:state.manual.serviceIds,start_at:state.manual.slot})});toast('Запись создана');route('bookings')};
}

async function renderMyBookings() {
  const bookings=await api('/api/my-bookings');
  content.innerHTML=`<div class="page">${pageTitle('Мои записи','Вся история записей в EasyBook')}
    <div class="list">${bookings.length?bookings.map(b=>bookingCard(b,false)).join(''):emptyHtml('🗓️','Записей пока нет','Выберите услугу и подходящее время.')}</div>
  </div>`;
  bindBookingButtons();
}

function renderProfile() {
  content.innerHTML=`<div class="page">${pageTitle('Профиль','Данные берутся из Telegram')}
    <section class="summary card"><div class="summary-row"><span>Имя</span><span>${esc(state.me.user.full_name)}</span></div><div class="summary-row"><span>Телефон</span><span>${esc(state.me.user.phone||'Не указан')}</span></div><div class="summary-row"><span>Часовой пояс</span><span>${esc(timezoneLabel(state.me.business.timezone))}</span></div></section>
  </div>`;
}

function emptyHtml(emoji,title,text){return `<div class="empty"><div class="emoji">${emoji}</div><h3>${esc(title)}</h3><p>${esc(text)}</p></div>`}
function renderError(err){content.innerHTML=`<section class="empty"><div class="emoji">⚠️</div><h3>Что-то пошло не так</h3><p>${esc(err.message||String(err))}</p></section>`}

init().catch(renderError);
