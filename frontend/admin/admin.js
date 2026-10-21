/**
 * Admin Control Center — JavaScript
 * Isolated from main app: all globals prefixed with Adm / adm
 * No frameworks — vanilla JS only.
 */

/* ──────────────────────────────────────────────────────────────────────────
   Configuration
   ────────────────────────────────────────────────────────────────────────── */
const ADM_API = {
  overview:    '/api/admin/overview',
  users:       '/api/admin/users',
  itineraries: '/api/admin/itineraries',
  logout:      '/api/auth/logout',
  me:          '/api/auth/me',
};

const PAGE_SIZE = 20;

/* ──────────────────────────────────────────────────────────────────────────
   State
   ────────────────────────────────────────────────────────────────────────── */
let admState = {
  currentPage: 'overview',
  adminUsername: '',

  users: { data: [], total: 0, page: 1, pages: 1, search: '', role: '' },
  itineraries: { data: [], total: 0, page: 1, pages: 1, search: '', type: '' },
};

/* ──────────────────────────────────────────────────────────────────────────
   Utilities
   ────────────────────────────────────────────────────────────────────────── */

function admFmt(val) {
  if (val == null) return '<span style="color:var(--adm-text-subtle)">—</span>';
  return val;
}

function admDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return isNaN(d) ? '—' : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function admDatetime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return '—';
  return d.toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function admEscape(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function admNumFmt(n) {
  return Number(n).toLocaleString('en-IN');
}

/* ── Toast ─────────────────────────────────────────────────────────── */
const admToastEl = document.getElementById('admToast');
let toastTimer = null;

function admToast(msg, type = 'info', duration = 3500) {
  if (!admToastEl) return;
  admToastEl.innerHTML = `
    <div class="adm-toast ${admEscape(type)}" role="alert">
      <span>${type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ'}</span>
      <span>${admEscape(msg)}</span>
    </div>`;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { admToastEl.innerHTML = ''; }, duration);
}

/* ── API fetch helper ──────────────────────────────────────────────── */
async function admFetch(url, options = {}) {
  const res = await fetch(url, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const msg = body.detail || `HTTP ${res.status}`;
    throw Object.assign(new Error(msg), { status: res.status });
  }
  if (res.status === 204) return null;
  return res.json();
}

/* ── Loading state helpers ─────────────────────────────────────────── */
function admShowLoading(container) {
  container.innerHTML = `
    <div class="adm-state-box">
      <div class="adm-spinner"></div>
      <div class="adm-state-text">Loading…</div>
    </div>`;
}

function admShowError(container, msg) {
  container.innerHTML = `
    <div class="adm-state-box">
      <div class="adm-state-icon">⚠️</div>
      <div class="adm-state-title">Something went wrong</div>
      <div class="adm-state-text">${admEscape(msg)}</div>
    </div>`;
}

function admShowEmpty(container, msg = 'No results found.') {
  container.innerHTML = `
    <div class="adm-state-box">
      <div class="adm-state-icon">🔍</div>
      <div class="adm-state-title">Nothing here yet</div>
      <div class="adm-state-text">${admEscape(msg)}</div>
    </div>`;
}

/* ──────────────────────────────────────────────────────────────────────────
   Navigation
   ────────────────────────────────────────────────────────────────────────── */
function admNavigate(page) {
  admState.currentPage = page;

  document.querySelectorAll('.adm-page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.adm-nav-item').forEach(n => n.classList.remove('active'));

  const pageEl = document.getElementById(`page-${page}`);
  if (pageEl) pageEl.classList.add('active');

  const navEl = document.querySelector(`[data-page="${page}"]`);
  if (navEl) navEl.classList.add('active');

  // Update header title
  const titles = {
    overview: 'Overview',
    users: 'User Management',
    itineraries: 'Itinerary Management',
    monitoring: 'API Monitoring',
    health: 'System Health',
    settings: 'Settings',
    feedback: 'Feedback & Diagnostics',
  };
  const titleEl = document.getElementById('admPageTitle');
  if (titleEl) titleEl.textContent = titles[page] || 'Admin';

  // Close mobile sidebar
  admCloseSidebar();

  // Load data for page
  if (page === 'overview') admLoadOverview();
  else if (page === 'users') admLoadUsers();
  else if (page === 'itineraries') admLoadItineraries();
}

