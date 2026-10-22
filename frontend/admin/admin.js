/**
 * Admin Control Center — JavaScript
 * Isolated from main app: all globals prefixed with Adm / adm
 * Vanilla JavaScript only — zero external frameworks.
 */

/* ──────────────────────────────────────────────────────────────────────────
   Configuration
   ────────────────────────────────────────────────────────────────────────── */
const ADM_API = {
  overview:     '/api/admin/overview',
  users:        '/api/admin/users',
  itineraries:  '/api/admin/itineraries',
  monitoring:   '/api/admin/monitoring',
  systemHealth: '/api/admin/system-health',
  authStatus:   '/api/admin/auth-status',
  stepup:       '/api/admin/stepup',
  logout:       '/api/auth/logout',
  me:           '/api/auth/me',
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

  monitoring: { window: '15m', autoRefreshInterval: 30, timer: null },
};

/* ──────────────────────────────────────────────────────────────────────────
   Theme System
   ────────────────────────────────────────────────────────────────────────── */
function admInitTheme() {
  const select = document.getElementById('admThemeSelect');
  const current = localStorage.getItem('adm_theme') || 'dark';
  if (select) {
    select.value = current;
    select.addEventListener('change', (e) => {
      admSetTheme(e.target.value);
    });
  }
  admApplyTheme(current);

  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
      const saved = localStorage.getItem('adm_theme') || 'dark';
      if (saved === 'system') {
        admApplyTheme('system');
      }
    });
  }
}

function admSetTheme(theme) {
  localStorage.setItem('adm_theme', theme);
  admApplyTheme(theme);
}

function admApplyTheme(theme) {
  const isLight = theme === 'light' || (theme === 'system' && window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches);
  if (isLight) {
    document.documentElement.classList.add('adm-theme-light');
    document.body.classList.add('adm-theme-light');
  } else {
    document.documentElement.classList.remove('adm-theme-light');
    document.body.classList.remove('adm-theme-light');
  }
}

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
    const err = Object.assign(new Error(msg), { status: res.status, headers: res.headers });
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

