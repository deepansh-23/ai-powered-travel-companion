/**
 * Admin — AI & API Usage monitor: AI requests by model and feature, successes, failures and response times,
 * external API usage with quota warnings, estimated AI spend, limits and alerts.
 * Numbers come from /api/admin/usage. Costs are estimates at list prices; nothing here shows API keys.
 */

const ADM_US_API = '/api/admin/usage';
let usState = { days: 30, start: '', end: '' };
let usData = null;

const usN = (v) => Number(v || 0).toLocaleString('en-IN');
const usMs = (v) => (v || v === 0 ? (v >= 1000 ? (v / 1000).toFixed(1) + ' s' : Math.round(v) + ' ms') : '—');
const usUsd = (v) => (v === null || v === undefined ? '—' : '$' + (v < 1 ? v.toFixed(4) : v.toFixed(2)));
const usFeature = (f) => ({ itinerary: 'Itinerary Planner', area: 'Area Guide', cafes: 'Quiet Work Cafés', medical: '24/7 Medical Care', places: 'Places Near You', export: 'Exports', auth: 'Sign-in', other: 'Other' }[f] || f);

async function admLoadUsage() {
  const cards = document.getElementById('admUsCards');
  if (!cards) return;
  admShowLoading(cards);
  const qs = new URLSearchParams();
  if (usState.start && usState.end) { qs.set('start', usState.start); qs.set('end', usState.end); } else qs.set('days', String(usState.days));
  try {
    usData = await admFetch(`${ADM_US_API}?${qs}`);
    usRender(usData);
    usLoadSettings();
  } catch (err) {
    if (admHandleAuthError(err)) return;
    admShowError(cards, err.message);
  }
}