/* ── Mobile sidebar ────────────────────────────────────────────────── */
function admToggleSidebar() {
  document.getElementById('admSidebar').classList.toggle('open');
  document.getElementById('admSidebarOverlay').classList.toggle('open');
}
function admCloseSidebar() {
  document.getElementById('admSidebar').classList.remove('open');
  document.getElementById('admSidebarOverlay').classList.remove('open');
}

/* ──────────────────────────────────────────────────────────────────────────
   Auth check on load
   ────────────────────────────────────────────────────────────────────────── */
async function admCheckAuth() {
  try {
    const me = await admFetch(ADM_API.me);
    if (!me.authenticated) {
      window.location.href = '/pages/login.html?next=/admin/';
      return;
    }
    // Verify admin access by probing the overview endpoint
    await admFetch(ADM_API.overview);
    admState.adminUsername = me.user?.username || 'Admin';
    const nameEl = document.getElementById('admAdminName');
    if (nameEl) nameEl.textContent = admState.adminUsername;
    admNavigate('overview');
  } catch (err) {
    if (err.status === 403) {
      document.getElementById('admGate').innerHTML = `
        <div style="display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center;padding:24px;">
          <div>
            <div style="font-size:56px;margin-bottom:16px;">🚫</div>
            <h2 style="color:#f85149;margin-bottom:8px;">Access Denied</h2>
            <p style="color:#8b949e;margin-bottom:24px;">Your account does not have admin privileges.</p>
            <a href="/" style="color:#58a6ff;font-size:14px;">← Return to main site</a>
          </div>
        </div>`;
    } else if (err.status === 401) {
      window.location.href = '/pages/login.html?next=/admin/';
    } else {
      admToast('Connection error. Check that the server is running.', 'error', 6000);
    }
  }
}

/* ──────────────────────────────────────────────────────────────────────────
   Logout
   ────────────────────────────────────────────────────────────────────────── */
async function admLogout() {
  try {
    await admFetch(ADM_API.logout, { method: 'POST' });
  } catch (_) { /* ignore */ }
  window.location.href = '/pages/login.html';
}

/* ──────────────────────────────────────────────────────────────────────────
   Overview
   ────────────────────────────────────────────────────────────────────────── */
async function admLoadOverview() {
  const el = document.getElementById('admOverviewCards');
  if (!el) return;
  admShowLoading(el);

  try {
    const d = await admFetch(ADM_API.overview);
    el.innerHTML = `
      <div class="adm-card">
        <div class="adm-card-label">Total Users</div>
        <div class="adm-card-value accent">${admNumFmt(d.total_users)}</div>
        <div class="adm-card-sub">Registered accounts</div>
      </div>
      <div class="adm-card">
        <div class="adm-card-label">Active Users</div>
        <div class="adm-card-value green">${admNumFmt(d.active_users)}</div>
        <div class="adm-card-sub">${admNumFmt(d.inactive_users)} inactive</div>
      </div>
      <div class="adm-card">
        <div class="adm-card-label">Admin Accounts</div>
        <div class="adm-card-value purple">${admNumFmt(d.total_admins)}</div>
        <div class="adm-card-sub">With admin privileges</div>
      </div>
      <div class="adm-card">
        <div class="adm-card-label">Saved Itineraries</div>
        <div class="adm-card-value yellow">${admNumFmt(d.total_itineraries)}</div>
        <div class="adm-card-sub">History entries</div>
      </div>
      <div class="adm-card">
        <div class="adm-card-label">New (7 days)</div>
        <div class="adm-card-value">${admNumFmt(d.registrations_last_7_days)}</div>
        <div class="adm-card-sub">Recent registrations</div>
      </div>
      <div class="adm-card">
        <div class="adm-card-label">Database</div>
        <div style="margin-top:6px;">
          <span class="adm-health-badge ${d.database_healthy ? 'healthy' : 'unhealthy'}">
            ${d.database_healthy ? '● Healthy' : '● Error'}
          </span>
        </div>
        ${d.db_error ? `<div class="adm-card-sub" style="margin-top:6px;color:var(--adm-red);font-size:11px;">${admEscape(d.db_error)}</div>` : ''}
      </div>
    `;
  } catch (err) {
    admShowError(el, err.message);
  }
}