function admHandleAuthError(err) {
  if (err && err.status === 401) {
    admShowStepupModal();
    return true;
  }
  return false;
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
   Step-up Re-Authentication Modal
   ────────────────────────────────────────────────────────────────────────── */
function admShowStepupModal() {
  const modal = document.getElementById('admStepupModal');
  const input = document.getElementById('admStepupPassword');
  const errBox = document.getElementById('admStepupError');
  if (modal) {
    if (errBox) errBox.hidden = true;
    if (input) input.value = '';
    modal.classList.add('open');
    if (input) setTimeout(() => input.focus(), 100);
  }
}

function admCloseStepupModal() {
  const modal = document.getElementById('admStepupModal');
  if (modal) modal.classList.remove('open');
}

async function admSubmitStepup() {
  const input = document.getElementById('admStepupPassword');
  const errBox = document.getElementById('admStepupError');
  const submitBtn = document.getElementById('admStepupSubmitBtn');
  const pwd = (input?.value || '').trim();

  if (!pwd) {
    if (errBox) { errBox.textContent = 'Please enter your password.'; errBox.hidden = false; }
    return;
  }

  if (errBox) errBox.hidden = true;
  if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Verifying…'; }

  try {
    await admFetch(ADM_API.stepup, {
      method: 'POST',
      body: JSON.stringify({ password: pwd }),
    });

    admCloseStepupModal();
    admToast('Admin authorization verified.', 'success');
    // Refresh current page
    admNavigate(admState.currentPage);
  } catch (err) {
    if (errBox) {
      errBox.textContent = err.message || 'Verification failed. Please check your password.';
      errBox.hidden = false;
    }
    if (input) input.select();
  } finally {
    if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Unlock Dashboard'; }
  }
}

/* ──────────────────────────────────────────────────────────────────────────
   Navigation
   ────────────────────────────────────────────────────────────────────────── */
function admNavigate(page) {
  admState.currentPage = page;

  // Clear monitoring auto-refresh timer if leaving monitoring
  if (page !== 'monitoring' && admState.monitoring.timer) {
    clearInterval(admState.monitoring.timer);
    admState.monitoring.timer = null;
  }

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
  else if (page === 'monitoring') admLoadMonitoring();
  else if (page === 'health') admLoadHealth();
  else if (page === 'settings' && typeof admLoadSettings === 'function') admLoadSettings();
  else if (page === 'feedback' && typeof admLoadFeedbackPage === 'function') admLoadFeedbackPage();
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
    const status = await admFetch(ADM_API.authStatus);

    if (!status.authenticated) {
      window.location.href = '/pages/login.html?next=/admin/';
      return;
    }

    if (!status.is_admin) {
      document.getElementById('admGate').innerHTML = `
        <div style="display:flex;align-items:center;justify-content:center;min-height:100vh;text-align:center;padding:24px;">
          <div>
            <div style="font-size:56px;margin-bottom:16px;">🚫</div>
            <h2 style="color:var(--adm-red,#f85149);margin-bottom:8px;">Access Denied</h2>
            <p style="color:var(--adm-text-muted,#8b949e);margin-bottom:24px;">Your account does not have admin privileges.</p>
            <a href="/" style="color:var(--adm-accent,#58a6ff);font-size:14px;text-decoration:none;">← Return to main site</a>
          </div>
        </div>`;
      return;
    }

    admState.adminUsername = status.username || 'Admin';
    const nameEl = document.getElementById('admAdminName');
    if (nameEl) nameEl.textContent = admState.adminUsername;

    // Check if step-up re-authentication is required
    if (!status.stepup_valid) {
      admShowStepupModal();
      return;
    }

    // Fully authorized with active step-up
    admNavigate('overview');
  } catch (err) {
    if (err.status === 401) {
      admShowStepupModal();
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
  } catch (_) {}
  window.location.href = '/';
}

/* ──────────────────────────────────────────────────────────────────────────
   PAGE: Overview
   ────────────────────────────────────────────────────────────────────────── */
async function admLoadOverview() {
  const container = document.getElementById('admOverviewCards');
  if (!container) return;
  admShowLoading(container);

  try {
    const data = await admFetch(ADM_API.overview);
    admRenderOverview(data);
  } catch (err) {
    if (admHandleAuthError(err)) return;
    admShowError(container, err.message);
  }
}

function admRenderOverview(d) {
  const container = document.getElementById('admOverviewCards');
  if (!container) return;

  const dbBadge = d.database_healthy
    ? '<span class="adm-badge badge-admin">Connected</span>'
    : '<span class="adm-badge badge-inactive">Offline</span>';

  container.innerHTML = `
    <div class="adm-card">
      <div class="adm-card-header">
        <span class="adm-card-title">Total Users</span>
        <span class="adm-card-icon">👥</span>
      </div>
      <div class="adm-card-value">${admNumFmt(d.total_users)}</div>
      <div class="adm-card-sub">${admNumFmt(d.active_users)} active &bull; ${admNumFmt(d.inactive_users)} inactive</div>
    </div>

    <div class="adm-card">
      <div class="adm-card-header">
        <span class="adm-card-title">Admins</span>
        <span class="adm-card-icon">🛡️</span>
      </div>
      <div class="adm-card-value">${admNumFmt(d.total_admins)}</div>
      <div class="adm-card-sub">With control center access</div>
    </div>

    <div class="adm-card">
      <div class="adm-card-header">
        <span class="adm-card-title">Saved Itineraries</span>
        <span class="adm-card-icon">🗺️</span>
      </div>
      <div class="adm-card-value">${admNumFmt(d.total_itineraries)}</div>
      <div class="adm-card-sub">Across all user accounts</div>
    </div>

    <div class="adm-card">
      <div class="adm-card-header">
        <span class="adm-card-title">New Registrations</span>
        <span class="adm-card-icon">📈</span>
      </div>
      <div class="adm-card-value">${admNumFmt(d.registrations_last_7_days)}</div>
      <div class="adm-card-sub">Last 7 days</div>
    </div>

    <div class="adm-card">
      <div class="adm-card-header">
        <span class="adm-card-title">PostgreSQL Status</span>
        <span class="adm-card-icon">🗄️</span>
      </div>
      <div class="adm-card-value" style="font-size:20px;padding-top:4px;">${dbBadge}</div>
      <div class="adm-card-sub">${d.db_error ? admEscape(d.db_error) : 'Aiven Managed Cloud'}</div>
    </div>
  `;
}

/* ──────────────────────────────────────────────────────────────────────────
   PAGE: User Management
   ────────────────────────────────────────────────────────────────────────── */
let userSearchTimer = null;

function admUserSearch(val) {
  clearTimeout(userSearchTimer);
  userSearchTimer = setTimeout(() => {
    admState.users.search = val.trim();
    admState.users.page = 1;
    admLoadUsers();
  }, 280);
}

function admUserRoleFilter(val) {
  admState.users.role = val;
  admState.users.page = 1;
  admLoadUsers();
}

async function admLoadUsers(page = 1) {
  admState.users.page = page;
  const tbody = document.getElementById('admUsersTbody');
  const totalEl = document.getElementById('admUsersTotal');
  const pagerEl = document.getElementById('admUsersPager');
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="7"><div class="adm-state-box"><div class="adm-spinner"></div><div class="adm-state-text">Loading users…</div></div></td></tr>`;

  try {
    const params = new URLSearchParams({ page });
    if (admState.users.search) params.set('search', admState.users.search);
    if (admState.users.role) params.set('role', admState.users.role);

    const res = await admFetch(`${ADM_API.users}?${params}`);
    admState.users.data = res.users;
    admState.users.total = res.total;
    admState.users.pages = res.pages;

    if (totalEl) totalEl.textContent = `${admNumFmt(res.total)} user${res.total === 1 ? '' : 's'} registered`;
    admRenderUsers(res.users);
    if (pagerEl) pagerEl.innerHTML = admBuildPager(res.page, res.pages, 'admLoadUsers');
  } catch (err) {
    if (admHandleAuthError(err)) return;
    tbody.innerHTML = `<tr><td colspan="7"><div class="adm-state-box"><div class="adm-state-icon">⚠️</div><div class="adm-state-text">${admEscape(err.message)}</div></div></td></tr>`;
  }
}

function admRenderUsers(users) {
  const tbody = document.getElementById('admUsersTbody');
  if (!tbody) return;

  if (!users || users.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7"><div class="adm-state-box"><div class="adm-state-icon">🔍</div><div class="adm-state-title">No users found</div></div></td></tr>`;
    return;
  }

  tbody.innerHTML = users.map(u => `
    <tr onclick="admOpenUserModal('${admEscape(u.id)}')">
      <td><strong>${admEscape(u.username)}</strong></td>
      <td style="font-family:monospace;font-size:12px;color:var(--adm-text-muted);">${admEscape(u.id.substring(0,8))}…</td>
      <td>${u.is_active ? '<span class="adm-badge badge-active">Active</span>' : '<span class="adm-badge badge-inactive">Inactive</span>'}</td>
      <td>${u.is_admin ? '<span class="adm-badge badge-admin">Admin</span>' : '<span class="adm-badge badge-user">User</span>'}</td>
      <td>${admDate(u.created_at)}</td>
      <td>${admDatetime(u.last_login_at)}</td>
      <td><span class="adm-num-chip">${u.itinerary_count}</span></td>
    </tr>
  `).join('');
}

