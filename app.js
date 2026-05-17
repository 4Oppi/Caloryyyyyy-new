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


/* ============================================================
   NutriOS — Mini App  (Part 2: Feature implementations)
   These functions overwrite the stubs declared in Part 1.
   ============================================================ */

// ── 1. renderHomeTab ──────────────────────────────────────────

renderHomeTab = async function () {
  if (!state.stats) return;

  const s = state.stats;

  // — Calorie ring —
  const CIRCUMFERENCE = 251.2; // 2π × r=40
  const eaten      = s.calories_eaten ?? 0;
  const goal       = s.calories_goal  ?? 2000;
  const pct        = Math.min(eaten / goal, 1);
  const offset     = CIRCUMFERENCE - pct * CIRCUMFERENCE;
  const remaining  = Math.max(goal - eaten, 0);
  const isOver     = eaten > goal;

  const ring = document.getElementById('calorie-progress');
  if (ring) {
    ring.style.strokeDashoffset = offset.toFixed(2);
    ring.style.stroke = isOver ? 'var(--danger)' : 'var(--primary)';
  }

  setText('calories-remaining', remaining.toLocaleString());
  setText('calories-eaten',     eaten.toLocaleString());
  setText('calories-goal',      goal.toLocaleString());

  // — Water glasses —
  const waterMl      = s.water_ml       ?? 0;
  const waterGoal    = s.water_goal     ?? 2500;
  const filledGlasses = Math.floor(waterMl / 250);
  const glassContainer = document.getElementById('water-glasses');

  if (glassContainer) {
    glassContainer.innerHTML = '';
    for (let i = 0; i < 8; i++) {
      const g = document.createElement('div');
      g.className = 'water-glass' + (i < filledGlasses ? ' filled' : '');
      g.title = `${(i + 1) * 250} ml`;
      g.onclick = addWater;
      glassContainer.appendChild(g);
    }
  }

  setText('water-text', `${waterMl.toLocaleString()} / ${waterGoal.toLocaleString()} ml`);
  setBarWidth('water-progress-bar', waterMl, waterGoal);

  // — Steps —
  const steps      = s.steps      ?? 0;
  const stepsGoal  = s.steps_goal ?? 10000;
  setText('steps-text', `${steps.toLocaleString()} / ${stepsGoal.toLocaleString()}`);
  setBarWidth('steps-progress-bar', steps, stepsGoal);

  // — Streak —
  const streak = state.streak ?? 0;
  setText('streak-count',        streak);
  setText('header-streak-count', streak);

  // — Meals list —
  await renderMealsList();
};

// ── Meals list renderer ───────────────────────────────────────

async function renderMealsList() {
  const container = document.getElementById('meals-list');
  if (!container) return;

  // Fetch today's meals via a dedicated call
  let meals = [];
  try {
    meals = await api('/meals/today');
  } catch {
    // Endpoint may not exist yet — fall back to count display
  }

  if (!meals || meals.length === 0) {
    const count = state.stats?.meals_count ?? 0;
    if (count > 0) {
      container.innerHTML = `<p class="empty-state">${count} ta ovqat kiritilgan</p>`;
    } else {
      container.innerHTML = '<p class="empty-state">Hali ovqat kiritilmagan</p>';
    }
    return;
  }

  const MEAL_LABELS = {
    breakfast: '🌅 Nonushta',
    lunch:     '☀️ Tushlik',
    dinner:    '🌙 Kechki',
    snack:     '🍎 Perekus',
  };

  container.innerHTML = meals.map(meal => `
    <div class="meal-item">
      <div class="meal-left">
        <div class="meal-name">${escHtml(meal.name)}</div>
        <span class="meal-type-badge">${MEAL_LABELS[meal.meal_type] ?? meal.meal_type}</span>
      </div>
      <span class="meal-cal">${meal.calories} kcal</span>
    </div>
  `).join('');
}


// ── 2. addWater ───────────────────────────────────────────────

addWater = async function (amount_ml = 250) {
  try {
    await api('/water', {
      method: 'POST',
      body: JSON.stringify({ amount_ml }),
    });
    await loadTodayStats();
    await renderHomeTab();
    showToast(`💧 +${amount_ml} ml qo'shildi`);
  } catch (err) {
    showToast(`Xato: ${err.message}`);
  }
};