/* ──────────────────────────────────────────────────────────────────────────
   User Management
   ────────────────────────────────────────────────────────────────────────── */
async function admLoadUsers(page) {
  if (page !== undefined) admState.users.page = page;
  const tbody = document.getElementById('admUsersTbody');
  const pager = document.getElementById('admUsersPager');
  const totalEl = document.getElementById('admUsersTotal');
  if (!tbody) return;

  admShowLoading(tbody);

  const params = new URLSearchParams({
    page: admState.users.page,
    ...(admState.users.search ? { search: admState.users.search } : {}),
    ...(admState.users.role ? { role: admState.users.role } : {}),
  });

  try {
    const d = await admFetch(`${ADM_API.users}?${params}`);
    admState.users = { ...admState.users, data: d.users, total: d.total, pages: d.pages };
    if (totalEl) totalEl.textContent = `${admNumFmt(d.total)} users`;

    if (!d.users.length) {
      admShowEmpty(tbody, 'No users match the current filter.');
      if (pager) pager.innerHTML = '';
      return;
    }

    tbody.innerHTML = d.users.map(u => `
      <tr data-uid="${admEscape(u.id)}" onclick="admShowUserDetail('${admEscape(u.id)}')">
        <td style="font-weight:500;">
          <span style="color:var(--adm-text)">${admEscape(u.username)}</span>
        </td>
        <td><code style="font-size:11px;color:var(--adm-text-muted)">${admEscape(u.id.slice(0,8))}…</code></td>
        <td>
          <span class="adm-badge ${u.is_active ? 'active' : 'inactive'}">
            ${u.is_active ? '● Active' : '● Inactive'}
          </span>
        </td>
        <td>
          <span class="adm-badge ${u.is_admin ? 'admin' : 'user'}">
            ${u.is_admin ? '⭐ Admin' : 'User'}
          </span>
        </td>
        <td>${admDate(u.created_at)}</td>
        <td>${admDate(u.last_login_at)}</td>
        <td>${admNumFmt(u.itinerary_count)}</td>
      </tr>`).join('');

    if (pager) pager.innerHTML = admBuildPager(d.page, d.pages, 'admLoadUsers');
  } catch (err) {
    admShowError(tbody, err.message);
  }
}

function admUserSearch(val) {
  admState.users.search = val;
  admState.users.page = 1;
  clearTimeout(admState._userSearchTimer);
  admState._userSearchTimer = setTimeout(() => admLoadUsers(), 350);
}

function admUserRoleFilter(val) {
  admState.users.role = val;
  admState.users.page = 1;
  admLoadUsers();
}

/* ── User Detail Modal ─────────────────────────────────────────────── */
let admCurrentUserId = null;
let admCurrentUserData = null;