async function admOpenUserModal(uid) {
  const body = document.getElementById('admUserModalBody');
  const modal = document.getElementById('admUserModal');
  if (!body || !modal) return;
  admShowLoading(body);
  modal.classList.add('open');

  try {
    const u = await admFetch(`${ADM_API.users}/${uid}`);
    body.innerHTML = `
      <div class="adm-detail-grid">
        <div class="adm-detail-item">
          <div class="adm-detail-label">Username</div>
          <div class="adm-detail-value" style="font-weight:700;">${admEscape(u.username)}</div>
        </div>
        <div class="adm-detail-item">
          <div class="adm-detail-label">User ID</div>
          <div class="adm-detail-value" style="font-family:monospace;font-size:11px;">${admEscape(u.id)}</div>
        </div>
        <div class="adm-detail-item">
          <div class="adm-detail-label">Status</div>
          <div class="adm-detail-value">${u.is_active ? '<span class="adm-badge badge-active">Active</span>' : '<span class="adm-badge badge-inactive">Inactive</span>'}</div>
        </div>
        <div class="adm-detail-item">
          <div class="adm-detail-label">Role</div>
          <div class="adm-detail-value">${u.is_admin ? '<span class="adm-badge badge-admin">Admin</span>' : '<span class="adm-badge badge-user">Regular User</span>'}</div>
        </div>
        <div class="adm-detail-item">
          <div class="adm-detail-label">Registered</div>
          <div class="adm-detail-value">${admDatetime(u.created_at)}</div>
        </div>
        <div class="adm-detail-item">
          <div class="adm-detail-label">Last Login</div>
          <div class="adm-detail-value">${admDatetime(u.last_login_at)}</div>
        </div>
        <div class="adm-detail-item" style="grid-column:1/-1;">
          <div class="adm-detail-label">Saved Itineraries</div>
          <div class="adm-detail-value">${u.itinerary_count} itinerary record(s)</div>
        </div>
      </div>

      <div class="adm-modal-actions">
        <button
          class="adm-btn ${u.is_active ? 'adm-btn-danger' : 'adm-btn-primary'}"
          onclick="admToggleUserActive('${u.id}', ${!u.is_active})"
        >
          ${u.is_active ? 'Deactivate User' : 'Activate User'}
        </button>

        <button
          class="adm-btn ${u.is_admin ? 'adm-btn-danger' : 'adm-btn-primary'}"
          onclick="admToggleUserAdmin('${u.id}', ${!u.is_admin})"
        >
          ${u.is_admin ? 'Revoke Admin Role' : 'Promote to Admin'}
        </button>

        <button
          class="adm-btn adm-btn-danger"
          style="margin-left:auto;"
          onclick="admConfirmDeleteUser('${u.id}', '${admEscape(u.username)}')"
        >
          Delete User
        </button>
      </div>
    `;
  } catch (err) {
    if (admHandleAuthError(err)) return;
    admShowError(body, err.message);
  }
}

