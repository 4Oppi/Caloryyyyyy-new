/* ============================================================
   NutriOS — Mini App  (Part 1: Core structure)
   ES2020+, async/await, no external libraries
   ============================================================ */

'use strict';

// ── 1. Constants & globals ────────────────────────────────────

const API_BASE = (() => {
  const { hostname, port, protocol } = window.location;
  // Local dev: served from localhost (any port) → hit FastAPI directly
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'http://localhost:8000';
  }
  // Production: Mini App and API share the same Railway origin
  return `${protocol}//${hostname}${port ? ':' + port : ''}`;
})();

const tg = window.Telegram.WebApp;

// Persisted across sessions
let token = localStorage.getItem('nutrios_token');

// In-memory state (reset on page load, rebuilt from API)
const state = {
  user:    null,   // { telegram_id, name, created_at }
  profile: null,   // { daily_calories, daily_water_goal_ml, daily_steps_goal, ... }
  stats:   null,   // today's DailyStats from GET /daily/today
  streak:  0,
  scanResult: null, // last ScanResult from POST /scan
};


// ── 2. Init ───────────────────────────────────────────────────

async function init() {
  tg.ready();
  tg.expand();

  if (tg.setHeaderColor)     tg.setHeaderColor('#000000');
  if (tg.setBackgroundColor) tg.setBackgroundColor('#000000');

  setDateDisplay();

  if (token) {
    try {
      await loadUser();
    } catch {
      // Token likely expired or invalid — re-auth
      clearToken();
      await authenticateWithTelegram();
    }
  } else {
    await authenticateWithTelegram();
  }
}


// ── 3. Telegram authentication ────────────────────────────────

async function authenticateWithTelegram() {
  showLoading();
  try {
    const initData = tg.initData;

    if (!initData) {
      // Running outside Telegram (local browser testing) — use a mock token flow
      console.warn('No Telegram initData — running in dev mode');
      showToast('Dev mode: no Telegram initData');
      hideLoading();
      showScreen('onboarding');
      return;
    }

    const data = await api('/users/auth/telegram', {
      method: 'POST',
      body: JSON.stringify({ init_data: initData }),
      skipAuth: true, // no token yet
    });

    token = data.access_token;
    localStorage.setItem('nutrios_token', token);

    state.user = data.user;

    if (data.onboarding_done) {
      await loadTodayStats();
      showApp();
    } else {
      showScreen('onboarding');
    }
  } catch (err) {
    console.error('Auth failed:', err);
    showToast('Autentifikatsiya xatosi. Qayta urinib ko'ring.');
  } finally {
    hideLoading();
  }
}


// ── 4. Load user & profile ────────────────────────────────────

async function loadUser() {
  const data = await api('/users/me');
  state.user    = data.user;
  state.profile = data.profile;

  updateGreeting();

  if (state.profile?.onboarding_done) {
    await loadTodayStats();
    showApp();
  } else {
    showScreen('onboarding');
  }
}

async function loadTodayStats() {
  try {
    state.stats = await api('/daily/today');
    const streakData = await api('/streak');
    state.streak = streakData.current_streak ?? 0;
  } catch (err) {
    console.error('Could not load today stats:', err);
  }
}

function updateGreeting() {
  if (!state.user) return;
  const firstName = (state.user.name || '').split(' ')[0] || 'Foydalanuvchi';
  const el = document.getElementById('greeting');
  if (el) el.textContent = `Assalomu alaykum, ${firstName}!`;
}


// ── 5. API helper ─────────────────────────────────────────────

async function api(endpoint, options = {}) {
  const { skipAuth = false, ...fetchOptions } = options;

  const headers = {
    'Content-Type': 'application/json',
    ...(fetchOptions.headers || {}),
  };

  if (!skipAuth && token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...fetchOptions,
    headers,
  });

  if (response.status === 401) {
    clearToken();
    window.location.reload();
    throw new Error('Unauthorised — reloading');
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const err = await response.json();
      detail = err.detail || detail;
    } catch { /* ignore parse error */ }
    throw new Error(detail);
  }

  // 204 No Content
  if (response.status === 204) return null;

  return response.json();
}

/** Multipart upload helper (for image scan — doesn't set Content-Type) */
async function apiUpload(endpoint, formData) {
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (response.status === 401) { clearToken(); window.location.reload(); throw new Error('Unauthorised'); }
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try { const err = await response.json(); detail = err.detail || detail; } catch { /* ignore */ }
    throw new Error(detail);
  }
  return response.json();
}

function clearToken() {
  token = null;
  localStorage.removeItem('nutrios_token');
}


// ── 6. UI helpers ─────────────────────────────────────────────

// -- Loading overlay --

function showLoading() {
  document.getElementById('loading').classList.remove('hidden');
}

function hideLoading() {
  document.getElementById('loading').classList.add('hidden');
}

// -- Screens (full-page views) --

function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.add('hidden'));
  const target = document.getElementById(id);
  if (target) {
    target.classList.remove('hidden');
    // Trigger reflow for any CSS entry animation
    target.offsetHeight; // eslint-disable-line no-unused-expressions
  }
}

function showApp() {
  showScreen('app');
  renderHomeTab();
}

function showOnboarding() {
  showScreen('onboarding');
  showOnboardingStep(1);
}

// -- Tab switching --

