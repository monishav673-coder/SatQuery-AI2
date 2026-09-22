/* ============================================================
   SATQUERY AI — History Page Controller
   ============================================================ */

let allAnalyses = [];
let currentPage = 1;
const perPage = 15;

document.addEventListener('DOMContentLoaded', async () => {
  if (!requireAuth()) return;
  initNavUser();
  const lang = localStorage.getItem('satquery_lang') || 'en';
  const navLang = document.getElementById('nav-lang');
  if (navLang) navLang.value = lang;
  await loadHistory();
});

async function loadHistory() {
  const token = localStorage.getItem('satquery_token');
  try {
    const resp = await fetch('/api/analysis/history?per_page=100', {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    const data = await resp.json();
    if (!data.success) { renderError('Failed to load history.'); return; }
    allAnalyses = data.analyses || [];
    renderHistoryPage();
  } catch (_) {
    renderError('Network error loading history.');
  }
}

function filterHistory() {
  currentPage = 1;
  renderHistoryPage();
}

function renderHistoryPage() {
  const search = (document.getElementById('search-input')?.value || '').toLowerCase();
  const modeF  = document.getElementById('mode-filter')?.value || '';
  const statF  = document.getElementById('status-filter')?.value || '';

  const filtered = allAnalyses.filter(a => {
    const loc = (a.place_name || '').toLowerCase();
    const id  = a.id.toLowerCase();
    const matchSearch = !search || loc.includes(search) || id.includes(search);
    const matchMode   = !modeF  || a.mode === modeF;
    const matchStatus = !statF  || a.status === statF;
    return matchSearch && matchMode && matchStatus;
  });

  const total = filtered.length;
  const pages = Math.ceil(total / perPage) || 1;
  currentPage = Math.min(currentPage, pages);
  const start = (currentPage - 1) * perPage;
  const pageItems = filtered.slice(start, start + perPage);

  const container = document.getElementById('history-content');

  if (!pageItems.length) {
    container.innerHTML = `
      <div style="text-align:center;padding:3rem;color:var(--text-muted);">
        <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin:0 auto 1rem;display:block;opacity:0.3;"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        <p>No analyses found.</p>
        <a href="/analysis" class="btn btn-primary btn-sm" style="margin-top:1rem;">New Analysis</a>
      </div>`;
    renderPagination(0, 1);
    return;
  }

  const modeLabels  = { single: 'Single', optical_sar: 'Optical+SAR', multitemporal: 'Multitemporal' };
  const modeClasses = { single: 'mode-single', optical_sar: 'mode-optical', multitemporal: 'mode-temporal' };
  const statusBadge = { completed: 'badge-success', failed: 'badge-danger', processing: 'badge-warning', pending: 'badge-accent' };

  const tableRows = pageItems.map(a => {
    const loc  = a.place_name || (a.latitude != null ? `${a.latitude.toFixed(3)}°, ${a.longitude.toFixed(3)}°` : 'Image upload');
    const conf = a.overall_confidence != null ? `${Math.round(a.overall_confidence)}/100` : '—';
    const date = new Date(a.created_at).toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' });

    return `<tr>
      <td style="font-family:var(--font-mono);font-size:0.78rem;color:var(--text-muted);">${a.id.slice(0,8)}</td>
      <td style="color:var(--text-primary);font-weight:500;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${loc}</td>
      <td><span class="history-mode-badge ${modeClasses[a.mode]||''}">${modeLabels[a.mode]||a.mode}</span></td>
      <td style="font-weight:700;color:var(--accent);">${conf}</td>
      <td><span class="badge ${statusBadge[a.status]||'badge-accent'}">${a.status}</span></td>
      <td style="font-size:0.8rem;">${date}</td>
      <td>
        <div style="display:flex;gap:6px;flex-wrap:nowrap;">
          ${a.status === 'completed' ? `<a href="/results?id=${a.id}" class="btn btn-secondary btn-sm">Results</a>` : ''}
          ${a.has_report ? `<button class="btn btn-ghost btn-sm" onclick="downloadReport('${a.id}')" title="Download report">
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
          </button>` : ''}
          <button class="btn btn-ghost btn-sm" onclick="deleteAnalysis('${a.id}', this)" title="Delete"
            style="color:var(--text-muted);">
            <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
          </button>
        </div>
      </td>
    </tr>`;
  }).join('');

  container.innerHTML = `
    <div style="overflow-x:auto;">
      <table class="history-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Location</th>
            <th>Mode</th>
            <th>Confidence</th>
            <th>Status</th>
            <th>Date</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>${tableRows}</tbody>
      </table>
    </div>
    <div style="padding:1rem 1.5rem;border-top:1px solid var(--border-color);font-size:0.82rem;color:var(--text-muted);">
      Showing ${start + 1}–${Math.min(start + perPage, total)} of ${total} analyses
    </div>`;

  renderPagination(total, pages);
}

function renderPagination(total, pages) {
  const pag = document.getElementById('pagination');
  if (!pag || pages <= 1) { if(pag) pag.innerHTML=''; return; }

  let html = `
    <button class="page-btn" onclick="goPage(${currentPage-1})" ${currentPage<=1?'disabled':''}>‹</button>`;
  for (let i = 1; i <= pages; i++) {
    if (i === 1 || i === pages || Math.abs(i - currentPage) <= 2) {
      html += `<button class="page-btn ${i===currentPage?'active':''}" onclick="goPage(${i})">${i}</button>`;
    } else if (Math.abs(i - currentPage) === 3) {
      html += `<span class="page-btn" style="cursor:default;">…</span>`;
    }
  }
  html += `<button class="page-btn" onclick="goPage(${currentPage+1})" ${currentPage>=pages?'disabled':''}>›</button>`;
  pag.innerHTML = html;
}

function goPage(page) {
  currentPage = page;
  renderHistoryPage();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

async function downloadReport(analysisId) {
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

async function deleteAnalysis(analysisId, btn) {
  if (!confirm('Delete this analysis? This cannot be undone.')) return;
  const token = localStorage.getItem('satquery_token');
  btn.disabled = true;
  try {
    const resp = await fetch(`/api/analysis/${analysisId}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await resp.json();
    if (data.success) {
      allAnalyses = allAnalyses.filter(a => a.id !== analysisId);
      renderHistoryPage();
    } else {
      alert(data.error || 'Delete failed.');
      btn.disabled = false;
    }
  } catch (_) { btn.disabled = false; }
}

function renderError(msg) {
  document.getElementById('history-content').innerHTML = `<div class="alert alert-error" style="margin:1rem;">${msg}</div>`;
}

function toggleMobileNav() {
  document.getElementById('mobile-nav')?.classList.toggle('open');
}
function setLanguage(lang) { localStorage.setItem('satquery_lang', lang); }
