/**
 * PACKCHECK — GUEST CHECKOUT
 * Standalone, no-framework SPA
 * Flow: S0 (Room+Floor) → S1 (Service) → S2 (Minibar Y/N) → S3 (Review) → S4 (Success)
 */
'use strict';

/* ─── STATE ────────────────────────────────────────────────────
   Mirrors the backend checkout-request model.
──────────────────────────────────────────────────────────── */
const INITIAL_STATE = () => ({
  room:          '',
  floor:         '',
  qrToken:       '',     // token from QR URL path
  session:       null,   // signed session from /api/verify
  hotelName:     '',     // from /api/room/{token}
  serviceType:   null,   // 'CHECKOUT_LUGGAGE_PICKUP' | 'CHECKOUT_ONLY' | 'ROOM_SERVICE'
  minibarUsed:   null,   // 'USED' | 'NOT_USED'
  message:       '',     // for room service
  requestStatus: 'DRAFT',
  timestamp:     null,
  currentScreen: 0,
  isTransitioning: false,
});

let state = INITIAL_STATE();

// Extract token from URL like /r/<token>
function getTokenFromUrl() {
  return window.location.pathname.split('/').filter(Boolean).pop() || '';
}

/* ─── DOM CACHE ───────────────────────────────────────────── */
const el = id => document.getElementById(id);
const dom = {
  progress:   el('progressFill'),

  /* S0 */
  s0:         el('s0'),
  inpRoom:    el('inp-room'),
  inpFloor:   el('inp-floor'),
  s0Error:    el('s0-error'),
  btnS0Next:  el('btn-s0-next'),

  /* S1 */
  s1:         el('s1'),
  btnS1Next:  el('btn-s1-next'),
  btnS1Back:  el('btn-s1-back'),

  /* S2 */
  s2:         el('s2'),
  btnS2Next:  el('btn-s2-next'),
  btnS2Back:  el('btn-s2-back'),
  s2Eyebrow:  el('s2-eyebrow'),
  s2Title:    el('s2-title'),
  s2MinibarGrp: el('s2-minibar-group'),
  s2MessageGrp: el('s2-message-group'),
  inpMessage: el('inp-message'),
  btnMic:     el('btn-mic'),
  micText:    el('mic-text'),
  s2MsgError: el('s2-msg-error'),

  /* S3 — Review */
  s3:         el('s3'),
  rvRoom:     el('rv-room'),
  rvFloor:    el('rv-floor'),
  rvService:  el('rv-service'),
  rvMinibar:  el('rv-minibar'),
  rvMinibarRow: el('rv-minibar-row'),
  rvMessage:  el('rv-message'),
  rvMessageRow: el('rv-message-row'),
  btnS3Conf:  el('btn-s3-confirm'),
  btnS3Edit:  el('btn-s3-edit'),

  /* S4 — Success */
  s4:          el('s4'),
  successAnim: el('successAnim'),
  successText: el('successText'),
  successMeta: el('successMeta'),
  smRoom:      el('sm-room'),
  smFloor:     el('sm-floor'),
  smTime:      el('sm-time'),
  btnRestart:  el('btn-restart'),

  resetBtn:    el('resetBtn'),
};

/* ─── NAVIGATION ──────────────────────────────────────────── */
// Screens: 0 → 1 → 2 → 3 → 4
const TOTAL_SCREENS = 5;

function goToScreen(n) {
  if (state.isTransitioning) return;
  if (state.currentScreen === n) return;
  
  const current = document.querySelector('.screen.active') || el('s' + state.currentScreen);
  const next    = el('s' + n);
  if (!next) return;

  state.isTransitioning = true;
  state.currentScreen = n;

  if (current && current !== next) {
    current.classList.add('leaving');
    current.classList.remove('active');
    setTimeout(() => {
      current.classList.remove('leaving');
      current.style.display = 'none';
    }, 260);
  }

  next.style.display = 'flex';
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      next.classList.add('active');
      setTimeout(() => { state.isTransitioning = false; }, 260);
    });
  });

  dom.progress.style.width = ((n / (TOTAL_SCREENS - 1)) * 100).toFixed(0) + '%';

  // Show RESET only on mid-flow screens (not welcome, not success)
  dom.resetBtn.style.display = (n > 0 && n < 4) ? 'block' : 'none';
}

