/**
 * Admin — Analytics: active users (daily / weekly / monthly), registrations, new vs returning,
 * feature usage and guests vs registered, with date-range filters and dependency-free SVG charts.
 * Numbers come from /api/admin/analytics (anonymous counters; guests have no accounts).
 */

const AN_COLORS = { registered: '#2563eb', guest: '#f59e0b', new: '#16a34a', returning: '#9333ea',
                    features: ['#2563eb', '#16a34a', '#f59e0b', '#ef4444', '#9333ea'] };
let anState = { days: 30, start: '', end: '', interval: 'day' };

const anN = (v) => Number(v || 0).toLocaleString('en-IN');

async function admLoadAnalytics() {
  const cards = document.getElementById('admAnCards');
  if (!cards) return;
  admShowLoading(cards);
  const qs = new URLSearchParams({ interval: anState.interval });
  if (anState.start && anState.end) { qs.set('start', anState.start); qs.set('end', anState.end); }
  else qs.set('days', String(anState.days));
  try {
    const d = await admFetch(`/api/admin/analytics?${qs}`);
    anRender(d);
  } catch (err) {
    if (admHandleAuthError(err)) return;
    admShowError(cards, err.message);
  }
}

function anRender(d) {
  document.getElementById('admAnStart').value = d.start;
  document.getElementById('admAnEnd').value = d.end;
  document.getElementById('admAnSub').textContent = `${d.start} to ${d.end} · days are counted in UTC`;
  const note = document.getElementById('admAnNotice');
  if (!d.tracking_started) note.textContent = 'No usage has been recorded yet. Visits and feature use are counted from the moment this update went live; registrations come from account records.';
  else if (d.tracking_started > d.start) note.textContent = `Usage tracking started on ${d.tracking_started}, so earlier days show no activity. Registrations come from account records and cover every day.`;
  else note.textContent = '';

  const s = d.summary, t = d.range_totals;
  const card = (label, value, sub, cls = '') => `<div class="adm-card"><div class="adm-card-label">${label}</div><div class="adm-card-value ${cls}">${value}</div><div class="adm-card-sub">${sub || ''}</div></div>`;
  document.getElementById('admAnCards').innerHTML =
    card('Daily active users', anN(s.dau), `${anN(s.dau_registered)} registered · ${anN(s.dau_guest)} guests · on ${d.end}`, 'accent') +
    card('Weekly active users', anN(s.wau), `${anN(s.wau_registered)} registered · ${anN(s.wau_guest)} guests · 7 days`) +
    card('Monthly active users', anN(s.mau), `${anN(s.mau_registered)} registered · ${anN(s.mau_guest)} guests · 30 days`) +
    card('New registrations', anN(t.new_registrations), 'in the selected range', 'green') +
    card('Returning users', anN(t.returning_users), `${anN(t.new_active_users)} were new to the site`) +
    card('Guests', anN(t.active_guest), 'distinct guest sessions') +
    card('Feature uses', anN(t.feature_uses), 'searches and plans created');

  const labels = d.series.map(x => x.label);
  anLine('admChartActive', labels, [
    { name: 'Registered', color: AN_COLORS.registered, values: d.series.map(x => x.active_registered) },
    { name: 'Guests', color: AN_COLORS.guest, values: d.series.map(x => x.active_guest) },
  ]);
  anBars('admChartNew', labels, [{ name: 'New registrations', color: AN_COLORS.new, values: d.series.map(x => x.new_registrations) }]);
  anBars('admChartReturning', labels, [
    { name: 'Returning', color: AN_COLORS.returning, values: d.series.map(x => x.returning_users) },
    { name: 'New to the site', color: AN_COLORS.new, values: d.series.map(x => Math.max(0, x.active_registered - x.returning_users)) },
  ], true);
  anHBars('admChartFeatures', d.features);
  anDonut('admChartSplit', [
    { name: 'Registered', color: AN_COLORS.registered, value: t.active_registered },
    { name: 'Guests', color: AN_COLORS.guest, value: t.active_guest },
  ], 'people');
  anLine('admChartFeatureTrend', labels, d.features.map((f, i) => ({
    name: f.label, color: AN_COLORS.features[i % AN_COLORS.features.length], values: d.series.map(x => x.features[f.key] || 0),
  })));
}