function switchTab(tabName) {
  // Hide all tabs
  document.querySelectorAll('.tab').forEach(t => t.classList.add('hidden'));

  // Show target tab
  const tab = document.getElementById(`tab-${tabName}`);
  if (tab) tab.classList.remove('hidden');

  // Update nav buttons
  document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
  const activeBtn = document.getElementById(`nav-${tabName}`);
  if (activeBtn) activeBtn.classList.add('active');

  // Lazy-load tab data
  if (tabName === 'progress') renderProgressTab();
  if (tabName === 'settings') renderSettingsTab();
}

// -- Modals --

function openModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;
  modal.classList.remove('hidden');
  // Allow CSS transition to play (needs one frame after display:flex)
  requestAnimationFrame(() => modal.classList.remove('hidden'));
  document.body.style.overflow = 'hidden';
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;
  modal.classList.add('hidden');
  document.body.style.overflow = '';
}

function handleModalBackdrop(event, modalId) {
  // Close only if the click landed directly on the backdrop (not inside .modal-content)
  if (event.target.id === modalId) {
    closeModal(modalId);
  }
}

// -- Toast --

let _toastTimer = null;

function showToast(message, duration = 2500) {
  const toast = document.getElementById('toast');
  if (!toast) return;

  toast.textContent = message;
  toast.classList.remove('hidden');
  // Next frame so the transition fires
  requestAnimationFrame(() => toast.classList.add('show'));

  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.classList.add('hidden'), 300);
  }, duration);
}

// -- Date display --

function setDateDisplay() {
  const UZ_MONTHS = [
    'yanvar','fevral','mart','aprel','may','iyun',
    'iyul','avgust','sentabr','oktabr','noyabr','dekabr',
  ];
  const now = new Date();
  const day   = now.getDate();
  const month = UZ_MONTHS[now.getMonth()];
  const year  = now.getFullYear();

  const el = document.getElementById('date');
  if (el) el.textContent = `${day}-${month}, ${year}-yil`;
}


// ── 7. Onboarding step navigation ────────────────────────────

function showOnboardingStep(stepNum) {
  document.querySelectorAll('.onboarding-step').forEach(s => s.classList.add('hidden'));
  const step = document.getElementById(`step-${stepNum}`);
  if (step) step.classList.remove('hidden');
}

function nextStep(stepNum) {
  // Validate current step before advancing
  if (stepNum === 3) {
    const age = document.getElementById('age').value;
    if (!age || age < 10 || age > 100) {
      showToast('Iltimos, yoshingizni to'g'ri kiriting');
      return;
    }
  }
  if (stepNum === 4) {
    const height = document.getElementById('height').value;
    const weight = document.getElementById('weight').value;
    if (!height || height < 100 || height > 250) {
      showToast('Iltimos, bo'yingizni to'g'ri kiriting (sm)');
      return;
    }
    if (!weight || weight < 30 || weight > 300) {
      showToast('Iltimos, vazningizni to'g'ri kiriting (kg)');
      return;
    }
  }
  showOnboardingStep(stepNum);
}

async function submitOnboarding() {
  const gender        = document.getElementById('gender').value;
  const age           = parseInt(document.getElementById('age').value, 10);
  const height_cm     = parseInt(document.getElementById('height').value, 10);
  const weight        = parseFloat(document.getElementById('weight').value);
  const targetWeight  = document.getElementById('target-weight').value;
  const activity      = document.getElementById('activity').value;
  const goal          = document.getElementById('goal').value;

  if (!gender || !age || !height_cm || !weight || !activity || !goal) {
    showToast('Iltimos, barcha maydonlarni to'ldiring');
    return;
  }

  showLoading();
  try {
    const body = {
      gender,
      age,
      height_cm,
      current_weight_kg: weight,
      target_weight_kg:  targetWeight ? parseFloat(targetWeight) : null,
      activity_level:    activity,
      goal,
    };

    state.profile = await api('/users/onboarding', {
      method: 'POST',
      body: JSON.stringify(body),
    });

    await loadTodayStats();
    showApp();
    showToast('🎉 Tabriklaymiz! NutriOS tayyor.');
  } catch (err) {
    showToast(`Xato: ${err.message}`);
  } finally {
    hideLoading();
  }
}


// ── Stub renderers (implemented in Part 2) ────────────────────
// Declared here so Part 1 is self-contained and won't throw
// ReferenceErrors if Part 2 hasn't loaded yet.

function renderHomeTab()     { /* → Part 2 */ }
function renderProgressTab() { /* → Part 2 */ }
function renderSettingsTab() { /* → Part 2 */ }
function showAddMeal()       { openModal('modal-add-meal'); }
function showScan()          { openModal('modal-scan'); }
function showSteps()         { openModal('modal-steps'); }
function addWater()          { /* → Part 2 */ }
function addWeight()         { /* → Part 2 */ }
function submitMeal()        { /* → Part 2 */ }
function submitScan()        { /* → Part 2 */ }
function confirmScan()       { /* → Part 2 */ }
function resetScan()         { /* → Part 2 */ }
function previewScanImage()  { /* → Part 2 */ }
function submitSteps()       { /* → Part 2 */ }
function saveSettings()      { /* → Part 2 */ }
function logout()            { clearToken(); window.location.reload(); }


// ── Boot ──────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', init);