async function admShowUserDetail(uid) {
  admCurrentUserId = uid;
  const modal = document.getElementById('admUserModal');
  const body = document.getElementById('admUserModalBody');
  if (!modal || !body) return;

  body.innerHTML = `<div class="adm-spinner" style="display:block;margin:20px auto;"></div>`;
  modal.classList.add('open');

  try {
    const u = await admFetch(`${ADM_API.users}/${uid}`);
    admCurrentUserData = u;
    body.innerHTML = `
      <div class="adm-modal-detail-row">
        <span class="adm-modal-detail-label">Username</span>
        <span class="adm-modal-detail-value"><strong>${admEscape(u.username)}</strong></span>
      </div>
      <div class="adm-modal-detail-row">
        <span class="adm-modal-detail-label">User ID</span>
        <span class="adm-modal-detail-value" style="font-size:12px;font-family:monospace">${admEscape(u.id)}</span>
      </div>
      <div class="adm-modal-detail-row">
        <span class="adm-modal-detail-label">Status</span>
        <span class="adm-modal-detail-value">
          <span class="adm-badge ${u.is_active ? 'active' : 'inactive'}">
            ${u.is_active ? '● Active' : '● Inactive'}
          </span>
        </span>
      </div>
      <div class="adm-modal-detail-row">
        <span class="adm-modal-detail-label">Role</span>
        <span class="adm-modal-detail-value">
          <span class="adm-badge ${u.is_admin ? 'admin' : 'user'}">
            ${u.is_admin ? '⭐ Admin' : 'User'}
          </span>
        </span>
      </div>
      <div class="adm-modal-detail-row">
        <span class="adm-modal-detail-label">Registered</span>
        <span class="adm-modal-detail-value">${admDatetime(u.created_at)}</span>
      </div>
      <div class="adm-modal-detail-row">
        <span class="adm-modal-detail-label">Last Login</span>
        <span class="adm-modal-detail-value">${admDatetime(u.last_login_at)}</span>
      </div>
      <div class="adm-modal-detail-row">
        <span class="adm-modal-detail-label">Itineraries</span>
        <span class="adm-modal-detail-value">${admNumFmt(u.itinerary_count)}</span>
      </div>
      <div class="adm-modal-actions">
        ${u.is_active
          ? `<button class="adm-btn adm-btn-warning" onclick="admPatchUser('${admEscape(uid)}','is_active',false)">⊘ Deactivate</button>`
          : `<button class="adm-btn adm-btn-success" onclick="admPatchUser('${admEscape(uid)}','is_active',true)">✓ Activate</button>`}
        ${u.is_admin
          ? `<button class="adm-btn adm-btn-ghost" onclick="admPatchUser('${admEscape(uid)}','is_admin',false)">Demote to User</button>`
          : `<button class="adm-btn adm-btn-primary" onclick="admPatchUser('${admEscape(uid)}','is_admin',true)">⭐ Promote to Admin</button>`}
        <button class="adm-btn adm-btn-danger" onclick="admConfirmDeleteUser('${admEscape(uid)}','${admEscape(u.username)}')">🗑 Delete Account</button>
      </div>`;
  } catch (err) {
    body.innerHTML = `<div class="adm-state-box"><div class="adm-state-text" style="color:var(--adm-red)">${admEscape(err.message)}</div></div>`;
  }
}

async function admPatchUser(uid, field, value) {
  try {
    await admFetch(`${ADM_API.users}/${uid}`, {
      method: 'PATCH',
      body: JSON.stringify({ [field]: value }),
    });
    admToast('User updated successfully.', 'success');
    admCloseUserModal();
    admLoadUsers();
  } catch (err) {
    admToast(err.message, 'error');
  }
}

function admCloseUserModal() {
  document.getElementById('admUserModal').classList.remove('open');
  admCurrentUserId = null;
  admCurrentUserData = null;
}

function admConfirmDeleteUser(uid, username) {
  admCloseUserModal();
  const overlay = document.getElementById('admConfirmModal');
  const txt = document.getElementById('admConfirmText');
  const btn = document.getElementById('admConfirmOkBtn');
  if (!overlay || !txt || !btn) return;
  txt.innerHTML = `Are you sure you want to permanently delete the account <span class="adm-confirm-target">"${admEscape(username)}"</span>?
    <br><br>Their itineraries and sessions will be removed. Reviews will be anonymised. This cannot be undone.`;
  btn.onclick = async () => {
    admCloseConfirm();
    try {
      await admFetch(`${ADM_API.users}/${uid}`, { method: 'DELETE' });
      admToast(`User "${username}" deleted.`, 'success');
      admLoadUsers();
    } catch (err) {
      admToast(err.message, 'error');
    }
  };
  overlay.classList.add('open');
}

/* ──────────────────────────────────────────────────────────────────────────
   Itinerary Management
   ────────────────────────────────────────────────────────────────────────── */
