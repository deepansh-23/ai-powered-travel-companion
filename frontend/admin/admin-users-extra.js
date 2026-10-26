/**
 * Admin — account controls: filters, deletion requests, password reset.
 * Loaded after admin.js; reuses admFetch, admToast, admEscape, admDatetime, admHandleAuthError.
 */

// ---- filters on the Users page
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('admUsersStatusFilter')?.addEventListener('change', (e) => {
    admState.users.status = e.target.value; admState.users.page = 1; admLoadUsers();
  });
  document.getElementById('admUsersSort')?.addEventListener('change', (e) => {
    admState.users.sort = e.target.value; admState.users.page = 1; admLoadUsers();
  });
});

// ---- deletion requests (asked for by users, decided by an admin)
const ADM_DELREQ_API = '/api/admin/deletion-requests';
let admDelReqs = [];

async function admLoadDeletionRequests() {
  const box = document.getElementById('admDelReqPanel');
  if (!box) return;
  try {
    const res = await admFetch(ADM_DELREQ_API);
    admDelReqs = res.requests || [];
  } catch (err) {
    if (admHandleAuthError(err)) return;
    box.hidden = true;
    return;
  }
  if (!admDelReqs.length) { box.hidden = true; box.innerHTML = ''; return; }
  box.hidden = false;
  box.innerHTML = `
    <div class="adm-delreq-head">🗑️ Account deletion requests <span class="adm-badge badge-inactive">${admDelReqs.length}</span></div>
    <div class="adm-delreq-list">${admDelReqs.map(r => `
      <div class="adm-delreq-row">
        <div>
          <b>${admEscape(r.username)}</b>${r.is_admin ? ' <span class="adm-badge badge-admin">Admin</span>' : ''}
          <div class="adm-set-desc">Asked ${admDatetime(r.requested_at)} · registered ${admDatetime(r.registered_at)} · last active ${admDatetime(r.last_active_at)}</div>
          ${r.reason ? `<div class="adm-delreq-reason">“${admEscape(r.reason)}”</div>` : ''}
        </div>
        <div class="adm-delreq-actions">
          <button class="adm-btn adm-btn-danger" onclick="admApproveDeletion('${admEscape(r.id)}', '${admEscape(r.username)}')">Approve &amp; delete</button>
          <button class="adm-btn adm-btn-ghost" onclick="admDismissDeletion('${admEscape(r.id)}')">Dismiss</button>
        </div>
      </div>`).join('')}</div>`;
}

function admApproveDeletion(id, username) {
  const overlay = document.getElementById('admConfirmModal');
  const txt = document.getElementById('admConfirmText');
  const btn = document.getElementById('admConfirmOkBtn');
  if (!overlay || !txt || !btn) return;
  txt.innerHTML = `Delete the account of <strong>${admEscape(username)}</strong>?<br><br>This permanently removes their login, History and saved sessions. Their reviews stay, but become anonymous.`;
  btn.onclick = async () => {
    admCloseConfirm();
    try {
      await admFetch(`${ADM_DELREQ_API}/${encodeURIComponent(id)}/approve`, { method: 'POST' });
      admToast('Account deleted.', 'success');
      admLoadUsers(admState.users.page);
    } catch (err) {
      if (admHandleAuthError(err)) return;
      admToast(err.message, 'error');
    }
  };
  overlay.classList.add('open');
}

async function admDismissDeletion(id) {
  try {
    await admFetch(`${ADM_DELREQ_API}/${encodeURIComponent(id)}/dismiss`, { method: 'POST' });
    admToast('Request dismissed. The account stays active.', 'success');
    admLoadUsers(admState.users.page);
  } catch (err) {
    if (admHandleAuthError(err)) return;
    admToast(err.message, 'error');
  }
}

// ---- reset a user's password (a random temporary password, shown once)
function admResetUserPassword(uid, username) {
  admCloseUserModal();
  const overlay = document.getElementById('admConfirmModal');
  const txt = document.getElementById('admConfirmText');
  const btn = document.getElementById('admConfirmOkBtn');
  if (!overlay || !txt || !btn) return;
  txt.innerHTML = `Reset the password of <strong>${admEscape(username)}</strong>?<br><br>They are signed out everywhere and get a temporary password that you must pass on to them privately. It is shown only once.`;
  btn.onclick = async () => {
    admCloseConfirm();
    try {
      const res = await admFetch(`${ADM_API.users}/${encodeURIComponent(uid)}/reset-password`, { method: 'POST' });
      admShowTempPassword(username, res.temporary_password, res.message);
    } catch (err) {
      if (admHandleAuthError(err)) return;
      admToast(err.message, 'error');
    }
  };
  overlay.classList.add('open');
}

function admShowTempPassword(username, password, message) {
  const body = document.getElementById('admResetPwBody');
  if (!body) return;
  body.innerHTML = `
    <p class="adm-set-desc">New password for <b>${admEscape(username)}</b>:</p>
    <div class="adm-temp-pw" id="admTempPw" tabindex="0">${admEscape(password)}</div>
    <p class="adm-set-warn">${admEscape(message || '')} This window is the only place it is shown.</p>
    <div class="adm-modal-actions">
      <button class="adm-btn adm-btn-primary" id="admCopyPw">Copy password</button>
      <button class="adm-btn adm-btn-ghost" id="admClosePw">Done</button>
    </div>`;
  const overlay = document.getElementById('admResetPwModal');
  const close = () => { body.innerHTML = ''; overlay.classList.remove('open'); };
  document.getElementById('admClosePw').onclick = close;
  document.getElementById('admCopyPw').onclick = async (e) => {
    try { await navigator.clipboard.writeText(password); e.target.textContent = 'Copied ✓'; }
    catch (_) { admToast('Copy failed: select the password and copy it manually.', 'error'); }
  };
  overlay.classList.add('open');
}