/* ─── S0: ROOM & FLOOR ENTRY ──────────────────────────────── */
function initS0() {
  const proceed = async () => {
    if (state.isTransitioning) return;
    
    const room  = dom.inpRoom.value.trim().substring(0, 6);
    const floor = dom.inpFloor.value.trim().substring(0, 4);
    
    const roomOk  = room  && /^\d+$/.test(room)  && parseInt(room, 10) >= 1;
    const floorOk = floor && /^\d+$/.test(floor) && parseInt(floor, 10) >= 1;

    dom.inpRoom.classList.toggle('input-field--error',  !roomOk);
    dom.inpFloor.classList.toggle('input-field--error', !floorOk);

    if (!roomOk || !floorOk) {
      showS0Error('Please enter valid room and floor numbers.');
      return;
    }

    // Verify room number against the QR token
    dom.btnS0Next.disabled = true;
    dom.btnS0Next.textContent = 'Verifying…';
    try {
      const res = await fetch('/api/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: state.qrToken, room_number: room })
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Room number does not match. Please check and try again.');
      }
      const data = await res.json();
      state.session = data.session;
      state.room    = room;
      state.floor   = floor;
      hideS0Error();
      goToScreen(1);
    } catch (err) {
      showS0Error(err.message);
      dom.inpRoom.classList.add('input-field--error');
    } finally {
      dom.btnS0Next.disabled = false;
      dom.btnS0Next.innerHTML = 'Begin Checkout <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg>';
    }
  };

  dom.btnS0Next.addEventListener('click', proceed);

  [dom.inpRoom, dom.inpFloor].forEach(inp => {
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') proceed(); });
    inp.addEventListener('input', () => {
      inp.classList.remove('input-field--error');
      if (dom.inpRoom.value.trim() && dom.inpFloor.value.trim()) hideS0Error();
    });
  });
}

function showS0Error(msg) {
  dom.s0Error.textContent = msg;
  dom.s0Error.classList.remove('hidden');
}

function hideS0Error() {
  dom.s0Error.classList.add('hidden');
}

/* ─── S1: SERVICE SELECTION ───────────────────────────────── */
function initS1() {
  const radios = document.querySelectorAll('input[name="service"]');

  radios.forEach(r => r.addEventListener('change', () => {
    state.serviceType = r.value;
    dom.btnS1Next.disabled = false;
  }));

  dom.btnS1Next.addEventListener('click', () => {
    if (!state.serviceType) return;
    if (state.serviceType === 'ROOM_SERVICE') {
      dom.s2Eyebrow.textContent = 'YOUR REQUEST';
      dom.s2Title.textContent = 'What do you need?';
      dom.s2MinibarGrp.style.display = 'none';
      dom.s2MessageGrp.style.display = 'block';
      dom.btnS2Next.disabled = false;
    } else {
      dom.s2Eyebrow.textContent = 'MINIBAR';
      dom.s2Title.textContent = 'Have you used anything from the minibar?';
      dom.s2MinibarGrp.style.display = '';
      dom.s2MessageGrp.style.display = 'none';
      dom.btnS2Next.disabled = !state.minibarUsed;
    }
    goToScreen(2);
  });

  dom.btnS1Back.addEventListener('click', () => goToScreen(0));
}

