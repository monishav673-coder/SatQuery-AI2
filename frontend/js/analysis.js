/* ============================================================
   SATQUERY AI — Analysis Page Controller
   ============================================================ */

let currentMode = null;
let currentInputMethod = 'image';
const uploadedFiles = {};

const MODE_CONFIG = {
  single: {
    title: 'Single Image Analysis',
    desc: 'Analyse one satellite image using AI-powered land-cover and geographic feature extraction.',
  },
  optical_sar: {
    title: 'Optical + SAR Analysis',
    desc: 'Combine optical and Synthetic Aperture Radar imagery for multimodal Earth observation analysis.',
  },
  multitemporal: {
    title: 'Multitemporal Change Detection',
    desc: 'Compare satellite observations from different dates to detect geographic changes.',
  },
};

const ANALYSIS_STAGES = [
  'Receiving imagery...',
  'Validating satellite data...',
  'Preprocessing image...',
  'Selecting analysis models...',
  'Running Agentic AI...',
  'Detecting land cover...',
  'Identifying geographic features...',
  'Analysing water bodies...',
  'Detecting agricultural areas...',
  'Calculating confidence...',
  'Generating visual evidence...',
  'Preparing report...',
];

document.addEventListener('DOMContentLoaded', () => {
  if (!requireAuth()) return;

  // Check if mode was pre-selected from dashboard
  const preMode = sessionStorage.getItem('satquery_mode');
  if (preMode) {
    sessionStorage.removeItem('satquery_mode');
    selectAnalysisMode(preMode);
  }
});

/* ── Mode selection ──────────────────────────────────────── */

function selectAnalysisMode(mode) {
  currentMode = mode;
  const cfg = MODE_CONFIG[mode];

  document.getElementById('mode-selector-section').classList.add('hidden');
  document.getElementById('analysis-panel').classList.remove('hidden');
  document.getElementById('mode-title-display').textContent = cfg.title;
  document.getElementById('mode-desc-display').textContent = cfg.desc;

  // Show/hide upload sections
  document.getElementById('single-upload').classList.toggle('hidden', mode !== 'single');
  document.getElementById('sar-upload').classList.toggle('hidden', mode !== 'optical_sar');
  document.getElementById('temporal-upload').classList.toggle('hidden', mode !== 'multitemporal');
}

function resetMode() {
  currentMode = null;
  uploadedFiles['primary'] = null;
  uploadedFiles['optical'] = null;
  uploadedFiles['sar'] = null;
  uploadedFiles['before'] = null;
  uploadedFiles['after'] = null;

  document.getElementById('analysis-panel').classList.add('hidden');
  document.getElementById('mode-selector-section').classList.remove('hidden');
  document.getElementById('analysis-error').classList.add('hidden');

  // Clear previews
  ['primary','optical','sar','before','after'].forEach(role => {
    const p = document.getElementById(`preview-${role}`);
    if (p) { p.innerHTML = ''; p.classList.add('hidden'); }
    const z = document.getElementById(`drop-${role}`);
    if (z) z.classList.remove('has-file');
  });
  document.getElementById('nlq-input').value = '';

  // Reset input method to image
  setInputMethod('image');
}

/* ── Input method switching ──────────────────────────────── */

function setInputMethod(method) {
  currentInputMethod = method;
  document.getElementById('tab-image').classList.toggle('active', method === 'image');
  document.getElementById('tab-coords').classList.toggle('active', method === 'coordinates');
  document.getElementById('image-input-panel').classList.toggle('hidden', method === 'coordinates');
  document.getElementById('coords-input-panel').classList.toggle('hidden', method === 'image');

  // Show/hide temporal date fields for coordinates
  const coordTemporal = document.getElementById('coord-temporal-dates');
  const coordSingle = document.getElementById('coord-single-dates');
  if (coordTemporal && coordSingle) {
    const isTemporal = currentMode === 'multitemporal';
    coordTemporal.classList.toggle('hidden', !isTemporal);
    coordSingle.classList.toggle('hidden', isTemporal);
  }

  if (method === 'coordinates') {
    setTimeout(() => initAnalysisMap(), 100);
  }
}

/* ── File upload handlers ────────────────────────────────── */