async function admLoadItineraries(page) {
  if (page !== undefined) admState.itineraries.page = page;
  const tbody = document.getElementById('admItinTbody');
  const pager = document.getElementById('admItinPager');
  const totalEl = document.getElementById('admItinTotal');
  if (!tbody) return;

  admShowLoading(tbody);

  const params = new URLSearchParams({
    page: admState.itineraries.page,
    ...(admState.itineraries.search ? { search: admState.itineraries.search } : {}),
    ...(admState.itineraries.type ? { feature_type: admState.itineraries.type } : {}),
  });

  try {
    const d = await admFetch(`${ADM_API.itineraries}?${params}`);
    admState.itineraries = { ...admState.itineraries, data: d.itineraries, total: d.total, pages: d.pages };
    if (totalEl) totalEl.textContent = `${admNumFmt(d.total)} records`;

    if (!d.itineraries.length) {
      admShowEmpty(tbody, 'No itinerary records match the current filter.');
      if (pager) pager.innerHTML = '';
      return;
    }

    tbody.innerHTML = d.itineraries.map(i => `
      <tr data-iid="${admEscape(i.id)}" onclick="admShowItinDetail('${admEscape(i.id)}')">
        <td style="font-weight:500;max-width:260px;">
          <span style="display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${admEscape(i.title)}</span>
        </td>
        <td>
          <span class="adm-badge type">${admEscape(i.feature_type)}</span>
        </td>
        <td>${admEscape(i.username || '—')}</td>
        <td style="font-size:12px;color:var(--adm-text-muted);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
          ${admEscape(i.preview)}
        </td>
        <td>${admDate(i.created_at)}</td>
      </tr>`).join('');

    if (pager) pager.innerHTML = admBuildPager(d.page, d.pages, 'admLoadItineraries');
  } catch (err) {
    admShowError(tbody, err.message);
  }
}

function admItinSearch(val) {
  admState.itineraries.search = val;
  admState.itineraries.page = 1;
  clearTimeout(admState._itinSearchTimer);
  admState._itinSearchTimer = setTimeout(() => admLoadItineraries(), 350);
}

function admItinTypeFilter(val) {
  admState.itineraries.type = val;
  admState.itineraries.page = 1;
  admLoadItineraries();
}

/* ── Itinerary Detail Modal ────────────────────────────────────────── */
async function admShowItinDetail(iid) {
  const modal = document.getElementById('admItinModal');
  const body = document.getElementById('admItinModalBody');
  if (!modal || !body) return;

  body.innerHTML = `<div class="adm-spinner" style="display:block;margin:20px auto;"></div>`;
  modal.classList.add('open');

  try {
    const i = await admFetch(`${ADM_API.itineraries}/${iid}`);
    body.innerHTML = `
      <div class="adm-modal-detail-row">
        <span class="adm-modal-detail-label">Title</span>
        <span class="adm-modal-detail-value">${admEscape(i.title)}</span>
      </div>
      <div class="adm-modal-detail-row">
        <span class="adm-modal-detail-label">ID</span>
        <span class="adm-modal-detail-value" style="font-size:12px;font-family:monospace">${admEscape(i.id)}</span>
      </div>
      <div class="adm-modal-detail-row">
        <span class="adm-modal-detail-label">Type</span>
        <span class="adm-modal-detail-value"><span class="adm-badge type">${admEscape(i.feature_type)}</span></span>
      </div>
      <div class="adm-modal-detail-row">
        <span class="adm-modal-detail-label">Owner</span>
        <span class="adm-modal-detail-value">${admEscape(i.username || '—')}</span>
      </div>
      <div class="adm-modal-detail-row">
        <span class="adm-modal-detail-label">Created</span>
        <span class="adm-modal-detail-value">${admDatetime(i.created_at)}</span>
      </div>
      <div class="adm-modal-detail-row">
        <span class="adm-modal-detail-label">Preview</span>
        <span class="adm-modal-detail-value" style="font-size:13px;color:var(--adm-text-muted);text-align:left;max-width:300px;word-break:break-word;">${admEscape(i.preview || '—')}</span>
      </div>
      <div class="adm-modal-actions">
        <button class="adm-btn adm-btn-danger" onclick="admConfirmDeleteItin('${admEscape(iid)}','${admEscape(i.title)}')">
          🗑 Delete Itinerary
        </button>
        <button class="adm-btn adm-btn-ghost" onclick="admCloseItinModal()">Close</button>
      </div>`;
  } catch (err) {
    body.innerHTML = `<div class="adm-state-box"><div class="adm-state-text" style="color:var(--adm-red)">${admEscape(err.message)}</div></div>`;
  }
}

function admCloseItinModal() {
  document.getElementById('admItinModal').classList.remove('open');
}

