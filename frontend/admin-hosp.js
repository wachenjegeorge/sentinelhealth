// admin-hosp.js — Department AI analysis for hospital_head / county_officer / admin
(function() {
  'use strict';
  if (typeof Auth === 'undefined') return;
  const session = Auth.readSession();
  if (!session) return;
  if (['hospital_head', 'county_officer', 'admin'].indexOf(session.role) < 0) return;

  let _dept = null;
  let _wvi = null;

  function ensureModal() {
    if (document.getElementById('dept-analysis-modal')) return;
    const m = document.createElement('div');
    m.id = 'dept-analysis-modal';
    m.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.8);z-index:60;display:none;align-items:center;justify-content:center;padding:1rem;backdrop-filter:blur(8px);';
    m.innerHTML =
      '<div style="background:linear-gradient(135deg,rgba(30,41,59,0.95),rgba(15,23,42,0.98));border:1px solid rgba(148,163,184,0.2);border-radius:18px;max-width:780px;width:100%;max-height:85vh;overflow-y:auto;box-shadow:0 32px 80px -16px rgba(0,0,0,0.9);">' +
        '<div style="padding:1.25rem 1.5rem;border-bottom:1px solid rgba(148,163,184,0.15);display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;background:rgba(15,23,42,0.98);backdrop-filter:blur(8px);z-index:10;">' +
          '<div>' +
            '<p style="font-size:0.68rem;letter-spacing:0.12em;text-transform:uppercase;color:#22d3ee;font-weight:700;margin:0;">Department AI</p>' +
            '<h3 id="da-title" style="font-size:1.15rem;font-weight:700;color:#f1f5f9;margin:0.25rem 0 0;">Loading...</h3>' +
            '<p id="da-subtitle" style="font-size:0.72rem;color:#64748b;margin:0.25rem 0 0;"></p>' +
          '</div>' +
          '<div style="display:flex;gap:0.5rem;align-items:center;">' +
            '<button id="da-run" onclick="runDeptAnalysis()" style="background:linear-gradient(135deg,#22d3ee,#3b82f6);border:none;color:#05080f;border-radius:8px;padding:0.5rem 1rem;font-size:0.75rem;font-weight:700;cursor:pointer;">Regenerate</button>' +
            '<button onclick="closeDeptAnalysis()" style="background:transparent;border:none;color:#94a3b8;font-size:1.25rem;cursor:pointer;padding:0.25rem 0.5rem;">✕</button>' +
          '</div>' +
        '</div>' +
        '<div style="padding:1.5rem;" id="da-body">' +
          '<p style="color:#94a3b8;font-size:0.875rem;">Opening analysis...</p>' +
        '</div>' +
      '</div>';
    document.body.appendChild(m);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureModal);
  } else {
    ensureModal();
  }

  window.openDeptAnalysis = function(dept, wvi) {
    ensureModal();
    _dept = dept;
    _wvi = typeof wvi === 'number' ? wvi : parseFloat(wvi) || 0;
    const modal = document.getElementById('dept-analysis-modal');
    if (!modal) return;
    document.getElementById('da-title').textContent = dept;
    document.getElementById('da-subtitle').textContent =
      'WVI ' + _wvi + ' · viewing as ' + session.role.replace(/_/g, ' ');
    modal.style.display = 'flex';
    runDeptAnalysis();
  };

  window.closeDeptAnalysis = function() {
    const m = document.getElementById('dept-analysis-modal');
    if (m) m.style.display = 'none';
  };

  window.runDeptAnalysis = async function() {
    if (!_dept) return;
    const btn = document.getElementById('da-run');
    const body = document.getElementById('da-body');
    btn.disabled = true;
    btn.textContent = 'Analyzing...';
    body.innerHTML = '<div style="display:flex;align-items:center;gap:0.5rem;color:#22d3ee;font-size:0.875rem;"><div style="width:16px;height:16px;border:2px solid rgba(34,211,238,0.3);border-top-color:#22d3ee;border-radius:50%;animation:spin 0.7s linear infinite;"></div><span>Generating AI analysis... 10-15 seconds.</span></div>' +
      '<style>@keyframes spin{to{transform:rotate(360deg)}}</style>';

    const key = (crypto.randomUUID ? crypto.randomUUID() : Date.now() + '-' + Math.random());
    try {
      const res = await Auth.apiFetch('/api/bff/hospital/departments/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key },
        body: JSON.stringify({ department: _dept }),
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const d = await res.json();

      let html = (d.analysis || 'No analysis')
        .replace(/^## (.*?)$/gm, '<h2 style="font-size:1rem;font-weight:700;color:#ffffff;margin:1rem 0 0.5rem;">$1</h2>')
        .replace(/^### (.*?)$/gm, '<h3 style="font-size:0.875rem;font-weight:600;color:#e2e8f0;margin:0.75rem 0 0.25rem;">$1</h3>')
        .replace(/\*\*(.*?)\*\*/g, '<strong style="color:#ffffff;">$1</strong>')
        .replace(/`([^`]+)`/g, '<code style="background:#1e293b;padding:0.1rem 0.35rem;border-radius:0.25rem;color:#22d3ee;font-size:0.82rem;">$1</code>')
        .replace(/^\s*- (.*?)$/gm, '<li style="margin-left:1rem;color:#cbd5e1;margin-bottom:0.35rem;">$1</li>')
        .replace(/^\s*(\d+)\. (.*?)$/gm, '<li style="margin-left:1rem;color:#cbd5e1;margin-bottom:0.35rem;">$2</li>')
        .replace(/\n\n/g, '</p><p style="margin-bottom:0.5rem;">')
        .replace(/\n/g, '<br>');

      const m = d.metrics || {};
      const info = m.total_reports != null
        ? m.total_reports + ' reports · WVI ' + m.avg_wvi + ' · ' + m.active_alerts + ' alerts'
        : '';

      body.innerHTML =
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem;padding-bottom:0.5rem;border-bottom:1px solid rgba(148,163,184,0.15);">' +
          '<span style="font-size:0.72rem;color:#22d3ee;font-family:ui-monospace,monospace;font-weight:600;">ENGINE: ' + (d.engine || '?').toUpperCase() + '</span>' +
          '<span style="font-size:0.65rem;color:#64748b;">' + info + '</span>' +
        '</div>' +
        '<div style="font-size:0.875rem;color:#cbd5e1;line-height:1.65;">' + html + '</div>';
    } catch (e) {
      body.innerHTML = '<p style="color:#fb7185;font-size:0.875rem;">Analysis failed: ' + e.message + '</p>';
    } finally {
      btn.disabled = false;
      btn.textContent = 'Regenerate';
    }
  };
})();