// ── 3. submitMeal ─────────────────────────────────────────────

submitMeal = async function () {
  const name     = document.getElementById('meal-name')?.value?.trim();
  const calories = parseInt(document.getElementById('meal-calories')?.value, 10);
  const mealType = document.getElementById('meal-type')?.value;

  if (!name) {
    showToast('Ovqat nomini kiriting');
    return;
  }
  if (!calories || calories < 1) {
    showToast('Kaloriya miqdorini kiriting');
    return;
  }

  showLoading();
  try {
    await api('/meals', {
      method: 'POST',
      body: JSON.stringify({
        name,
        calories,
        meal_type: mealType,
        source: 'manual',
        protein_g: 0,
        carbs_g:   0,
        fat_g:     0,
      }),
    });

    closeModal('modal-add-meal');
    // Reset form
    setVal('meal-name',     '');
    setVal('meal-calories', '');

    await loadTodayStats();
    await renderHomeTab();
    showToast(`✅ ${name} qo'shildi — ${calories} kcal`);
  } catch (err) {
    showToast(`Xato: ${err.message}`);
  } finally {
    hideLoading();
  }
};


// ── 4. submitSteps ────────────────────────────────────────────

submitSteps = async function () {
  const stepsVal = parseInt(document.getElementById('steps-input')?.value, 10);

  if (!stepsVal || stepsVal < 0) {
    showToast('Qadamlar sonini kiriting');
    return;
  }

  showLoading();
  try {
    await api('/steps', {
      method: 'POST',
      body: JSON.stringify({ steps: stepsVal }),
    });

    closeModal('modal-steps');
    setVal('steps-input', '');

    await loadTodayStats();
    await renderHomeTab();
    showToast(`👟 ${stepsVal.toLocaleString()} qadam saqlandi`);
  } catch (err) {
    showToast(`Xato: ${err.message}`);
  } finally {
    hideLoading();
  }
};


// ── 5. submitScan ─────────────────────────────────────────────

submitScan = async function () {
  const fileInput = document.getElementById('scan-file');
  const file      = fileInput?.files?.[0];

  if (!file) {
    showToast('Iltimos, rasm tanlang');
    return;
  }

  showLoading();
  try {
    const formData = new FormData();
    formData.append('file', file);

    const result = await apiUpload('/scan', formData);
    state.scanResult = result;

    // Show result panel
    setText('scan-food-name',  result.food_name);
    setText('scan-calories',   `${result.calories} kcal`);
    setText('scan-confidence', `Ishonch: ${Math.round(result.confidence * 100)}%`);

    document.getElementById('scan-upload-area')?.classList.add('hidden');
    document.getElementById('btn-scan-submit')?.classList.add('hidden');
    document.getElementById('scan-result')?.classList.remove('hidden');
  } catch (err) {
    showToast(`Skan xatosi: ${err.message}`);
  } finally {
    hideLoading();
  }
};


// ── 6. confirmScan ────────────────────────────────────────────

confirmScan = async function () {
  if (!state.scanResult) {
    showToast('Avval ovqatni skaner qiling');
    return;
  }

  const mealType = document.getElementById('scan-meal-type')?.value ?? 'snack';

  showLoading();
  try {
    await api('/scan/confirm', {
      method: 'POST',
      body: JSON.stringify({
        scan_result: state.scanResult,
        meal_type:   mealType,
      }),
    });

    closeModal('modal-scan');
    resetScan();

    await loadTodayStats();
    await renderHomeTab();
    showToast(`✅ ${state.scanResult.food_name} qo'shildi`);
    state.scanResult = null;
  } catch (err) {
    showToast(`Xato: ${err.message}`);
  } finally {
    hideLoading();
  }
};


// ── 7. resetScan ─────────────────────────────────────────────

resetScan = function () {
  state.scanResult = null;

  // Reset file input
  const fileInput = document.getElementById('scan-file');
  if (fileInput) fileInput.value = '';

  // Hide preview
  const preview = document.getElementById('scan-preview');
  if (preview) { preview.src = ''; preview.classList.add('hidden'); }

  // Restore upload area
  document.getElementById('scan-upload-area')?.classList.remove('hidden');
  document.getElementById('btn-scan-submit')?.classList.remove('hidden');
  document.getElementById('scan-result')?.classList.add('hidden');
};


// ── 8. previewScanImage ───────────────────────────────────────

