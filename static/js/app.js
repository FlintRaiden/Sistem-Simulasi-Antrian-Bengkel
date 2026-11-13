(() => {
  const $ = (id) => document.getElementById(id);
  const RANDOM_IDS = ['n_cars','mean_interarrival','reg_mean','reg_std','service_mean','service_std','pay_mean','pay_std','seed'];
  const MANUAL_IDS = ['arrivals','reg','service','pay'];
  const st = { mode: 'random', result: null, step: -1, timer: null, chart: null };

  // ---- init
  const D = window.DEFAULTS || {};
  RANDOM_IDS.forEach((k) => { if (D[k] !== undefined) $(k).value = D[k]; });
  $('discipline').value = D.discipline || 'FIFO';

  function setMode(m) {
    st.mode = m;
    $('form-random').classList.toggle('hidden', m !== 'random');
    $('form-manual').classList.toggle('hidden', m !== 'manual');
    $('tab-random').classList.toggle('active', m === 'random');
    $('tab-manual').classList.toggle('active', m === 'manual');
  }
  $('tab-random').onclick = () => setMode('random');
  $('tab-manual').onclick = () => setMode('manual');

  // ---- run
  async function run() {
    stopPlay();
    const err = $('error'); err.classList.add('hidden');
    const payload = { mode: st.mode, discipline: $('discipline').value };
    RANDOM_IDS.forEach((k) => { payload[k] = $(k).value; });
    MANUAL_IDS.forEach((k) => { payload[k] = $(k).value; });
    $('btn-run').disabled = true;
    try {
      const res = await fetch('/api/simulate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Simulasi gagal dijalankan.');
      st.result = data; st.step = -1;
      renderCards(); renderTable(); renderChart(); renderViz();
      ['btn-next','btn-play','btn-reset','btn-csv'].forEach((id) => { $(id).disabled = false; });
    } catch (e) {
      err.textContent = e.message; err.classList.remove('hidden');
    } finally { $('btn-run').disabled = false; }
  }
  $('btn-run').onclick = run;

  // ---- visualisasi
  const chips = (el, list, cur) => {
    el.innerHTML = list.length ? list.map((c) => `<span class="chip${c === cur ? ' cur' : ''}">${c}</span>`).join('') : '<span class="empty-q">kosong</span>';
  };
  const status = (el, txt) => {
    el.textContent = txt;
    el.className = 'status ' + (txt.startsWith('IDLE') ? 'idle' : 'busy');
  };
  function renderViz() {
    const log = st.result ? st.result.log : [];
    const r = st.step >= 0 ? log[st.step] : null;
    const cur = r ? r.car : null;
    chips($('n-reg'), r ? r.reg_queue : [], cur);
    chips($('n-wait'), r ? r.wait_queue : [], cur);
    chips($('n-pay'), r ? r.pay_queue : [], cur);
    status($('n-recep'), r ? r.recep : 'IDLE');
    status($('n-m1'), r ? r.m1 : 'IDLE');
    status($('n-m2'), r ? r.m2 : 'IDLE');
    $('n-done').textContent = r ? r.done : 0;
    $('v-done').textContent = r ? r.done : 0;
    $('v-clock').textContent = r ? r.clock : 0;
    $('v-event').textContent = r ? `${r.event} ${r.car}` : '-';
    $('v-step').textContent = `${st.step + 1} / ${log.length}`;
    if (r) $('v-detail').textContent = `${r.car}: ${r.detail}`;
    else if (st.result) $('v-detail').textContent = 'Kondisi awal. Tekan Next event untuk memulai.';
    document.querySelectorAll('#log-body tr').forEach((tr, i) => {
      tr.classList.toggle('current', i === st.step);
      tr.classList.toggle('future', i > st.step);
    });
    const row = document.querySelector('#log-body tr.current');
    if (row) {
      const w = $('tablewrap');
      w.scrollTop = row.offsetTop - w.clientHeight / 2;
    }
  }
  function next() {
    if (!st.result) return;
    if (st.step < st.result.log.length - 1) { st.step++; renderViz(); }
    else stopPlay();
  }
  function stopPlay() {
    if (st.timer) { clearInterval(st.timer); st.timer = null; }
    $('btn-play').textContent = 'Auto play';
  }
  function togglePlay() {
    if (st.timer) { stopPlay(); return; }
    if (st.step >= st.result.log.length - 1) st.step = -1;
    $('btn-play').textContent = 'Pause';
    st.timer = setInterval(next, parseInt($('speed').value, 10));
  }
  $('btn-next').onclick = () => { stopPlay(); next(); };
  $('btn-play').onclick = togglePlay;
  $('speed').onchange = () => { if (st.timer) { stopPlay(); togglePlay(); } };
  $('btn-reset').onclick = () => { stopPlay(); st.step = -1; renderViz(); };

  // ---- kartu statistik
  function renderCards() {
    const s = st.result.stats;
    const items = [
      ['Total mobil dilayani', s.total_served, ''],
      ['Rata-rata waktu tunggu (ruang tunggu)', s.avg_wait, 'menit'],
      ['Waktu tunggu maksimum', s.max_wait, 'menit'],
      ['Total waktu simulasi', s.total_time, 'menit'],
      ['Utilisasi Montir 1', s.util_m1, '%'],
      ['Utilisasi Montir 2', s.util_m2, '%'],
      ['Utilisasi resepsionis/kasir', s.util_recep, '%'],
      ['Rata-rata waktu di bengkel', s.avg_time_in_system, 'menit'],
    ];
    $('cards').innerHTML = items.map(([l, v, u]) =>
      `<div class="card"><div class="lab">${l}</div><div class="val">${v}<span class="unit">${u}</span></div></div>`).join('');
  }

  // ---- tabel
  const q = (a) => (a.length ? a.join(', ') : '-');
  function renderTable() {
    $('log-body').innerHTML = st.result.log.map((r) =>
      `<tr class="future"><td>${r.no}</td><td>${r.clock}</td><td>${r.event}</td><td>${r.car}</td><td>${r.detail}</td>` +
      `<td>${q(r.wait_queue)}</td><td>${r.m1}</td><td>${r.m2}</td><td>${r.recep}</td><td>${r.wait === null ? '-' : r.wait}</td></tr>`).join('');
  }

  // ---- grafik
  function renderChart() {
    const s = st.result.series;
    const ds = (label, key, color) => ({ label, data: s.map((p) => ({ x: p.clock, y: p[key] })), stepped: true, borderColor: color, backgroundColor: color, borderWidth: 2, pointRadius: 0, tension: 0 });
    if (st.chart) st.chart.destroy();
    st.chart = new Chart($('chart'), {
      type: 'line',
      data: { datasets: [ds('Ruang tunggu bengkel', 'wait', '#1D4E89'), ds('Antrian resepsionis', 'reg', '#C77700'), ds('Antrian kasir', 'pay', '#2F7D57')] },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode: 'nearest', intersect: false },
        scales: {
          x: { type: 'linear', title: { display: true, text: 'Clock (menit)' } },
          y: { beginAtZero: true, ticks: { precision: 0 }, title: { display: true, text: 'Jumlah mobil dalam antrian' } },
        },
      },
    });
  }

  // ---- CSV
  $('btn-csv').onclick = () => {
    const head = ['No','Clock (Menit)','Event Type','ID Mobil','Detail Aktivitas','Antrian Resepsionis','Isi Antrian Tunggu','Antrian Kasir','Status Montir 1','Status Montir 2','Status Resepsionis/Kasir','Waktu Tunggu Mobil'];
    const esc = (v) => `"${String(v).replace(/"/g, '""')}"`;
    const lines = [head.map(esc).join(',')].concat(st.result.log.map((r) =>
      [r.no, r.clock, r.event, r.car, r.detail, q(r.reg_queue), q(r.wait_queue), q(r.pay_queue), r.m1, r.m2, r.recep, r.wait === null ? '' : r.wait].map(esc).join(',')));
    const blob = new Blob(['\ufeff' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `log_simulasi_bengkel_${st.result.params.discipline}.csv`;
    a.click(); URL.revokeObjectURL(a.href);
  };

  renderViz();
})();