function usRender(d) {
  document.getElementById('admUsStart').value = d.start;
  document.getElementById('admUsEnd').value = d.end;
  document.getElementById('admUsSub').textContent = `${d.start} to ${d.end} · days are counted in UTC · costs are estimates at list prices`;
  const note = document.getElementById('admUsNotice');
  note.textContent = !d.tracking_started
    ? 'No calls have been recorded yet. Counting starts when this update goes live and the first AI or API call is made.'
    : (d.tracking_started > d.start ? `Counting started on ${d.tracking_started}, so earlier days are empty.` : '');

  // alerts
  const icon = { critical: '🔴', warning: '🟠', info: 'ℹ️' };
  document.getElementById('admUsAlerts').innerHTML = d.alerts.length
    ? `<div class="us-alerts">${d.alerts.map(a => `<div class="us-alert us-${admEscape(a.level)}"><b>${icon[a.level] || ''} ${admEscape(a.title)}</b><span>${admEscape(a.detail)}</span></div>`).join('')}</div>`
    : '<div class="us-alert us-ok"><b>✅ No alerts</b><span>Usage is within your limits and traffic looks normal.</span></div>';

  const s = d.summary;
  const card = (label, value, sub, cls = '') => `<div class="adm-card"><div class="adm-card-label">${label}</div><div class="adm-card-value ${cls}">${value}</div><div class="adm-card-sub">${sub || ''}</div></div>`;
  document.getElementById('admUsCards').innerHTML =
    card('AI requests', usN(s.ai_requests), `${usN(s.ai_ok)} succeeded · ${usN(s.ai_failed)} failed`, 'accent') +
    card('AI success rate', s.success_rate === null ? '—' : s.success_rate + '%', 'of AI calls in this range', s.success_rate !== null && s.success_rate < 90 ? 'red' : 'green') +
    card('AI response time', usMs(s.avg_ms), `average · slowest 5% about ${usMs(s.p95_ms)} (recent)`) +
    card('Estimated AI spend', usUsd(s.est_cost_usd), s.est_cost_inr !== null ? `≈ ₹${usN(Math.round(s.est_cost_inr))} · list prices, may be free on a free tier` : 'no model prices set') +
    card('AI tokens', usN(s.tokens_in + s.tokens_out), `${usN(s.tokens_in)} in · ${usN(s.tokens_out)} out`) +
    card('External API calls', usN(s.external_requests), `${usN(s.external_failed)} failed`);

  const labels = d.series.map(x => x.label);
  anBars('admUsChartCalls', labels, [
    { name: 'AI ok', color: '#2563eb', values: d.series.map(x => x.ai_ok) },
    { name: 'AI failed', color: '#ef4444', values: d.series.map(x => x.ai_failed) },
    { name: 'External ok', color: '#16a34a', values: d.series.map(x => x.external_ok) },
    { name: 'External failed', color: '#f59e0b', values: d.series.map(x => x.external_failed) },
  ], true);
  anBars('admUsChartCost', labels, [{ name: 'Estimated cost (USD)', color: '#9333ea', values: d.series.map(x => x.cost_usd) }]);

  const table = (head, body, empty) => body ? `<table class="adm-table"><thead><tr>${head.map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table>` : `<div class="adm-set-desc" style="padding:12px 0;">${empty}</div>`;
  document.getElementById('admUsModels').innerHTML = table(
    ['Model', 'Requests', 'Succeeded', 'Failed', 'Avg time', 'Slowest', 'Tokens in', 'Tokens out', 'Est. cost'],
    d.by_model.map(m => `<tr><td><code>${admEscape(m.model)}</code></td><td>${usN(m.requests)}</td><td>${usN(m.ok)}</td><td>${m.failed ? `<span class="adm-badge badge-inactive">${usN(m.failed)}</span>` : 0}</td>
      <td>${usMs(m.avg_ms)}</td><td>${usMs(m.max_ms)}</td><td>${usN(m.tokens_in)}</td><td>${usN(m.tokens_out)}</td><td>${m.cost_usd === null ? '<span class="adm-set-desc">no price</span>' : usUsd(m.cost_usd)}</td></tr>`).join(''),
    'No AI calls recorded in this range.');
  document.getElementById('admUsFeatures').innerHTML = table(
    ['Feature', 'Requests', 'Failed', 'Avg time', 'Models used'],
    d.by_feature.map(f => `<tr><td>${admEscape(usFeature(f.feature))}</td><td>${usN(f.requests)}</td><td>${f.failed ? `<span class="adm-badge badge-inactive">${usN(f.failed)}</span>` : 0}</td><td>${usMs(f.avg_ms)}</td>
      <td>${f.models.map(m => `<code>${admEscape(m.model)}</code> × ${usN(m.requests)}${m.failed ? ` (${usN(m.failed)} failed)` : ''}`).join('<br>')}</td></tr>`).join(''),
    'No AI calls recorded in this range.');

  document.getElementById('admUsExternal').innerHTML = table(
    ['Service', 'Calls', 'Failed', 'Avg time', 'Slowest 5%', 'Quota (limit you set)', 'Endpoints'],
    d.external.map(e => {
      let quota = '<span class="adm-set-desc">no limit set</span>';
      if (e.limit) {
        const pct = Math.min(100, Math.round((e.period_used / e.limit) * 100));
        quota = `<div class="us-quota"><span class="us-quota-bar ${pct >= 100 ? 'crit' : pct >= 80 ? 'warn' : ''}" style="width:${pct}%"></span></div>
          <small>${usN(e.period_used)} of ${usN(e.limit)} this ${e.limit_period} (${pct}%)</small>`;
      }
      return `<tr><td>${admEscape(e.label)}</td><td>${usN(e.requests)}</td><td>${e.failed ? `<span class="adm-badge badge-inactive">${usN(e.failed)}</span>` : 0}</td><td>${usMs(e.avg_ms)}</td><td>${usMs(e.p95_ms)}</td><td>${quota}</td>
        <td>${e.endpoints.map(x => `<code>${admEscape(x.endpoint)}</code> × ${usN(x.requests)}`).join('<br>') || '—'}</td></tr>`;
    }).join(''), '');
  const sa = d.serpapi_account;
  if (sa && sa.available) usShowSerp(sa);

  document.getElementById('admUsFailures').innerHTML = table(
    ['Time', 'Service', 'Model / endpoint', 'Feature', 'Status', 'Duration', 'Message'],
    d.recent_failures.map(f => `<tr><td>${admDatetime(f.time)}</td><td>${admEscape(f.provider)}</td><td><code>${admEscape(f.model)}</code></td><td>${admEscape(usFeature(f.feature))}</td>
      <td>${f.status ? admEscape(f.status) : '—'}</td><td>${usMs(f.duration_ms)}</td><td>${admEscape(f.error || '')}</td></tr>`).join(''),
    'No failures since the server last started. (Recent failures are kept in memory only.)');
}

function usShowSerp(sa) {
  const out = document.getElementById('admUsSerpOut');
  out.className = 'adm-set-status ' + (sa.left !== null && sa.searches_per_month && sa.left / sa.searches_per_month <= 0.2 ? 'err' : 'ok');
  out.textContent = `${sa.plan ? sa.plan + ': ' : ''}${usN(sa.left)} of ${usN(sa.searches_per_month)} searches left this month (${usN(sa.used_this_month)} used)`;
}

async function usSerpCheck() {
  const out = document.getElementById('admUsSerpOut');
  out.className = 'adm-set-status'; out.textContent = 'Checking…';
  try {
    const sa = await admFetch(`${ADM_US_API}/serpapi-quota`, { method: 'POST' });
    if (sa.available) { usShowSerp(sa); admLoadUsage(); }
    else { out.className = 'adm-set-status err'; out.textContent = sa.message || 'Not available.'; }
  } catch (err) {
    if (admHandleAuthError(err)) return;
    out.className = 'adm-set-status err'; out.textContent = err.message;
  }
}