function admConfirmDeleteItin(iid, title) {
  admCloseItinModal();
  const overlay = document.getElementById('admConfirmModal');
  const txt = document.getElementById('admConfirmText');
  const btn = document.getElementById('admConfirmOkBtn');
  if (!overlay || !txt || !btn) return;
  txt.innerHTML = `Are you sure you want to delete the itinerary:<br><span class="adm-confirm-target">"${admEscape(title)}"</span>?
    <br><br>This will permanently remove this history record. The user account is not affected.`;
  btn.onclick = async () => {
    admCloseConfirm();
    try {
      await admFetch(`${ADM_API.itineraries}/${iid}`, { method: 'DELETE' });
      admToast('Itinerary deleted.', 'success');
      admLoadItineraries();
    } catch (err) {
      admToast(err.message, 'error');
    }
  };
  overlay.classList.add('open');
}

/* ──────────────────────────────────────────────────────────────────────────
   Confirm dialog helpers
   ────────────────────────────────────────────────────────────────────────── */
function admCloseConfirm() {
  document.getElementById('admConfirmModal').classList.remove('open');
}

/* ──────────────────────────────────────────────────────────────────────────
   Pagination builder
   ────────────────────────────────────────────────────────────────────────── */
function admBuildPager(page, pages, loadFn) {
  if (pages <= 1) return '';
  const makeBtn = (p, label, disabled, current) =>
    `<button class="adm-pg-btn${current ? ' current' : ''}" ${disabled ? 'disabled' : ''} onclick="${loadFn}(${p})">${label}</button>`;

  let btns = makeBtn(page - 1, '←', page <= 1, false);

  // Show window of pages
  const window_ = 3;
  let lo = Math.max(1, page - window_);
  let hi = Math.min(pages, page + window_);
  if (lo > 1) btns += `<button class="adm-pg-btn" onclick="${loadFn}(1)">1</button><span style="color:var(--adm-text-subtle);padding:0 4px">…</span>`;
  for (let p = lo; p <= hi; p++) btns += makeBtn(p, p, false, p === page);
  if (hi < pages) btns += `<span style="color:var(--adm-text-subtle);padding:0 4px">…</span><button class="adm-pg-btn" onclick="${loadFn}(${pages})">${pages}</button>`;

  btns += makeBtn(page + 1, '→', page >= pages, false);
  return `<div class="adm-pagination-btns">${btns}</div>`;
}

/* ──────────────────────────────────────────────────────────────────────────
   DOMContentLoaded — wire up everything
   ────────────────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  // Nav items
  document.querySelectorAll('[data-page]').forEach(el => {
    el.addEventListener('click', () => admNavigate(el.dataset.page));
  });

  // Logout
  document.getElementById('admLogoutBtn')?.addEventListener('click', admLogout);

  // Mobile hamburger
  document.getElementById('admHamburger')?.addEventListener('click', admToggleSidebar);
  document.getElementById('admSidebarOverlay')?.addEventListener('click', admCloseSidebar);

  // Confirm cancel
  document.getElementById('admConfirmCancelBtn')?.addEventListener('click', admCloseConfirm);

  // Modal close on overlay click
  document.querySelectorAll('.adm-modal-overlay').forEach(ov => {
    ov.addEventListener('click', e => { if (e.target === ov) ov.classList.remove('open'); });
  });

  // Escape key closes modals
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.adm-modal-overlay.open').forEach(m => m.classList.remove('open'));
    }
  });

  // User search input
  document.getElementById('admUsersSearch')?.addEventListener('input', e => admUserSearch(e.target.value));
  document.getElementById('admUsersRoleFilter')?.addEventListener('change', e => admUserRoleFilter(e.target.value));
  document.getElementById('admUsersRefresh')?.addEventListener('click', () => admLoadUsers());

  // Itinerary search input
  document.getElementById('admItinSearch')?.addEventListener('input', e => admItinSearch(e.target.value));
  document.getElementById('admItinTypeFilter')?.addEventListener('change', e => admItinTypeFilter(e.target.value));
  document.getElementById('admItinRefresh')?.addEventListener('click', () => admLoadItineraries());

  // Auth check and initial load
  admCheckAuth();
});
