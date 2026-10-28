/**
 * Admin — Database page: size, storage left, connections, memory, performance, plan limits and warnings.
 * Numbers come from /api/admin/database (read-only). Limits you enter only raise warnings; they never block anyone.
 */

const ADM_DB_API = '/api/admin/database';

const dbN = (v) => (v === null || v === undefined ? '—' : Number(v).toLocaleString('en-IN'));
function dbB(v) {
    if (v === null || v === undefined) return '—';
    let n = Number(v);
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    while (Math.abs(n) >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return (i === 0 ? n.toFixed(0) : n.toFixed(1)) + ' ' + units[i];
}
function dbDuration(sec) {
    if (sec === null || sec === undefined) return '—';
    const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60);
    return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`;
}
const dbCls = (pct) => (pct >= 100 ? 'crit' : pct >= 80 ? 'warn' : '');

function dbBar(pct, label) {
    if (pct === null || pct === undefined) return '';
    const w = Math.max(0, Math.min(100, pct));
    return `<div class="db-bar" role="progressbar" aria-valuenow="${Math.round(w)}" aria-valuemin="0" aria-valuemax="100" aria-label="${admEscape(label || '')}"><span class="us-quota-bar ${dbCls(pct)}" style="width:${w}%"></span></div>`;
}

async function admLoadDatabase() {
    const cards = document.getElementById('admDbCards');
    if (!cards) return;
    admShowLoading(cards);
    try {
        const d = await admFetch(ADM_DB_API);
        dbRender(d);
        dbLoadSettings(d);
    } catch (err) {
        if (admHandleAuthError(err)) return;
        admShowError(cards, err.message);
    }
}

function dbRender(d) {
    const icon = { critical: '🔴', warning: '🟠', info: 'ℹ️' };
    document.getElementById('admDbSub').textContent =
        `${d.engine === 'postgresql' ? (d.server && d.server.version ? d.server.version : 'PostgreSQL') : d.engine} · updated ${admDatetime(d.generated_at)}`;

    const real = d.alerts.filter(a => a.level !== 'info');
    document.getElementById('admDbAlerts').innerHTML = d.alerts.length
        ? `<div class="us-alerts">${d.alerts.map(a => `<div class="us-alert us-${admEscape(a.level)}"><b>${icon[a.level] || ''} ${admEscape(a.title)}</b><span>${admEscape(a.detail)}</span></div>`).join('')}</div>`
        + (real.length ? '' : '<div class="us-alert us-ok"><b>✅ No warnings</b><span>Nothing is close to a limit right now.</span></div>')
        : '<div class="us-alert us-ok"><b>✅ No warnings</b><span>Nothing is close to a limit right now.</span></div>';

    const card = (label, value, sub, cls = '') => `<div class="adm-card"><div class="adm-card-label">${label}</div><div class="adm-card-value ${cls}">${value}</div><div class="adm-card-sub">${sub || ''}</div></div>`;
    const app = d.app || {};
    const out = [];

    if (!d.supported) {
        document.getElementById('admDbNotice').textContent = d.message || '';
    } else {
        document.getElementById('admDbNotice').textContent = d.reachable ? '' : 'The database did not answer.';
    }

    if (d.supported && d.reachable) {
        const s = d.storage || {}, c = d.connections || {}, p = d.performance || {};
        out.push(card('Database size', dbB(s.used_bytes), s.limit_is_set ? `of ${dbB(s.limit_bytes)} plan (${s.pct}% used)` : 'plan size not set', s.pct >= 80 ? 'red' : 'accent'));
        out.push(card('Storage left', s.limit_is_set ? dbB(s.free_bytes) : '—', s.limit_is_set ? 'before the plan is full' : 'set your plan size below', s.pct >= 80 ? 'red' : 'green'));
        out.push(card('Connections', `${dbN(c.current)}${c.limit ? ' / ' + dbN(c.limit) : ''}`, `${dbN(c.active)} active · ${dbN(c.idle)} idle`, c.pct >= 80 ? 'red' : ''));
        out.push(card('Memory cache hit', p.cache_hit_pct === null || p.cache_hit_pct === undefined ? '—' : p.cache_hit_pct + '%', 'reads served from memory (aim above 95%)', p.cache_hit_pct !== null && p.cache_hit_pct < 90 ? 'red' : 'green'));
        out.push(card('Response time', d.latency_ms === null ? '—' : d.latency_ms + ' ms', 'simple check (under 100 ms is healthy)', d.latency_ms > 500 ? 'red' : ''));
        out.push(card('Database running for', dbDuration(d.server && d.server.uptime_seconds), 'since the last restart'));
    }
    out.push(card('Website server memory', app.memory_used !== null && app.memory_used !== undefined ? dbB(app.memory_used) : '—',
        app.memory_limit ? `of ${dbB(app.memory_limit)} · ${dbB(app.memory_free)} free` : 'not reported by this system', app.memory_pct >= 85 ? 'red' : ''));
    document.getElementById('admDbCards').innerHTML = out.join('');

    const sec = (id, html) => { const el = document.getElementById(id); if (el) el.innerHTML = html; };
    const table = (head, body, empty) => body ? `<table class="adm-table"><thead><tr>${head.map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table>` : `<div class="adm-set-desc" style="padding:12px 0">${empty}</div>`;

    // ---- storage
    if (d.supported && d.reachable) {
        const s = d.storage;
        sec('admDbStorage', `
      <div class="db-meter"><div class="db-meter-head"><b>${dbB(s.used_bytes)} used</b><span>${s.limit_is_set ? `of ${dbB(s.limit_bytes)} · ${dbB(s.free_bytes)} left · ${s.pct}%` : 'No plan size set, so space left is unknown'}</span></div>${dbBar(s.pct, 'Storage used')}</div>
      <h4 class="db-sub">Biggest tables</h4>` +
            table(['Table', 'Size', 'Rows', 'Dead rows'], s.tables.map(t => `<tr><td><code>${admEscape(t.name)}</code></td><td>${dbB(t.total_bytes)}</td><td>${dbN(t.rows)}</td><td>${t.dead_rows ? dbN(t.dead_rows) : 0}</td></tr>`).join(''), 'No table statistics available.'));

        // ---- connections
        const c = d.connections;
        const pool = c.pool ? `<h4 class="db-sub">This website's own connection pool</h4>
      <div class="db-meter"><div class="db-meter-head"><b>${c.pool.in_use} of ${c.pool.max} in use</b><span>${c.pool.size} kept ready, up to ${c.pool.max - c.pool.size} extra when busy</span></div>${dbBar(c.pool.max ? c.pool.in_use / c.pool.max * 100 : 0, 'Pool in use')}</div>` : '';
        sec('admDbConnections', `
      <div class="db-meter"><div class="db-meter-head"><b>${dbN(c.current)} connected</b><span>${c.limit ? `limit ${dbN(c.limit)} (${admEscape(c.limit_source)}) · ${c.pct}%` : 'limit unknown'}</span></div>${dbBar(c.pct, 'Connections used')}</div>
      <div class="db-facts"><span>Active <b>${dbN(c.active)}</b></span><span>Idle <b>${dbN(c.idle)}</b></span><span>Waiting in a transaction <b>${dbN(c.idle_in_transaction)}</b></span><span>Server maximum <b>${dbN(c.server_max)}</b></span><span>Kept for admin use <b>${dbN(c.reserved)}</b></span></div>${pool}`);

        // ---- performance
        const p = d.performance;
        const row = (k, v, hint) => `<tr><td>${k}</td><td><b>${v}</b></td><td class="adm-set-desc">${hint}</td></tr>`;
        sec('admDbPerformance', table(['Measure', 'Value', 'What it means'], [
            row('Cache hit rate', p.cache_hit_pct === null ? 'not enough reads yet' : p.cache_hit_pct + '%', 'Share of reads answered from memory. Low means the data does not fit in memory.'),
            row('Longest running query', p.longest_query_seconds === null ? '—' : p.longest_query_seconds + ' s', 'A query that runs for minutes can slow everything else.'),
            row('Transactions committed', dbN(p.commits), 'Successful changes since the statistics were reset.'),
            row('Transactions rolled back', dbN(p.rollbacks), 'Cancelled changes. A high share can mean errors in the app.'),
            row('Deadlocks', dbN(p.deadlocks), 'Two updates blocked each other and one was cancelled.'),
            row('Temporary files', `${dbN(p.temp_files)} (${dbB(p.temp_bytes)})`, 'Big queries that did not fit in memory and wrote to disk.'),
            row('Transaction ID age', p.xid_age === null ? '—' : `${dbN(p.xid_age)} (${p.xid_pct}% of the safe limit)`, 'PostgreSQL must clean up before about 2.1 billion. Autovacuum does this normally.'),
            row('Statistics counted since', p.stats_since ? admDatetime(p.stats_since) : '—', 'These counters reset when the database is restored or reset.'),
        ].join(''), ''));

        // ---- database memory
        const m = d.memory;
        sec('admDbMemory', `
      <p class="adm-set-desc">${admEscape(m.note)}</p>
      ${m.limit_is_set ? `<div class="db-meter"><div class="db-meter-head"><b>Up to ${dbB(m.worst_case_bytes)} could be used</b><span>of ${dbB(m.plan_limit_bytes)} plan memory · ${m.worst_case_pct}%</span></div>${dbBar(m.worst_case_pct, 'Possible memory use')}</div>` : ''}` +
            table(['Setting', 'Value', 'What it does'], [
                ['Shared buffers', m.shared_buffers, 'The database\'s own memory cache for table data.'],
                ['Work memory (per sort or join)', m.work_mem, 'Memory each query step may use before writing to disk.'],
                ['Maintenance memory', m.maintenance_work_mem, 'Used by cleaning and index building.'],
                ['Effective cache size', m.effective_cache_size, 'The planner\'s guess of memory available for caching.'],
            ].map(r => `<tr><td>${r[0]}</td><td><b>${dbB(r[1])}</b></td><td class="adm-set-desc">${r[2]}</td></tr>`).join(''), ''));
    } else {
        ['admDbStorage', 'admDbConnections', 'admDbPerformance', 'admDbMemory'].forEach(id => sec(id, `<div class="adm-set-desc" style="padding:8px 0">${admEscape(d.message || 'Not available right now.')}</div>`));
    }

    // ---- website server (real numbers from the operating system)
    const disk = app.disk;
    sec('admDbApp', `
    ${app.memory_limit ? `<div class="db-meter"><div class="db-meter-head"><b>${dbB(app.memory_used)} used</b><span>of ${dbB(app.memory_limit)} (${admEscape(app.memory_source)}) · ${dbB(app.memory_free)} available · ${app.memory_pct}%</span></div>${dbBar(app.memory_pct, 'Server memory used')}</div>` : '<div class="adm-set-desc">This system does not report its memory.</div>'}
    ${disk ? `<div class="db-meter"><div class="db-meter-head"><b>Disk: ${dbB(disk.used)} used</b><span>of ${dbB(disk.total)} · ${dbB(disk.free)} free · ${disk.pct}%</span></div>${dbBar(disk.pct, 'Server disk used')}</div>` : ''}
    <div class="db-facts"><span>This app's process <b>${dbB(app.process_rss)}</b></span><span>Its peak <b>${dbB(app.process_peak)}</b></span><span>CPU cores <b>${dbN(app.cpu_count)}</b></span>${app.load_average ? `<span>Load (1 / 5 / 15 min) <b>${app.load_average.join(' / ')}</b></span>` : ''}</div>`);
}

/* ---------------------------------------------------------------- plan sizes and limits */
function dbLoadSettings(d) {
    const box = document.getElementById('admDbSettings');
    if (!box) return;
    const L = d.limits || {};
    box.innerHTML = `
    <p class="adm-set-desc">These are the sizes of <b>your database plan</b> (see your Aiven service page). The database cannot report them itself. They only raise warnings on this page at 80% and 100%; they never block visitors. Enter 0 to switch one off.</p>
    <div class="us-fields">
      <label class="us-field"><span>Storage of your plan (MB)</span><input type="number" min="0" step="1" data-dblimit="storage_mb" class="adm-select" value="${L.storage_mb || 0}"><small>For example 1 GB = 1024. Used for "storage left".</small></label>
      <label class="us-field"><span>Memory (RAM) of your plan (MB)</span><input type="number" min="0" step="1" data-dblimit="memory_mb" class="adm-select" value="${L.memory_mb || 0}"><small>Compared with the memory the database is set up to use.</small></label>
      <label class="us-field"><span>Connection limit</span><input type="number" min="0" step="1" data-dblimit="connections" class="adm-select" value="${L.connections || 0}"><small>0 = use the maximum the server reports${d.connections && d.connections.server_max ? ' (' + d.connections.server_max + ')' : ''}.</small></label>
    </div>
    <div class="adm-set-actions"><button class="adm-btn adm-btn-primary" id="dbSaveSettings">Save limits</button><span class="adm-set-status" id="dbSaveStatus"></span></div>`;
    document.getElementById('dbSaveSettings').onclick = dbSaveSettings;
}

async function dbSaveSettings() {
    const status = document.getElementById('dbSaveStatus');
    const limits = {};
    document.querySelectorAll('[data-dblimit]').forEach(i => { limits[i.dataset.dblimit] = i.value === '' ? 0 : Number(i.value); });
    status.className = 'adm-set-status'; status.textContent = 'Saving…';
    try {
        await admFetch(`${ADM_DB_API}/settings`, { method: 'PUT', body: JSON.stringify({ limits }) });
        status.className = 'adm-set-status ok'; status.textContent = 'Saved.';
        admToast('Database limits saved.', 'success');
        admLoadDatabase();
    } catch (err) {
        if (admHandleAuthError(err)) return;
        status.className = 'adm-set-status err'; status.textContent = err.message;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('admDbRefresh')?.addEventListener('click', admLoadDatabase);
});