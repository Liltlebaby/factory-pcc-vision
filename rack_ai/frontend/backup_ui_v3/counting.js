/**
 * แผงยอดนับเก๊ะ รายชั่วโมงและรายกะ
 *
 * ดึงจาก /api/v1/rack-count/daily ซึ่งสรุปมาจากเหตุการณ์ที่บันทึกไว้จริง
 * ไม่ใช่ตัวนับสะสมในหน่วยความจำ ยอดจึงไม่หายเมื่อรีสตาร์ทบริการ
 *
 * วันรายงานหนึ่งวันคือ 07:00 ถึง 08:00 ของวันถัดไป รวม 25 ชั่วโมง แบ่งเป็น
 * กะเช้า 07:00–18:00 · นอกกะ 18:00–20:00 · กะดึก 20:00–08:00
 * ช่วง 18:00–20:00 ไม่ได้อยู่ในกะไหนตามที่โรงงานกำหนด จึงแสดงแยกให้เห็น
 * แทนที่จะซ่อนไว้ ไม่งั้นยอดรวมสองกะจะน้อยกว่ายอดจริงโดยไม่มีใครรู้
 */
(function () {
  const GROUP_STYLE = { day: 'is-day', outside: 'is-outside', night: 'is-night' };
  const state = { date: null, today: null, busy: false };

  const $ = (id) => document.getElementById(id);

  function authHeaders() {
    const token = (window.RackAuth && window.RackAuth.token) || '';
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  function shiftDate(key, days) {
    const [year, month, day] = key.split('-').map(Number);
    // ใช้ UTC ในการบวกลบวัน เพื่อไม่ให้ daylight saving หรือ timezone ของเบราว์เซอร์
    // ทำให้วันเลื่อน — ค่าที่ได้ใช้เป็นแค่คีย์ข้อความส่งกลับไปให้เซิร์ฟเวอร์
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

  function renderShifts(shifts, total) {
    const host = $('count-shifts');
    host.textContent = '';
    for (const shift of shifts) {
      const card = document.createElement('article');
      card.className = `shift-card ${GROUP_STYLE[shift.key] || ''}${shift.current ? ' is-current' : ''}`;
      card.innerHTML = `
        <header><span>${shift.name}</span>${shift.current ? '<i>กำลังดำเนินอยู่</i>' : ''}</header>
        <strong>${shift.count.toLocaleString('th-TH')}</strong>
        <footer><span>${shift.label}</span><span>${shift.hours} ชม.</span></footer>`;
      host.appendChild(card);
    }
    const summary = document.createElement('article');
    summary.className = 'shift-card is-total';
    summary.innerHTML = `
      <header><span>รวมทั้งวันรายงาน</span></header>
      <strong>${total.toLocaleString('th-TH')}</strong>
      <footer><span>07:00 – 08:00 วันถัดไป</span><span>25 ชม.</span></footer>`;
    host.appendChild(summary);
  }

  function renderHours(hours) {
    const host = $('count-hours');
    host.textContent = '';
    const peak = Math.max(1, ...hours.map((hour) => hour.count));
    for (const hour of hours) {
      const cell = document.createElement('div');
      const group = hour.hour >= 7 && hour.hour < 18 && !hour.next_day ? 'day'
        : hour.hour >= 18 && hour.hour < 20 && !hour.next_day ? 'outside' : 'night';
      cell.className = `hour-cell ${GROUP_STYLE[group]}${hour.pending ? ' is-pending' : ''}`;
      // ชั่วโมงที่ยังมาไม่ถึงต้องดูต่างจากชั่วโมงที่ผ่านไปแล้วและนับได้ศูนย์
      cell.title = hour.pending
        ? `${hour.label} ยังไม่ถึงเวลา`
        : `${hour.label}${hour.next_day ? ' (วันถัดไป)' : ''} นับได้ ${hour.count} เก๊ะ`;
      const bar = document.createElement('span');
      bar.className = 'hour-bar';
      bar.style.height = hour.pending ? '4px' : `${Math.max(4, (hour.count / peak) * 100)}%`;
      const value = document.createElement('b');
      value.textContent = hour.pending ? '' : hour.count;
      const label = document.createElement('small');
      label.textContent = hour.label;
      cell.append(value, bar, label);
      host.appendChild(cell);
    }
  }

  async function load(dateKey) {
    if (state.busy) return;
    state.busy = true;
    $('count-report').classList.add('is-loading');
    try {
      const query = dateKey ? `?date=${encodeURIComponent(dateKey)}` : '';
      const response = await fetch(`/api/v1/rack-count/daily${query}`, {
        headers: authHeaders(), cache: 'no-store',
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();

      state.date = data.date;
      if (!state.today) state.today = data.date;
      $('count-date-label').textContent = thaiDate(data.date);
      $('count-date-input').value = data.date;
      $('count-next').disabled = data.date >= state.today;
      $('count-today').disabled = data.date === state.today;
      $('count-error').textContent = data.storage === 'unavailable'
        ? 'ยังไม่มีที่เก็บเหตุการณ์ — ตัวเลขด้านล่างจึงเป็นศูนย์ทั้งหมด'
        : '';
      renderShifts(data.shifts, data.total);
      renderHours(data.hours);
    } catch (error) {
      $('count-error').textContent = `โหลดยอดนับไม่สำเร็จ: ${error.message}`;
    } finally {
      state.busy = false;
      $('count-report').classList.remove('is-loading');
    }
  }

  function mount() {
    if (!$('count-report')) return;
    $('count-prev').onclick = () => load(shiftDate(state.date, -1));
    $('count-next').onclick = () => load(shiftDate(state.date, 1));
    $('count-today').onclick = () => load(state.today);
    $('count-date-input').onchange = (event) => {
      if (event.target.value) load(event.target.value);
    };
    load(null);
    // รีเฟรชเบา ๆ ทุกนาที เผื่อไม่มีเหตุการณ์ใหม่เข้ามาแต่ชั่วโมงเดินไปแล้ว
    setInterval(() => { if (state.date === state.today) load(state.date); }, 60000);
  }

  window.RackCounting = {
    mount,
    refresh() { load(state.date); },
    /** เรียกเมื่อยอดสะสมขยับ — อัปเดตเฉพาะตอนดูวันปัจจุบันอยู่ */
    onCount() { if (state.date && state.date === state.today) load(state.date); },
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
})();
