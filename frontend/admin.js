(function() {
  const session = Auth.requireRole(["admin", "county_officer", "health_officer", "hospital_head"]);
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
    if ($("nav-facilities")) $("nav-facilities").classList.remove("hidden");
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
      const res = await Auth.apiFetch("/api/bff/assistant/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": "ai-" + Date.now() },
        body: JSON.stringify({ question: "Give me a 2-sentence summary of the current situation and recommend one action." })
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      ins.innerHTML = (data.answer || "")
        .replace(/\*\*(.*?)\*\*/g, '<strong class="text-white">$1</strong>')
        .replace(/\n/g, '<br>');
      status.textContent = "Engine: " + (data.engine || "unknown").toUpperCase();
    } catch (e) {
      ins.innerHTML = "<span class='text-rose-400'>AI synthesis temporarily offline.</span>";
      status.textContent = "OFFLINE";
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
        setText("drill-title", "Department Breakdown");
        setHtml("drill-list", (d.departments || []).map(function(dept) {
          return '<div class="flex justify-between items-center p-3 bg-slate-800 rounded-lg">' +
            '<div><span class="text-sm font-medium text-slate-200 block">' + dept.department + '</span>' +
            '<span class="text-[10px] text-slate-500">' + dept.shifts.join(", ") + ' &middot; ' + dept.reported + ' reports</span></div>' +
            '<span class="text-sm font-bold" style="color:' + colorFor(dept.wvi) + '">' + dept.wvi + ' WVI</span>' +
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
        headers: { "Idempotency-Key": Date.now().toString() }
      });
      loadOverview();
  loadDepartments();
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
        headers: { "Content-Type": "application/json", "Idempotency-Key": Date.now().toString() },
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
  window.openCreateShift = function() {
    if (typeof UI !== "undefined" && UI.toast) UI.toast("Create shift — coming next");
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

  // ── 10. Init ──
  loadOverview();
  loadDepartments();
  if (role !== "admin") loadRoster();
  checkApprovals();
  setInterval(loadOverview, 30000);
  setInterval(checkApprovals, 60000);
})();
