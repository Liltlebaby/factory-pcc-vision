/**
 * Vision Monitor — หน้าจอหลัก
 *
 * หน้าเดียว สลับมุมมองด้วย hash
 *   #/                    ภาพรวมทุกกล้อง จัดกลุ่มตามจุดงาน
 *   #/camera/<camera_id>  หน้ารายละเอียดของกล้องแต่ละตัว แยกตามงาน AI
 *
 * ข้อมูลทุกตัวมาจาก API จริง ถ้ายังไม่มีข้อมูลจะแสดง "—" ไม่เดาค่าให้
 * โครงหน้าวาดใหม่เฉพาะเมื่อโครงสร้างเปลี่ยน (สถานะกล้อง งาน หรือหน้า)
 * ส่วนตัวเลขอัปเดตในที่ผ่าน data-v เพื่อไม่ให้ภาพสดกะพริบทุกครั้งที่มีข้อมูลใหม่
 */
(function () {
  const $ = (id) => document.getElementById(id);
  const RC = window.RackCounting;
  const view = $('view');

  window.RackAuth = { token: '' };
  const S = {
    token: '',
    cameras: [],
    snapshot: null,
    dailyToday: null,
    rackDate: null,
    rackView: null,
    magnetToday: null,
    magnetError: null,
    magnetDate: null,
    magnetView: null,
    events: [],
    eventsFor: null,
    eventFilter: 'all',
    blobUrls: new Map(),
    previewReady: new Set(),
    epoch: 0,
    socket: null,
    structure: '',
    fleetError: null,
  };
  const requestedStation = new URLSearchParams(location.search).get('station');
  const ABSENT_LIMIT = 300;                         // ไม่พบคนในพื้นที่บ่อสุดท้ายเกิน 5 นาที
  // โรงงานใช้เวลาไทยเสมอ ไม่ขึ้นกับเขตเวลาที่ตั้งไว้ในเครื่องที่เปิดดู
  const TZ = 'Asia/Bangkok';
  const bangkokHour = () => Number(new Intl.DateTimeFormat('en-GB', { hour: '2-digit', hour12: false, timeZone: TZ }).format(new Date())) % 24;

  // ---------- เครื่องมือเล็ก ๆ ----------
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = (value) => (value === null || value === undefined || value === '' || !Number.isFinite(Number(value)) ? null : Number(value));
  const fmt = (value, digits) => {
    const n = num(value);
    if (n === null) return '—';
    return digits === undefined ? n.toLocaleString('th-TH') : n.toFixed(digits);
  };
  const mmss = (seconds) => {
    const n = num(seconds);
    if (n === null) return '—';
    const s = Math.max(0, Math.floor(n));
    return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  };
  function toDate(value) {
    if (value === null || value === undefined || value === '') return null;
    const date = new Date(typeof value === 'number' && value < 1e12 ? value * 1000 : value);
    return Number.isFinite(date.getTime()) ? date : null;
  }
  function when(value, withDate = true) {
    const date = toDate(value);
    if (!date) return '—';
    return new Intl.DateTimeFormat('th-TH', {
      ...(withDate ? { day: 'numeric', month: 'short' } : {}),
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: TZ,
    }).format(date);
  }

  const ICONS = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"></rect><rect x="14" y="3" width="7" height="7" rx="1.5"></rect><rect x="3" y="14" width="7" height="7" rx="1.5"></rect><rect x="14" y="14" width="7" height="7" rx="1.5"></rect>',
    camera: '<rect x="2" y="6" width="14" height="12" rx="2"></rect><path d="M16 10l6-3v10l-6-3"></path>',
    bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"></path><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"></path>',
    cpu: '<rect x="5" y="5" width="14" height="14" rx="2"></rect><rect x="9" y="9" width="6" height="6"></rect><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"></path>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"></path>',
    helmet: '<path d="M4 16a8 8 0 0 1 16 0"></path><path d="M2 16h20v3H2z"></path><path d="M12 8V5"></path>',
    magnet: '<path d="M6 3h4v8a2 2 0 0 0 4 0V3h4v8a6 6 0 0 1-12 0z"></path><path d="M6 7h4M14 7h4"></path>',
    person: '<circle cx="12" cy="7" r="4"></circle><path d="M4 21a8 8 0 0 1 16 0"></path>',
    pulse: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>',
    clock: '<circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path>',
    alert: '<path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"></path><path d="M12 9v4M12 17h.01"></path>',
    chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L3 21l1.9-6.4A8 8 0 1 1 21 12z"></path>',
    box: '<path d="M3 7l9-4 9 4-9 4-9-4z"></path><path d="M3 7v10l9 4 9-4V7"></path><path d="M12 11v10"></path>',
    eyeoff: '<path d="M3 3l18 18"></path><path d="M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.2M6.6 6.6C3.8 8.4 2 12 2 12s3.5 7 10 7a9.6 9.6 0 0 0 5.4-1.6"></path><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"></path>',
    check: '<path d="M5 12l5 5L20 7"></path>',
    scale: '<path d="M12 3v18M5 21h14"></path><path d="M5 7h14"></path><path d="M5 7l-3 7a3 3 0 0 0 6 0z"></path><path d="M19 7l-3 7a3 3 0 0 0 6 0z"></path>',
    refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4"></path><path d="M21 3v6h-6"></path>',
    expand: '<path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"></path>',
  };
  const icon = (name, size = 18, width = 1.8) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;

  // งาน AI แต่ละชนิดมีสี ไอคอน และชื่อย่อประจำตัว ใช้เหมือนกันทุกหน้า
  const TASK_KIND = {
    line_crossing_count: { tone: 'rack', icon: 'box', short: 'นับเก๊ะ' },
    area_presence: { tone: 'act', icon: 'person', short: 'เฝ้าพื้นที่' },
    ppe_compliance: { tone: 'ppe', icon: 'helmet', short: 'หมวกนิรภัย' },
    hourly_inspection: { tone: 'mag', icon: 'magnet', short: 'ตรวจแม่เหล็ก' },
    activity_assessment: { tone: 'act', icon: 'person', short: 'สถานะงาน' },
  };
  const kindOf = (task) => TASK_KIND[task.task_type] || { tone: 'act', icon: 'cpu', short: task.task_type };
  // หมวดกล้อง แยกจากชนิดงานในทะเบียน ไม่ผูกกับชื่อกล้อง — เพิ่มกล้องเฝ้าคนจุดใหม่
  // ในทะเบียนแล้วจะเข้าหมวดเองโดยไม่ต้องแก้หน้าจอ
  const CAMERA_GROUPS = [
    { id: 'people', title: 'กล้องเฝ้าคนในพื้นที่', short: 'เฝ้าคน', icon: 'person', tone: 'act',
      types: ['area_presence', 'ppe_compliance', 'activity_assessment'],
      desc: 'ไม่มีคนในพื้นที่ทำงานเกิน 5 นาที · หมวกนิรภัย (เปิดภายหลัง)' },
    { id: 'rack', title: 'กล้องนับเก๊ะ', short: 'นับเก๊ะ', icon: 'box', tone: 'rack',
      types: ['line_crossing_count'], desc: 'นับเก๊ะหอโรยยางก่อนเข้าเตา' },
  ];
  const OTHER_GROUP = { id: 'other', title: 'กล้องอื่น ๆ', short: 'อื่น ๆ', icon: 'camera', tone: 'act', types: [], desc: '' };
  // กล้องที่มีงานนับเก๊ะอยู่หมวดนับเก๊ะเสมอ แม้จะมีงานอื่นพ่วง เพราะยอดนับคือหน้าที่หลักของมัน
  const groupOf = (camera) => {
    const types = (camera.tasks || []).map((task) => task.task_type);
    return CAMERA_GROUPS.find((group) => group.id === 'rack' && group.types.some((type) => types.includes(type)))
      || CAMERA_GROUPS.find((group) => group.types.some((type) => types.includes(type)))
      || OTHER_GROUP;
  };
  const camerasByGroup = (cams) => [...CAMERA_GROUPS, OTHER_GROUP]
    .map((group) => ({ ...group, cameras: cams.filter((camera) => groupOf(camera).id === group.id) }))
    .filter((group) => group.cameras.length);
  const stationName = (camera) => String(camera.location || camera.station_id).split('·')[0].trim();
  const findTask = (camera, type) => (camera.tasks || []).find((task) => task.task_type === type);
  const statusTask = (camera, taskId) => (camera.status?.tasks || []).find((task) => task.task_id === taskId) || {};

  function cameraState(camera) {
    const status = camera.status || {};
    if (camera.ai_pilot) return status.data_status === 'pilot'
      ? { cls: 'warn', text: 'AI ทดลอง' } : { cls: 'bad', text: 'ภาพ AI ขาด' };
    if (camera.lifecycle === 'planned') return { cls: 'plan', text: 'เตรียมใช้งาน' };
    if (camera.lifecycle === 'disabled') return { cls: '', text: 'ปิดใช้งาน' };
    if (status.source_signal?.signal === 'no_video') return { cls: 'bad', text: 'ภาพดับ' };
    if (status.camera_status === 'online' && status.data_status === 'live') return { cls: 'ok', text: 'ทำงาน' };
    if (status.camera_status === 'online') return { cls: 'warn', text: 'AI ไม่พร้อม' };
    return { cls: 'bad', text: 'ออฟไลน์' };
  }
  function taskState(camera, task) {
    const runtime = statusTask(camera, task.task_id).runtime_status;
    if (camera.ai_pilot && (runtime === 'pilot' || runtime === 'waiting')) return { cls: 'warn', text: runtime === 'pilot' ? 'AI ทดลอง' : 'รอภาพ AI' };
    if (runtime === 'running') return { cls: 'ok', text: 'ทำงาน' };
    if (runtime === 'not_installed' || task.lifecycle === 'planned') return { cls: 'plan', text: 'เตรียมใช้งาน' };
    return { cls: 'bad', text: 'ไม่ได้เชื่อมต่อ' };
  }
  const primaryCamera = () => S.cameras.find((camera) => camera.lifecycle === 'active' && findTask(camera, 'line_crossing_count'))
    || S.cameras.find((camera) => camera.lifecycle === 'active');
  const isPrimary = (camera) => primaryCamera()?.camera_id === camera.camera_id;

  // ---------- API ----------
  async function api(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (S.token) headers.Authorization = `Bearer ${S.token}`;
    const response = await fetch(path, { ...options, headers, cache: 'no-store' });
    if (!response.ok) {
      const raw = await response.text();
      const detail = response.headers.get('content-type')?.includes('application/json') && raw.length < 240 ? raw : '';
      throw new Error(`เชื่อมต่อไม่สำเร็จ (${response.status})${detail ? `: ${detail}` : ''}`);
    }
    return response;
  }

  let toastTimer = null;
  function notify(text, isError = false) {
    const toast = $('toast');
    toast.textContent = text;
    toast.className = `toast show${isError ? ' error' : ''}`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.className = 'toast'; }, 5000);
  }

  function setConnection(cls, text) {
    const node = $('connection');
    node.querySelector('i').className = `dot ${cls}`;
    node.querySelector('span').textContent = text;
  }

  // ---------- เส้นทาง ----------
  function route() {
    const hash = location.hash || '#/';
    const match = hash.match(/^#\/camera\/([A-Za-z0-9_-]+)/);
    if (match) return { view: 'camera', id: match[1] };
    // ลิงก์เก่าจาก PCC ยังใช้ได้
    if (hash === '#count-report' || hash === '#camera-09') return { view: 'camera', id: primaryCamera()?.camera_id || 'camera-09' };
    return { view: 'overview' };
  }

  // ---------- ค่าที่อัปเดตบ่อย ----------
  function values() {
    const v = {};
    const c = {};
    const cams = S.cameras;
    const online = cams.filter((camera) => camera.status?.camera_status === 'online').length;
    const active = cams.filter((camera) => camera.lifecycle === 'active').length;
    v['fleet.online'] = String(online);
    v['fleet.sub'] = `${active} ใช้งาน · ${cams.length - active} เตรียมติดตั้ง`;

    const snap = S.snapshot || {};
    const fps = snap.fps || {};
    const running = Boolean(snap.running);
    const camFps = Number(fps.camera) || 0;
    const aiFps = Number(fps.inference) || 0;
    const shift = RC.currentShift(S.dailyToday);
    const hour = RC.currentHour(S.dailyToday);
    v['rack.shiftName'] = shift ? shift.name : 'กะนี้';
    v['rack.shift'] = shift ? fmt(shift.count) : '—';
    v['rack.hour'] = hour ? fmt(hour.count) : '—';
    v['rack.total'] = S.dailyToday ? `รวมวันรายงาน ${fmt(S.dailyToday.total)} เก๊ะ` : 'กำลังโหลด';
    v['rack.tracks'] = S.snapshot ? fmt(snap.active_tracks || 0) : '—';
    v['rack.service'] = S.snapshot ? fmt(snap.rack_count) : '—';
    v['rack.model'] = snap.model || primaryCamera()?.status?.tasks?.[0]?.model_version || '—';
    const last = snap.lastEvent;
    v['rack.last'] = last ? `เก๊ะ #${last.rackNumber || snap.rack_count} · ${when(last.timestamp)}` : 'ยังไม่มีข้อมูล';
    v['fps.camera'] = S.snapshot ? `${camFps.toFixed(1)} FPS`
      : primaryCamera()?.status?.camera_fps != null ? `${Number(primaryCamera().status.camera_fps).toFixed(1)} FPS` : '—';
    v['fps.inference'] = S.snapshot ? aiFps.toFixed(1) : '—';
    v['fps.sub'] = S.snapshot ? `กล้อง ${camFps.toFixed(1)} FPS · ${snap.model || 'โมเดล —'}` : 'รอข้อมูลจากบริการ';
    c['health.camera'] = running && camFps > 0 ? 'ok' : 'bad';
    c['health.ai'] = running && aiFps > 0 ? 'ok' : 'bad';
    v['live.cam'] = S.snapshot ? (running ? 'CAMERA ONLINE' : 'CAMERA OFFLINE') : 'CAMERA —';
    c['live.cam'] = running ? 'good' : 'bad';
    v['live.ai'] = S.snapshot ? (aiFps > 0 ? 'AI ACTIVE' : 'AI WAITING') : 'AI —';
    c['live.ai'] = aiFps > 0 ? 'good' : 'bad';

    const primary = primaryCamera();
    const signal = primary?.status?.source_signal;
    v['dvr.text'] = !signal ? 'ไม่ได้ตรวจ' : signal.signal === 'ok' ? 'มีสัญญาณ' : signal.signal === 'no_video' ? 'ภาพดับ (NO VIDEO)' : signal.error ? `ตรวจไม่ได้ · ${signal.error}` : 'ไม่ทราบ';
    c['dvr'] = !signal ? '' : signal.signal === 'ok' ? 'ok' : signal.signal === 'no_video' ? 'bad' : 'warn';

    // รอบตรวจแม่เหล็กของวันนี้
    const magnet = S.magnetToday;
    if (magnet && magnet.tally) {
      const t = magnet.tally;
      v['mag.done'] = fmt(t.completed);
      v['mag.sub'] = `พลาด ${t.missed} · ต้องตรวจสอบ ${t.verify_required} · ไม่มีข้อมูล ${t.no_data}`;
      const done = magnet.rounds.filter((round) => round.checked_at).pop();
      v['mag.last'] = done ? when(done.checked_at, false) : 'ยังไม่มี';
      const now = magnet.rounds.find((round) => round.status === 'waiting');
      v['mag.now'] = now ? `${now.label.slice(0, 5)} · รอตรวจ` : '—';
      v['mag.weight'] = done ? WEIGHT_TEXT[done.weight_source] || '—' : '—';
    } else {
      v['mag.done'] = '—';
      v['mag.sub'] = S.magnetError || 'กำลังโหลด';
      v['mag.last'] = '—'; v['mag.now'] = '—'; v['mag.weight'] = '—';
    }

    // งานของ worker ภายนอก เช่น หมวกและคนประจำจุด
    for (const camera of cams) {
      const src = camera.status?.source_stats;
      if (camera.preview_url) {
        const ready = S.previewReady.has(camera.camera_id);
        const fpsText = src ? ` · ${Number(src.source_fps || 0).toFixed(1)} FPS` : '';
        v[`${camera.camera_id}:feed`] = ready ? `CAMERA ONLINE${fpsText}` : 'กำลังรอภาพ';
        c[`${camera.camera_id}:feed`] = ready ? 'good' : 'warn';
      }
      if (src) {
        // FPS ที่รับจาก DVR จริง ใช้เทียบกับกล้อง 9 ว่าปัญหาอยู่ที่เครือข่าย/เครื่อง หรือเฉพาะกล้อง
        const id = camera.camera_id;
        const fps = Number(src.source_fps) || 0;
        v[`${id}:src.fps`] = src.connected ? `${fps.toFixed(1)} FPS` : 'ไม่ได้รับภาพ';
        c[`${id}:src.fps`] = !src.connected ? 'bad' : fps >= 20 ? 'ok' : fps >= 10 ? 'warn' : 'bad';
        v[`${id}:src.gap`] = src.longest_gap_ms == null ? '—' : `${fmt(src.longest_gap_ms)} ms`;
        c[`${id}:src.gap`] = src.longest_gap_ms == null ? '' : src.longest_gap_ms < 300 ? 'ok' : src.longest_gap_ms < 1000 ? 'warn' : 'bad';
        v[`${id}:src.age`] = src.last_frame_age == null ? '—' : `${Number(src.last_frame_age).toFixed(1)} วินาทีที่แล้ว`;
        v[`${id}:src.reconnects`] = `${fmt(src.reconnects)} ครั้ง`;
        v[`${id}:src.res`] = src.resolution || '—';
        const ai = (camera.status?.tasks || []).find((task) => task.inference_fps);
        v[`${id}:src.ai`] = ai ? `${Number(ai.inference_fps).toFixed(1)} FPS` : '—';
      }
      for (const task of camera.tasks || []) {
        const latest = statusTask(camera, task.task_id).latest || {};
        const key = `${camera.camera_id}:${task.task_id}`;
        if (task.task_type === 'ppe_compliance') {
          v[`${key}:people`] = fmt(latest.people_count);
          v[`${key}:pass`] = fmt(latest.helmet_pass);
          v[`${key}:no`] = fmt(latest.no_helmet);
          v[`${key}:undecided`] = fmt(latest.undecided);
          v[`${key}:filtered`] = fmt(latest.filtered_out);
          v[`${key}:alerts`] = fmt(latest.violation_count);
        }
        // งานเฝ้าพื้นที่ (กล้องรุ่นเก่าที่ยังรวมไว้ในงานหมวกก็อ่านค่าชุดเดียวกัน)
        if (task.task_type === 'area_presence' || (task.task_type === 'ppe_compliance' && !findTask(camera, 'area_presence'))) {
          v[`${key}:people`] = fmt(latest.people_count);
          v[`${key}:filtered`] = fmt(latest.filtered_out);
          v[`${key}:absent`] = latest.seconds_since_person == null ? '—' : `${mmss(latest.seconds_since_person)} / ${mmss(ABSENT_LIMIT)}`;
          v[`${key}:clock`] = mmss(latest.seconds_since_person);
          v[`${key}:zonepeople`] = fmt(latest.workers_in_zone ?? latest.workers_in_pond);
          const presence = PRESENCE[latest.presence_status] || PRESENCE.unknown;
          v[`${key}:presence`] = presence.text;
          c[`${key}:presence`] = presence.cls;
          for (const name of ['attended', 'absent', 'unattended', 'break', 'blind']) c[`${key}:state:${name}`] = latest.presence_status === name ? 'on' : '';
        }
        if (task.task_type === 'activity_assessment') {
          v[`${key}:status`] = latest.assessment_status || '—';
          v[`${key}:count`] = fmt(latest.event_count);
        }
      }
    }
    return { v, c };
  }

  const PRESENCE = {
    attended: { cls: 'ok', text: 'มีคนอยู่' },
    absent: { cls: 'warn', text: 'ไม่พบคน · กำลังจับเวลา' },
    unattended: { cls: 'bad', text: 'แจ้งเตือน · ไม่พบคนเกิน 5 นาที' },
    break: { cls: 'info', text: 'ช่วงพัก · หยุดนับเวลา' },
    blind: { cls: '', text: 'ภาพดับ/มืด' },
    unknown: { cls: '', text: 'ยังไม่มีข้อมูล' },
  };
  const WEIGHT_TEXT = { measured: 'มีน้ำหนักยืนยัน', unavailable: 'ไม่มีน้ำหนักยืนยัน', scale_offline: 'ตาชั่งออฟไลน์', missing: 'ไม่พบน้ำหนักนิ่ง' };
  const ROUND_TEXT = { completed: 'ตรวจแล้ว', verify_required: 'ต้องตรวจสอบ', missed: 'พลาดรอบ', no_data: 'ไม่มีข้อมูล', waiting: 'รอตรวจ', upcoming: 'ยังไม่ถึง' };
  const ROUND_ICON = { completed: 'check', verify_required: 'scale', missed: 'alert', no_data: 'eyeoff', waiting: 'clock' };

  function applyValues() {
    const { v, c } = values();
    view.querySelectorAll('[data-v]').forEach((node) => {
      const text = v[node.dataset.v];
      if (text !== undefined && node.textContent !== text) node.textContent = text;
    });
    view.querySelectorAll('[data-c]').forEach((node) => {
      const cls = c[node.dataset.c];
      if (cls === undefined) return;
      const next = `${node.dataset.base || ''} ${cls}`.trim();
      if (node.className !== next) node.className = next;
    });
    view.querySelectorAll('[data-ring]').forEach((node) => {
      const [cameraId, taskId] = node.dataset.ring.split('|');
      const camera = S.cameras.find((item) => item.camera_id === cameraId);
      const latest = camera ? statusTask(camera, taskId).latest || {} : {};
      const seconds = num(latest.seconds_since_person);
      const fraction = seconds === null ? 0 : Math.min(1, seconds / ABSENT_LIMIT);
      const length = 2 * Math.PI * 76;
      node.setAttribute('stroke-dasharray', `${(fraction * length).toFixed(1)} ${length.toFixed(1)}`);
      node.setAttribute('stroke-opacity', fraction > 0 ? '1' : '0');
      node.setAttribute('stroke', fraction >= 1 ? 'var(--bad)' : latest.presence_status === 'attended' ? 'var(--ok)' : 'var(--warn)');
    });
  }

  // ---------- ชิ้นส่วน HTML ----------
  function shiftStrip() {
    const hour = bangkokHour();
    const on = hour >= 7 && hour < 18 ? 'day' : hour >= 18 && hour < 20 ? 'outside' : 'night';
    const name = { day: 'กะเช้า', outside: 'นอกกะ', night: 'กะดึก' }[on];
    return `<div class="shift-strip">
      <div class="top"><span>รอบรายงาน 07:00 → 08:00 วันถัดไป</span><span class="pill sm ${on === 'day' ? 'warn' : on === 'night' ? 'info' : ''}">${name}</span></div>
      <div class="shift-bar"><span class="day${on === 'day' ? ' on' : ''}"></span><span class="outside${on === 'outside' ? ' on' : ''}"></span><span class="night${on === 'night' ? ' on' : ''}"></span></div>
      <div class="shift-names"><div class="day"><b>กะเช้า</b><span class="mono">07–18</span></div><div class="outside"><b>นอกกะ</b><span class="mono">18–20</span></div><div class="night"><b>กะดึก</b><span class="mono">20–08</span></div></div>
    </div>`;
  }

  function pageHead(crumbs, title, meta) {
    return `<header class="page-head"><div>
      <div class="crumbs">${crumbs.join('<i>/</i>')}</div>
      <h1>${title}</h1>
      <div class="meta">${meta}</div>
    </div>${shiftStrip()}</header>`;
  }

  const pill = (state, extra = '') => `<span class="pill ${state.cls} ${extra}">${esc(state.text)}</span>`;
  const chip = (task, text, label) => `<span class="chip tone-${kindOf(task).tone}">${icon('cpu', 16)}${esc(text)}${label ? ` <em>${esc(label)}</em>` : ''}</span>`;

  function feed(camera, large = false) {
    const status = camera.status || {};
    const primary = isPrimary(camera);
    const live = primary || Boolean(camera.preview_url);
    const name = esc(camera.name);
    let inner;
    if (live) {
      inner = `<div class="ph">${icon('camera', 30, 1.5)}<b>กำลังรอภาพจาก ${name}</b><small>ระบบจะเชื่อมต่อใหม่โดยอัตโนมัติ</small></div>
        <img data-live="${esc(camera.camera_id)}" alt="ภาพสด ${name}${primary ? ' พร้อมกรอบตรวจจับ' : ''}">
        <div class="badges"><span class="fbadge live"><i></i>สด · ${name}</span></div>
        <div class="badges right">${primary
          ? '<span class="fbadge" data-v="live.cam" data-c="live.cam" data-base="fbadge">CAMERA —</span><span class="fbadge" data-v="live.ai" data-c="live.ai" data-base="fbadge">AI —</span>'
          : `<span class="fbadge" data-v="${esc(camera.camera_id)}:feed" data-c="${esc(camera.camera_id)}:feed" data-base="fbadge">กำลังรอภาพ</span><span class="fbadge">${camera.ai_pilot ? 'AI ทดลอง · เฝ้าคน 5 นาที' : 'AI ยังไม่เปิดใช้งาน'}</span>`}</div>`;
    } else {
      const text = camera.lifecycle === 'planned' ? 'ยังไม่เปิดใช้งานกล้องนี้' : status.camera_status === 'online' ? 'กล้องทำงานผ่าน worker แยก ภาพสดไม่ได้ส่งมาที่หน้านี้' : 'ไม่ได้รับสัญญาณจากกล้อง';
      inner = `<div class="ph">${icon('camera', 30, 1.5)}<span>${text}</span></div>
        <div class="badges"><span class="fbadge"><i></i>${name}</span></div>`;
    }
    if (status.source_signal?.signal === 'no_video') {
      inner += `<div class="blind"><span class="badge-icon" style="background:var(--bad-bg);color:var(--bad)">${icon('eyeoff', 18, 2)}</span><div><b>ภาพจากกล้องขาดหาย</b><small>DVR รายงาน NO VIDEO ช่วงนี้จะไม่นับเป็นศูนย์ ให้ตรวจสายกล้อง</small></div></div>`;
    }
    const cls = `${large ? ' large' : ''}${live ? '' : ' off'}`;
    return `<div class="feed${cls}" id="feed-${esc(camera.camera_id)}">${inner}</div>`;
  }

  function modelBox(camera, task) {
    const kind = kindOf(task);
    const st = taskState(camera, task);
    const model = statusTask(camera, task.task_id).model_version;
    const key = `${camera.camera_id}:${task.task_id}`;
    const rows = {
      line_crossing_count: [['นับได้<span data-v="rack.shiftName">กะนี้</span>', 'rack.shift'], ['ชั่วโมงนี้', 'rack.hour'], ['กำลังติดตาม', 'rack.tracks']],
      ppe_compliance: [['คนในภาพ', `${key}:people`], ['ไม่สวมหมวก', `${key}:no`], ['ไม่พบคนมาแล้ว', `${key}:absent`]],
      hourly_inspection: [['ตรวจล่าสุด', 'mag.last'], ['รอบนี้', 'mag.now'], ['น้ำหนัก', 'mag.weight']],
      activity_assessment: [['สถานะ', `${key}:status`], ['เหตุการณ์', `${key}:count`]],
    }[task.task_type] || [];
    return `<div class="model-box tone-${kind.tone}">
      <div class="mb-head"><span class="badge-icon">${icon(kind.icon, 18, 2.2)}</span><b>${esc(task.name)}</b></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">${chip(task, model || task.task_id)}${pill(st, 'sm')}</div>
      <div class="kv">${rows.map(([label, key2]) => `<div><span>${label}</span><b data-v="${esc(key2)}">—</b></div>`).join('')}</div>
    </div>`;
  }

  function camCard(camera) {
    const st = cameraState(camera);
    const tasks = camera.tasks || [];
    const title = tasks.length === 1 ? tasks[0].name : camera.name;
    return `<article class="cam-card${camera.lifecycle === 'planned' && !tasks.length ? ' planned' : ''}" id="card-${esc(camera.camera_id)}">
      ${feed(camera)}
      <div class="cam-info">
        <div class="cam-top">
          <div><div class="id"><span class="mono">${esc(camera.camera_id)}</span>${pill(st)}</div>
          <h3>${esc(title)}</h3><div class="loc">${esc(camera.location)}</div></div>
          <a class="btn primary" href="#/camera/${esc(camera.camera_id)}">เปิดหน้ากล้อง ${icon('arrow', 16, 2)}</a>
        </div>
        <div class="models">${tasks.map((task) => modelBox(camera, task)).join('') || '<p class="muted">ยังไม่ได้กำหนดงาน AI</p>'}</div>
      </div>
    </article>`;
  }

  // ---------- หน้าภาพรวม ----------
  function overview() {
    const cams = S.cameras;
    const stations = [];
    for (const camera of cams) {
      let group = stations.find((item) => item.id === camera.station_id);
      if (!group) { group = { id: camera.station_id, name: stationName(camera), cameras: [] }; stations.push(group); }
      group.cameras.push(camera);
    }
    const taskCount = cams.reduce((sum, camera) => sum + (camera.tasks || []).length, 0);
    const today = new Intl.DateTimeFormat('th-TH', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: TZ }).format(new Date());
    let context = '';
    if (requestedStation) {
      const matched = stations.find((item) => item.id === requestedStation);
      context = `<div class="context-banner"><div><small>PCC STATION CONTEXT</small><b>${matched ? `กล้องของจุดงาน ${esc(matched.name)}` : `ยังไม่มีกล้องที่ผูกกับสถานี ${esc(requestedStation)}`}</b></div><span class="muted">${matched ? `${matched.cameras.length} กล้อง` : 'เพิ่มได้ที่ Camera Registry'}</span></div>`;
    }
    const tiles = `<section class="tiles" aria-label="สรุป">
      <div class="card tile"><div class="t-head"><span>กล้องที่ออนไลน์</span>${icon('camera', 20)}</div><div class="t-value"><b data-v="fleet.online">—</b><span>จาก ${cams.length} ตัว</span></div><small data-v="fleet.sub"></small></div>
      <div class="card tile tone-rack"><div class="t-head"><span>เก๊ะเข้าเตา · <span data-v="rack.shiftName">กะนี้</span></span>${icon('box', 20)}</div><div class="t-value"><b data-v="rack.shift">—</b><span>เก๊ะ</span></div><small data-v="rack.total"></small></div>
      <div class="card tile tone-mag"><div class="t-head"><span>รอบตรวจแม่เหล็กวันนี้</span>${icon('magnet', 20)}</div><div class="t-value"><b data-v="mag.done">—</b><span>/ 25 รอบ</span></div><small data-v="mag.sub"></small></div>
      <div class="card tile tone-ppe"><div class="t-head"><span>AI ประมวลผล</span>${icon('cpu', 20)}</div><div class="t-value"><b data-v="fps.inference">—</b><span>FPS</span></div><small data-v="fps.sub"></small></div>
    </section>`;
    // หมวดกล้องก่อน แล้วค่อยแยกจุดงานภายในหมวด — จุดงานเดียวกันอาจมีกล้องอยู่หลายหมวด
    const groups = camerasByGroup(cams);
    const sections = groups.map((group) => {
      const groupStations = [];
      for (const camera of group.cameras) {
        let station = groupStations.find((item) => item.id === camera.station_id);
        if (!station) { station = { id: camera.station_id, name: stationName(camera), cameras: [] }; groupStations.push(station); }
        station.cameras.push(camera);
      }
      const online = group.cameras.filter((camera) => ['ok', 'warn'].includes(cameraState(camera).cls)).length;
      return `<section class="cam-group tone-${group.tone}" id="group-${group.id}">
        <div class="group-head"><span class="badge-icon">${icon(group.icon, 20, 2.2)}</span>
          <div><h2>${esc(group.title)}</h2>${group.desc ? `<small>${esc(group.desc)}</small>` : ''}</div>
          <span class="pill sm no-dot">${group.cameras.length} กล้อง · ออนไลน์ ${online}</span></div>
        ${groupStations.map((station) => `<section class="station${station.id === requestedStation ? ' context' : ''}" data-station="${esc(station.id)}">
          <div class="station-head"><span class="num">จุดงาน</span><h2>${esc(station.name)}</h2><span>${station.cameras.length} กล้อง · ${station.cameras.reduce((sum, camera) => sum + (camera.tasks || []).length, 0)} งาน AI</span><hr></div>
          ${station.cameras.map(camCard).join('')}
        </section>`).join('')}
      </section>`;
    }).join('');
    const error = S.fleetError ? `<p class="err">${esc(S.fleetError)}</p>` : '';
    return pageHead(['Vision Monitor', 'ภาพรวม'], 'กล้องทั้งหมด',
      `<span>${today}</span><span>·</span><span>${groups.map((group) => `${esc(group.short)} ${group.cameras.length}`).join(' · ')} กล้อง · ${stations.length} จุดงาน · ${taskCount} งาน AI</span>`)
      + error + context + tiles + (sections || '<div class="card empty">กำลังโหลด Camera Registry</div>');
  }

  // ---------- หน้ากล้องนับเก๊ะ ----------
  function rackDetail(camera) {
    const task = findTask(camera, 'line_crossing_count');
    const st = cameraState(camera);
    return pageHead(
      ['Vision Monitor', '<a href="#/">ภาพรวม</a>', esc(stationName(camera))],
      `${esc(stationName(camera))} · ${esc(task.name)}`,
      `<span class="mono">${esc(camera.camera_id)}</span>${pill(st)}<span class="chip tone-rack">${icon('cpu', 16)}<span data-v="rack.model">—</span> <em>นับเก๊ะ</em></span>`)
      + `<div class="detail-top">
        <div class="col">
          ${feed(camera, true)}
          <div class="feed-tools"><button class="btn sm" id="refresh" type="button">${icon('refresh', 16)} รีเฟรช</button><button class="btn sm" id="fullscreen" type="button">${icon('expand', 16)} เต็มจอ</button><p class="err" id="message" role="status"></p></div>
          <section class="card">
        <div class="card-head" style="justify-content:flex-start;margin-bottom:14px"><span class="badge-icon tone-rack">${icon('cpu', 18, 2.2)}</span><h3 style="font-size:18px">โมเดลที่ใช้</h3></div>
        <ul class="health">
          <li><span>ไฟล์โมเดล</span><b data-v="rack.model">—</b></li>
          <li><span>งาน</span><b>${esc(task.task_id)} · ${esc(task.task_type)}</b></li>
          <li><span>สิ่งที่ตรวจ</span><b class="wrap" style="font-family:var(--body)">${esc(task.name)}</b></li>
          <li><span>ตำแหน่ง</span><b class="wrap" style="font-family:var(--body)">${esc(camera.location)}</b></li>
        </ul>
      </section>
        </div>
        <div class="col">
          <div class="card tone-rack">
            <div class="card-head"><span class="muted" style="font-weight:600">นับได้<span data-v="rack.shiftName">กะนี้</span></span><span class="pill sm info no-dot">จากเหตุการณ์ที่บันทึกจริง</span></div>
            <div class="count-big" style="margin-top:6px"><b data-v="rack.shift">—</b><span>เก๊ะ</span></div>
            <div class="muted" style="margin-top:4px">ชั่วโมงนี้ <b class="mono" data-v="rack.hour" style="color:var(--ink)">—</b> เก๊ะ</div>
            <div class="shift-rows" id="shift-rows"></div>
          </div>
          <div class="card">
            <div class="card-head" style="margin-bottom:8px"><h3 style="font-size:17px">ความพร้อมของระบบ</h3></div>
            <ul class="health">
              <li><span><i class="dot" data-c="dvr" data-base="dot"></i>สัญญาณจาก DVR</span><b data-v="dvr.text">—</b></li>
              <li><span><i class="dot" data-c="health.camera" data-base="dot"></i>กล้อง</span><b data-v="fps.camera">—</b></li>
              <li><span><i class="dot" data-c="health.ai" data-base="dot"></i>AI ตรวจจับ</span><b><span data-v="fps.inference">—</span> FPS</b></li>
              <li><span>กำลังติดตาม</span><b><span data-v="rack.tracks">—</span> เก๊ะ</b></li>
              <li><span>เหตุการณ์ล่าสุด</span><b data-v="rack.last">—</b></li>
              <li><span>ยอดสะสมของบริการ</span><b style="display:flex;align-items:center;gap:10px"><span data-v="rack.service">—</span><button class="btn sm danger" id="reset-count" type="button">รีเซ็ต</button></b></li>
            </ul>
          </div>
        </div>
      </div>
      <section class="card col" id="count-report" aria-label="ยอดนับรายชั่วโมง">
        <div class="card-head">
          <div><h2>ยอดนับรายชั่วโมง</h2><span class="muted">แยกรายชั่วโมงและรายกะ นับจากเหตุการณ์ที่บันทึกไว้จริง</span></div>
          <div class="date-nav">
            <button type="button" id="rack-prev" aria-label="วันก่อนหน้า">‹</button>
            <label><span id="rack-date-label">—</span><input id="rack-date" type="date" aria-label="เลือกวันที่"></label>
            <button type="button" id="rack-next" aria-label="วันถัดไป">›</button>
            <button type="button" class="text" id="rack-today">วันนี้</button>
          </div>
        </div>
        <p class="err" id="count-error" role="status"></p>
        <div class="hours" id="hours"></div>
        <div class="shift-band"><div class="day">กะเช้า 07–18</div><div class="outside">นอกกะ</div><div class="night">กะดึก 20–08</div></div>
        <div class="legend"><span><i style="border-color:var(--rack);background:var(--rack)"></i>เก๊ะที่นับได้</span><span><i style="border-color:#9DBBFF;background:#9DBBFF"></i>ชั่วโมงปัจจุบัน</span><span><i style="border:0;height:4px;background:var(--line-2)"></i>ยังไม่ถึงเวลา</span></div>
      </section>`;
  }

  // การ์ดสัญญาณภาพ: FPS ที่รับจาก DVR ของกล้องนี้ เทียบกับกล้องนับเก๊ะในจังหวะเดียวกัน
  function sourceCard(camera) {
    if (!camera.status?.source_stats) return '';
    const id = esc(camera.camera_id);
    const dot = (key) => `<i class="dot" data-c="${key}" data-base="dot"></i>`;
    const primary = primaryCamera();
    return `<div class="card">
      <div class="card-head" style="margin-bottom:8px"><h3 style="font-size:17px">สัญญาณภาพจากกล้อง</h3><span class="muted" style="font-size:12px">อัปเดตทุก 10 วินาที</span></div>
      <ul class="health">
        <li><span>${dot(`${id}:src.fps`)}FPS ที่รับจาก DVR</span><b data-v="${id}:src.fps">—</b></li>
        <li><span>${dot(`${id}:src.gap`)}ภาพขาดช่วงนานสุด (10 วิ)</span><b data-v="${id}:src.gap">—</b></li>
        <li><span>ภาพล่าสุด</span><b data-v="${id}:src.age">—</b></li>
        <li><span>ต่อสตรีมใหม่ตั้งแต่เปิดระบบ</span><b data-v="${id}:src.reconnects">—</b></li>
        <li><span>ความละเอียดสตรีม</span><b data-v="${id}:src.res">—</b></li>
        <li><span>AI ประมวลผล</span><b data-v="${id}:src.ai">—</b></li>
        ${primary ? `<li><span>${dot('health.camera')}เทียบ: ${esc(primary.name)} (หอโรยยาง)</span><b data-v="fps.camera">—</b></li>` : ''}
      </ul>
      <p class="muted" style="font-size:12px;margin:10px 0 0">ถ้าทั้งสองกล้องตกพร้อมกัน ปัญหาอยู่ที่เครือข่าย/เครื่องนี้ · ถ้าตกกล้องเดียว ปัญหาอยู่ที่กล้องหรือ DVR ตัวนั้น
      (กล้องนี้ใช้ substream ซึ่งใช้ข้อมูลน้อยกว่า)</p>
    </div>`;
  }

  // ---------- หน้ากล้องหลายงาน (บ่อสุดท้าย) ----------
  function multiDetail(camera) {
    const st = cameraState(camera);
    const tasks = camera.tasks || [];
    const ppe = findTask(camera, 'ppe_compliance');
    // การ์ดคนประจำจุดอ่านจากงานเฝ้าพื้นที่ ถ้าทะเบียนยังไม่แยกงานก็ใช้งานหมวกแทน
    const area = findTask(camera, 'area_presence') || ppe;
    const areaMode = camera.status?.ai_mode === 'area';
    const magnet = findTask(camera, 'hourly_inspection');
    const letters = 'ABCDEFG';
    const letterOf = (task) => letters[tasks.indexOf(task)] || '';
    const chips = tasks.map((task) => chip(task, task.task_id, letterOf(task))).join('');

    const legend = areaMode
      ? '<div class="legend"><span><i style="border-color:#5AC83C"></i>พื้นที่ทำงาน (นับเฉพาะคนที่เท้าอยู่ในกรอบ)</span><span><i style="border-color:#3CAA2E"></i>คนในพื้นที่</span><span><i style="border-color:#787878"></i>คนนอกพื้นที่ (ไม่นับ)</span></div>'
      : `<div class="legend">
      ${ppe ? '<span><i style="border-color:#22A45D"></i>สวมหมวก</span><span><i style="border-color:#E0483D"></i>ไม่สวมหมวก</span><span><i style="border-color:#8B929C"></i>ตัดสินไม่ได้ (ไม่นับเป็นการฝ่าฝืน)</span>' : ''}</div>`;

    let presence = '';
    if (area) {
      const key = `${camera.camera_id}:${area.task_id}`;
      const model = statusTask(camera, area.task_id).model_version;
      const r = 76;
      const stateRow = (name, cls, ic, title, text) => `<div class="state" data-c="${esc(key)}:state:${name}" data-base="state"><span class="si" style="background:var(--${cls}-bg);color:var(--${cls})">${icon(ic, 16, 2)}</span><div><b>${title}</b><small>${text}</small></div></div>`;
      presence = `<div class="card col tone-${kindOf(area).tone}">
        <div class="card-head"><div style="display:flex;align-items:center;gap:10px"><span class="badge-icon">${icon('person', 17, 2.2)}</span><h3 style="font-size:18px">คนประจำจุด</h3></div><span class="pill sm" data-c="${esc(key)}:presence" data-base="pill sm" data-v="${esc(key)}:presence">—</span></div>
        ${camera.ai_pilot ? `<div class="muted" style="font-size:13px">คนในพื้นที่บ่อ <b data-v="${esc(key)}:zonepeople">—</b> คน · ทั้งภาพ <b data-v="${esc(key)}:people">—</b> คน · กรองกล่องหลอกออก <b data-v="${esc(key)}:filtered">—</b>${model ? ` · โมเดล <span class="mono">${esc(model)}</span>` : ''}</div>` : ''}
        <div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap">
          <div class="ring"><svg width="170" height="170" viewBox="0 0 176 176" aria-hidden="true"><circle cx="88" cy="88" r="${r}" fill="none" stroke="var(--line)" stroke-width="14"></circle><circle data-ring="${esc(camera.camera_id)}|${esc(area.task_id)}" cx="88" cy="88" r="${r}" fill="none" stroke="var(--warn)" stroke-width="14" stroke-linecap="round" stroke-dasharray="0 478"></circle></svg>
            <div class="inner"><b data-v="${esc(key)}:clock">—</b><small>จากเกณฑ์ ${mmss(ABSENT_LIMIT)}</small></div></div>
          <div class="grow" style="min-width:140px"><b style="display:block;margin-bottom:4px">เฝ้าคนในพื้นที่บ่อสุดท้าย · เกณฑ์ 5 นาที</b><span class="muted" style="font-size:13px">ครบเวลาแล้วบันทึกแจ้งเตือน และแจ้งซ้ำทุก 10 นาทีจนกว่าจะกลับมา</span></div>
        </div>
        <div class="states">
          ${stateRow('attended', 'ok', 'check', 'มีคนอยู่', 'เห็นคนต่อเนื่อง 3 ครั้ง ถือว่ากลับมาแล้ว รีเซ็ตเวลา')}
          ${stateRow('absent', 'warn', 'clock', 'ไม่พบคน', 'เริ่มจับเวลา ครบ 5 นาทีส่งแจ้งเตือน')}
          ${stateRow('unattended', 'bad', 'alert', 'เกิน 5 นาที', 'แจ้งเตือนแล้ว และแจ้งซ้ำถ้ายังไม่พบคน')}
          ${stateRow('break', 'info', 'clock', 'ช่วงพักเที่ยง', 'ไม่นับเวลาและไม่เตือน หมดพักเริ่มนับ 5 นาทีใหม่')}
          ${stateRow('blind', 'none', 'eyeoff', 'ภาพดับหรือมืด', 'หยุดนับ ไม่ถือว่าคนหายจากจุด')}
        </div>
        <div style="display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted);padding-top:12px;border-top:1px solid var(--line)">${icon('chat', 15)}ช่องทางแจ้งเตือน: WhatsApp <span class="pill sm no-dot" style="margin-left:auto">ยังไม่เชื่อมต่อ</span></div>
      </div>`;
    }

    const modelHead = (task, title) => {
      const kind = kindOf(task);
      const model = statusTask(camera, task.task_id).model_version;
      return `<div class="model-head"><div class="l"><span class="badge-icon lg">${icon(kind.icon, 22, 2.2)}</span><div><div class="k">โมเดล ${letterOf(task)}</div><h2>${esc(title || task.name)}</h2></div></div>
        <div class="r">${chip(task, model || task.task_id)}${pill(taskState(camera, task), 'sm')}</div></div>`;
    };

    let ppePanel = '';
    if (ppe) {
      const key = `${camera.camera_id}:${ppe.task_id}`;
      const model = statusTask(camera, ppe.task_id).model_version;
      const rule = (text) => `<div>${icon('check', 14, 2.4)}<span>${text}</span></div>`;
      ppePanel = `<section class="card col grow tone-ppe" style="gap:20px">
        ${modelHead(ppe, 'ตรวจหมวกนิรภัย')}
        ${areaMode ? '<div class="note">ยังไม่เปิดตรวจหมวก · รอเทรนโมเดลหมวกด้วยภาพจากกล้องนี้ ตอนนี้กล้องนี้ทำเฉพาะงานเฝ้าพื้นที่ (ไม่มีคนเกิน 5 นาที)</div>'
          : camera.ai_pilot ? '<div class="note">AI ตรวจหมวกยังเป็นการทดลองจาก best_PEE_V1.pt และไม่แจ้งเตือนเรื่องหมวก · ระบบเฝ้าคนประจำบ่อและแจ้งเตือนเมื่อไม่พบคน 5 นาที · ยังไม่มีโมเดลคันโยกแม่เหล็ก</div>' : ''}
        <div class="metrics4">
          <div class="cell"><div class="metric"><span>คนในภาพ</span><div><b data-v="${esc(key)}:people">—</b><small>คน</small></div></div></div>
          <div class="cell ok"><div class="metric"><span>สวมหมวก</span><div><b data-v="${esc(key)}:pass">—</b><small>คน</small></div></div></div>
          <div class="cell bad"><div class="metric"><span>ไม่สวม</span><div><b data-v="${esc(key)}:no">—</b><small>คน</small></div></div></div>
          ${camera.ai_pilot
            ? `<div class="cell none"><div class="metric"><span>ยังไม่แน่ชัด</span><div><b data-v="${esc(key)}:undecided">—</b><small>คน</small></div></div></div>`
            : `<div class="cell none"><div class="metric"><span>แจ้งเตือนแล้ว</span><div><b data-v="${esc(key)}:alerts">—</b><small>ครั้ง</small></div></div></div>`}
        </div>
        ${camera.ai_pilot && !areaMode ? `<div style="display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted)">${icon('check', 15)}กรองกล่องที่ไม่ใช่คนออก <b class="mono" style="color:var(--ink)" data-v="${esc(key)}:filtered">—</b> กล่องในภาพนี้ (เครื่องจักร เสา หรือคะแนนต่ำ)</div>` : ''}
        ${camera.ai_pilot ? '' : `<div class="rules"><span>เกณฑ์การตัดสิน</span>
          ${rule('ต้องเห็นไม่สวมหมวกต่อเนื่อง 2.5 วินาที (8 เฟรม) จึงแจ้งเตือน')}
          ${rule('หมวกต้องอยู่ในส่วนบน 40% ของกรอบตัวคน')}
          ${rule('คนที่สูงไม่ถึง 8% ของภาพ → ตัดสินไม่ได้ ไม่นับเป็นการฝ่าฝืน')}
          ${rule('ความมั่นใจของโมเดลขั้นต่ำ 0.5')}
        </div>`}
        ${model ? '' : `<div class="note">${icon('cpu', 16)}<span>ยังไม่มีโมเดล · กำลังเก็บภาพทำ dataset คลาส <b class="mono">person · helmet · head</b></span></div>`}
      </section>`;
    }

    let magPanel = '';
    if (magnet) {
      const legendRounds = Object.entries(ROUND_TEXT).map(([key, text]) => `<span><i class="round ${key}" style="height:12px;width:12px;border-radius:3px;display:inline-block"></i>${text}</span>`).join('');
      magPanel = `<section class="card col grow tone-mag" style="gap:20px">
        ${modelHead(magnet)}
        <div class="last-check" id="last-check"><span class="muted">กำลังโหลดรอบตรวจ</span></div>
        <div class="col" style="gap:12px">
          <div class="card-head"><b>รอบวันรายงาน <span class="muted" style="font-weight:400">07:00 → 08:00 · 25 รอบ</span></b>
            <div class="date-nav">
              <button type="button" id="mag-prev" aria-label="วันก่อนหน้า">‹</button>
              <label><span id="mag-date-label">—</span><input id="mag-date" type="date" aria-label="เลือกวันที่"></label>
              <button type="button" id="mag-next" aria-label="วันถัดไป">›</button>
            </div></div>
          <p class="err" id="mag-error" role="status"></p>
          <div class="rounds" id="rounds"></div>
          <div class="round-legend">${legendRounds}</div>
          <div class="tally" id="tally"></div>
        </div>
      </section>`;
    }

    const filters = [['all', 'ทั้งหมด', '']].concat(tasks.map((task) => [task.task_id, `โมเดล ${letterOf(task)} · ${kindOf(task).short}`, `tone-${kindOf(task).tone}`]));
    const events = `<section class="card col" style="gap:6px">
      <div class="card-head" style="padding-bottom:8px"><h2>เหตุการณ์ของกล้องนี้</h2>
        <div class="seg" id="event-filter">${filters.map(([id, text, tone]) => `<button type="button" data-filter="${esc(id)}" class="${tone}${S.eventFilter === id ? ' on' : ''}">${esc(text)}</button>`).join('')}</div></div>
      <div class="events" id="events"><div class="empty">กำลังโหลดเหตุการณ์</div></div>
    </section>`;

    return pageHead(
      ['Vision Monitor', '<a href="#/">ภาพรวม</a>', esc(stationName(camera))],
      String(camera.name).startsWith(stationName(camera)) ? esc(camera.name) : `${esc(stationName(camera))} · ${esc(camera.name)}`,
      `<span class="mono">${esc(camera.camera_id)}</span>${pill(st)}${chips}`)
      + `<div class="${presence ? 'detail-top' : 'col'}"><div class="col">${feed(camera, true)}${legend}<span class="muted" style="font-size:12px">${esc(camera.location)}</span>${sourceCard(camera)}</div>${presence}</div>`
      + (ppePanel || magPanel ? `<div class="row stack-md">${ppePanel}${magPanel}</div>` : '')
      + events;
  }

  // ---------- วาดหน้า ----------
  function structureKey() {
    const r = route();
    return JSON.stringify([r, S.cameras.map((camera) => [camera.camera_id, camera.lifecycle, camera.preview_url, cameraState(camera).text,
      (camera.status?.tasks || []).map((task) => [task.runtime_status, task.model_version])]), S.fleetError]);
  }

  function render() {
    const r = route();
    S.structure = structureKey();
    document.querySelectorAll('.nav-link[data-route]').forEach((link) => {
      const on = (r.view === 'overview' && link.dataset.route === 'overview') || (r.view === 'camera' && link.dataset.route === `camera:${r.id}`);
      link.classList.toggle('active', on);
    });
    if (r.view === 'camera') {
      const camera = S.cameras.find((item) => item.camera_id === r.id);
      if (!camera) {
        view.innerHTML = S.cameras.length ? `<div class="card empty">ไม่พบกล้อง ${esc(r.id)} ในทะเบียน · <a href="#/">กลับหน้าภาพรวม</a></div>` : '<div class="card empty">กำลังโหลด Camera Registry</div>';
        return;
      }
      document.title = `${camera.name} · Vision Monitor`;
      view.innerHTML = findTask(camera, 'line_crossing_count') ? rackDetail(camera) : multiDetail(camera);
      bindDetail(camera);
    } else {
      document.title = 'Vision Monitor · กล้อง AI โรงงาน';
      view.innerHTML = overview();
      if (requestedStation) view.querySelector(`[data-station="${CSS.escape(requestedStation)}"]`)?.scrollIntoView({ block: 'start' });
    }
    view.querySelectorAll('img[data-live]').forEach((img) => {
      const url = S.blobUrls.get(img.dataset.live);
      if (url) { img.src = url; img.classList.add('ready'); }
    });
    applyValues();
  }

  function renderNav() {
    const host = $('nav-cameras');
    const r = route();
    host.innerHTML = camerasByGroup(S.cameras).map((group) => `<div class="nav-sub tone-${group.tone}">${icon(group.icon, 14, 2.2)}<span>${esc(group.title)}</span><em>${group.cameras.length}</em></div>`
      + group.cameras.map((camera) => {
        const st = cameraState(camera);
        // จุดงานเดียวกันมีหลายกล้อง ใช้ชื่อกล้องแทน ไม่งั้นเมนูจะซ้ำกัน
        const shared = S.cameras.filter((item) => item.station_id === camera.station_id).length > 1;
        const label = shared ? camera.name : stationName(camera);
        const on = r.view === 'camera' && r.id === camera.camera_id;
        return `<a class="nav-link${on ? ' active' : ''}" data-route="camera:${esc(camera.camera_id)}" href="#/camera/${esc(camera.camera_id)}">${icon('camera')}<span><span>${esc(label)}</span><span class="sub">${esc(camera.camera_id)}</span></span><i class="dot ${st.cls}" title="${esc(st.text)}"></i></a>`;
      }).join('')).join('');
  }

  // ---------- ผูกปุ่มของหน้ารายละเอียด ----------
  function bindDetail(camera) {
    if ($('fullscreen')) {
      $('fullscreen').onclick = async () => {
        try {
          if (document.fullscreenElement) await document.exitFullscreen();
          else await $(`feed-${camera.camera_id}`).requestFullscreen();
        } catch (_) { notify('เบราว์เซอร์นี้เปิดภาพเต็มจอไม่ได้', true); }
      };
    }
    if ($('refresh')) {
      $('refresh').onclick = () => { restartLive(); loadFleet(); notify('กำลังตรวจสอบกล้องและ AI อีกครั้ง'); };
    }
    if ($('reset-count')) {
      $('reset-count').onclick = () => {
        if (!window.confirm('ยืนยันรีเซ็ตจำนวนเก๊ะสะสมของบริการเป็น 0?\n(ยอดรายชั่วโมงและรายกะที่บันทึกไว้จะไม่หาย)')) return;
        api('/api/rack-counter/reset', { method: 'POST' })
          .then((response) => response.json())
          .then(() => { notify('รีเซ็ตจำนวนเก๊ะสะสมแล้ว'); loadDaily(); })
          .catch((error) => notify(error.message, true));
      };
    }
    if ($('hours')) {
      $('rack-prev').onclick = () => loadRackView(RC.shiftDate(S.rackView?.date || todayKey(), -1));
      $('rack-next').onclick = () => loadRackView(RC.shiftDate(S.rackView?.date || todayKey(), 1));
      $('rack-today').onclick = () => loadRackView(null);
      $('rack-date').onchange = (event) => { if (event.target.value) loadRackView(event.target.value); };
      fillRack();
      if (S.rackDate) loadRackView(S.rackDate);
    }
    if ($('rounds')) {
      $('mag-prev').onclick = () => loadMagnetView(RC.shiftDate(S.magnetView?.date || todayKey(), -1));
      $('mag-next').onclick = () => loadMagnetView(RC.shiftDate(S.magnetView?.date || todayKey(), 1));
      $('mag-date').onchange = (event) => { if (event.target.value) loadMagnetView(event.target.value); };
      fillMagnet();
      if (S.magnetDate) loadMagnetView(S.magnetDate);
    }
    if ($('events')) {
      $('event-filter').onclick = (event) => {
        const button = event.target.closest('button[data-filter]');
        if (!button) return;
        S.eventFilter = button.dataset.filter;
        $('event-filter').querySelectorAll('button').forEach((node) => node.classList.toggle('on', node === button));
        fillEvents(camera);
      };
      $('events').onclick = (event) => {
        const button = event.target.closest('button[data-evidence]');
        if (button) openEvidence(button.dataset.evidence);
      };
      if (S.eventsFor === camera.camera_id) fillEvents(camera);
      loadEvents(camera);
    }
  }

  const todayKey = () => S.dailyToday?.date || S.magnetToday?.date || null;

  // ---------- ยอดนับเก๊ะ ----------
  async function loadDaily() {
    try {
      S.dailyToday = await RC.loadDaily(null);
      if (!S.rackDate) S.rackView = S.dailyToday;
      fillRack();
      applyValues();
    } catch (error) {
      if ($('count-error')) $('count-error').textContent = `โหลดยอดนับไม่สำเร็จ: ${error.message}`;
    }
  }

  async function loadRackView(dateKey) {
    const today = todayKey();
    S.rackDate = dateKey && dateKey !== today ? dateKey : null;
    if (!S.rackDate) { S.rackView = S.dailyToday; fillRack(); return; }
    $('count-report')?.classList.add('is-loading');
    try {
      S.rackView = await RC.loadDaily(S.rackDate);
      fillRack();
    } catch (error) {
      if ($('count-error')) $('count-error').textContent = `โหลดยอดนับไม่สำเร็จ: ${error.message}`;
    } finally {
      $('count-report')?.classList.remove('is-loading');
    }
  }

  function fillRack() {
    if ($('shift-rows') && S.dailyToday) RC.renderShiftRows($('shift-rows'), S.dailyToday);
    const data = S.rackView;
    if (!$('hours') || !data) return;
    const today = todayKey();
    $('rack-date-label').textContent = RC.thaiDate(data.date);
    $('rack-date').value = data.date;
    $('rack-next').disabled = Boolean(today) && data.date >= today;
    $('rack-today').disabled = data.date === today;
    $('count-error').textContent = data.storage === 'unavailable' ? 'ยังไม่มีที่เก็บเหตุการณ์ ตัวเลขจึงเป็นศูนย์ทั้งหมด' : '';
    RC.renderHours($('hours'), data);
  }

  // ---------- รอบตรวจแม่เหล็ก ----------
  async function loadMagnet() {
    try {
      S.magnetToday = await RC.loadMagnet(null);
      S.magnetError = null;
      if (!S.magnetDate) S.magnetView = S.magnetToday;
    } catch (error) {
      S.magnetError = error.status === 404 ? 'ยังไม่มีกล้องที่ทำงานตรวจแม่เหล็กในทะเบียน' : `โหลดไม่สำเร็จ (${error.message})`;
    }
    fillMagnet();
    applyValues();
  }

  async function loadMagnetView(dateKey) {
    const today = todayKey();
    S.magnetDate = dateKey && dateKey !== today ? dateKey : null;
    if (!S.magnetDate) { S.magnetView = S.magnetToday; fillMagnet(); return; }
    try {
      S.magnetView = await RC.loadMagnet(S.magnetDate);
      fillMagnet();
    } catch (error) {
      if ($('mag-error')) $('mag-error').textContent = `โหลดรอบตรวจไม่สำเร็จ: ${error.message}`;
    }
  }

  function fillMagnet() {
    if (!$('rounds')) return;
    const data = S.magnetView;
    if (!data) {
      $('mag-error').textContent = S.magnetError || '';
      return;
    }
    const today = todayKey();
    $('mag-date-label').textContent = RC.thaiDate(data.date);
    $('mag-date').value = data.date;
    $('mag-next').disabled = Boolean(today) && data.date >= today;
    $('mag-error').textContent = data.storage === 'unavailable' ? 'ยังไม่มีที่เก็บเหตุการณ์' : '';
    $('rounds').innerHTML = data.rounds.map((round) => {
      const text = ROUND_TEXT[round.status] || round.status;
      const extra = round.checked_at ? ` · ตรวจเมื่อ ${when(round.checked_at, false)}` : '';
      return `<div class="round ${esc(round.status)}" title="${esc(round.label)}${round.next_day ? ' (วันถัดไป)' : ''} · ${esc(text)}${esc(extra)}"><b>${String(round.hour).padStart(2, '0')}</b><span style="height:13px;display:flex">${ROUND_ICON[round.status] ? icon(ROUND_ICON[round.status], 13, 2.2) : ''}</span></div>`;
    }).join('');
    const t = data.tally || {};
    $('tally').innerHTML = `<span>ตรวจแล้ว <b>${t.completed ?? 0}</b></span><span>ต้องตรวจสอบ <b>${t.verify_required ?? 0}</b></span><span>พลาดรอบ <b>${t.missed ?? 0}</b></span><span>ไม่มีข้อมูล <b>${t.no_data ?? 0}</b></span>`
      + `<span>อัตราตรวจครบ <b>${data.compliance === null || data.compliance === undefined ? '—' : `${(data.compliance * 100).toFixed(0)}%`}</b> <small>(ไม่นับรอบที่กล้องมองไม่เห็น)</small></span>`;

    const done = data.rounds.filter((round) => round.checked_at);
    const last = done[done.length - 1];
    const box = $('last-check');
    if (!last) {
      box.innerHTML = `<span class="ic" style="color:var(--muted)">${icon('clock', 20, 2)}</span><div class="txt"><small>ตรวจล่าสุด</small><b>วันนี้ยังไม่มีการยกคันโยก</b></div>`;
      return;
    }
    const inspection = (last.inspections || [])[0] || {};
    const held = num(inspection.lever_held_seconds);
    const weight = last.weight_source === 'measured' && num(last.weight_kg) !== null
      ? `<span class="pill sm ok">${fmt(last.weight_kg, 1)} กก.</span>`
      : `<span class="pill sm warn">${esc(WEIGHT_TEXT[last.weight_source] || 'ไม่มีน้ำหนักยืนยัน')}</span>`;
    box.innerHTML = `<span class="ic" style="color:var(--ok)">${icon('check', 20, 2.4)}</span>
      <div class="txt"><small>ตรวจล่าสุด · รอบ ${esc(last.label.slice(0, 5))}</small><b>${esc(when(last.checked_at))}${held !== null ? ` · ยกคันโยกค้าง <span class="mono">${held.toFixed(1)}</span> วินาที` : ''}</b></div>${weight}`;
  }

  // ---------- เหตุการณ์ ----------
  const EVENT_TEXT = {
    ppe_violation: ['พบคนไม่สวมหมวก', 'bad', 'เปิดอยู่'],
    ppe_resolved: ['กลับมาสวมหมวกแล้ว', 'ok', 'แก้ไขแล้ว'],
    station_unattended: ['ไม่พบคนในพื้นที่บ่อเกิน 5 นาที · AI ทดลอง', 'bad', 'ตรวจสอบ'],
    station_attended: ['มีคนกลับมาประจำจุด', 'ok', 'กลับมาแล้ว'],
    magnet_inspection: ['ยกคันโยกตรวจแม่เหล็ก', 'ok', 'ตรวจแล้ว'],
    activity_assessed: ['ประเมินสถานะงาน', 'info', 'บันทึก'],
    rack_counted: ['นับเก๊ะ', 'info', 'บันทึก'],
  };

  async function loadEvents(camera) {
    const epoch = S.epoch;
    try {
      let cursor = 0;
      const found = [];
      // API เรียงจากเก่าไปใหม่ จึงไล่หน้าจนหมด แล้วเก็บเฉพาะของกล้องนี้
      for (let page = 0; page < 20; page += 1) {
        const response = await api(`/api/v1/events?station_id=${encodeURIComponent(camera.station_id)}&limit=500&cursor=${cursor}`);
        const data = await response.json();
        found.push(...data.items.filter((item) => item.camera_id === camera.camera_id));
        cursor = data.next_cursor;
        if (!data.has_more) break;
      }
      if (epoch !== S.epoch) return;
      S.events = found.slice(-200).reverse();
      S.eventsFor = camera.camera_id;
      fillEvents(camera);
    } catch (error) {
      if ($('events')) $('events').innerHTML = `<div class="empty">โหลดเหตุการณ์ไม่สำเร็จ: ${esc(error.message)}</div>`;
    }
  }

  function eventDetail(item) {
    const p = item.payload || {};
    if (item.type === 'magnet_inspection') {
      const parts = [];
      if (num(p.lever_held_seconds) !== null) parts.push(`ยกค้าง ${Number(p.lever_held_seconds).toFixed(1)} วินาที`);
      parts.push(p.weight_source === 'measured' && num(p.weight_kg) !== null ? `น้ำหนัก ${fmt(p.weight_kg, 1)} กก.` : WEIGHT_TEXT[p.weight_source] || '');
      if (p.inspection_status) parts.push(ROUND_TEXT[p.inspection_status] || p.inspection_status);
      return parts.filter(Boolean).join(' · ');
    }
    if (item.type === 'station_unattended' || item.type === 'station_attended') {
      return `ไม่พบคน ${mmss(p.absent_seconds)}${p.repeat ? ' · แจ้งซ้ำ' : ''}${p.review_required ? ' · โปรดตรวจภาพยืนยัน' : ''}`;
    }
    if (item.type === 'ppe_violation') return `ยืนยันแล้ว ${fmt(p.confirmed_seconds, 1)} วินาที · คนที่ #${esc(p.track_id ?? '—')}`;
    if (item.type === 'ppe_resolved') return `คนที่ #${esc(p.track_id ?? '—')}`;
    return item.model_version ? `โมเดล ${item.model_version}` : '';
  }

  function fillEvents(camera) {
    const host = $('events');
    if (!host) return;
    const items = S.events.filter((item) => S.eventFilter === 'all' || item.task_id === S.eventFilter).slice(0, 50);
    if (!items.length) {
      host.innerHTML = `<div class="empty">${camera.ai_pilot ? 'ยังไม่มีเหตุการณ์เฝ้าคนบ่อสุดท้าย' : camera.lifecycle === 'planned' ? 'กล้องนี้ยังไม่เปิดใช้งาน เหตุการณ์จะเริ่มแสดงเมื่อ worker ส่งข้อมูลเข้ามา' : 'ยังไม่มีเหตุการณ์'}</div>`;
      return;
    }
    host.innerHTML = items.map((item) => {
      const task = (camera.tasks || []).find((entry) => entry.task_id === item.task_id) || { task_type: '' };
      const kind = kindOf(task);
      const [title, cls, label] = EVENT_TEXT[item.type] || [item.type, '', 'บันทึก'];
      const evidence = item.payload?.evidence_image
        ? ` <button type="button" class="linkish" data-evidence="${esc(item.payload.evidence_image)}">ดูภาพหลักฐาน</button>` : '';
      return `<div class="event tone-${kind.tone}"><time>${esc(when(item.occurred_at))}</time><span class="model"><i></i>${esc(kind.short)}</span><span><b>${esc(title)}</b><small>${esc(eventDetail(item))}${evidence}</small></span><span class="pill sm ${cls}">${esc(label)}</span></div>`;
    }).join('');
  }

  // ภาพหลักฐานต้องผ่าน token เหมือน API อื่น จึงโหลดด้วย fetch แล้วเปิดเป็น blob
  // แทนการใส่ลิงก์ตรง ซึ่งเบราว์เซอร์จะยิงโดยไม่มี Authorization header
  async function openEvidence(name) {
    const viewer = window.open('', '_blank');
    try {
      const response = await api(`/api/v1/final-pond/evidence/${encodeURIComponent(name)}`);
      const url = URL.createObjectURL(await response.blob());
      if (viewer) viewer.location.href = url; else window.location.href = url;
    } catch (error) {
      if (viewer) viewer.close();
      notify(`เปิดภาพหลักฐานไม่สำเร็จ: ${error.message}`);
    }
  }

  // ---------- ภาพสด และสถานะจาก websocket ----------
  function setLiveImages(cameraId, url) {
    view.querySelectorAll('img[data-live]').forEach((img) => {
      if (img.dataset.live !== cameraId) return;
      img.src = url;
      img.classList.add('ready');
    });
  }

  async function frames(run) {
    const lastPoll = new Map();
    while (run === S.epoch) {
      if (!document.hidden) {
        const visible = [...new Set([...view.querySelectorAll('img[data-live]')].map((img) => img.dataset.live))];
        for (const cameraId of visible) {
          const camera = S.cameras.find((item) => item.camera_id === cameraId);
          if (!camera) continue;
          const due = isPrimary(camera) ? 250 : 65;
          if (Date.now() - (lastPoll.get(cameraId) || 0) < due) continue;
          lastPoll.set(cameraId, Date.now());
          try {
            const response = await api(camera.preview_url || '/api/live/frame');
            const blob = await response.blob();
            if (run !== S.epoch) return;
            const next = URL.createObjectURL(blob);
            setLiveImages(cameraId, next);
            const old = S.blobUrls.get(cameraId);
            if (old) URL.revokeObjectURL(old);
            S.blobUrls.set(cameraId, next);
            S.previewReady.add(cameraId);
            if ($('message') && route().id === cameraId) $('message').textContent = '';
          } catch (error) {
            if ($('message') && route().id === cameraId) $('message').textContent = `โหลดภาพสดไม่ได้: ${error.message}`;
            view.querySelectorAll('img[data-live]').forEach((img) => {
              if (img.dataset.live === cameraId) img.classList.remove('ready');
            });
            S.previewReady.delete(cameraId);
          }
        }
        applyValues();
      }
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
  }

  let lastCount = null;
  function metadata(run) {
    if (run !== S.epoch) return;
    setConnection('warn', 'กำลังเชื่อมต่อ');
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${protocol}://${location.host}/ws/rack-counter`);
    S.socket = ws;
    ws.onopen = () => ws.send(JSON.stringify({ token: S.token }));
    ws.onmessage = (event) => {
      if (run !== S.epoch) return;
      try {
        S.snapshot = JSON.parse(event.data);
        const ready = Boolean(S.snapshot.running);
        setConnection(ready ? 'ok' : 'bad', ready ? 'ระบบทำงานปกติ' : 'กล้องหรือ AI ไม่พร้อม');
        // ยอดขยับเมื่อไหร่ ดึงยอดรายชั่วโมงใหม่ทันที ไม่ต้องรอรอบหนึ่งนาที
        const counted = Number(S.snapshot.rack_count) || 0;
        if (lastCount !== null && counted !== lastCount) loadDaily();
        lastCount = counted;
        applyValues();
      } catch (error) { notify(`อ่านสถานะระบบไม่ได้: ${error.message}`, true); }
    };
    ws.onerror = () => setConnection('bad', 'การเชื่อมต่อมีปัญหา');
    ws.onclose = (event) => {
      if (run !== S.epoch) return;
      setConnection('bad', 'การเชื่อมต่อขาด');
      if (event.code !== 1008) setTimeout(() => metadata(run), 3000);
      else notify('API token ไม่ถูกต้อง หรือ origin นี้ไม่ได้รับอนุญาต', true);
    };
  }

  function restartLive() {
    S.epoch += 1;
    if (S.socket) S.socket.close();
    metadata(S.epoch);
    frames(S.epoch);
  }

  // ---------- ทะเบียนกล้อง ----------
  async function loadFleet() {
    try {
      const response = await api('/api/v1/cameras');
      const payload = await response.json();
      S.cameras = Array.isArray(payload.items) ? payload.items : [];
      S.fleetError = null;
    } catch (error) {
      S.fleetError = `โหลด Camera Registry ไม่สำเร็จ: ${error.message}`;
    }
    renderNav();
    if (structureKey() !== S.structure) render();
    else applyValues();
  }

  async function loadSystemLinks() {
    try {
      const response = await api('/api/v1/system-links');
      const links = await response.json();
      if (typeof links.pcc === 'string') $('pcc-link').href = links.pcc;
    } catch (_) { /* ใช้ลิงก์ localhost เดิมไปก่อน */ }
  }

  function setClock() {
    $('clock').textContent = new Intl.DateTimeFormat('th-TH', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: TZ }).format(new Date());
  }

  $('connect').onsubmit = (event) => {
    event.preventDefault();
    S.token = $('token').value.trim();
    window.RackAuth.token = S.token;
    restartLive();
    loadFleet();
    loadDaily();
    loadMagnet();
  };

  window.addEventListener('hashchange', () => {
    S.rackDate = null; S.rackView = S.dailyToday;
    S.magnetDate = null; S.magnetView = S.magnetToday;
    S.eventFilter = 'all';
    render();
    renderNav();
    window.scrollTo(0, 0);
  });
  document.addEventListener('fullscreenchange', () => {
    const button = $('fullscreen');
    if (button) button.innerHTML = document.fullscreenElement ? '× ออกจากเต็มจอ' : `${icon('expand', 16)} เต็มจอ`;
  });

  setClock();
  setInterval(setClock, 1000);
  render();
  loadSystemLinks();
  $('connect').requestSubmit();
  setInterval(loadFleet, 10000);
  // รีเฟรชเบา ๆ ทุกนาที เผื่อไม่มีเหตุการณ์ใหม่แต่ชั่วโมงเดินไปแล้ว
  setInterval(() => { loadDaily(); loadMagnet(); }, 60000);
  setInterval(() => {
    const r = route();
    const camera = r.view === 'camera' && S.cameras.find((item) => item.camera_id === r.id);
    if (camera && $('events')) loadEvents(camera);
  }, 30000);
})();