function onDragOver(e, dropId) {
  e.preventDefault();
  document.getElementById(dropId)?.classList.add('dragover');
}
function onDragLeave(dropId) {
  document.getElementById(dropId)?.classList.remove('dragover');
}
function onDrop(e, role) {
  e.preventDefault();
  const dropId = `drop-${role}`;
  document.getElementById(dropId)?.classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) processFile(file, role);
}
function onFileSelect(e, role) {
  const file = e.target.files[0];
  if (file) processFile(file, role);
}

function processFile(file, role) {
  const allowed = ['image/jpeg', 'image/jpg', 'image/png', 'image/tiff', 'image/tif'];
  const ext = file.name.split('.').pop().toLowerCase();
  const allowedExts = ['jpg','jpeg','png','tif','tiff'];

  if (!allowed.includes(file.type) && !allowedExts.includes(ext)) {
    showAnalysisError(`Invalid file type for ${role}. Accepted: JPG, JPEG, PNG, TIFF, GeoTIFF.`);
    return;
  }
  if (file.size > 100 * 1024 * 1024) {
    showAnalysisError(`File too large (${(file.size/1024/1024).toFixed(1)} MB). Maximum: 100 MB.`);
    return;
  }

  uploadedFiles[role] = file;
  showFilePreview(file, role);
  document.getElementById(`drop-${role}`)?.classList.add('has-file');
  document.getElementById(`analysis-error`)?.classList.add('hidden');
}

function showFilePreview(file, role) {
  const previewEl = document.getElementById(`preview-${role}`);
  if (!previewEl) return;

  const sizeMB = (file.size / 1024 / 1024).toFixed(2);
  const ext = file.name.split('.').pop().toUpperCase();
  let thumbHtml = `<div class="file-thumb" style="display:flex;align-items:center;justify-content:center;font-size:1.5rem;background:rgba(0,212,255,0.1);border-radius:var(--radius-md);">🛰️</div>`;

  previewEl.innerHTML = `
    <div class="file-preview">
      <div id="thumb-wrap-${role}">${thumbHtml}</div>
      <div class="file-info" style="flex:1;">
        <div class="file-name" style="font-weight:600;color:var(--text-primary);">${file.name}</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;font-size:0.75rem;color:var(--text-muted);margin-top:2px;">
          <span>Size: <strong>${sizeMB} MB</strong></span>
          <span>Format: <strong>${ext}</strong></span>
          <span id="dims-${role}">Dimensions: <em>Loading...</em></span>
        </div>
      </div>
      <button class="file-remove" onclick="removeFile('${role}')" title="Remove file">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
      </button>
    </div>`;
  previewEl.classList.remove('hidden');

  // Asynchronously extract image dimensions & preview thumbnail
  if (['JPG','JPEG','PNG'].includes(ext)) {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const dimsEl = document.getElementById(`dims-${role}`);
      if (dimsEl) dimsEl.innerHTML = `Dimensions: <strong>${img.naturalWidth} × ${img.naturalHeight} px</strong>`;
      const thumbWrap = document.getElementById(`thumb-wrap-${role}`);
      if (thumbWrap) thumbWrap.innerHTML = `<img class="file-thumb" src="${url}" alt="Preview" style="object-fit:cover;border-radius:var(--radius-md);" />`;
    };
    img.onerror = () => {
      const dimsEl = document.getElementById(`dims-${role}`);
      if (dimsEl) dimsEl.textContent = 'Standard Satellite Format';
    };
    img.src = url;
  } else {
    // TIFF / GeoTIFF
    const dimsEl = document.getElementById(`dims-${role}`);
    if (dimsEl) dimsEl.innerHTML = `Format: <strong>GeoTIFF / Raster Multi-band</strong>`;
  }
}

function removeFile(role) {
  uploadedFiles[role] = null;
  const previewEl = document.getElementById(`preview-${role}`);
  if (previewEl) { previewEl.innerHTML = ''; previewEl.classList.add('hidden'); }
  const dropEl = document.getElementById(`drop-${role}`);
  if (dropEl) dropEl.classList.remove('has-file');
  // Reset file input
  const fileInput = document.getElementById(`file-${role}`);
  if (fileInput) fileInput.value = '';
}

/* ── NLQ & Voice Query ───────────────────────────────────── */

function setNLQ(text) {
  const el = document.getElementById('nlq-input');
  if (el) {
    el.value = text;
    el.focus();
  }
}

