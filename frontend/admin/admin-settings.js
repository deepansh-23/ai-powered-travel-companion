/**
 * Admin — Settings and Feedback & Diagnostics.
 * Loaded after admin.js and reuses its helpers (admFetch, admToast, admEscape, admDatetime,
 * admBuildPager, admHandleAuthError). All globals are prefixed adm / Adm.
 */

const ADM_API_X = {
  settings: '/api/admin/settings',
  feedback: '/api/admin/feedback',
  diagnostics: '/api/admin/diagnostics',
};

/* ──────────────────────────────────────────────────────────────────────────
   SETTINGS
   ────────────────────────────────────────────────────────────────────────── */
const ADM_SETTING_FIELDS = [
  { key: 'maintenance_mode', label: 'Maintenance mode', disruptiveWhen: true,
    desc: 'Visitors get a maintenance message and the public API returns 503. Admin login and this dashboard keep working.',
    warn: 'Turning this ON blocks the public site for everyone except admins.' },
  { key: 'allow_registration', label: 'Allow new registrations', disruptiveWhen: false,
    desc: 'When off, nobody can create a new account. Existing users can still log in.',
    warn: 'Turning this OFF stops new sign-ups.' },
  { key: 'guest_mode_enabled', label: 'Allow guest mode', disruptiveWhen: false,
    desc: 'Lets visitors use the planner without an account. Nothing is saved for guests.',
    warn: 'Turning this OFF forces visitors to log in.' },
  { key: 'allow_reviews', label: 'Allow new reviews', disruptiveWhen: false,
    desc: 'When off, logged-in users cannot submit new reviews. Existing reviews stay visible.',
    warn: 'Turning this OFF hides the ability to leave reviews.' },
  { key: 'public_notice_enabled', label: 'Show announcement banner',
    desc: 'Shows the text below as a banner at the top of the public site.' },
];
const ADM_NOTICE_MAX = 300;
// Choices for "itineraries per month": 0 means no restriction
const ADM_LIMIT_CHOICES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 25, 30, 40, 50, 75, 100];

let admSet = { server: null, draft: null };

async function admLoadSettings() {
  const body = document.getElementById('admSetBody');
  if (!body) return;
  admShowLoading(body);
  admSetStatus('');
  try {
    const data = await admFetch(ADM_API_X.settings);
    admSet.server = data;
    admSet.draft = { ...data };
    admRenderSettings();
  } catch (err) {
    if (admHandleAuthError(err)) return;
    admShowError(body, err.message);
  }
}

