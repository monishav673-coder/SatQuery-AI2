/* ============================================================
   SATQUERY AI — Auth Module
   Shared auth utilities used across all pages.
   ============================================================ */

const API_BASE = '';  // Same origin — Flask serves both frontend and API

/* ── API calls ─────────────────────────────────────────────── */

async function apiLogin(email, password) {
  try {
    const resp = await fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await resp.json();
    if (data.success) {
      localStorage.setItem('satquery_token', data.access_token);
      localStorage.setItem('satquery_user', JSON.stringify(data.user));
      if (data.user && data.user.preferred_language) {
        localStorage.setItem('satquery_lang', data.user.preferred_language);
      }
    }
    return data;
  } catch (e) {
    return { success: false, error: 'Network error. Please check your connection.' };
  }
}

async function apiRegister(payload) {
  try {
    const resp = await fetch(`${API_BASE}/api/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return await resp.json();
  } catch (e) {
    return { success: false, error: 'Network error. Please check your connection.' };
  }
}

async function apiLogout() {
  const token = localStorage.getItem('satquery_token');
  if (!token) return;
  try {
    await fetch(`${API_BASE}/api/auth/logout`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
    });
  } catch (_) {}
}

/* ── Session guard ─────────────────────────────────────────── */

function requireAuth() {
  const token = localStorage.getItem('satquery_token');
  if (!token) {
    window.location.href = '/login';
    return false;
  }
  return true;
}

async function handleLogout() {
  await apiLogout();
  localStorage.removeItem('satquery_token');
  localStorage.removeItem('satquery_user');
  window.location.href = '/login';
}

/* ── Nav helpers ───────────────────────────────────────────── */

function initNavUser() {
  const user = JSON.parse(localStorage.getItem('satquery_user') || '{}');
  const avatarEl = document.getElementById('nav-avatar');
  const nameEl   = document.getElementById('nav-username');
  if (avatarEl && user.full_name) avatarEl.textContent = user.full_name[0].toUpperCase();
  if (nameEl && user.full_name)   nameEl.textContent = user.full_name.split(' ')[0];
  const lang = user.preferred_language || localStorage.getItem('satquery_lang') || 'en';
  const navLang = document.getElementById('nav-lang');
  if (navLang) navLang.value = lang;
}

function toggleMobileNav() {
  const nav = document.getElementById('mobile-nav');
  if (nav) nav.classList.toggle('open');
}

/* ── Validation helpers ────────────────────────────────────── */

function isValidEmail(email) {
  return /^[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-.]+$/.test(email);
}

function validatePassword(pw) {
  if (!pw || pw.length < 8)     return 'Password must be at least 8 characters.';
  if (!/[A-Za-z]/.test(pw))     return 'Password must contain at least one letter.';
  if (!/\d/.test(pw))           return 'Password must contain at least one number.';
  return null;
}

/** 0=weak 1=fair 2=good 3=strong */
function getPasswordStrength(pw) {
  if (!pw || pw.length < 6) return 0;
  let score = 0;
  if (pw.length >= 8)  score++;
  if (pw.length >= 12) score++;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score++;
  if (/\d/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  if (score <= 1) return 0;
  if (score === 2) return 1;
  if (score === 3) return 2;
  return 3;
}

/* ── UI helpers ────────────────────────────────────────────── */

function setLoading(btn, loading, label) {
  if (loading) {
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner" style="width:16px;height:16px;border-width:2px;"></span> ${label}`;
  } else {
    btn.disabled = false;
    btn.innerHTML = label;
  }
}

function togglePassword(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const isHidden = input.type === 'password';
  input.type = isHidden ? 'text' : 'password';
  // Swap icon
  btn.innerHTML = isHidden
    ? `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" x2="22" y1="2" y2="22"/></svg>`
    : `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>`;
}

/* ── Auto-init on protected pages ──────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  // Skip auth check on login/register pages
  const publicPaths = ['/login', '/register', '/'];
  if (publicPaths.includes(window.location.pathname)) return;
  if (!requireAuth()) return;
  initNavUser();
});