let speechRecognitionInstance = null;

function startVoiceQuery() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const voiceBtn = document.getElementById('voice-btn');
  const voiceStatus = document.getElementById('voice-status');
  const inputEl = document.getElementById('nlq-input');

  if (!SpeechRecognition) {
    alert('Voice input (Speech Recognition) is not supported in this browser. Please type your query in the box.');
    return;
  }

  if (speechRecognitionInstance) {
    try { speechRecognitionInstance.stop(); } catch (_) {}
    speechRecognitionInstance = null;
    if (voiceStatus) voiceStatus.classList.add('hidden');
    if (voiceBtn) voiceBtn.style.background = '';
    return;
  }

  try {
    const lang = localStorage.getItem('satquery_lang') || 'en';
    const langMap = {
      en: 'en-US',
      ta: 'ta-IN',
      hi: 'hi-IN',
      te: 'te-IN',
      kn: 'kn-IN',
      ml: 'ml-IN',
      bn: 'bn-IN',
      mr: 'mr-IN',
    };

    const recognition = new SpeechRecognition();
    recognition.lang = langMap[lang] || 'en-US';
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    speechRecognitionInstance = recognition;
    if (voiceStatus) voiceStatus.classList.remove('hidden');
    if (voiceBtn) {
      voiceBtn.style.background = 'rgba(239, 68, 68, 0.2)';
      voiceBtn.style.borderColor = '#ef4444';
      voiceBtn.style.color = '#ef4444';
    }

    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map(r => r[0].transcript)
        .join('');
      if (inputEl) inputEl.value = transcript;
    };

    recognition.onerror = (event) => {
      console.warn('Speech recognition error:', event.error);
      if (voiceStatus) voiceStatus.classList.add('hidden');
      if (voiceBtn) {
        voiceBtn.style.background = '';
        voiceBtn.style.borderColor = '';
        voiceBtn.style.color = '';
      }
      speechRecognitionInstance = null;
    };

    recognition.onend = () => {
      if (voiceStatus) voiceStatus.classList.add('hidden');
      if (voiceBtn) {
        voiceBtn.style.background = '';
        voiceBtn.style.borderColor = '';
        voiceBtn.style.color = '';
      }
      speechRecognitionInstance = null;
    };

    recognition.start();
  } catch (err) {
    console.error('Failed to initialize speech recognition:', err);
    alert('Could not activate microphone. Please ensure microphone permissions are granted.');
  }
}

/* ── Analysis submission ─────────────────────────────────── */

async function startAnalysis() {
  const errEl = document.getElementById('analysis-error');
  errEl.classList.add('hidden');

  if (!currentMode) { showAnalysisError('Please select an analysis mode.'); return; }

  const nlQuery = document.getElementById('nlq-input')?.value.trim() || '';

  if (currentInputMethod === 'image') {
    // Validate required files
    if (currentMode === 'single' && !uploadedFiles['primary']) {
      showAnalysisError('Please upload a satellite image to analyse.'); return;
    }
    if (currentMode === 'optical_sar' && (!uploadedFiles['optical'] || !uploadedFiles['sar'])) {
      showAnalysisError('Please upload both an optical image and a SAR image.'); return;
    }
    if (currentMode === 'multitemporal' && (!uploadedFiles['before'] || !uploadedFiles['after'])) {
      showAnalysisError('Please upload both the before and after images.'); return;
    }
    await submitImageAnalysis(nlQuery);
  } else {
    await submitCoordinateAnalysis(nlQuery);
  }
}