function admRenderSettings() {
  const body = document.getElementById('admSetBody');
  const d = admSet.draft;
  const rows = ADM_SETTING_FIELDS.map(f => `
    <div class="adm-set-row${f.warn ? ' disruptive' : ''}">
      <div>
        <div class="adm-set-label">${admEscape(f.label)}</div>
        <div class="adm-set-desc">${admEscape(f.desc)}</div>
        ${f.warn ? `<div class="adm-set-warn">${admEscape(f.warn)}</div>` : ''}
      </div>
      <label class="adm-switch" aria-label="${admEscape(f.label)}">
        <input type="checkbox" data-key="${f.key}" ${d[f.key] ? 'checked' : ''}>
        <span></span>
      </label>
    </div>`).join('');

  // The saved value may be a number that is not in the list (set earlier): keep it selectable
  const curLimit = Number(d.itinerary_monthly_limit) || 0;
  const limitChoices = ADM_LIMIT_CHOICES.includes(curLimit) ? ADM_LIMIT_CHOICES : [...ADM_LIMIT_CHOICES, curLimit].sort((a, b) => a - b);
  const limitRow = `
    <div class="adm-set-row">
      <div>
        <div class="adm-set-label">Itineraries per month (normal accounts)</div>
        <div class="adm-set-desc">How many itineraries each normal account can generate per calendar month. Choose "No restriction" to remove the limit. Admin accounts are never limited. The limit is shown to users on the Home and Itinerary pages and counts restart on the 1st of each month.</div>
      </div>
      <select id="admSetItinLimit" class="adm-select" aria-label="Itineraries per month">
        ${limitChoices.map(n => `<option value="${n}" ${n === curLimit ? 'selected' : ''}>${n === 0 ? 'No restriction' : n + (n === 1 ? ' per month' : ' per month')}</option>`).join('')}
      </select>
    </div>`;

  body.innerHTML = rows + limitRow + `
    <div class="adm-set-row" style="display:block;">
      <div class="adm-set-label">Announcement text</div>
      <div class="adm-set-desc" style="margin-bottom:8px;">Plain text only, up to ${ADM_NOTICE_MAX} characters.</div>
      <textarea id="admSetNotice" class="adm-textarea" maxlength="${ADM_NOTICE_MAX}"
        aria-label="Announcement text">${admEscape(d.public_notice_text || '')}</textarea>
      <div class="adm-set-count" id="admSetNoticeCount"></div>
    </div>`;

  body.querySelectorAll('input[type=checkbox][data-key]').forEach(cb =>
    cb.addEventListener('change', () => { admSet.draft[cb.dataset.key] = cb.checked; admSetDirtyCheck(); }));
  const ta = document.getElementById('admSetNotice');
  ta.addEventListener('input', () => { admSet.draft.public_notice_text = ta.value; admSetDirtyCheck(); });
  const lim = document.getElementById('admSetItinLimit');
  if (lim) lim.addEventListener('change', () => { admSet.draft.itinerary_monthly_limit = Number(lim.value); admSetDirtyCheck(); });

  const upd = document.getElementById('admSetUpdated');
  if (upd) upd.textContent = admSet.server.updated_at
    ? `Last saved ${admDatetime(admSet.server.updated_at)}` : 'Using safe defaults (nothing saved yet).';
  admSetDirtyCheck();
}

function admSetChanges() {
  const s = admSet.server, d = admSet.draft, out = {};
  ['maintenance_mode', 'public_notice_enabled', 'guest_mode_enabled', 'allow_registration', 'allow_reviews']
    .forEach(k => { if (!!d[k] !== !!s[k]) out[k] = !!d[k]; });
  if ((Number(d.itinerary_monthly_limit) || 0) !== (Number(s.itinerary_monthly_limit) || 0)) {
    out.itinerary_monthly_limit = Number(d.itinerary_monthly_limit) || 0;
  }
  if ((d.public_notice_text || '').trim() !== (s.public_notice_text || '').trim()) {
    out.public_notice_text = (d.public_notice_text || '').trim();
  }
  return out;
}

function admSetDirtyCheck() {
  const changed = Object.keys(admSetChanges()).length > 0;
  const save = document.getElementById('admSetSave'), cancel = document.getElementById('admSetCancel');
  if (save) save.disabled = !changed;
  if (cancel) cancel.disabled = !changed;
  const ta = document.getElementById('admSetNotice'), cnt = document.getElementById('admSetNoticeCount');
  if (ta && cnt) cnt.textContent = `${ta.value.length} / ${ADM_NOTICE_MAX}`;
  if (changed) admSetStatus('You have unsaved changes.', '');
  else admSetStatus('');
}

function admSetStatus(msg, kind) {
  const el = document.getElementById('admSetStatus');
  if (!el) return;
  el.textContent = msg || '';
  el.className = 'adm-set-status' + (kind ? ` ${kind}` : '');
}

function admSetCancel() {
  if (!admSet.server) return;
  admSet.draft = { ...admSet.server };
  admRenderSettings();
}

function admDisruptiveList(changes) {
  const out = [];
  ADM_SETTING_FIELDS.forEach(f => {
    if (f.disruptiveWhen !== undefined && f.key in changes && changes[f.key] === f.disruptiveWhen) out.push(f);
  });
  return out;
}