function admCloseUserModal() {
  document.getElementById('admUserModal')?.classList.remove('open');
}

async function admToggleUserActive(uid, newActive) {
  try {
    await admFetch(`${ADM_API.users}/${uid}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: newActive }),
    });
    admToast(`User ${newActive ? 'activated' : 'deactivated'}.`, 'success');
    admCloseUserModal();
    admLoadUsers(admState.users.page);
  } catch (err) {
    admToast(err.message, 'error');
  }
}

async function admToggleUserAdmin(uid, newAdmin) {
  try {
    await admFetch(`${ADM_API.users}/${uid}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_admin: newAdmin }),
    });
    admToast(`User role updated to ${newAdmin ? 'Admin' : 'Regular User'}.`, 'success');
    admCloseUserModal();
    admLoadUsers(admState.users.page);
  } catch (err) {
    admToast(err.message, 'error');
  }
}

function admConfirmDeleteUser(uid, username) {
  admCloseUserModal();
  const overlay = document.getElementById('admConfirmModal');
  const txt = document.getElementById('admConfirmText');
  const btn = document.getElementById('admConfirmOkBtn');
  if (!overlay || !txt || !btn) return;
  txt.innerHTML = `Are you sure you want to delete user <strong>${admEscape(username)}</strong>?<br><br>
    This will permanently remove the user, all their itineraries, login sessions, and history.`;
  btn.onclick = async () => {
    admCloseConfirm();
    try {
      await admFetch(`${ADM_API.users}/${uid}`, { method: 'DELETE' });
      admToast('User deleted permanently.', 'success');
      admLoadUsers(admState.users.page);
    } catch (err) {
      admToast(err.message, 'error');
    }
  };
  overlay.classList.add('open');
}

/* ──────────────────────────────────────────────────────────────────────────
   PAGE: Itinerary Management
   ────────────────────────────────────────────────────────────────────────── */
let itinSearchTimer = null;

function admItinSearch(val) {
  clearTimeout(itinSearchTimer);
  itinSearchTimer = setTimeout(() => {
    admState.itineraries.search = val.trim();
    admState.itineraries.page = 1;
    admLoadItineraries();
  }, 280);
}

function admItinTypeFilter(val) {
  admState.itineraries.type = val;
  admState.itineraries.page = 1;
  admLoadItineraries();
}