async function submitImageAnalysis(nlQuery) {
  const token = localStorage.getItem('satquery_token');
  const formData = new FormData();
  if (nlQuery) formData.append('nl_query', nlQuery);

  // Attach any optional image coordinates
  const imgCoords = window.imgCoords || {};

  let endpoint = '';
  if (currentMode === 'single') {
    endpoint = '/api/analyze/single';
    formData.append('image', uploadedFiles['primary']);
    const c = imgCoords['primary'];
    if (c) { formData.append('img_lat', c.lat); formData.append('img_lon', c.lon); }
  } else if (currentMode === 'optical_sar') {
    endpoint = '/api/analyze/optical-sar';
    formData.append('optical_image', uploadedFiles['optical']);
    formData.append('sar_image', uploadedFiles['sar']);
    const c = imgCoords['optical'];
    if (c) { formData.append('img_lat', c.lat); formData.append('img_lon', c.lon); }
  } else if (currentMode === 'multitemporal') {
    endpoint = '/api/analyze/multitemporal';
    formData.append('before_image', uploadedFiles['before']);
    formData.append('after_image', uploadedFiles['after']);
    const beforeDate = document.getElementById('before-date')?.value;
    const beforeTime = document.getElementById('before-time')?.value;
    const afterDate  = document.getElementById('after-date')?.value;
    const afterTime  = document.getElementById('after-time')?.value;
    if (beforeDate) formData.append('before_date', beforeDate);
    if (beforeTime) formData.append('before_time', beforeTime);
    if (afterDate)  formData.append('after_date', afterDate);
    if (afterTime)  formData.append('after_time', afterTime);
    const cb = imgCoords['before'];
    if (cb) { formData.append('img_lat', cb.lat); formData.append('img_lon', cb.lon); }
  }

  showProcessing();

  try {
    const resp = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: formData,
    });
    const data = await resp.json();
    hideProcessing();
    if (data.success) {
      window.location.href = `/results?id=${data.analysis_id}`;
    } else {
      showAnalysisError(data.error || JSON.stringify(data.errors) || 'Analysis failed.');
      showAnalysisPanel();
    }
  } catch (e) {
    hideProcessing();
    showAnalysisError('Network error. Please check your connection.');
    showAnalysisPanel();
  }
}

async function submitCoordinateAnalysis(nlQuery) {
  const token = localStorage.getItem('satquery_token');
  const lat = parseFloat(document.getElementById('coord-lat')?.value);
  const lon = parseFloat(document.getElementById('coord-lon')?.value);

  if (isNaN(lat) || lat < -90 || lat > 90) {
    showAnalysisError('Latitude must be between −90 and 90.'); return;
  }
  if (isNaN(lon) || lon < -180 || lon > 180) {
    showAnalysisError('Longitude must be between −180 and 180.'); return;
  }

  let endpoint = '/api/analyze/coordinates';
  let body = { latitude: lat, longitude: lon, mode: currentMode, nl_query: nlQuery || undefined };

  if (currentMode === 'multitemporal') {
    endpoint = '/api/analyze/coordinates/multitemporal';
    const bd = document.getElementById('coord-before-date')?.value || '2020-01-01';
    const bt = document.getElementById('coord-before-time')?.value;
    const ad = document.getElementById('coord-after-date')?.value || '2024-01-01';
    const at_ = document.getElementById('coord-after-time')?.value;
    body = { ...body, before_date: bd, before_time: bt || undefined, after_date: ad, after_time: at_ || undefined };
  } else {
    const date = document.getElementById('coord-date')?.value;
    const time = document.getElementById('coord-time')?.value;
    if (date) body.date = date;
    if (time) body.time = time;
  }

  showProcessing();

  try {
    const resp = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    hideProcessing();
    if (data.success) {
      window.location.href = `/results?id=${data.analysis_id}`;
    } else {
      showAnalysisError(data.error || JSON.stringify(data.errors) || 'Analysis failed.');
      showAnalysisPanel();
    }
  } catch (e) {
    hideProcessing();
    showAnalysisError('Network error. Please check your connection.');
    showAnalysisPanel();
  }
}

/* ── Direct Satellite Tile Fetch for Coordinates ────────── */