/* ---------------------------------------------------------------- limits and prices form */
async function usLoadSettings() {
  const box = document.getElementById('admUsSettings');
  try {
    const st = await admFetch(`${ADM_US_API}/settings`);
    const L = st.limits;
    const field = (key, label, hint, step = '1') => `<label class="us-field"><span>${label}</span><input type="number" min="0" step="${step}" data-limit="${key}" class="adm-select" value="${L[key]}"><small>${hint}</small></label>`;
    const models = Array.from(new Set([...Object.keys(st.prices), ...((usData && usData.by_model) || []).map(m => m.model)])).sort();
    box.innerHTML = `
      <p class="adm-set-desc">Limits only raise alerts on this page. They never block visitors. Enter 0 to switch a limit off.</p>
      <div class="us-fields">
        ${field('ai_daily_requests', 'AI requests per day', 'Alert at 80% and 100%')}
        ${field('ai_monthly_cost_usd', 'AI spend per month (USD)', 'Estimated spend, alert at 80% and 100%', '0.01')}
        ${field('serpapi_monthly_requests', 'SerpApi searches per month', 'Your plan size (check your SerpApi account)')}
        ${field('geoapify_daily_requests', 'Geoapify requests per day', 'Your plan size (see your Geoapify dashboard)')}
        ${field('railradar_daily_requests', 'RailRadar requests per day', 'Your plan size')}
        ${field('hourly_burst_requests', 'Calls per hour (burst alert)', 'Alert when AI and API calls in one hour reach this')}
        ${field('error_rate_percent', 'Failure rate alert (%)', 'Alert when a service fails this often today (10 calls or more)')}
        ${field('usd_to_inr', 'USD to INR rate', 'Only used to show the rupee estimate', '0.01')}
      </div>
      <h4 style="margin:16px 0 6px;">AI model prices (USD per 1 million tokens)</h4>
      <p class="adm-set-desc">Starter list prices. Prices change often and a free tier may cost nothing, so check Google's pricing page. Models without a price get no cost estimate.</p>
      <table class="adm-table"><thead><tr><th>Model</th><th>Input</th><th>Output</th></tr></thead><tbody id="usPriceRows">
        ${models.map(m => usPriceRow(m, st.prices[m])).join('')}
      </tbody></table>
      <div class="adm-set-actions"><button class="adm-btn adm-btn-ghost" id="usAddModel">+ Add a model</button>
        <button class="adm-btn adm-btn-primary" id="usSaveSettings">Save limits and prices</button><span class="adm-set-status" id="usSaveStatus"></span></div>`;
    document.getElementById('usAddModel').onclick = () => {
      const name = (prompt('Model name, for example gemini-3.8-flash') || '').trim();
      if (name) document.getElementById('usPriceRows').insertAdjacentHTML('beforeend', usPriceRow(name, [0, 0]));
    };
    document.getElementById('usSaveSettings').onclick = usSaveSettings;
  } catch (err) {
    if (admHandleAuthError(err)) return;
    admShowError(box, err.message);
  }
}
function usPriceRow(model, p) {
  const v = p || ['', ''];
  return `<tr data-model="${admEscape(model)}"><td><code>${admEscape(model)}</code></td>
    <td><input type="number" min="0" step="0.01" class="adm-select us-price" data-i="0" value="${v[0]}" placeholder="no price"></td>
    <td><input type="number" min="0" step="0.01" class="adm-select us-price" data-i="1" value="${v[1]}" placeholder="no price"></td></tr>`;
}
async function usSaveSettings() {
  const status = document.getElementById('usSaveStatus');
  const limits = {};
  document.querySelectorAll('[data-limit]').forEach(i => { limits[i.dataset.limit] = i.value === '' ? 0 : Number(i.value); });
  const prices = {};
  document.querySelectorAll('#usPriceRows tr').forEach(tr => {
    const [a, b] = Array.from(tr.querySelectorAll('.us-price')).map(i => i.value);
    if (a !== '' && b !== '') prices[tr.dataset.model] = [Number(a), Number(b)];
  });
  status.className = 'adm-set-status'; status.textContent = 'Saving…';
  try {
    await admFetch(`${ADM_US_API}/settings`, { method: 'PUT', body: JSON.stringify({ limits, prices }) });
    status.className = 'adm-set-status ok'; status.textContent = 'Saved.';
    admToast('Limits and prices saved.', 'success');
    admLoadUsage();
  } catch (err) {
    if (admHandleAuthError(err)) return;
    status.className = 'adm-set-status err'; status.textContent = err.message;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const presets = document.getElementById('admUsPresets');
  presets?.addEventListener('click', (e) => {
    const b = e.target.closest('[data-days]'); if (!b) return;
    usState = { days: Number(b.dataset.days), start: '', end: '' };
    presets.querySelectorAll('.adm-pill-btn').forEach(x => x.classList.toggle('active', x === b));
    admLoadUsage();
  });
  document.getElementById('admUsApply')?.addEventListener('click', () => {
    const s = document.getElementById('admUsStart').value, e = document.getElementById('admUsEnd').value;
    if (!s || !e) return admToast('Pick both a start and an end date.', 'error');
    usState.start = s; usState.end = e;
    presets?.querySelectorAll('.adm-pill-btn').forEach(x => x.classList.remove('active'));
    admLoadUsage();
  });
  document.getElementById('admUsRefresh')?.addEventListener('click', admLoadUsage);
  document.getElementById('admUsSerpCheck')?.addEventListener('click', usSerpCheck);
});
