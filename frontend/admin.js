(function() {
  const session = Auth.requireRole(["admin", "county_officer", "hospital_head"]);
  if (!session) return;
  const $ = id => document.getElementById(id);
  const role = session.role;

  // ── 1. Header configuration ──
  const headerMap = {
    "admin": "NATIONAL SCOPE // SENTINEL ADMIN",
    "county_officer": (session.county || "").toUpperCase() + " COUNTY // OFFICER",
    "health_officer": (session.county || "").toUpperCase() + " COUNTY // OFFICER",
    "hospital_head": (session.facility_id || "").toUpperCase() + " // HOSPITAL HEAD"
  };
  if ($("headerSub")) $("headerSub").textContent = headerMap[role] || "SENTINELHEALTH";

  if (role !== "admin") {
    if ($("nav-verify")) $("nav-verify").classList.remove("hidden");
    if ($("nav-facilities")) {
      $("nav-facilities").classList.remove("hidden");
      if (role === "hospital_head") {
        $("nav-facilities").textContent = "Departments";
        $("nav-facilities").href = "#";
        $("nav-facilities").onclick = function(e) {
          e.preventDefault();
          var el = document.querySelector("#drill-title");
          if (el) el.scrollIntoView({ behavior: "smooth" });
        };
      }
    }
    if ($("operational-tools")) $("operational-tools").classList.remove("hidden");
  }

  let currentDeepDiveCounty = null;
  let currentScope = role === "admin" ? "national" : (role === "hospital_head" ? "facility" : "county");

  // ── 2. Helpers ──
  function colorFor(score) {
    if (score >= 65) return "#e11d48";
    if (score >= 35) return "#d97706";
    return "#059669";
  }
  function setText(id, text) { const el = $(id); if (el) el.textContent = text; }
  function setHtml(id, html) { const el = $(id); if (el) el.innerHTML = html; }

  // ── 3. AI Co-Pilot panel ──
  async function fetchAiInsights() {
    const ins = $("ai-insights"), status = $("ai-status");
    if (!ins) return;
    try {
      const res = await Auth.apiFetch("/api/bff/admin/ai-brief");
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();
      if (status) status.textContent = "ENGINE: " + String(d.engine || "?").toUpperCase();

      const m = d.metrics || {};
      const pwvi = m.pooled_wvi || 0;
      const badge = pwvi >= 65 ? '<span class="text-[10px] bg-rose-500/20 text-rose-300 px-2 py-0.5 rounded">CRITICAL</span>'
                  : pwvi >= 35 ? '<span class="text-[10px] bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded">MODERATE</span>'
                  : '<span class="text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded">LOW</span>';

      const kpiRow = '<div class="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">' +
        '<div class="bg-slate-900/50 rounded-lg p-2 border border-slate-800"><p class="text-[9px] uppercase text-slate-500">Pooled WVI</p><p class="text-lg font-bold text-white">' + pwvi + '</p>' + badge + '</div>' +
        '<div class="bg-slate-900/50 rounded-lg p-2 border border-slate-800"><p class="text-[9px] uppercase text-slate-500">Facilities</p><p class="text-lg font-bold text-white">' + (m.facilities || 0) + '</p></div>' +
        '<div class="bg-slate-900/50 rounded-lg p-2 border border-slate-800"><p class="text-[9px] uppercase text-slate-500">Critical</p><p class="text-lg font-bold text-rose-400">' + (m.critical_facilities || 0) + '</p></div>' +
        '<div class="bg-slate-900/50 rounded-lg p-2 border border-slate-800"><p class="text-[9px] uppercase text-slate-500">Alerts</p><p class="text-lg font-bold text-amber-400">' + (m.alerts || 0) + '</p></div>' +
      '</div>';

      const body = String(d.brief || "")
        .replace(/^## (.*?)$/gm, '<h3 class="text-xs font-bold text-cyan-300 uppercase tracking-wider mt-4 mb-2">$1</h3>')
        .replace(/\*\*(.*?)\*\*/g, '<strong class="text-white">$1</strong>')
        .replace(/^\s*- (.*?)$/gm, '<li class="ml-4 mb-1">$1</li>')
        .replace(/^\s*(\d+)\. (.*?)$/gm, '<li class="ml-4 mb-1"><span class="text-cyan-400 font-bold">$1.</span> $2</li>')
        .replace(/\n\n/g, '</p><p class="mb-2">')
        .replace(/\n/g, '<br>');

      ins.innerHTML = kpiRow + '<div class="text-sm text-slate-300 leading-relaxed">' + body + '</div>';
    } catch (e) {
      ins.innerHTML = "<span class='text-rose-400'>Strategic brief unavailable. Try again.</span>";
      if (status) status.textContent = "OFFLINE";
    }
  }

  // ── 4. Deep dive: open a county workspace ──
  window.drillToCounty = (countyName) => {
    window.location.href = "/admin/intel/" + encodeURIComponent(countyName);
  };

  window.closeDeepDive = () => {
    const panel = $("deep-dive-panel");
    if (panel) { panel.classList.add("hidden"); panel.classList.remove("flex"); }
    currentDeepDiveCounty = null;
  };

  window.drillToFacility = async (facilityId) => {
    // Loads departments for that facility inside the deep-dive workspace
    try {
      const res = await Auth.apiFetch("/api/bff/admin/facility/" + encodeURIComponent(facilityId));
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();
      const depts = d.departments || [];
      setHtml("dd-facilities", depts.length
        ? depts.map(dept =>
            '<div class="flex justify-between items-center p-3 bg-slate-800 rounded-lg">' +
              '<div><span class="text-sm font-medium text-slate-200 block">' + dept.department + '</span>' +
              '<span class="text-[10px] text-slate-500">' + dept.shifts.join(", ") + ' &middot; ' + dept.reported + ' reports</span></div>' +
              '<span class="text-sm font-bold" style="color:' + colorFor(dept.wvi) + '">' + dept.wvi + ' WVI</span>' +
            '</div>'
          ).join("")
        : '<p class="text-sm text-slate-500">No department data clears k=5.</p>');
      setText("dd-title", facilityId.replace(/-/g, " ").toUpperCase());
    } catch (e) {
      console.error("Facility drill failed", e);
    }
  };

  window.exportCounty = () => { window.downloadReport(); };

  // ── 5. Main dashboard overview ──
  async function loadOverview() {
    currentScope = role === "admin" ? "national" : (role === "hospital_head" ? "facility" : "county");
    if ($("drill-back")) $("drill-back").classList.add("hidden");

    try {
      const res = await Auth.apiFetch("/api/bff/admin/overview");
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();

      setText("kpi-1-val", Math.round(d.pooled_wvi || 0));
      const lvlEl = $("kpi-1-lvl");
      if (lvlEl) {
        lvlEl.textContent = d.pooled_level || "--";
        lvlEl.style.color = colorFor(d.pooled_wvi || 0);
      }
      let totalReports = 0;
      (d.groups || []).forEach(function(g) { totalReports += g.reported; });
      setText("kpi-2-val", totalReports);
      setText("kpi-3-val", (d.autonomous_alerts || []).length);
      setText("kpi-4-val", (d.scope || "").toUpperCase());

      // Alerts
      const alerts = d.autonomous_alerts || [];
      if (alerts.length === 0) {
        setHtml("alerts", '<div class="card p-4 text-sm text-slate-400 text-center">No active anomalies detected.</div>');
      } else {
        setHtml("alerts", alerts.map(function(a) {
          return '<div class="card p-4 border-l-4 border-l-rose-500">' +
            '<p class="text-xs font-bold text-rose-400 uppercase tracking-widest mb-1">Anomaly Detected</p>' +
            '<p class="text-sm font-semibold text-slate-200">' + a.department + ' (' + a.shift + ')</p>' +
            '<p class="text-xs text-slate-400 mt-2">' + (a.ai_protocol || "") + '</p>' +
            '<button onclick="resolveAlert(\'' + a.id + '\')" class="mt-3 w-full rounded bg-rose-500/20 text-rose-300 text-xs py-1.5 hover:bg-rose-500/30 transition">Acknowledge</button>' +
          '</div>';
        }).join(""));
      }

      // Drill-down list on the right panel
      if (d.scope === "national") {
        setText("drill-title", "47 Counties");
        setHtml("drill-list", (d.counties || []).map(function(c) {
          return '<div onclick="drillToCounty(\'' + c.county + '\')" class="flex justify-between items-center p-3 bg-slate-800 hover:bg-slate-700 rounded-lg cursor-pointer transition">' +
            '<span class="text-sm font-medium text-slate-200">' + c.county + '</span>' +
            '<span class="text-sm font-bold" style="color:' + colorFor(c.wvi) + '">' + c.wvi + ' WVI</span>' +
          '</div>';
        }).join(""));
      } else if (d.scope === "county") {
        setText("drill-title", d.county + " Facilities");
        setHtml("drill-list", (d.facilities || []).map(function(f) {
          return '<div onclick="drillToFacility(\'' + f.facility_id + '\')" class="flex justify-between items-center p-3 bg-slate-800 hover:bg-slate-700 rounded-lg cursor-pointer transition">' +
            '<div><span class="text-sm font-medium text-slate-200 block">' + f.name + '</span>' +
            '<span class="text-[10px] text-slate-500">L' + f.keph_level + ' &middot; ' + f.reported + ' reports</span></div>' +
            '<span class="text-sm font-bold" style="color:' + (f.wvi ? colorFor(f.wvi) : "#64748b") + '">' +
              (f.suppressed ? 'Hidden' : f.wvi + ' WVI') + '</span>' +
          '</div>';
        }).join(""));
      } else if (d.scope === "facility") {
        setText("drill-title", "Departments");
        window._currentDepts = d.departments || [];
        setHtml("drill-list", window._currentDepts.map(function(dept, idx) {
          return '<div onclick="openDeptAnalysisByIndex(' + idx + ')" class="flex justify-between items-center p-3 bg-slate-800 hover:bg-slate-700 rounded-lg cursor-pointer transition">' +
            '<div><span class="text-sm font-medium text-slate-200 block">' + dept.department + '</span>' +
            '<span class="text-[10px] text-slate-500">' + dept.shifts.join(", ") + ' &middot; ' + dept.reported + ' reports</span></div>' +
            '<div class="flex items-center gap-2">' +
            '<span class="text-sm font-bold" style="color:' + colorFor(dept.wvi) + '">' + dept.wvi + ' WVI</span>' +
            '<span class="text-cyan-400 text-xs">&#8594;</span>' +
            '</div>' +
          '</div>';
        }).join(""));
      }

      fetchAiInsights();
      setText("live", "System Live");
    } catch (err) {
      setText("live", "Disconnected");
      console.error(err);
    }
  }

  window.resetDrilldown = function() { loadOverview(); };

  window.resolveAlert = async function(id) {
    try {
      await Auth.apiFetch("/api/bff/admin/alerts/" + id + "/resolve", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID ? crypto.randomUUID() : (Date.now() + "-" + Math.random().toString(36).slice(2)) }
      });
      loadOverview();
  loadDepartments();
  loadForecast();
    } catch (e) { console.error(e); }
  };

  // ── 6. Export ──
  window.downloadReport = async function() {
    try {
      const res = await Auth.apiFetch("/api/bff/admin/export");
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "sentinel_export.csv";
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (e) { console.error(e); }
  };

  // ── 7. Simulator ──
  if ($("sim-slider")) {
    $("sim-slider").oninput = function() { setText("sim-val", this.value); };
  }
  window.runSimulation = async function() {
    try {
      const res = await Auth.apiFetch("/api/bff/admin/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID ? crypto.randomUUID() : (Date.now() + "-" + Math.random().toString(36).slice(2)) },
        body: JSON.stringify({
          department: "ICU / Critical Care",
          shift: "day",
          extra_staff: parseInt($("sim-slider").value),
          current_wvi: 45.0
        })
      });
      const d = await res.json();
      setText("sim-current", Math.round(d.current_wvi));
      setText("sim-projected", Math.round(d.projected_wvi));
      setText("sim-reasoning", d.ai_reasoning);
    } catch (e) { console.error(e); }
  };

  // ── 8. Roster ──
  async function loadRoster() {
    if (role === "admin") return;
    const el = $("roster-list");
    if (!el) return;
    try {
      const res = await Auth.apiFetch("/api/bff/admin/roster");
      if (!res.ok) return;
      const d = await res.json();
      const roster = d.roster || [];
      if (roster.length === 0) { setHtml("roster-list", "No upcoming shifts."); return; }
      setHtml("roster-list", roster.slice(0, 5).map(function(r) {
        return '<div class="flex justify-between border-b border-slate-700/50 pb-2 mb-2">' +
          '<div><p class="font-medium text-slate-200">' + r.department + ' (' + r.shift_type + ')</p>' +
          '<p class="text-xs text-slate-500">' + new Date(r.start_time).toLocaleDateString() + '</p></div>' +
          '<span class="text-xs bg-slate-800 px-2 py-1 rounded h-fit text-slate-300">' + (r.full_name || r.username) + '</span>' +
        '</div>';
      }).join(""));
    } catch (e) { console.error(e); }
  }
  window.openCreateShift = async function() {
    const modal = $("create-shift-modal");
    if (!modal) return UI.toast("Modal missing", "error");
    modal.style.display = "flex";
    const deptSel = $("cs-dept");
    const workerSel = $("cs-worker");
    deptSel.innerHTML = "<option>Loading...</option>";
    try {
      const r1 = await Auth.apiFetch("/api/bff/hospital/departments");
      const d1 = r1.ok ? await r1.json() : { departments: [] };
      const depts = d1.departments || [];
      deptSel.innerHTML = depts.length
        ? depts.map(function(d) { return '<option value="' + d.department + '">' + d.department + '</option>'; }).join("")
        : '<option value="">No departments</option>';
      const r2 = await Auth.apiFetch("/api/bff/admin/roster/workers");
      const d2 = r2.ok ? await r2.json() : { workers: [] };
      window._allWorkers = d2.workers || [];
      filterWorkersByDept();
      deptSel.onchange = filterWorkersByDept;
    } catch (e) {
      deptSel.innerHTML = '<option value="">Failed to load</option>';
    }
  };

  function filterWorkersByDept() {
    const dept = $("cs-dept").value;
    const workerSel = $("cs-worker");
    const all = window._allWorkers || [];
    const matching = all.filter(function(w) {
      return w.primary_department === dept || (w.primary_department || "").indexOf(dept) === 0;
    });
    if (matching.length === 0) {
      workerSel.innerHTML = '<option value="">No workers in this department</option>';
    } else {
      workerSel.innerHTML = matching.map(function(w) {
        return '<option value="' + w.id + '">' + (w.full_name || w.username) + '</option>';
      }).join("");
    }
  }

  window.closeCreateShift = function() {
    const m = $("create-shift-modal");
    if (m) m.style.display = "none";
  };

  window.submitCreateShift = async function() {
    const workerId = $("cs-worker").value;
    const dept = $("cs-dept").value;
    const type = $("cs-type").value;
    const date = $("cs-date").value;
    const start = $("cs-start").value;
    const end = $("cs-end").value;
    if (!workerId || !date || !start || !end) return UI.toast("Fill all fields", "error");
    const startISO = new Date(date + "T" + start).toISOString();
    const endISO = new Date(date + "T" + end).toISOString();
    const key = crypto.randomUUID ? crypto.randomUUID() : Date.now().toString();
    try {
      const res = await Auth.apiFetch("/api/bff/admin/roster", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": key },
        body: JSON.stringify({ user_id: workerId, department: dept, shift_type: type, start_time: startISO, end_time: endISO }),
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      UI.toast("Shift scheduled");
      closeCreateShift();
      if (typeof loadRoster === "function") loadRoster();
    } catch (e) { UI.toast("Failed: " + e.message, "error"); }
  };

  window.openActionPlan = async function() {
    const modal = $("action-plan-modal");
    const body = $("ap-body");
    if (!modal) return;
    modal.style.display = "flex";
    body.innerHTML = '<div style="display:flex;align-items:center;gap:0.5rem;color:#22d3ee;"><span>Generating comprehensive action plan... 15-20 seconds.</span></div>';
    const key = crypto.randomUUID ? crypto.randomUUID() : Date.now().toString();
    try {
      const res = await Auth.apiFetch("/api/bff/assistant/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": key },
        body: JSON.stringify({ question: "Generate a comprehensive action plan for my scope: 1) Current situation with numbers, 2) Top 3 priority areas and why, 3) Three specific actions for THIS WEEK with named owners, 4) Escalation decision yes/no to higher level, 5) What to measure next week." }),
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();
      const html = String(d.answer || "")
        .replace(/^### (.*?)$/gm, '<h3 style="font-size:0.9rem;font-weight:600;color:#67e8f9;margin:1rem 0 0.5rem;">$1</h3>')
        .replace(/^## (.*?)$/gm, '<h2 style="font-size:1.1rem;font-weight:700;color:#ffffff;margin:1rem 0 0.5rem;">$1</h2>')
        .replace(/\*\*(.*?)\*\*/g, '<strong style="color:#ffffff;">$1</strong>')
        .replace(/^\s*- (.*?)$/gm, '<li style="margin-left:1rem;margin-bottom:0.25rem;">$1</li>')
        .replace(/^\s*(\d+)\. (.*?)$/gm, '<li style="margin-left:1rem;margin-bottom:0.25rem;">$2</li>')
        .replace(/\n\n/g, '</p><p style="margin-bottom:0.5rem;">')
        .replace(/\n/g, '<br>');
      body.innerHTML = '<p style="font-size:0.65rem;color:#64748b;margin-bottom:0.75rem;font-family:monospace;">ENGINE: ' + String(d.engine || "?").toUpperCase() + '</p><div style="font-size:0.875rem;color:#cbd5e1;line-height:1.65;">' + html + '</div>';
    } catch (e) {
      body.innerHTML = '<p style="color:#fb7185;">Failed: ' + e.message + '</p>';
    }
  };

  window.regenerateActionPlan = function() { openActionPlan(); };

  window.closeActionPlan = function() {
    const m = $("action-plan-modal");
    if (m) m.style.display = "none";
  };

  // ── 9. Approval badge ──
  async function checkApprovals() {
    if (role !== "admin" && role !== "county_officer" && role !== "health_officer" && role !== "hospital_head") return;
    try {
      const res = await Auth.apiFetch("/api/bff/admin/verify/queue");
      if (!res.ok) return;
      const d = await res.json();
      const badge = $("verify-badge");
      if (badge && d.queue && d.queue.length > 0) {
        badge.textContent = d.queue.length;
        badge.classList.remove("hidden");
      }
    } catch (e) { /* silent */ }
  }

  async function loadDepartments() {
    const section = $("hospital-departments-section");
    if (!section) return;
    if (role !== "hospital_head") { section.classList.add("hidden"); return; }
    section.classList.remove("hidden");
    try {
      const res = await Auth.apiFetch("/api/bff/hospital/departments");
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();
      const depts = d.departments || [];
      setHtml("dept-list", depts.length ? depts.map(function(dept) {
        return '<div class="rounded-lg border border-slate-800 p-3">' +
          '<p class="text-sm font-semibold text-slate-200">' + dept.name + '</p>' +
          '<p class="text-[10px] text-slate-500">' + (dept.head_name || 'No head') + '</p>' +
          '<p class="text-[10px] text-slate-600 mt-1">' + (dept.reports || 0) + ' reports</p>' +
        '</div>';
      }).join("") : '<p class="text-sm text-slate-500">No departments.</p>');
    } catch (e) { section.classList.add("hidden"); }
  }

  // ── 10. Init ──
  loadOverview();
  loadDepartments();
  loadForecast();
  if (role !== "admin") loadRoster();
  checkApprovals();
  setInterval(loadOverview, 30000);
  setInterval(checkApprovals, 60000);

  
  window._currentDepts = [];
  window.openDeptAnalysisByIndex = function(idx) {
    if (!window._currentDepts || !window._currentDepts[idx]) return;
    var d = window._currentDepts[idx];
    if (typeof window.openDeptAnalysis === 'function') {
      window.openDeptAnalysis(d.department, d.wvi);
    } else {
      alert('admin-hosp.js not loaded');
    }
  };


  async function loadForecast() {
    if (role !== "county_officer") return;
    const section = $("forecast-section");
    if (section) section.classList.remove("hidden");
    const body = $("forecast-body");
    const dirEl = $("forecast-direction");
    if (!body) return;
    try {
      const res = await Auth.apiFetch("/api/bff/admin/forecast");
      if (!res.ok) return;
      const d = await res.json();
      if (!d.available) {
        body.innerHTML = '<p class="text-sm text-slate-500 col-span-4">Not enough data yet (need 3+ days of confirmed check-ins).</p>';
        return;
      }
      const colorFor = function(v) { return v >= 65 ? "text-rose-400" : v >= 35 ? "text-amber-400" : "text-emerald-400"; };
      const bgFor = function(v) { return v >= 65 ? "bg-rose-500" : v >= 35 ? "bg-amber-500" : "bg-emerald-500"; };
      const trendColor = d.trend_direction === "worsening" ? "text-rose-400"
                        : d.trend_direction === "improving" ? "text-emerald-400" : "text-slate-400";
      const trendIcon = d.trend_direction === "worsening" ? "\u2191"
                       : d.trend_direction === "improving" ? "\u2193" : "\u2192";
      if (dirEl) {
        dirEl.textContent = trendIcon + " " + d.trend_direction;
        dirEl.className = "text-xs font-medium " + trendColor;
      }
      const peer = (d.peer_delta != null)
        ? '<div class="col-span-4 p-3 rounded bg-slate-900/50 border border-slate-800">' +
            '<p class="text-[10px] uppercase text-slate-500">Peer Comparison</p>' +
            '<p class="text-sm">You are <strong class="' + (d.peer_delta > 0 ? "text-rose-400" : "text-emerald-400") + '">' + (d.peer_delta > 0 ? "+" : "") + d.peer_delta + '</strong> WVI vs national median (' + d.national_median + ')</p>' +
          '</div>'
        : '';
      const bars = d.forecast.map(function(p) {
        var h = (p.projected_wvi / 100) * 100;
        return '<div class="flex-1 ' + bgFor(p.projected_wvi) + ' rounded-t" style="height:' + h + '%" title="Day +' + p.day_offset + ': ' + p.projected_wvi + '"></div>';
      }).join("");
      body.innerHTML =
        '<div class="col-span-2 p-3 rounded bg-slate-900/50 border border-slate-800">' +
          '<p class="text-[10px] uppercase text-slate-500">Current WVI</p>' +
          '<p class="text-2xl font-bold ' + colorFor(d.current_wvi) + '">' + d.current_wvi + '</p>' +
          '<p class="text-[10px] text-slate-500">' + d.level + '</p>' +
        '</div>' +
        '<div class="col-span-2 p-3 rounded bg-slate-900/50 border border-slate-800">' +
          '<p class="text-[10px] uppercase text-slate-500">7-Day Projection</p>' +
          '<p class="text-2xl font-bold ' + colorFor(d.projected_7d_wvi) + '">' + d.projected_7d_wvi + '</p>' +
          '<p class="text-[10px] text-slate-500">' + (d.slope_per_day > 0 ? "+" : "") + d.slope_per_day + ' /day</p>' +
        '</div>' +
        peer +
        '<div class="col-span-4">' +
          '<div class="h-24 flex items-end gap-1">' + bars + '</div>' +
          '<p class="text-[9px] uppercase text-slate-600 mt-1 text-center">Next 7 days</p>' +
        '</div>';
    } catch (e) { console.error("forecast:", e); }
  }

})();
