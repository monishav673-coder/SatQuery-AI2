/* ============================================================
   SATQUERY AI — Dashboard Page Controller
   ============================================================ */

document.addEventListener('DOMContentLoaded', async () => {
  if (!requireAuth()) return;

  const lang = localStorage.getItem('satquery_lang') || 'en';
  const navLang = document.getElementById('nav-lang');
  if (navLang) navLang.value = lang;

  await loadDashboardStats();
  await loadRecentAnalyses();
});

async function loadDashboardStats() {
  const token = localStorage.getItem('satquery_token');
  try {
    const resp = await fetch('/api/analysis/history?per_page=100', {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    const data = await resp.json();
    if (!data.success) return;

    const all = data.analyses || [];
    const completed = all.filter(a => a.status === 'completed');
    const avgConf = completed.length
      ? (completed.reduce((s, a) => s + (a.overall_confidence || 0), 0) / completed.length).toFixed(0)
      : '—';

    document.getElementById('stat-total').textContent = data.total || 0;
    document.getElementById('stat-completed').textContent = completed.length;
    document.getElementById('stat-confidence').textContent = avgConf !== '—' ? avgConf + '/100' : '—';
  } catch (_) {}
}

async function loadRecentAnalyses() {
  const token = localStorage.getItem('satquery_token');
  const container = document.getElementById('recent-list');

  try {
    const resp = await fetch('/api/analysis/history?per_page=5', {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    const data = await resp.json();
    if (!data.success || !data.analyses.length) {
      container.innerHTML = `
        <div style="text-align:center;padding:3rem;color:var(--text-muted);">
          <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin:0 auto 1rem;display:block;opacity:0.3;"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
          <p>No analyses yet.</p>
          <a href="/analysis" class="btn btn-primary btn-sm" style="margin-top:1rem;">Start your first analysis</a>
        </div>`;
      return;
    }

    const modeLabels = { single: 'Single Image', optical_sar: 'Optical + SAR', multitemporal: 'Multitemporal' };
    const modeClasses = { single: 'mode-single', optical_sar: 'mode-optical', multitemporal: 'mode-temporal' };

    const rows = data.analyses.map(a => {
      const conf = a.overall_confidence != null ? `${Math.round(a.overall_confidence)}/100` : '—';
      const date = new Date(a.created_at).toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'numeric' });
      const location = a.place_name || (a.latitude != null ? `${a.latitude.toFixed(3)}°, ${a.longitude.toFixed(3)}°` : 'Image upload');
      const statusColor = { completed: 'badge-success', failed: 'badge-danger', processing: 'badge-warning', pending: 'badge-accent' }[a.status] || 'badge-accent';

      return `
      <div class="glass-card" style="padding:1.25rem;margin-bottom:0.75rem;display:flex;align-items:center;gap:1rem;flex-wrap:wrap;">
        <div style="flex:1;min-width:160px;">
          <div style="font-size:0.78rem;font-family:var(--font-mono);color:var(--text-muted);">${a.id.slice(0,8)}</div>
          <div style="font-size:0.95rem;font-weight:600;color:var(--text-primary);margin-top:2px;">${location}</div>
        </div>
        <span class="history-mode-badge ${modeClasses[a.mode] || ''}">${modeLabels[a.mode] || a.mode}</span>
        <div style="text-align:center;min-width:70px;">
          <div style="font-size:1.1rem;font-weight:700;color:var(--accent);">${conf}</div>
          <div style="font-size:0.72rem;color:var(--text-muted);">Confidence</div>
        </div>
        <span class="badge ${statusColor}">${a.status}</span>
        <div style="font-size:0.8rem;color:var(--text-muted);min-width:80px;text-align:right;">${date}</div>
        ${a.status === 'completed' ? `<a href="/results?id=${a.id}" class="btn btn-secondary btn-sm">View</a>` : ''}
        ${a.has_report ? `<button class="btn btn-ghost btn-sm" onclick="quickDownload('${a.id}')">
          <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
          PDF
        </button>` : ''}
      </div>`;
    }).join('');

    container.innerHTML = rows;
  } catch (e) {
    container.innerHTML = `<div class="alert alert-error">Failed to load recent analyses.</div>`;
  }
}

async function quickDownload(analysisId) {
  const token = localStorage.getItem('satquery_token');
  try {
    const resp = await fetch(`/api/report/${analysisId}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (resp.ok) {
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `SATQUERY_Report_${analysisId.slice(0,8)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    }
  } catch (_) {}
}

function selectMode(mode) {
  sessionStorage.setItem('satquery_mode', mode);
  window.location.href = '/analysis';
}

/* ── Custom Training Agent Modal Controller ──────────────── */

function openAgentModal() {
  const modal = document.getElementById('agent-modal');
  if (modal) {
    modal.classList.remove('hidden');
    checkAgentStatus();
  }
}

function closeAgentModal() {
  const modal = document.getElementById('agent-modal');
  if (modal) modal.classList.add('hidden');
}

function onAgentTypeChange() {
  const type = document.getElementById('agent-type')?.value;
  const weightsGroup = document.getElementById('agent-weights-group');
  const endpointGroup = document.getElementById('agent-endpoint-group');

  if (type === 'rest_endpoint') {
    if (weightsGroup) weightsGroup.classList.add('hidden');
    if (endpointGroup) endpointGroup.classList.remove('hidden');
  } else {
    if (weightsGroup) weightsGroup.classList.remove('hidden');
    if (endpointGroup) endpointGroup.classList.add('hidden');
  }
}

async function checkAgentStatus() {
  try {
    const resp = await fetch('/api/agent/status');
    const data = await resp.json();
    const badge = document.getElementById('agent-link-status-badge');
    if (data.success && data.agent) {
      const a = data.agent;
      if (a.connected) {
        if (badge) {
          badge.textContent = `🔗 Agent Linked: ${a.name}`;
          badge.className = 'badge badge-success';
        }
        const nameInput = document.getElementById('agent-name');
        if (nameInput) nameInput.value = a.name;
        const typeSelect = document.getElementById('agent-type');
        if (typeSelect) typeSelect.value = a.type;
        const pathInput = document.getElementById('agent-weights-path');
        if (pathInput && a.weights_path) pathInput.value = a.weights_path;
        const urlInput = document.getElementById('agent-endpoint-url');
        if (urlInput && a.endpoint_url) urlInput.value = a.endpoint_url;
        onAgentTypeChange();
      } else {
        if (badge) {
          badge.textContent = '🔗 Training Agent: Standby';
          badge.className = 'badge badge-purple';
        }
      }
    }
  } catch (_) {}
}

async function testAgentConnection() {
  const token = localStorage.getItem('satquery_token');
  const alertEl = document.getElementById('agent-modal-alert');
  if (alertEl) {
    alertEl.className = 'alert alert-info';
    alertEl.textContent = 'Pinging agent inference runtime...';
    alertEl.classList.remove('hidden');
  }

  try {
    const resp = await fetch('/api/agent/test', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    });
    const data = await resp.json();
    if (data.success) {
      if (alertEl) {
        alertEl.className = 'alert alert-success';
        alertEl.textContent = `⚡ Agent Status: ${data.status} · Latency: ${data.latency_ms}ms · Ready for pipeline inference.`;
        alertEl.classList.remove('hidden');
      }
    } else {
      if (alertEl) {
        alertEl.className = 'alert alert-error';
        alertEl.textContent = 'Agent verification failed. Check weights path or endpoint URL.';
        alertEl.classList.remove('hidden');
      }
    }
  } catch (err) {
    if (alertEl) {
      alertEl.className = 'alert alert-error';
      alertEl.textContent = 'Network error while contacting agent test endpoint.';
      alertEl.classList.remove('hidden');
    }
  }
}

async function saveAgentConnection() {
  const token = localStorage.getItem('satquery_token');
  const alertEl = document.getElementById('agent-modal-alert');
  const name = document.getElementById('agent-name')?.value.trim() || 'Custom Training Agent';
  const type = document.getElementById('agent-type')?.value;
  const task = document.getElementById('agent-task')?.value;
  const weightsPath = document.getElementById('agent-weights-path')?.value.trim();
  const endpointUrl = document.getElementById('agent-endpoint-url')?.value.trim();

  try {
    const resp = await fetch('/api/agent/connect', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        name,
        type,
        task,
        weights_path: weightsPath,
        endpoint_url: endpointUrl,
        framework: 'PyTorch / HuggingFace'
      })
    });
    const data = await resp.json();
    if (data.success) {
      if (alertEl) {
        alertEl.className = 'alert alert-success';
        alertEl.textContent = `✅ Successfully linked '${name}' to the SATQUERY analysis engine!`;
        alertEl.classList.remove('hidden');
      }
      checkAgentStatus();
      setTimeout(() => closeAgentModal(), 1200);
    } else {
      if (alertEl) {
        alertEl.className = 'alert alert-error';
        alertEl.textContent = data.message || 'Failed to connect agent.';
        alertEl.classList.remove('hidden');
      }
    }
  } catch (err) {
    if (alertEl) {
      alertEl.className = 'alert alert-error';
      alertEl.textContent = 'Failed to connect agent. Check network connection.';
      alertEl.classList.remove('hidden');
    }
  }
}

// Initial agent status check
document.addEventListener('DOMContentLoaded', () => {
  checkAgentStatus();
});