function admSetSave() {
  const changes = admSetChanges();
  if (!Object.keys(changes).length) return;

  const noticeOn = 'public_notice_enabled' in changes ? changes.public_notice_enabled : admSet.server.public_notice_enabled;
  const noticeText = 'public_notice_text' in changes ? changes.public_notice_text : admSet.server.public_notice_text;
  if (noticeOn && !noticeText) {
    admSetStatus('Enter the announcement text before enabling the banner.', 'err');
    return;
  }

  const risky = admDisruptiveList(changes);
  if (!risky.length) return admSetSend(changes, false);

  document.getElementById('admSetConfirmText').innerHTML =
    'These changes affect every visitor right away:<ul style="margin:8px 0 0 18px;">' +
    risky.map(f => `<li>${admEscape(f.warn)}</li>`).join('') + '</ul>';
  document.getElementById('admSetConfirmOk').onclick = () => {
    document.getElementById('admSetConfirmModal').classList.remove('open');
    admSetSend(changes, true);
  };
  document.getElementById('admSetConfirmModal').classList.add('open');
}

async function admSetSend(changes, confirmed) {
  const save = document.getElementById('admSetSave');
  if (save) save.disabled = true;
  admSetStatus('Saving…', '');
  try {
    const payload = { ...changes };
    if (confirmed) payload.confirm_disruptive = true;
    const data = await admFetch(ADM_API_X.settings, { method: 'PUT', body: JSON.stringify(payload) });
    admSet.server = data;
    admSet.draft = { ...data };
    admRenderSettings();
    admSetStatus('Saved.', 'ok');
    admToast('Settings saved.', 'success');
  } catch (err) {
    if (admHandleAuthError(err)) { admSetDirtyCheck(); return; }
    admSetStatus(err.message || 'Could not save settings.', 'err');
    admToast(err.message || 'Could not save settings.', 'error');
    if (save) save.disabled = false;
  }
}

/* ──────────────────────────────────────────────────────────────────────────
   FEEDBACK
   ────────────────────────────────────────────────────────────────────────── */
let admFb = { page: 1, search: '', service: '', status: '', rating: '', items: [], timer: null };

function admStars(n) {
  const r = Math.max(0, Math.min(5, Number(n) || 0));
  return `<span class="adm-stars" aria-label="${r} out of 5">${'★'.repeat(r)}${'☆'.repeat(5 - r)}</span>`;
}

function admFbTab(tab) {
  const isFb = tab === 'feedback';
  document.getElementById('admFbPanel').hidden = !isFb;
  document.getElementById('admDiagPanel').hidden = isFb;
  document.getElementById('admFbTabFeedback').classList.toggle('active', isFb);
  document.getElementById('admFbTabDiag').classList.toggle('active', !isFb);
  if (isFb) admLoadFeedback(admFb.page); else admLoadDiagnostics();
}

function admLoadFeedbackPage() {
  const diagOpen = !document.getElementById('admDiagPanel').hidden;
  if (diagOpen) admLoadDiagnostics(); else admLoadFeedback(admFb.page);
}