async function admLoadItineraries(page = 1) {
  admState.itineraries.page = page;
  const tbody = document.getElementById('admItinTbody');
  const totalEl = document.getElementById('admItinTotal');
  const pagerEl = document.getElementById('admItinPager');
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="5"><div class="adm-state-box"><div class="adm-spinner"></div><div class="adm-state-text">Loading itineraries…</div></div></td></tr>`;

  try {
    const params = new URLSearchParams({ page });
    if (admState.itineraries.search) params.set('search', admState.itineraries.search);
    if (admState.itineraries.type) params.set('feature_type', admState.itineraries.type);

    const res = await admFetch(`${ADM_API.itineraries}?${params}`);
    admState.itineraries.data = res.itineraries;
    admState.itineraries.total = res.total;
    admState.itineraries.pages = res.pages;

    if (totalEl) totalEl.textContent = `${admNumFmt(res.total)} saved itinerary record${res.total === 1 ? '' : 's'}`;
    admRenderItineraries(res.itineraries);
    if (pagerEl) pagerEl.innerHTML = admBuildPager(res.page, res.pages, 'admLoadItineraries');
  } catch (err) {
    if (admHandleAuthError(err)) return;
    tbody.innerHTML = `<tr><td colspan="5"><div class="adm-state-box"><div class="adm-state-icon">⚠️</div><div class="adm-state-text">${admEscape(err.message)}</div></div></td></tr>`;
  }
}

function admRenderItineraries(items) {
  const tbody = document.getElementById('admItinTbody');
  if (!tbody) return;

  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5"><div class="adm-state-box"><div class="adm-state-icon">🔍</div><div class="adm-state-title">No itineraries found</div></div></td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(i => `
    <tr onclick="admOpenItinModal('${admEscape(i.id)}')">
      <td><strong>${admEscape(i.title)}</strong></td>
      <td><span class="adm-type-badge">${admEscape(i.feature_type)}</span></td>
      <td>${admEscape(i.username || '—')}</td>
      <td class="adm-preview-col">${admEscape(i.preview)}</td>
      <td>${admDate(i.created_at)}</td>
    </tr>
  `).join('');
}

async function admOpenItinModal(iid) {
  const body = document.getElementById('admItinModalBody');
  const modal = document.getElementById('admItinModal');
  if (!body || !modal) return;
  admShowLoading(body);
  modal.classList.add('open');

  try {
    const item = await admFetch(`${ADM_API.itineraries}/${iid}`);
    let payloadJson = '—';
    try {
      payloadJson = JSON.stringify(item.payload, null, 2);
    } catch (_) {}

    body.innerHTML = `
      <div class="adm-detail-grid">
        <div class="adm-detail-item" style="grid-column:1/-1;">
          <div class="adm-detail-label">Title</div>
          <div class="adm-detail-value" style="font-weight:700;">${admEscape(item.title)}</div>
        </div>
        <div class="adm-detail-item">
          <div class="adm-detail-label">Type</div>
          <div class="adm-detail-value"><span class="adm-type-badge">${admEscape(item.feature_type)}</span></div>
        </div>
        <div class="adm-detail-item">
          <div class="adm-detail-label">Owner</div>
          <div class="adm-detail-value">${admEscape(item.username || '—')}</div>
        </div>
        <div class="adm-detail-item">
          <div class="adm-detail-label">Created</div>
          <div class="adm-detail-value">${admDatetime(item.created_at)}</div>
        </div>
        <div class="adm-detail-item">
          <div class="adm-detail-label">Record ID</div>
          <div class="adm-detail-value" style="font-family:monospace;font-size:11px;">${admEscape(item.id)}</div>
        </div>
        <div class="adm-detail-item" style="grid-column:1/-1;">
          <div class="adm-detail-label">Details</div>
          ${typeof admRenderRecordView === 'function' ? admRenderRecordView(item.feature_type, item.payload) : ''}
          <button type="button" class="adm-btn adm-btn-ghost adm-raw-toggle" onclick="admToggleRaw(this)">Show raw data</button>
          <div class="adm-json-wrap" hidden>${admEscape(payloadJson)}</div>
        </div>
      </div>

      <div class="adm-modal-actions">
        <button
          class="adm-btn adm-btn-danger"
          style="margin-left:auto;"
          onclick="admConfirmDeleteItin('${item.id}', '${admEscape(item.title)}')"
        >
          Delete Itinerary
        </button>
      </div>
    `;
  } catch (err) {
    if (admHandleAuthError(err)) return;
    admShowError(body, err.message);
  }
}

function admCloseItinModal() {
  document.getElementById('admItinModal')?.classList.remove('open');
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

function admCloseConfirm() {
  document.getElementById('admConfirmModal')?.classList.remove('open');
}

/* ──────────────────────────────────────────────────────────────────────────
   PAGE: API Monitoring
   ────────────────────────────────────────────────────────────────────────── */
async function admLoadMonitoring(winOverride) {
  if (winOverride) admState.monitoring.window = winOverride;
  const win = admState.monitoring.window || '15m';

  const cardsContainer = document.getElementById('admMonCards');
  const slowestTbody = document.getElementById('admMonSlowestTbody');
  const errorsTbody = document.getElementById('admMonErrorsTbody');
  const failuresTbody = document.getElementById('admMonFailuresTbody');
  const subtitle = document.getElementById('admMonSubtitle');
  const infoEl = document.getElementById('admMonProcessInfo');

  if (!cardsContainer) return;

  // Toggle button active state
  document.querySelectorAll('.adm-pill-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.win === win);
  });

  try {
    const data = await admFetch(`${ADM_API.monitoring}?window=${win}`);

    if (subtitle) subtitle.textContent = `Real-time request metrics for ${data.window_label.toLowerCase()}.`;
    if (infoEl) infoEl.textContent = `Uptime: ${Math.floor(data.uptime_seconds / 60)}m • ${admNumFmt(data.total_lifetime_requests)} requests recorded since startup`;

    // Render KPI Cards
    const successRate = data.total_requests > 0
      ? ((data.successful_requests / data.total_requests) * 100).toFixed(1)
      : '100.0';

    cardsContainer.innerHTML = `
      <div class="adm-mon-card">
        <div class="adm-mon-card-label">Total Requests</div>
        <div class="adm-mon-card-val">${admNumFmt(data.total_requests)}</div>
        <div class="adm-mon-card-sub">${data.window_label}</div>
      </div>
      <div class="adm-mon-card">
        <div class="adm-mon-card-label">Success Rate</div>
        <div class="adm-mon-card-val" style="color:var(--adm-green);">${successRate}%</div>
        <div class="adm-mon-card-sub">${admNumFmt(data.successful_requests)} 2xx/3xx calls</div>
      </div>
      <div class="adm-mon-card">
        <div class="adm-mon-card-label">Error Rate</div>
        <div class="adm-mon-card-val" style="color:${data.error_rate_percent > 0 ? 'var(--adm-red)' : 'var(--adm-text)'};">${data.error_rate_percent}%</div>
        <div class="adm-mon-card-sub">${admNumFmt(data.failed_requests)} failed calls</div>
      </div>
      <div class="adm-mon-card">
        <div class="adm-mon-card-label">Avg Response Time</div>
        <div class="adm-mon-card-val">${data.avg_response_time_ms} <span style="font-size:14px;font-weight:normal;color:var(--adm-text-muted);">ms</span></div>
        <div class="adm-mon-card-sub">Measured via middleware</div>
      </div>
      <div class="adm-mon-card">
        <div class="adm-mon-card-label">Client Errors (4xx)</div>
        <div class="adm-mon-card-val" style="color:var(--adm-yellow);">${admNumFmt(data.c4xx_count)}</div>
        <div class="adm-mon-card-sub">Bad requests, auth failures</div>
      </div>
      <div class="adm-mon-card">
        <div class="adm-mon-card-label">Server Errors (5xx)</div>
        <div class="adm-mon-card-val" style="color:var(--adm-red);">${admNumFmt(data.c5xx_count)}</div>
        <div class="adm-mon-card-sub">Internal server exceptions</div>
      </div>
    `;

    // Render Slowest Endpoints Table
    if (slowestTbody) {
      if (!data.slowest_endpoints || data.slowest_endpoints.length === 0) {
        slowestTbody.innerHTML = `<tr><td colspan="4" style="text-align:center;color:var(--adm-text-muted);padding:20px;">No traffic recorded in this time window.</td></tr>`;
      } else {
        slowestTbody.innerHTML = data.slowest_endpoints.map(item => `
          <tr>
            <td><code>${admEscape(item.endpoint)}</code></td>
            <td><strong>${item.avg_duration_ms} ms</strong></td>
            <td style="color:var(--adm-text-muted);">${item.max_duration_ms} ms</td>
            <td><span class="adm-num-chip">${item.count}</span></td>
          </tr>
        `).join('');
      }
    }

    // Render Endpoints with Most Errors
    if (errorsTbody) {
      if (!data.endpoints_with_most_errors || data.endpoints_with_most_errors.length === 0) {
        errorsTbody.innerHTML = `<tr><td colspan="3" style="text-align:center;color:var(--adm-green);padding:20px;">✓ Zero API errors recorded in this time window.</td></tr>`;
      } else {
        errorsTbody.innerHTML = data.endpoints_with_most_errors.map(item => {
          const badgeClass = item.last_status_code >= 500 ? 's5xx' : 's4xx';
          return `
            <tr>
              <td><code>${admEscape(item.endpoint)}</code></td>
              <td><span style="color:var(--adm-red);font-weight:700;">${item.error_count}</span></td>
              <td><span class="adm-http-badge ${badgeClass}">${item.last_status_code}</span></td>
            </tr>
          `;
        }).join('');
      }
    }

    // Render Recent Failures Table
    if (failuresTbody) {
      if (!data.recent_failures || data.recent_failures.length === 0) {
        failuresTbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--adm-green);padding:24px;">✓ No recent API failures recorded.</td></tr>`;
      } else {
        failuresTbody.innerHTML = data.recent_failures.map(f => {
          const badgeClass = f.status_code >= 500 ? 's5xx' : 's4xx';
          return `
            <tr>
              <td>${admDatetime(f.timestamp)}</td>
              <td><strong>${admEscape(f.method)}</strong></td>
              <td><code>${admEscape(f.path)}</code></td>
              <td><span class="adm-http-badge ${badgeClass}">HTTP ${f.status_code}</span></td>
              <td style="color:var(--adm-text-muted);">${f.duration_ms} ms</td>
            </tr>
          `;
        }).join('');
      }
    }

  } catch (err) {
    if (admHandleAuthError(err)) return;
    admShowError(cardsContainer, err.message);
  }
}

