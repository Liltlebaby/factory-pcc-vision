const byId = (id) => document.getElementById(id);

let token = '';
// แผงยอดนับอยู่คนละไฟล์ จึงอ่าน token ผ่านตัวแปรกลางตัวนี้
window.RackAuth = { token: '' };
let socket = null;
let epoch = 0;
let blobUrl = null;
let toastTimer = null;
let lastKnownCount = null;
let fleetTimer = null;
const requestedStation = new URLSearchParams(window.location.search).get('station');

function setClock() {
  byId('clock').textContent = new Intl.DateTimeFormat('th-TH', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
  }).format(new Date());
}

function setConnection(state, text) {
  const element = byId('connection');
  element.className = `status-pill ${state}`;
  element.querySelector('span').textContent = text;
}

function notify(text, isError = false) {
  const toast = byId('action-message');
  toast.textContent = text;
  toast.className = `toast show${isError ? ' error' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.className = 'toast'; }, 5000);
}

async function action(work) {
  try { await work(); }
  catch (error) { notify(error.message || String(error), true); }
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    const rawDetail = await response.text();
    const detail = response.headers.get('content-type')?.includes('application/json') && rawDetail.length < 240
      ? rawDetail : '';
    throw new Error(`เชื่อมต่อไม่สำเร็จ (${response.status})${detail ? `: ${detail}` : ''}`);
  }
  return response;
}

function health(name, ready, readyText, errorText) {
  byId(`health-${name}`).className = ready ? 'good' : 'bad';
  byId(`health-${name}-text`).textContent = ready ? readyText : errorText;
}

function formatDate(value) {
  if (value === null || value === undefined || value === '') return '—';
  const date = new Date(typeof value === 'number' && value < 1e12 ? value * 1000 : value);
  if (!Number.isFinite(date.getTime())) return String(value);
  return new Intl.DateTimeFormat('th-TH', {
    day: '2-digit', month: 'short', year: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  }).format(date);
}

function setVideoReady(ready) {
  byId('video').classList.toggle('ready', ready);
  byId('video-placeholder').classList.toggle('hidden', ready);
}

function lifecycleText(value) {
  return value === 'active' ? 'Active' : value === 'disabled' ? 'Disabled' : 'Planned';
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderFleet(payload) {
  const cameras = Array.isArray(payload.items) ? payload.items : [];
  const tasks = cameras.flatMap((camera) => Array.isArray(camera.tasks) ? camera.tasks.map((task) => ({ camera, task })) : []);
  const active = cameras.filter((camera) => camera.lifecycle === 'active').length;
  const planned = cameras.filter((camera) => camera.lifecycle === 'planned').length;
  const online = cameras.filter((camera) => camera.status?.camera_status === 'online').length;
  byId('fleet-total').textContent = String(cameras.length);
  byId('fleet-online').textContent = String(online);
  byId('fleet-tasks').textContent = String(tasks.length);
  byId('fleet-lifecycle').textContent = `${active} ใช้งาน · ${planned} วางแผน`;
  byId('fleet-count-label').textContent = `${cameras.length} กล้อง`;
  byId('task-count-label').textContent = `${tasks.length} งาน`;

  const primary = cameras.find((camera) => camera.lifecycle === 'active');
  if (primary) {
    const task = primary.tasks?.[0];
    byId('active-camera-name').textContent = primary.name;
    byId('active-camera-location').textContent = `· ${primary.location}`;
    byId('active-task-name').textContent = task?.name || task?.task_type || 'AI TASK';
    byId('video-waiting-title').textContent = `กำลังรอภาพจาก ${primary.name}`;
    byId('video-camera-label').textContent = `${primary.name} · ${primary.location}`;
    byId('video').alt = `ภาพสด ${primary.name} พร้อมผลตรวจจาก AI`;
  }

  const body = byId('camera-fleet-body');
  body.replaceChildren();
  cameras.forEach((camera) => {
    const row = document.createElement('tr');
    row.dataset.station = camera.station_id;
    row.id = `camera-row-${camera.camera_id}`;
    if (camera.lifecycle !== 'active') row.className = 'planned-row';
    if (requestedStation && camera.station_id === requestedStation) row.classList.add('context-row');
    const name = element('td', 'camera-name');
    name.append(element('strong', '', camera.name), element('small', '', camera.camera_id));
    const task = camera.tasks?.[0];
    const taskCell = element('td', '', task?.name || 'ยังไม่ได้กำหนด');
    const statusCell = element('td');
    const statusValue = camera.status?.camera_status === 'online' ? 'online' : camera.lifecycle;
    statusCell.append(element('span', `fleet-status ${statusValue}`, camera.status?.camera_status === 'online' ? 'Online' : lifecycleText(camera.lifecycle)));
    row.append(name, taskCell, statusCell, element('td', '', camera.location));
    body.append(row);
  });

  const context = byId('station-context');
  if (requestedStation) {
    const matches = cameras.filter((camera) => camera.station_id === requestedStation);
    context.hidden = false;
    context.classList.toggle('empty', matches.length === 0);
    context.querySelector('strong').textContent = matches.length
      ? `กล้องสำหรับสถานี ${requestedStation}`
      : `ยังไม่มีกล้องที่ผูกกับสถานี ${requestedStation}`;
    context.querySelector('span').textContent = matches.length
      ? `${matches.length} กล้อง · ${matches.flatMap((camera) => camera.tasks || []).length} งาน AI`
      : 'เพิ่มกล้องได้ที่ Camera Registry โดยไม่ต้องแก้หน้า PCC';
  } else {
    context.hidden = true;
  }

  const list = byId('task-list');
  list.replaceChildren();
  tasks.forEach(({ camera, task }, index) => {
    const item = element('article', `task-item ${task.lifecycle}`);
    if (requestedStation && camera.station_id === requestedStation) item.classList.add('context-task');
    const icon = element('span', 'task-icon', ['▦', '⌁', '◎'][index] || 'AI');
    const copy = element('div', 'task-copy');
    copy.append(element('strong', '', task.name), element('small', '', `${camera.name} · ${task.task_type}`));
    item.append(icon, copy, element('span', `task-state ${task.lifecycle}`, lifecycleText(task.lifecycle)));
    list.append(item);
  });
}

async function loadFleet() {
  try {
    const response = await api('/api/v1/cameras');
    renderFleet(await response.json());
  } catch (error) {
    notify(`โหลด Camera Registry ไม่สำเร็จ: ${error.message}`, true);
  }
}

async function loadSystemLinks() {
  try {
    const response = await api('/api/v1/system-links');
    const links = await response.json();
    if (typeof links.pcc === 'string') byId('pcc-link').href = links.pcc;
  } catch (_) {
    // Keep the safe localhost fallback when configuration is temporarily unavailable.
  }
}

async function frames(run) {
  while (run === epoch) {
    try {
      const response = await api('/api/live/frame');
      const blob = await response.blob();
      if (run !== epoch) return;
      const nextUrl = URL.createObjectURL(blob);
      const video = byId('video');
      video.src = nextUrl;
      setVideoReady(true);
      if (blobUrl) URL.revokeObjectURL(blobUrl);
      blobUrl = nextUrl;
      byId('message').textContent = '';
    } catch (error) {
      byId('message').textContent = `ไม่สามารถโหลดภาพสด: ${error.message}`;
      setVideoReady(false);
      byId('video').removeAttribute('src');
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
}

function updateStatus(state) {
  const fps = state.fps || {};
  const isReady = Boolean(state.running);
  const cameraFps = Number(fps.camera) || 0;
  const inferenceFps = Number(fps.inference) || 0;

  setConnection(isReady ? 'online' : 'offline', isReady ? 'ระบบทำงานปกติ' : 'กล้องหรือ AI ไม่พร้อม');
  byId('camera-state').textContent = isReady ? 'CAMERA ONLINE' : 'CAMERA OFFLINE';
  byId('camera-state').className = `mini-badge ${isReady ? 'good' : 'bad'}`;
  byId('ai-state').textContent = inferenceFps > 0 ? 'AI ACTIVE' : 'AI WAITING';
  byId('ai-state').className = `mini-badge ${inferenceFps > 0 ? 'good' : 'bad'}`;

  byId('count').textContent = Number.isFinite(Number(state.rack_count)) ? Number(state.rack_count).toLocaleString('th-TH') : '—';
  byId('camera').textContent = cameraFps.toFixed(1);
  byId('inference').textContent = inferenceFps.toFixed(1);
  byId('tracks').textContent = Number(state.active_tracks) || 0;
  byId('model').textContent = state.model || 'กำลังโหลด';

  const lastEvent = state.lastEvent;
  byId('last-event').textContent = lastEvent
    ? `เก๊ะ #${lastEvent.rackNumber || state.rack_count} · ${formatDate(lastEvent.timestamp)}`
    : 'ยังไม่มีข้อมูล';
  // ยอดขยับเมื่อไหร่ ให้แผงรายชั่วโมงตามไปด้วย จะได้ไม่ต้องรอรอบรีเฟรชหนึ่งนาที
  const counted = Number(state.rack_count) || 0;
  if (counted !== lastKnownCount) {
    lastKnownCount = counted;
    window.RackCounting?.onCount();
  }
  const fleetEvent = byId('fleet-last-event');
  if (fleetEvent) fleetEvent.textContent = lastEvent ? `#${lastEvent.rackNumber || state.rack_count}` : '—';

  health('camera', isReady && cameraFps > 0, `${cameraFps.toFixed(1)} FPS`, 'ไม่พบสัญญาณ');
  health('ai', isReady && inferenceFps > 0, `${inferenceFps.toFixed(1)} FPS`, 'ยังไม่พร้อม');
}