/* ─── S2: MINIBAR DECLARATION ─────────────────────────────── */
function initS2() {
  const radios = document.querySelectorAll('input[name="minibar"]');

  radios.forEach(r => r.addEventListener('change', () => {
    state.minibarUsed = r.value;
    dom.btnS2Next.disabled = false;
  }));

  dom.inpMessage.addEventListener('input', () => {
    dom.s2MsgError.classList.add('hidden');
    dom.inpMessage.classList.remove('input-field--error');
  });

  dom.btnS2Next.addEventListener('click', () => {
    if (state.serviceType === 'ROOM_SERVICE') {
      state.message = dom.inpMessage.value.trim();
      if (state.message.length < 2) {
        dom.s2MsgError.textContent = 'Please tell us what you need.';
        dom.s2MsgError.classList.remove('hidden');
        dom.inpMessage.classList.add('input-field--error');
        return;
      }
    } else {
      if (!state.minibarUsed) return;
    }
    buildReview();
    goToScreen(3);
  });

  dom.btnS2Back.addEventListener('click', () => goToScreen(1));

  // Voice recognition logic
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null, listening = false;
  if (SR) {
    dom.btnMic.style.display = 'flex';
    dom.btnMic.addEventListener('click', () => {
      if (listening) {
        if (rec) rec.stop();
        return;
      }
      rec = new SR();
      rec.lang = navigator.language || 'en-US';
      rec.interimResults = true;
      const base = dom.inpMessage.value.trim();
      rec.onresult = e => {
        let text = '';
        for (const r of e.results) text += r[0].transcript;
        dom.inpMessage.value = (base ? base + ' ' : '') + text;
      };
      rec.onend = () => {
        listening = false;
        dom.micText.textContent = 'Speak request';
        dom.btnMic.classList.remove('active');
      };
      rec.onerror = () => {
        dom.s2MsgError.textContent = 'Microphone unavailable. You can type your request instead.';
        dom.s2MsgError.classList.remove('hidden');
      };
      rec.start();
      listening = true;
      dom.micText.textContent = 'Listening... tap to stop';
      dom.btnMic.classList.add('active');
      dom.s2MsgError.classList.add('hidden');
      dom.inpMessage.classList.remove('input-field--error');
    });
  }
}

/* ─── S3: REVIEW & CONFIRM ────────────────────────────────── */
function buildReview() {
  dom.rvRoom.textContent  = state.room;
  dom.rvFloor.textContent = state.floor;

  if (state.serviceType === 'ROOM_SERVICE') {
    dom.rvService.textContent = 'Room Service & Requests';
    dom.rvMinibarRow.style.display = 'none';
    dom.rvMessageRow.style.display = 'flex';
    dom.rvMessage.textContent = state.message;
  } else {
    dom.rvService.textContent = state.serviceType === 'CHECKOUT_LUGGAGE_PICKUP'
      ? 'Checkout & Luggage Pickup'
      : 'Checkout Only';
    dom.rvMinibarRow.style.display = 'flex';
    dom.rvMessageRow.style.display = 'none';
    dom.rvMinibar.textContent = state.minibarUsed === 'USED'
      ? 'Used — will be verified'
      : 'Not used';
  }
}

function initS3() {
  dom.btnS3Conf.addEventListener('click', submitRequest);
  dom.btnS3Edit.addEventListener('click', () => goToScreen(1));
}

/* ─── SUBMIT ──────────────────────────────────────────────── */
async function submitRequest() {
  if (state.requestStatus === 'SENT' || state.requestStatus === 'SUBMITTING') return;
  
  state.requestStatus = 'SUBMITTING';
  dom.btnS3Conf.disabled = true;
  dom.btnS3Conf.textContent = 'Sending…';

  try {
    // Compose a human-readable message for the staff queue
    let message = '';
    let reqType = 'checkout';
    
    if (state.serviceType === 'ROOM_SERVICE') {
      reqType = 'room_service';
      message = state.message;
    } else {
      const serviceLine = state.serviceType === 'CHECKOUT_LUGGAGE_PICKUP'
        ? 'Checkout & Luggage Pickup'
        : 'Checkout Only';
      const minibarLine = state.minibarUsed === 'USED' ? 'Yes (will be verified)' : 'No';
      message = `Service: ${serviceLine}\nMinibar used: ${minibarLine}`;
    }

    const res = await fetch('/api/requests', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session': state.session
      },
      body: JSON.stringify({
        type: reqType,
        message: message,
        preferred_time: ''
      })
    });

    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail || 'Failed to submit. Please try again.');
    }

    const now = new Date();
    state.requestStatus = 'SENT';
    state.timestamp     = now.toISOString();

    dom.smRoom.textContent  = state.room;
    dom.smFloor.textContent = state.floor;
    dom.smTime.textContent  = now.toLocaleTimeString('en-IN', {
      hour: '2-digit', minute: '2-digit', hour12: true,
    });

    goToScreen(4);
    runSuccessAnimation();
  } catch (err) {
    // Show error inline on the review screen
    let errEl = document.getElementById('s3-error');
    if (!errEl) {
      errEl = document.createElement('p');
      errEl.id = 's3-error';
      errEl.className = 'input-error';
      errEl.style.marginTop = '12px';
      dom.btnS3Conf.parentElement.insertBefore(errEl, dom.btnS3Conf);
    }
    errEl.textContent = err.message;
    state.requestStatus = 'DRAFT';
    dom.btnS3Conf.disabled = false;
    dom.btnS3Conf.innerHTML = 'Confirm Checkout <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg>';
  }
}