function admSetupMonitoringInterval() {
  const select = document.getElementById('admMonAutoRefresh');
  if (!select) return;

  const updateInterval = () => {
    if (admState.monitoring.timer) {
      clearInterval(admState.monitoring.timer);
      admState.monitoring.timer = null;
    }
    const sec = parseInt(select.value, 10);
    if (sec > 0 && admState.currentPage === 'monitoring') {
      admState.monitoring.timer = setInterval(() => {
        if (admState.currentPage === 'monitoring') {
          admLoadMonitoring();
        }
      }, sec * 1000);
    }
  };

  select.addEventListener('change', updateInterval);
  updateInterval();
}

/* ──────────────────────────────────────────────────────────────────────────
   PAGE: System Health
   ────────────────────────────────────────────────────────────────────────── */
async function admLoadHealth() {
  const banner = document.getElementById('admHealthBanner');
  const cards = document.getElementById('admHealthCards');
  const tbody = document.getElementById('admHealthDepsTbody');
  if (!banner) return;

  admShowLoading(banner);

  try {
    const data = await admFetch(ADM_API.systemHealth);

    const stClass = data.status.toLowerCase(); // 'healthy', 'degraded', 'unavailable'
    const stBadge = stClass === 'healthy'
      ? '<span class="adm-badge badge-active" style="font-size:13px;">Healthy</span>'
      : stClass === 'degraded'
      ? '<span class="adm-badge" style="background:var(--adm-yellow-dim);color:var(--adm-yellow);font-size:13px;">Degraded</span>'
      : '<span class="adm-badge badge-inactive" style="font-size:13px;">Unavailable</span>';

    // Banner
    banner.innerHTML = `
      <div class="adm-health-status-wrap">
        <div class="adm-pulse-dot ${stClass}"></div>
        <div>
          <div class="adm-health-title">System Status: ${data.status}</div>
          <div class="adm-health-desc">
            FastAPI application is <strong>${data.app_status}</strong> &bull;
            PostgreSQL is <strong>${data.database_status}</strong>
            ${data.database_latency_ms != null ? `(${data.database_latency_ms} ms latency)` : ''}
          </div>
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:12px;">
        <span style="font-size:12px;color:var(--adm-text-muted);">Last checked: ${admDatetime(data.timestamp)}</span>
        ${stBadge}
      </div>
    `;

    // Cards Grid
    if (cards) {
      cards.innerHTML = `
        <div class="adm-health-card">
          <div class="adm-health-card-head">
            <span class="adm-health-card-title">Application Runtime</span>
            <span style="font-size:16px;">⚡</span>
          </div>
          <div class="adm-health-stat-line">
            <span class="adm-health-stat-label">FastAPI Status</span>
            <span class="adm-health-stat-value" style="color:var(--adm-green);">Running</span>
          </div>
          <div class="adm-health-stat-line">
            <span class="adm-health-stat-label">Measured Uptime</span>
            <span class="adm-health-stat-value">${admEscape(data.uptime_human)}</span>
          </div>
          <div class="adm-health-stat-line">
            <span class="adm-health-stat-label">Python Version</span>
            <span class="adm-health-stat-value">${admEscape(data.python_version)}</span>
          </div>
          <div class="adm-health-stat-line">
            <span class="adm-health-stat-label">App Release</span>
            <span class="adm-health-stat-value">v${admEscape(data.app_version)}</span>
          </div>
        </div>

        <div class="adm-health-card">
          <div class="adm-health-card-head">
            <span class="adm-health-card-title">Aiven PostgreSQL</span>
            <span style="font-size:16px;">🗄️</span>
          </div>
          <div class="adm-health-stat-line">
            <span class="adm-health-stat-label">Connectivity</span>
            <span class="adm-health-stat-value" style="color:${data.database_connected ? 'var(--adm-green)' : 'var(--adm-red)'};">
              ${data.database_connected ? 'Connected' : 'Offline'}
            </span>
          </div>
          <div class="adm-health-stat-line">
            <span class="adm-health-stat-label">Query Latency</span>
            <span class="adm-health-stat-value">${data.database_latency_ms != null ? data.database_latency_ms + ' ms' : 'N/A'}</span>
          </div>
          <div class="adm-health-stat-line">
            <span class="adm-health-stat-label">Timeout Safety</span>
            <span class="adm-health-stat-value">2000 ms strict cap</span>
          </div>
          <div class="adm-health-stat-line">
            <span class="adm-health-stat-label">Last Successful Check</span>
            <span class="adm-health-stat-value">${admDate(data.last_successful_check)}</span>
          </div>
        </div>

        <div class="adm-health-card">
          <div class="adm-health-card-head">
            <span class="adm-health-card-title">API Stability</span>
            <span style="font-size:16px;">📡</span>
          </div>
          <div class="adm-health-stat-line">
            <span class="adm-health-stat-label">Error Rate</span>
            <span class="adm-health-stat-value" style="color:${data.api_error_rate_percent > 5 ? 'var(--adm-red)' : 'var(--adm-green)'};">
              ${data.api_error_rate_percent}%
            </span>
          </div>
          <div class="adm-health-stat-line">
            <span class="adm-health-stat-label">Recorded Requests</span>
            <span class="adm-health-stat-value">${admNumFmt(data.api_total_requests)} (15m window)</span>
          </div>
          <div class="adm-health-stat-line">
            <span class="adm-health-stat-label">Public Health Route</span>
            <span class="adm-health-stat-value">/api/health (200 OK)</span>
          </div>
          <div class="adm-health-stat-line">
            <span class="adm-health-stat-label">Render Deployment</span>
            <span class="adm-health-stat-value">Production Ready</span>
          </div>
        </div>
      `;
    }

    // Dependencies Table
    if (tbody && data.dependencies) {
      tbody.innerHTML = Object.entries(data.dependencies).map(([name, dep]) => {
        const isOk = dep.status === 'Healthy' || dep.status === 'Configured';
        const badge = isOk
          ? '<span class="adm-badge badge-active">' + admEscape(dep.status) + '</span>'
          : '<span class="adm-badge badge-inactive">' + admEscape(dep.status) + '</span>';
        return `
          <tr>
            <td><strong>${admEscape(name)}</strong></td>
            <td>${badge}</td>
            <td style="color:var(--adm-text-muted);">${admEscape(dep.info)}</td>
          </tr>
        `;
      }).join('');
    }

  } catch (err) {
    if (admHandleAuthError(err)) return;
    admShowError(banner, err.message);
  }
}