async function fetchSatelliteForCoordinates() {
  const token = localStorage.getItem('satquery_token');
  const lat = parseFloat(document.getElementById('coord-lat')?.value);
  const lon = parseFloat(document.getElementById('coord-lon')?.value);

  const latErr = document.getElementById('lat-error');
  const lonErr = document.getElementById('lon-error');
  if (latErr) latErr.classList.add('hidden');
  if (lonErr) lonErr.classList.add('hidden');

  let valid = true;
  if (isNaN(lat) || lat < -90 || lat > 90) {
    if (latErr) { latErr.textContent = 'Latitude must be between −90 and 90.'; latErr.classList.remove('hidden'); }
    valid = false;
  }
  if (isNaN(lon) || lon < -180 || lon > 180) {
    if (lonErr) { lonErr.textContent = 'Longitude must be between −180 and 180.'; lonErr.classList.remove('hidden'); }
    valid = false;
  }
  if (!valid) return;

  // Update map and reverse geocode
  if (typeof previewCoordinates === 'function') {
    previewCoordinates();
  }

  const previewContainer = document.getElementById('coord-sat-preview-container');
  const previewBody = document.getElementById('coord-sat-preview-body');
  const btnFetch = document.getElementById('btn-fetch-sat-img');

  if (previewContainer) previewContainer.classList.remove('hidden');
  if (previewBody) {
    previewBody.innerHTML = `
      <div style="text-align:center;padding:1.5rem;color:var(--text-muted);">
        <div class="spinner" style="margin:0 auto 0.75rem;"></div>
        <div>Acquiring real-time high-resolution satellite tiles for (${lat.toFixed(4)}°, ${lon.toFixed(4)}°)...</div>
      </div>
    `;
  }
  if (btnFetch) btnFetch.disabled = true;

  try {
    const payload = {
      latitude: lat,
      longitude: lon,
      mode: currentMode || 'single',
    };

    if (currentMode === 'multitemporal') {
      const bd = document.getElementById('coord-before-date')?.value || '2020-01-01';
      const ad = document.getElementById('coord-after-date')?.value || '2024-01-01';
      payload.before_date = bd;
      payload.after_date = ad;
    } else {
      const dt = document.getElementById('coord-date')?.value;
      if (dt) payload.date = dt;
    }

    const resp = await fetch('/api/analyze/coordinates/preview', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(payload)
    });

    const data = await resp.json();
    if (btnFetch) btnFetch.disabled = false;

    if (!data.success) {
      if (previewBody) {
        previewBody.innerHTML = `<div class="alert alert-error">${data.error || 'Failed to retrieve satellite imagery.'}</div>`;
      }
      return;
    }

    if (currentMode === 'multitemporal') {
      const beforeImg = data.before || {};
      const afterImg = data.after || {};
      const bd = payload.before_date;
      const ad = payload.after_date;

      previewBody.innerHTML = `
        <div style="margin-bottom:0.75rem;padding:8px 12px;background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.25);border-radius:var(--radius-sm);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
          <span style="font-size:0.83rem;color:#fcd34d;font-weight:600;">✓ 2-Year Satellite Imagery Retrieved for ${data.place_name || `${lat}°, ${lon}°`}</span>
          <span class="badge badge-warning" style="font-size:0.72rem;">Temporal Delta: ${bd.slice(0,4)} vs ${ad.slice(0,4)}</span>
        </div>
        <div class="grid-2" style="gap:1rem;">
          <div class="glass-card" style="padding:1rem;background:rgba(255,255,255,0.03);text-align:center;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
              <span class="badge badge-accent" style="font-size:0.72rem;">YEAR 1 (${bd})</span>
              <span style="font-size:0.72rem;color:var(--text-muted);">Sentinel-2 Optical</span>
            </div>
            ${beforeImg.thumbnail_url ? `<img src="${beforeImg.thumbnail_url}" style="width:100%;height:180px;object-fit:cover;border-radius:var(--radius-md);border:1px solid var(--border-color);cursor:pointer;" onclick="openLightbox('${beforeImg.thumbnail_url}')" title="Click to enlarge" />` : '<div style="height:180px;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.3);border-radius:var(--radius-md);">Satellite Tile Acquired</div>'}
            <div style="font-size:0.75rem;color:var(--text-muted);margin-top:6px;display:flex;justify-content:space-between;">
              <span>GSD: 0.5m - 2.5m</span>
              <span>Dim: ${beforeImg.dimensions || '512×512'}</span>
            </div>
          </div>
          <div class="glass-card" style="padding:1rem;background:rgba(255,255,255,0.03);text-align:center;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
              <span class="badge badge-warning" style="font-size:0.72rem;">YEAR 2 (${ad})</span>
              <span style="font-size:0.72rem;color:var(--text-muted);">Sentinel-2 Optical</span>
            </div>
            ${afterImg.thumbnail_url ? `<img src="${afterImg.thumbnail_url}" style="width:100%;height:180px;object-fit:cover;border-radius:var(--radius-md);border:1px solid var(--border-color);cursor:pointer;" onclick="openLightbox('${afterImg.thumbnail_url}')" title="Click to enlarge" />` : '<div style="height:180px;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.3);border-radius:var(--radius-md);">Satellite Tile Acquired</div>'}
            <div style="font-size:0.75rem;color:var(--text-muted);margin-top:6px;display:flex;justify-content:space-between;">
              <span>GSD: 0.5m - 2.5m</span>
              <span>Dim: ${afterImg.dimensions || '512×512'}</span>
            </div>
          </div>
        </div>
        <div style="margin-top:0.75rem;font-size:0.8rem;color:var(--text-secondary);text-align:center;">
          Exact area imagery loaded across both target years. Ready for Agentic AI change detection and land transformation analysis.
        </div>
      `;
    } else {
      const img = data.image || {};
      previewBody.innerHTML = `
        <div style="margin-bottom:0.75rem;padding:8px 12px;background:rgba(0,212,255,0.08);border:1px solid rgba(0,212,255,0.25);border-radius:var(--radius-sm);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
          <span style="font-size:0.83rem;color:var(--accent);font-weight:600;">✓ High-Resolution Satellite Tile Acquired for ${data.place_name || `${lat}°, ${lon}°`}</span>
          <span class="badge badge-accent" style="font-size:0.72rem;">${img.resolution || '0.5m GSD'}</span>
        </div>
        <div style="display:flex;gap:1rem;flex-wrap:wrap;align-items:center;">
          ${img.thumbnail_url ? `<div style="flex:0 0 200px;"><img src="${img.thumbnail_url}" style="width:200px;height:140px;object-fit:cover;border-radius:var(--radius-md);border:1px solid var(--border-color);cursor:pointer;" onclick="openLightbox('${img.thumbnail_url}')" title="Click to enlarge" /></div>` : ''}
          <div style="flex:1;min-width:200px;display:flex;flex-direction:column;gap:6px;font-size:0.82rem;">
            <div><strong style="color:var(--text-primary);">Satellite Constellation:</strong> <span style="color:var(--text-secondary);">${img.satellite || 'Sentinel-2 / High-Resolution Constellation'}</span></div>
            <div><strong style="color:var(--text-primary);">Provider:</strong> <span style="color:var(--text-secondary);">${img.provider || 'Earth Observation Remote Sensing'}</span></div>
            <div><strong style="color:var(--text-primary);">Dimensions:</strong> <span style="color:var(--text-secondary);">${img.dimensions || '512 × 512 px'}</span></div>
            <div><strong style="color:var(--text-primary);">Acquisition Date:</strong> <span style="color:var(--text-secondary);">${img.acquisition_date || 'Current Active Tile'}</span></div>
            <div style="margin-top:4px;color:var(--accent);">✓ Tile cached and ready for AI feature extraction.</div>
          </div>
        </div>
      `;
    }
  } catch (err) {
    if (btnFetch) btnFetch.disabled = false;
    if (previewBody) {
      previewBody.innerHTML = `<div class="alert alert-error">Failed to fetch satellite imagery tile. Please verify connection.</div>`;
    }
  }
}