async function admLoadFeedback(page = 1) {
  admFb.page = page;
  const tbody = document.getElementById('admFbTbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:24px;">Loading…</td></tr>';
  const qs = new URLSearchParams({ page: String(page) });
  if (admFb.search) qs.set('search', admFb.search);
  if (admFb.service) qs.set('service_used', admFb.service);
  if (admFb.status) qs.set('status', admFb.status);
  if (admFb.rating) qs.set('rating', admFb.rating);
  try {
    const data = await admFetch(`${ADM_API_X.feedback}?${qs}`);
    admFb.items = data.items;
    admRenderFbSummary(data.summary);
    if (!data.items.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:24px;">No feedback matches these filters.</td></tr>';
    } else {
      tbody.innerHTML = data.items.map(f => `
        <tr class="adm-fb-row" onclick="admOpenFbModal('${admEscape(f.id)}')">
          <td>${admDatetime(f.created_at)}</td>
          <td>${admEscape(f.username || 'Anonymous')}</td>
          <td>${admStars(f.rating)}</td>
          <td>${admEscape(f.service_used || '—')}</td>
          <td><div class="adm-fb-comment">${admEscape(f.comment)}</div></td>
          <td><span class="adm-badge ${admEscape(f.status)}">${admEscape(f.status)}</span></td>
        </tr>`).join('');
    }
    document.getElementById('admFbPager').innerHTML = admBuildPager(data.page, data.pages, 'admLoadFeedback');
  } catch (err) {
    if (admHandleAuthError(err)) return;
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;">${admEscape(err.message)}</td></tr>`;
  }
}

function admRenderFbSummary(s) {
  const card = (label, value, cls = '') =>
    `<div class="adm-card"><div class="adm-card-label">${label}</div><div class="adm-card-value ${cls}">${value}</div></div>`;
  document.getElementById('admFbSummary').innerHTML =
    card('Total', admNumFmt(s.total)) + card('Pending', admNumFmt(s.pending), 'yellow') +
    card('Reviewed', admNumFmt(s.reviewed), 'accent') + card('Resolved', admNumFmt(s.resolved), 'green') +
    card('Avg rating', s.total ? `${s.avg_rating} ★` : '—');
}

function admOpenFbModal(id) {
  const f = admFb.items.find(x => x.id === id);
  if (!f) return;
  const body = document.getElementById('admFbModalBody');
  body.innerHTML = `
    <div class="adm-modal-detail-row"><span>From</span><span>${admEscape(f.username || 'Anonymous')}</span></div>
    <div class="adm-modal-detail-row"><span>Service</span><span>${admEscape(f.service_used || '—')}</span></div>
    <div class="adm-modal-detail-row"><span>Rating</span><span>${admStars(f.rating)}</span></div>
    <div class="adm-modal-detail-row"><span>Submitted</span><span>${admDatetime(f.created_at)}</span></div>
    <div class="adm-modal-detail-row"><span>Status</span><span class="adm-badge ${admEscape(f.status)}">${admEscape(f.status)}</span></div>
    <div class="adm-fb-full">${admEscape(f.comment)}</div>
    <div class="adm-set-desc">Emails, phone numbers and token-like strings are masked in this view.</div>
    <label class="adm-set-label" for="admFbNotes" style="display:block;margin-top:10px;">Admin notes (private)</label>
    <textarea id="admFbNotes" class="adm-textarea" maxlength="1000">${admEscape(f.admin_notes || '')}</textarea>
    <div class="adm-modal-actions" style="flex-wrap:wrap;">
      <button class="adm-btn adm-btn-primary" onclick="admSaveFb('${admEscape(f.id)}', null)">Save notes</button>
      ${f.status !== 'reviewed' ? `<button class="adm-btn adm-btn-ghost" onclick="admSaveFb('${admEscape(f.id)}','reviewed')">Mark reviewed</button>` : ''}
      ${f.status !== 'resolved' ? `<button class="adm-btn adm-btn-success" onclick="admSaveFb('${admEscape(f.id)}','resolved')">Mark resolved</button>` : ''}
      ${f.status !== 'pending' ? `<button class="adm-btn adm-btn-ghost" onclick="admSaveFb('${admEscape(f.id)}','pending')">Reopen</button>` : ''}
      <button class="adm-btn adm-btn-danger" onclick="admConfirmDeleteFb('${admEscape(f.id)}')">Delete</button>
    </div>`;
  document.getElementById('admFbModal').classList.add('open');
}

function admCloseFbModal() {
  document.getElementById('admFbModal')?.classList.remove('open');
}

async function admSaveFb(id, status) {
  const notes = document.getElementById('admFbNotes')?.value ?? '';
  const payload = { admin_notes: notes };
  if (status) payload.status = status;
  try {
    await admFetch(`${ADM_API_X.feedback}/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(payload) });
    admToast(status ? `Marked ${status}.` : 'Notes saved.', 'success');
    admCloseFbModal();
    admLoadFeedback(admFb.page);
  } catch (err) {
    if (admHandleAuthError(err)) return;
    admToast(err.message, 'error');
  }
}

function admConfirmDeleteFb(id) {
  admCloseFbModal();
  const overlay = document.getElementById('admConfirmModal');
  const txt = document.getElementById('admConfirmText');
  const btn = document.getElementById('admConfirmOkBtn');
  if (!overlay || !txt || !btn) return;
  txt.innerHTML = 'Delete this feedback permanently? This also removes it from the public Reviews page.';
  btn.onclick = async () => {
    admCloseConfirm();
    try {
      await admFetch(`${ADM_API_X.feedback}/${encodeURIComponent(id)}`, { method: 'DELETE' });
      admToast('Feedback deleted.', 'success');
      admLoadFeedback(admFb.page);
    } catch (err) {
      if (admHandleAuthError(err)) return;
      admToast(err.message, 'error');
    }
  };
  overlay.classList.add('open');
}

/* ──────────────────────────────────────────────────────────────────────────
   DIAGNOSTICS (sanitized, in-memory, bounded)
   ────────────────────────────────────────────────────────────────────────── */
let admDiag = { search: '', level: 'all', timer: null };

async function admLoadDiagnostics() {
  const tbody = document.getElementById('admDiagTbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:24px;">Loading…</td></tr>';
  const qs = new URLSearchParams({ level: admDiag.level, limit: '50' });
  if (admDiag.search) qs.set('search', admDiag.search);
  try {
    const d = await admFetch(`${ADM_API_X.diagnostics}?${qs}`);
    const card = (label, value, cls = '') =>
      `<div class="adm-card"><div class="adm-card-label">${label}</div><div class="adm-card-value ${cls}">${value}</div></div>`;
    document.getElementById('admDiagSummary').innerHTML =
      card('Errors recorded', admNumFmt(d.total_recorded)) + card('4xx', admNumFmt(d.c4xx_count), 'yellow') +
      card('5xx', admNumFmt(d.c5xx_count), d.c5xx_count ? 'red' : 'green') +
      card('Database', admEscape(d.database_status), d.database_status === 'Connected' ? 'green' : 'red');
    if (!d.items.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:24px;">No errors recorded since the last restart.</td></tr>';
      return;
    }
    tbody.innerHTML = d.items.map(e => `
      <tr>
        <td>${admDatetime(e.timestamp)}</td>
        <td>${admEscape(e.method)}</td>
        <td><code>${admEscape(e.endpoint)}</code></td>
        <td><span class="adm-badge ${e.status_code >= 500 ? 'inactive' : 'pending'}">${admEscape(e.status_code)}</span></td>
        <td>${admEscape(e.error_summary)}</td>
        <td>${admEscape(e.duration_ms)} ms</td>
        <td>${admEscape(e.client_ip_masked)}</td>
      </tr>`).join('');
  } catch (err) {
    if (admHandleAuthError(err)) return;
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:24px;">${admEscape(err.message)}</td></tr>`;
  }
}

/* ──────────────────────────────────────────────────────────────────────────
   Wiring
   ────────────────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('admSetSave')?.addEventListener('click', admSetSave);
  document.getElementById('admSetCancel')?.addEventListener('click', admSetCancel);
  document.getElementById('admSetConfirmCancel')?.addEventListener('click',
    () => document.getElementById('admSetConfirmModal').classList.remove('open'));

  document.getElementById('admFbTabFeedback')?.addEventListener('click', () => admFbTab('feedback'));
  document.getElementById('admFbTabDiag')?.addEventListener('click', () => admFbTab('diagnostics'));

  const debounce = (obj, fn) => { clearTimeout(obj.timer); obj.timer = setTimeout(fn, 350); };
  document.getElementById('admFbSearch')?.addEventListener('input', e => {
    admFb.search = e.target.value.trim(); debounce(admFb, () => admLoadFeedback(1));
  });
  [['admFbService', 'service'], ['admFbStatus', 'status'], ['admFbRating', 'rating']].forEach(([id, key]) =>
    document.getElementById(id)?.addEventListener('change', e => { admFb[key] = e.target.value; admLoadFeedback(1); }));
  document.getElementById('admFbRefresh')?.addEventListener('click', () => admLoadFeedback(admFb.page));

  document.getElementById('admDiagSearch')?.addEventListener('input', e => {
    admDiag.search = e.target.value.trim(); debounce(admDiag, admLoadDiagnostics);
  });
  document.getElementById('admDiagLevel')?.addEventListener('change', e => { admDiag.level = e.target.value; admLoadDiagnostics(); });
  document.getElementById('admDiagRefresh')?.addEventListener('click', admLoadDiagnostics);
});