/* ---------------------------------------------------------------- tiny SVG chart helpers (all text escaped) */
const AN_W = 640, AN_H = 230, AN_L = 38, AN_R = 12, AN_T = 12, AN_B = 34;

function anNiceMax(v) {
  if (v <= 4) return 4;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  return Math.ceil(v / p) * p;
}
function anAxes(labels, max) {
  const iw = AN_W - AN_L - AN_R, ih = AN_H - AN_T - AN_B;
  let g = '';
  for (let i = 0; i <= 4; i++) {
    const y = AN_T + ih - (ih * i) / 4;
    g += `<line x1="${AN_L}" x2="${AN_W - AN_R}" y1="${y}" y2="${y}" class="an-grid"/><text x="${AN_L - 6}" y="${y + 4}" class="an-tick" text-anchor="end">${anN(Math.round((max * i) / 4))}</text>`;
  }
  const step = Math.max(1, Math.ceil(labels.length / 8));
  labels.forEach((l, i) => {
    if (i % step) return;
    const x = AN_L + (labels.length === 1 ? iw / 2 : (iw * i) / (labels.length - 1));
    g += `<text x="${x}" y="${AN_H - 12}" class="an-tick" text-anchor="middle">${admEscape(l)}</text>`;
  });
  return g;
}
function anLegend(series) {
  return `<div class="an-legend">${series.map(s => `<span><i style="background:${s.color}"></i>${admEscape(s.name)}</span>`).join('')}</div>`;
}
function anEmpty(el, msg = 'No data in this range yet.') { el.innerHTML = `<div class="adm-set-desc" style="padding:24px 0;text-align:center;">${admEscape(msg)}</div>`; }

function anLine(id, labels, series) {
  const el = document.getElementById(id);
  const all = series.flatMap(s => s.values);
  if (!labels.length || !all.some(v => v > 0)) return anEmpty(el);
  const max = anNiceMax(Math.max(...all)), iw = AN_W - AN_L - AN_R, ih = AN_H - AN_T - AN_B;
  const X = (i) => AN_L + (labels.length === 1 ? iw / 2 : (iw * i) / (labels.length - 1));
  const Y = (v) => AN_T + ih - (ih * v) / max;
  const lines = series.map(s => {
    const pts = s.values.map((v, i) => `${X(i)},${Y(v)}`).join(' ');
    const dots = s.values.map((v, i) => `<circle cx="${X(i)}" cy="${Y(v)}" r="${labels.length > 40 ? 0 : 3}" fill="${s.color}"><title>${admEscape(s.name)} · ${admEscape(labels[i])}: ${anN(v)}</title></circle>`).join('');
    return `<polyline points="${pts}" fill="none" stroke="${s.color}" stroke-width="2.2" stroke-linejoin="round"/>${dots}`;
  }).join('');
  el.innerHTML = `<svg viewBox="0 0 ${AN_W} ${AN_H}" class="an-svg" role="img">${anAxes(labels, max)}${lines}</svg>${anLegend(series)}`;
}

function anBars(id, labels, series, stacked = false) {
  const el = document.getElementById(id);
  const totals = labels.map((_, i) => series.reduce((a, s) => a + s.values[i], 0));
  if (!labels.length || !totals.some(v => v > 0)) return anEmpty(el);
  const max = anNiceMax(stacked ? Math.max(...totals) : Math.max(...series.flatMap(s => s.values)));
  const iw = AN_W - AN_L - AN_R, ih = AN_H - AN_T - AN_B, slot = iw / labels.length;
  const bw = Math.max(2, (slot * 0.7) / (stacked ? 1 : series.length));
  let bars = '';
  labels.forEach((l, i) => {
    let acc = 0;
    series.forEach((s, k) => {
      const v = s.values[i], h = (ih * v) / max;
      const x = AN_L + slot * i + slot * 0.15 + (stacked ? 0 : bw * k);
      const y = AN_T + ih - h - (stacked ? (ih * acc) / max : 0);
      if (v > 0) bars += `<rect x="${x}" y="${y}" width="${bw}" height="${h}" rx="2" fill="${s.color}"><title>${admEscape(s.name)} · ${admEscape(l)}: ${anN(v)}</title></rect>`;
      acc += v;
    });
  });
  el.innerHTML = `<svg viewBox="0 0 ${AN_W} ${AN_H}" class="an-svg" role="img">${anAxes(labels.map(String), max)}${bars}</svg>${series.length > 1 ? anLegend(series) : ''}`;
}