/* ── Processing UI ───────────────────────────────────────── */

let stageInterval = null;
let stageIndex = 0;

function showProcessing() {
  document.getElementById('analysis-panel').classList.add('hidden');
  document.getElementById('processing-panel').classList.remove('hidden');
  document.getElementById('analyze-btn').disabled = true;

  stageIndex = 0;
  renderStagesList();
  updateStage(0);

  stageInterval = setInterval(() => {
    stageIndex = Math.min(stageIndex + 1, ANALYSIS_STAGES.length - 1);
    updateStage(stageIndex);
    const pct = Math.round((stageIndex / (ANALYSIS_STAGES.length - 1)) * 95);
    document.getElementById('progress-fill').style.width = pct + '%';
  }, 1200);
}

function hideProcessing() {
  clearInterval(stageInterval);
  document.getElementById('progress-fill').style.width = '100%';
  setTimeout(() => {
    document.getElementById('processing-panel').classList.add('hidden');
  }, 400);
}

function showAnalysisPanel() {
  document.getElementById('analysis-panel').classList.remove('hidden');
  document.getElementById('analyze-btn').disabled = false;
}

function updateStage(idx) {
  const stage = ANALYSIS_STAGES[idx];
  document.getElementById('current-stage').textContent = stage;

  const items = document.querySelectorAll('.stage-item');
  items.forEach((item, i) => {
    item.classList.remove('active', 'done');
    if (i < idx) item.classList.add('done');
    else if (i === idx) item.classList.add('active');
  });
}