/* ──────────────────────────────────────────────────────────────────────────
   Pagination builder
   ────────────────────────────────────────────────────────────────────────── */
function admBuildPager(page, pages, loadFn) {
  if (pages <= 1) return '';
  const makeBtn = (p, label, disabled, current) =>
    `<button class="adm-pg-btn${current ? ' current' : ''}" ${disabled ? 'disabled' : ''} onclick="${loadFn}(${p})">${label}</button>`;

  let btns = makeBtn(page - 1, '←', page <= 1, false);

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
  // Initialize Theme System
  admInitTheme();

  // Navigation items
  document.querySelectorAll('[data-page]').forEach(el => {
    el.addEventListener('click', () => admNavigate(el.dataset.page));
  });

  // Logout
  document.getElementById('admLogoutBtn')?.addEventListener('click', admLogout);

  // Mobile hamburger
  document.getElementById('admHamburger')?.addEventListener('click', admToggleSidebar);
  document.getElementById('admSidebarOverlay')?.addEventListener('click', admCloseSidebar);

  // Confirm dialog
  document.getElementById('admConfirmCancelBtn')?.addEventListener('click', admCloseConfirm);

  // Modal overlay click close (exclude stepup modal)
  document.querySelectorAll('.adm-modal-overlay').forEach(ov => {
    if (ov.id !== 'admStepupModal') {
      ov.addEventListener('click', e => { if (e.target === ov) ov.classList.remove('open'); });
    }
  });

  // Escape key closes modals (except stepup)
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.adm-modal-overlay.open').forEach(m => {
        if (m.id !== 'admStepupModal') m.classList.remove('open');
      });
    }
  });

  // Step-up Form submission
  document.getElementById('admStepupForm')?.addEventListener('submit', (e) => {
    e.preventDefault();
    admSubmitStepup();
  });

  // User search & filters
  document.getElementById('admUsersSearch')?.addEventListener('input', e => admUserSearch(e.target.value));
  document.getElementById('admUsersRoleFilter')?.addEventListener('change', e => admUserRoleFilter(e.target.value));
  document.getElementById('admUsersRefresh')?.addEventListener('click', () => admLoadUsers());

  // Itinerary search & filters
  document.getElementById('admItinSearch')?.addEventListener('input', e => admItinSearch(e.target.value));
  document.getElementById('admItinTypeFilter')?.addEventListener('change', e => admItinTypeFilter(e.target.value));
  document.getElementById('admItinRefresh')?.addEventListener('click', () => admLoadItineraries());

  // API Monitoring controls
  document.getElementById('admMonWin15m')?.addEventListener('click', () => admLoadMonitoring('15m'));
  document.getElementById('admMonWin24h')?.addEventListener('click', () => admLoadMonitoring('24h'));
  document.getElementById('admMonRefreshBtn')?.addEventListener('click', () => admLoadMonitoring());
  admSetupMonitoringInterval();

  // System Health controls
  document.getElementById('admHealthRefreshBtn')?.addEventListener('click', () => admLoadHealth());

  // Initial Auth Check
  admCheckAuth();
});