/* ─── SUCCESS ANIMATION ───────────────────────────────────── */
function runSuccessAnimation() {
  dom.successAnim.classList.remove('animate');
  dom.successText.classList.remove('visible');
  dom.successMeta.classList.remove('visible');

  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      dom.successAnim.classList.add('animate');
      setTimeout(() => dom.successText.classList.add('visible'), 1050);
      setTimeout(() => dom.successMeta.classList.add('visible'), 1500);
    })
  );
}

/* ─── RESET ───────────────────────────────────────────────── */
function resetApp() {
  document.querySelectorAll('input[name="service"], input[name="minibar"]')
    .forEach(r => { r.checked = false; });

  if (dom.inpRoom)  { dom.inpRoom.value  = ''; dom.inpRoom.classList.remove('input-field--error'); }
  if (dom.inpFloor) { dom.inpFloor.value = ''; dom.inpFloor.classList.remove('input-field--error'); }
  if (dom.inpMessage) { dom.inpMessage.value = ''; dom.inpMessage.classList.remove('input-field--error'); }
  dom.s0Error.classList.add('hidden');

  dom.btnS1Next.disabled = true;
  dom.btnS2Next.disabled = true;
  dom.btnS3Conf.disabled = false;

  dom.successAnim.classList.remove('animate');
  dom.successText.classList.remove('visible');
  dom.successMeta.classList.remove('visible');

  state = INITIAL_STATE();
  goToScreen(0);
}

/* ─── THEME ───────────────────────────────────────────────── */
function initTheme() {
  const mq    = window.matchMedia('(prefers-color-scheme: dark)');
  const apply = dark => document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  apply(mq.matches);
  mq.addEventListener('change', e => apply(e.matches));
}

/* ─── INIT ────────────────────────────────────────────────── */
async function init() {
  dom.progress.style.width   = '0%';
  dom.resetBtn.style.display = 'none';

  document.querySelectorAll('.screen').forEach(s => {
    if (s.id === 's0') {
      s.style.display = 'flex';
      s.classList.add('active');
    } else {
      s.style.display = 'none';
      s.classList.remove('active');
    }
  });

  initTheme();

  // ── Validate QR token before showing the form ──
  state.qrToken = getTokenFromUrl();
  if (state.qrToken) {
    dom.btnS0Next.disabled = true;
    dom.btnS0Next.textContent = 'Loading…';
    try {
      const res = await fetch(`/api/room/${encodeURIComponent(state.qrToken)}`);
      if (!res.ok) throw new Error('QR not active');
      const data = await res.json();
      state.hotelName = data.hotel_name || '';
      // Display hotel name in the welcome heading
      const subtitle = document.querySelector('#s0 .screen-subtitle');
      if (subtitle && state.hotelName) {
        subtitle.textContent = `Welcome to ${state.hotelName}. Enter your room details to begin.`;
      }
    } catch {
      // QR is invalid or expired — lock the form and show an error
      showS0Error('This QR code is not active or has expired. Please call reception for assistance.');
      dom.btnS0Next.textContent = 'QR Code Inactive';
      dom.btnS0Next.disabled = true;
      dom.inpRoom.disabled  = true;
      dom.inpFloor.disabled = true;
      return;
    }
  }

  dom.btnS0Next.disabled = false;
  dom.btnS0Next.innerHTML = 'Begin Checkout <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg>';

  initS0();
  initS1();
  initS2();
  initS3();

  dom.btnRestart.addEventListener('click', resetApp);
  dom.resetBtn.addEventListener('click', resetApp);
}

document.addEventListener('DOMContentLoaded', init);