function renderStagesList() {
  const list = document.getElementById('stages-list');
  list.innerHTML = ANALYSIS_STAGES.map((s, i) => `
    <div class="stage-item" id="stage-${i}">
      <div class="stage-dot"></div>
      <span>${s}</span>
    </div>`).join('');
}

function showAnalysisError(msg) {
  const el = document.getElementById('analysis-error');
  el.textContent = msg;
  el.classList.remove('hidden');
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/* ── Lightbox ────────────────────────────────────────────── */
function openLightbox(src) {
  document.getElementById('lightbox-img').src = src;
  document.getElementById('lightbox').classList.remove('hidden');
}
function closeLightbox(e) { if (e.target === e.currentTarget) document.getElementById('lightbox').classList.add('hidden'); }
function closeLightboxBtn() { document.getElementById('lightbox').classList.add('hidden'); }

/* ── SSE Progress streaming ──────────────────────────────── */

/**
 * Subscribe to the SSE progress stream for an async analysis.
 * Updates the processing UI in real-time with server-pushed stages.
 * Falls back gracefully if EventSource is unavailable.
 */
async function streamProgress(analysisId) {
  const token = localStorage.getItem('satquery_token');

  return new Promise((resolve) => {
    if (!window.EventSource) {
      // Fallback: poll DB status
      pollAnalysisStatus(analysisId, resolve);
      return;
    }

    // Note: EventSource doesn't support custom headers natively in browsers.
    // We pass the token as a query param (backend must accept it).
    const url = `/api/analysis/${analysisId}/progress?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);

    const STAGE_MAP = {
      input_validation:  0,  preprocessing: 1,  modality: 2,
      landcover: 3,  buildings: 4,  water: 5,  agriculture: 6,
      change_detection: 7,  evidence: 8,  confidence: 9,
      nlp: 10,  report_prep: 11,  completed: 11,  failed: 11,
    };

    es.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const stageIdx = STAGE_MAP[payload.stage] ?? stageIndex;
        updateStage(stageIdx);
        const pct = payload.pct ?? Math.round((stageIdx / (ANALYSIS_STAGES.length - 1)) * 100);
        document.getElementById('progress-fill').style.width = Math.min(pct, 99) + '%';
        document.getElementById('current-stage').textContent = payload.message || ANALYSIS_STAGES[stageIdx];

        if (payload.stage === 'completed') {
          es.close();
          clearInterval(stageInterval);
          document.getElementById('progress-fill').style.width = '100%';
          setTimeout(() => {
            hideProcessing();
            window.location.href = `/results?id=${analysisId}`;
          }, 400);
          resolve();
        } else if (payload.stage === 'failed') {
          es.close();
          clearInterval(stageInterval);
          hideProcessing();
          showAnalysisError(payload.message || 'Analysis failed on the server.');
          showAnalysisPanel();
          resolve();
        }
      } catch (_) {}
    };

    es.onerror = () => {
      es.close();
      // Fall back to polling
      pollAnalysisStatus(analysisId, resolve);
    };

    // Safety timeout — 10 minutes
    setTimeout(() => {
      es.close();
      pollAnalysisStatus(analysisId, resolve);
    }, 600_000);
  });
}

async function pollAnalysisStatus(analysisId, resolve) {
  const token = localStorage.getItem('satquery_token');
  const MAX_POLLS = 240;  // 240 × 2.5s = 10 min
  let polls = 0;

  const interval = setInterval(async () => {
    polls++;
    try {
      const resp = await fetch(`/api/analysis/${analysisId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await resp.json();
      const status = data?.analysis?.status;

      if (status === 'completed') {
        clearInterval(interval);
        hideProcessing();
        window.location.href = `/results?id=${analysisId}`;
        resolve();
      } else if (status === 'failed') {
        clearInterval(interval);
        hideProcessing();
        showAnalysisError(data?.analysis?.error_message || 'Analysis failed.');
        showAnalysisPanel();
        resolve();
      }
    } catch (_) {}

    if (polls >= MAX_POLLS) {
      clearInterval(interval);
      hideProcessing();
      showAnalysisError('Analysis timed out. Please check your history for results.');
      showAnalysisPanel();
      resolve();
    }
  }, 2500);
}