function anHBars(id, features) {
  const el = document.getElementById(id);
  const max = Math.max(1, ...features.map(f => f.total));
  if (!features.some(f => f.total > 0)) return anEmpty(el);
  el.innerHTML = features.map(f => `
    <div class="an-hrow"><div class="an-hlabel">${admEscape(f.label)}</div>
      <div class="an-hbar" title="${admEscape(f.label)}: ${anN(f.registered)} registered, ${anN(f.guest)} guest">
        <span style="width:${(f.registered / max) * 100}%;background:${AN_COLORS.registered}"></span><span style="width:${(f.guest / max) * 100}%;background:${AN_COLORS.guest}"></span>
      </div><div class="an-hval">${anN(f.total)}</div></div>`).join('') +
    anLegend([{ name: 'Registered', color: AN_COLORS.registered }, { name: 'Guests', color: AN_COLORS.guest }]);
}

function anDonut(id, parts, unit) {
  const el = document.getElementById(id);
  const total = parts.reduce((a, p) => a + p.value, 0);
  if (!total) return anEmpty(el);
  const R = 62, C = 2 * Math.PI * R;
  let off = 0;
  const arcs = parts.map(p => {
    const len = (p.value / total) * C;
    const a = `<circle cx="90" cy="90" r="${R}" fill="none" stroke="${p.color}" stroke-width="26" stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-off}" transform="rotate(-90 90 90)"><title>${admEscape(p.name)}: ${anN(p.value)} ${unit}</title></circle>`;
    off += len; return a;
  }).join('');
  el.innerHTML = `<div class="an-donut"><svg viewBox="0 0 180 180" class="an-donut-svg" role="img">${arcs}<text x="90" y="88" text-anchor="middle" class="an-donut-n">${anN(total)}</text><text x="90" y="106" text-anchor="middle" class="an-tick">${unit}</text></svg>
    <div class="an-donut-legend">${parts.map(p => `<div><i style="background:${p.color}"></i>${admEscape(p.name)}: <b>${anN(p.value)}</b> (${Math.round((p.value / total) * 100)}%)</div>`).join('')}</div></div>`;
}

/* ---------------------------------------------------------------- controls */
document.addEventListener('DOMContentLoaded', () => {
  const presets = document.getElementById('admAnPresets');
  presets?.addEventListener('click', (e) => {
    const b = e.target.closest('[data-days]'); if (!b) return;
    anState.days = Number(b.dataset.days); anState.start = ''; anState.end = '';
    presets.querySelectorAll('.adm-pill-btn').forEach(x => x.classList.toggle('active', x === b));
    admLoadAnalytics();
  });
  document.getElementById('admAnApply')?.addEventListener('click', () => {
    const s = document.getElementById('admAnStart').value, e = document.getElementById('admAnEnd').value;
    if (!s || !e) return admToast('Pick both a start and an end date.', 'error');
    anState.start = s; anState.end = e;
    presets?.querySelectorAll('.adm-pill-btn').forEach(x => x.classList.remove('active'));
    admLoadAnalytics();
  });
  const iv = document.getElementById('admAnInterval');
  iv?.addEventListener('click', (e) => {
    const b = e.target.closest('[data-interval]'); if (!b) return;
    anState.interval = b.dataset.interval;
    iv.querySelectorAll('.adm-pill-btn').forEach(x => x.classList.toggle('active', x === b));
    admLoadAnalytics();
  });
  document.getElementById('admAnRefresh')?.addEventListener('click', admLoadAnalytics);
});