function metadata(run) {
  if (run !== epoch) return;
  setConnection('waiting', 'กำลังเชื่อมต่อ');
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${protocol}://${location.host}/ws/rack-counter`);
  socket = ws;
  ws.onopen = () => ws.send(JSON.stringify({ token }));
  ws.onmessage = (event) => {
    if (run !== epoch) return;
    try { updateStatus(JSON.parse(event.data)); }
    catch (error) { notify(`อ่านสถานะระบบไม่ได้: ${error.message}`, true); }
  };
  ws.onerror = () => setConnection('offline', 'การเชื่อมต่อมีปัญหา');
  ws.onclose = (event) => {
    if (run !== epoch) return;
    setConnection('offline', 'การเชื่อมต่อขาด');
    if (event.code !== 1008) setTimeout(() => metadata(run), 3000);
    else notify('API token ไม่ถูกต้อง หรือ origin นี้ไม่ได้รับอนุญาต', true);
  };
}

byId('connect').onsubmit = (event) => {
  event.preventDefault();
  epoch += 1;
  if (socket) socket.close();
  token = byId('token').value.trim();
  window.RackAuth.token = token;
  window.RackCounting?.refresh();
  metadata(epoch);
  frames(epoch);
};

byId('fullscreen').onclick = async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await byId('video-stage').requestFullscreen();
  } catch (error) { notify('เบราว์เซอร์นี้ไม่สามารถเปิดภาพเต็มจอได้', true); }
};

byId('refresh').onclick = () => {
  epoch += 1;
  if (socket) socket.close();
  metadata(epoch);
  frames(epoch);
  loadFleet();
  notify('กำลังตรวจสอบกล้องและ AI อีกครั้ง');
};

byId('reset-count').onclick = () => {
  if (!window.confirm('ยืนยันรีเซ็ตจำนวนเก๊ะสะสมเป็น 0?')) return;
  action(async () => {
    const response = await api('/api/rack-counter/reset', { method: 'POST' });
    const value = await response.json();
    byId('count').textContent = Number(value.rack_count).toLocaleString('th-TH');
    notify('รีเซ็ตจำนวนเก๊ะแล้ว');
    window.RackCounting?.refresh();
  });
};
document.addEventListener('fullscreenchange', () => {
  byId('fullscreen').innerHTML = document.fullscreenElement
    ? '<span aria-hidden="true">×</span> ออกจากเต็มจอ'
    : '<span aria-hidden="true">⛶</span> เต็มจอ';
});

setClock();
setInterval(setClock, 1000);
loadSystemLinks();
loadFleet();
fleetTimer = setInterval(loadFleet, 10000);
byId('connect').requestSubmit();
