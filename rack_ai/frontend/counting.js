/**
 * ข้อมูลยอดนับเก๊ะ และรอบตรวจแม่เหล็ก สำหรับหน้า Vision Monitor
 *
 * ยอดนับดึงจาก /api/v1/rack-count/daily ซึ่งสรุปจากเหตุการณ์ที่บันทึกไว้จริง
 * ไม่ใช่ตัวนับในหน่วยความจำ ยอดจึงไม่หายเมื่อรีสตาร์ทบริการ
 *
 * วันรายงานคือ 07:00 ถึง 08:00 ของวันถัดไป รวม 25 ชั่วโมง
 *   กะเช้า 07:00–18:00 · นอกกะ 18:00–20:00 · กะดึก 20:00–08:00
 * ช่วง 18:00–20:00 ไม่อยู่ในกะไหน จึงแสดงแยกให้เห็น ไม่งั้นยอดสองกะรวมกัน
 * จะน้อยกว่ายอดจริงโดยไม่มีใครรู้
 */
(function () {
  const SHIFT_COLOR = { day: 'var(--day)', outside: 'var(--outside)', night: 'var(--night)' };

  function authHeaders() {
    const token = (window.RackAuth && window.RackAuth.token) || '';
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  async function getJson(path) {
    const response = await fetch(path, { headers: authHeaders(), cache: 'no-store' });
    if (!response.ok) {
      const error = new Error(`HTTP ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return response.json();
  }

  const query = (dateKey) => (dateKey ? `?date=${encodeURIComponent(dateKey)}` : '');

  function shiftDate(key, days) {
    const [year, month, day] = key.split('-').map(Number);
    // บวกลบวันด้วย UTC เพื่อไม่ให้ timezone ของเบราว์เซอร์ทำให้วันเลื่อน
    const moment = new Date(Date.UTC(year, month - 1, day));
    moment.setUTCDate(moment.getUTCDate() + days);
    return moment.toISOString().slice(0, 10);
  }

  function thaiDate(key) {
    const [year, month, day] = key.split('-').map(Number);
    return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString('th-TH', {
      weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
    });
  }

  const nowSeconds = () => Date.now() / 1000;
  const currentShift = (data) => (data && data.shifts || []).find((shift) => shift.current) || null;
  const currentHour = (data) => {
    const now = nowSeconds();
    return (data && data.hours || []).find((hour) => hour.start <= now && now < hour.end) || null;
  };
  const fmt = (value) => (Number.isFinite(Number(value)) ? Number(value).toLocaleString('th-TH') : '—');

  function renderShiftRows(host, data) {
    host.textContent = '';
    for (const shift of data.shifts) {
      const row = document.createElement('div');
      if (shift.current) row.className = 'current';
      row.innerHTML = `<i style="background:${SHIFT_COLOR[shift.key] || 'var(--none)'}"></i>`
        + `<span class="name"></span><span class="time"></span>`
        + (shift.current ? '<span class="now">กำลังดำเนินอยู่</span>' : '')
        + '<b></b>';
      row.querySelector('.name').textContent = shift.name;
      row.querySelector('.time').textContent = shift.label;
      row.querySelector('b').textContent = fmt(shift.count);
      host.appendChild(row);
    }
    const total = document.createElement('div');
    total.className = 'total';
    total.innerHTML = '<span class="name">รวมทั้งวันรายงาน</span><span class="time">07:00 → 08:00</span><b></b>';
    total.querySelector('b').textContent = fmt(data.total);
    host.appendChild(total);
  }

  function renderHours(host, data) {
    host.textContent = '';
    const peak = Math.max(1, ...data.hours.map((hour) => hour.count));
    const now = currentHour(data);
    for (const hour of data.hours) {
      const cell = document.createElement('div');
      const isNow = now && now.start === hour.start;
      // ชั่วโมงที่ยังมาไม่ถึงต้องดูต่างจากชั่วโมงที่ผ่านไปแล้วและนับได้ศูนย์
      cell.className = `hour${hour.pending ? ' pending' : ''}${isNow ? ' current' : ''}`;
      cell.title = hour.pending
        ? `${hour.label}${hour.next_day ? ' (วันถัดไป)' : ''} ยังไม่ถึงเวลา`
        : `${hour.label}${hour.next_day ? ' (วันถัดไป)' : ''} นับได้ ${hour.count} เก๊ะ`;
      const value = document.createElement('span');
      value.className = 'val';
      value.textContent = hour.pending ? '' : String(hour.count);
      const track = document.createElement('div');
      track.className = 'track';
      const bar = document.createElement('div');
      bar.className = 'bar';
      bar.style.height = hour.pending ? '100%' : `${Math.max(2, (hour.count / peak) * 100)}%`;
      track.appendChild(bar);
      const label = document.createElement('small');
      label.textContent = hour.label.slice(0, 2);
      cell.append(value, track, label);
      host.appendChild(cell);
    }
  }

  window.RackCounting = {
    loadDaily: (dateKey) => getJson(`/api/v1/rack-count/daily${query(dateKey)}`),
    loadMagnet: (dateKey) => getJson(`/api/v1/final-pond/magnet-rounds${query(dateKey)}`),
    getJson,
    shiftDate,
    thaiDate,
    currentShift,
    currentHour,
    renderShiftRows,
    renderHours,
    fmt,
  };
})();