previewScanImage = function (event) {
  const file    = event.target?.files?.[0];
  const preview = document.getElementById('scan-preview');
  if (!file || !preview) return;

  const reader = new FileReader();
  reader.onload = (e) => {
    preview.src = e.target.result;
    preview.classList.remove('hidden');
  };
  reader.readAsDataURL(file);
};


// ── Progress tab ──────────────────────────────────────────────

renderProgressTab = async function () {
  if (!state.profile) return;

  // Placeholder weekly stats (extend with real API later)
  const streak = state.streak ?? 0;
  const water  = state.stats?.water_ml ?? 0;
  const steps  = state.stats?.steps ?? 0;
  const cal    = state.stats?.calories_eaten ?? 0;

  setText('week-avg-cal', cal.toLocaleString());
  setText('week-streak',  streak);
  setText('week-water',   water.toLocaleString());
  setText('week-steps',   steps.toLocaleString());
};

async function addWeight() {
  const val = parseFloat(document.getElementById('new-weight')?.value);
  if (!val || val < 30 || val > 300) {
    showToast('Iltimos, to'g'ri vazn kiriting');
    return;
  }

  showLoading();
  try {
    await api('/users/profile', {
      method: 'PUT',
      body: JSON.stringify({ current_weight_kg: val }),
    });
    setVal('new-weight', '');
    showToast(`⚖️ Vazn yangilandi: ${val} kg`);
  } catch (err) {
    showToast(`Xato: ${err.message}`);
  } finally {
    hideLoading();
  }
}


// ── Settings tab ──────────────────────────────────────────────

renderSettingsTab = function () {
  if (!state.profile) return;

  const p = state.profile;

  // Pre-fill goal inputs
  setVal('setting-calories', p.daily_calories      ?? '');
  setVal('setting-water',    p.daily_water_goal_ml  ?? '');
  setVal('setting-steps',    p.daily_steps_goal     ?? '');

  // Profile info rows
  const container = document.getElementById('profile-info');
  if (!container) return;

  const GENDER_LABELS = { male: 'Erkak', female: 'Ayol' };
  const GOAL_LABELS   = {
    lose_weight:  'Vazn yo'qotish',
    maintain:     'Ushlab turish',
    gain_muscle:  'Mushak o'stirish',
  };

  const rows = [
    ['Jinsi',     GENDER_LABELS[p.gender] ?? p.gender],
    ['Yoshi',     `${p.age} yosh`],
    ['Bo'y',      `${p.height_cm} sm`],
    ['Vazn',      `${p.current_weight_kg} kg`],
    ['Maqsad',    GOAL_LABELS[p.goal] ?? p.goal],
    ['Kaloriya',  `${p.daily_calories} kcal`],
  ];

  container.innerHTML = rows.map(([label, value]) => `
    <div class="profile-row">
      <span class="profile-label">${label}</span>
      <span class="profile-value">${escHtml(String(value))}</span>
    </div>
  `).join('');
};

saveSettings = async function () {
  const calories = parseInt(document.getElementById('setting-calories')?.value, 10);
  const water    = parseInt(document.getElementById('setting-water')?.value,    10);
  const steps    = parseInt(document.getElementById('setting-steps')?.value,    10);

  if (!calories || !water || !steps) {
    showToast('Iltimos, barcha maydonlarni to'ldiring');
    return;
  }

  showLoading();
  try {
    state.profile = await api('/users/profile', {
      method: 'PUT',
      body: JSON.stringify({
        daily_calories:      calories,
        daily_water_goal_ml: water,
        daily_steps_goal:    steps,
      }),
    });

    await loadTodayStats();
    renderSettingsTab();
    showToast('✅ Sozlamalar saqlandi');
  } catch (err) {
    showToast(`Xato: ${err.message}`);
  } finally {
    hideLoading();
  }
};


// ── Utility functions ─────────────────────────────────────────

/** Safely set textContent of an element by id */
function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value ?? '';
}

/** Safely set value of an input/select by id */
function setVal(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value ?? '';
}

/** Set width of a progress bar as a clamped percentage */
function setBarWidth(id, value, max) {
  const el = document.getElementById(id);
  if (!el) return;
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  el.style.width = `${pct.toFixed(1)}%`;
}

/** Minimal HTML escaping to prevent XSS from API strings */
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
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

