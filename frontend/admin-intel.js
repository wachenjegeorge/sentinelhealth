(function() {
  const session = Auth.requireRole(["admin", "county_officer", "health_officer"]);
  if (!session) return;
  const $ = id => document.getElementById(id);

  // Extract county from URL: /admin/intel/Mombasa
  const pathParts = window.location.pathname.split("/");
  const COUNTY = decodeURIComponent(pathParts[pathParts.length - 1] || "");

  if (!COUNTY || COUNTY === "intel") {
    window.location.href = "/admin";
    return;
  }

  $("countyTitle").textContent = COUNTY + " County";
  $("countySub").textContent = "Intelligence Center • " + (session.role === "admin" ? "National Admin Access" : "County Officer Access");

  let facilitiesData = [];
  let trendData = [];
  let anomalyData = [];
  let sortField = "wvi";
  let sortDir = "desc";

  // ── Helpers ─────────────────────────────────────────────
  const colorFor = s => s >= 65 ? "#e11d48" : s >= 35 ? "#d97706" : "#059669";
  const setText = (id, t) => { const e = $(id); if (e) e.textContent = t; };
  const setHtml = (id, h) => { const e = $(id); if (e) e.innerHTML = h; };

  function fmtDate(iso) {
    try { return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); }
    catch (e) { return iso; }
  }

  // ── Tabs ────────────────────────────────────────────────
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll("section[id^='tab-']").forEach(s => s.classList.add("hidden"));
      btn.classList.add("active");
      const tab = btn.getAttribute("data-tab");
      $(`tab-${tab}`).classList.remove("hidden");

      if (tab === "facilities") renderFacilities();
      if (tab === "trends") renderTrends();
    });
  });

  // ── Load summary ────────────────────────────────────────
  async function loadSummary() {
    try {
      const res = await Auth.apiFetch(`/api/bff/admin/intel/county/${encodeURIComponent(COUNTY)}/summary`);
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();

      setText("kpi-wvi", d.pooled_wvi || 0);
      const lvlEl = $("kpi-level");
      lvlEl.textContent = d.pooled_level || "--";
      lvlEl.style.color = colorFor(d.pooled_wvi || 0);

      setText("kpi-facs", d.facility_count || 0);
      setText("kpi-facs-sub", `${d.facility_with_data || 0} with active data`);
      setText("kpi-reports", d.total_reports || 0);
      setText("kpi-crit", d.critical_facilities || 0);
      setText("kpi-alerts", d.active_alerts || 0);

      // Risk distribution
      const distEl = $("riskDistribution");
      if (distEl) {
        const crit = d.critical_facilities || 0;
        const mod = d.moderate_facilities || 0;
        const low = (d.facility_with_data || 0) - crit - mod;
        const total = Math.max(1, d.facility_with_data || 1);
        distEl.innerHTML = `
          <div class="space-y-3">
            <div>
              <div class="flex justify-between text-xs mb-1">
                <span class="text-rose-400 font-medium">Critical (≥65)</span>
                <span class="font-bold">${crit}</span>
              </div>
              <div class="h-2 bg-slate-800 rounded-full overflow-hidden">
                <div class="h-full bg-rose-500" style="width: ${(crit/total)*100}%"></div>
              </div>
            </div>
            <div>
              <div class="flex justify-between text-xs mb-1">
                <span class="text-amber-400 font-medium">Moderate (35–64)</span>
                <span class="font-bold">${mod}</span>
              </div>
              <div class="h-2 bg-slate-800 rounded-full overflow-hidden">
                <div class="h-full bg-amber-500" style="width: ${(mod/total)*100}%"></div>
              </div>
            </div>
            <div>
              <div class="flex justify-between text-xs mb-1">
                <span class="text-emerald-400 font-medium">Low (&lt;35)</span>
                <span class="font-bold">${low < 0 ? 0 : low}</span>
              </div>
              <div class="h-2 bg-slate-800 rounded-full overflow-hidden">
                <div class="h-full bg-emerald-500" style="width: ${Math.max(0, low/total)*100}%"></div>
              </div>
            </div>
          </div>
        `;
      }

      // Alerts
      const alertEl = $("alertList");
      if (alertEl) {
        if (!d.alerts || d.alerts.length === 0) {
          alertEl.innerHTML = '<p class="text-sm text-slate-500">No active alerts in this county.</p>';
        } else {
          alertEl.innerHTML = d.alerts.map(a => `
            <div class="p-3 bg-slate-800/50 rounded border-l-2 border-l-rose-500">
              <p class="text-xs font-bold text-rose-400 uppercase tracking-widest">${a.alert_type.replace("_", " ")}</p>
              <p class="text-sm font-medium text-slate-200">${a.department} (${a.shift})</p>
              <p class="text-xs text-slate-400 mt-1">${a.ai_protocol || ""}</p>
              <p class="text-[10px] text-slate-600 mt-2">${fmtDate(a.created_at)}</p>
            </div>
          `).join("");
        }
      }
    } catch (e) {
      console.error("Summary load failed", e);
      if (typeof UI !== "undefined") UI.toast("Failed to load summary", "error");
    }
  }

  // ── Load facilities ─────────────────────────────────────
  async function loadFacilities() {
    try {
      const res = await Auth.apiFetch(`/api/bff/admin/intel/county/${encodeURIComponent(COUNTY)}/facilities`);
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();
      facilitiesData = d.facilities || [];
      renderFacilities();
    } catch (e) {
      console.error("Facilities load failed", e);
    }
  }

  function renderFacilities() {
    const body = $("facBody");
    if (!body) return;
    const q = ($("facSearch") ? $("facSearch").value : "").toLowerCase();

    let rows = facilitiesData.filter(f => !q || f.name.toLowerCase().includes(q));
    rows.sort((a, b) => {
      const av = a[sortField] != null ? a[sortField] : -999;
      const bv = b[sortField] != null ? b[sortField] : -999;
      if (typeof av === "string") return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      return sortDir === "asc" ? av - bv : bv - av;
    });

    body.innerHTML = rows.map(f => {
      const wvi = f.wvi;
      const color = wvi ? colorFor(wvi) : "#64748b";
      const sup = f.suppressed;
      return `
        <tr class="border-b border-slate-800/60 hover:bg-slate-800/30">
          <td class="py-2 px-2">
            <div class="font-medium text-slate-200">${f.name}</div>
            <div class="text-[10px] text-slate-500">${f.facility_type || ""} ${f.sub_county ? "• " + f.sub_county : ""}</div>
          </td>
          <td class="py-2 px-2 text-slate-400">L${f.keph_level}</td>
          <td class="py-2 px-2 text-right text-slate-300">${f.reports}</td>
          <td class="py-2 px-2 text-right">${f.avg_fatigue != null ? f.avg_fatigue.toFixed(1) : "—"}</td>
          <td class="py-2 px-2 text-right">${f.avg_heat != null ? f.avg_heat.toFixed(1) : "—"}</td>
          <td class="py-2 px-2 text-right">${f.critical_share != null ? (f.critical_share * 100).toFixed(0) + "%" : "—"}</td>
          <td class="py-2 px-2 text-right">
            <span class="font-bold" style="color:${color}">${sup ? "Suppressed" : wvi}</span>
          </td>
          <td class="py-2 px-2 text-right">
            ${sup ? "" : `<button onclick="openFacilityDetail('${f.facility_id}','${f.name.replace(/'/g, "\\'")}')" class="text-xs text-cyan-400 hover:text-cyan-300 underline">View</button>`}
          </td>
        </tr>
      `;
    }).join("");

    if (rows.length === 0) {
      body.innerHTML = '<tr><td colspan="8" class="py-8 text-center text-slate-500 text-sm">No facilities match.</td></tr>';
    }
  }

  // Sort handlers
  document.querySelectorAll("th[data-sort]").forEach(th => {
    th.addEventListener("click", () => {
      const field = th.getAttribute("data-sort");
      if (sortField === field) {
        sortDir = sortDir === "asc" ? "desc" : "asc";
      } else {
        sortField = field;
        sortDir = "desc";
      }
      renderFacilities();
    });
  });
  if ($("facSearch")) $("facSearch").addEventListener("input", renderFacilities);

  // ── Facility detail modal ──────────────────────────────
  window.openFacilityDetail = async (facilityId, facilityName) => {
    const modal = document.createElement("div");
    modal.className = "fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4";
    modal.innerHTML = `
      <div class="bg-slate-900 border border-slate-700 rounded-xl max-w-2xl w-full max-h-[85vh] overflow-y-auto">
        <div class="px-5 py-4 border-b border-slate-700 flex justify-between items-center sticky top-0 bg-slate-900">
          <div>
            <p class="text-xs uppercase tracking-widest text-cyan-400">Facility Detail</p>
            <h3 class="text-lg font-bold text-white">${facilityName}</h3>
          </div>
          <button class="text-slate-400 hover:text-white text-xl" onclick="this.closest('.fixed').remove()">✕</button>
        </div>
        <div class="p-5 space-y-3" id="facDetailBody">
          <div class="flex items-center gap-2 text-slate-400 text-sm"><div class="spinner"></div> Loading department breakdown...</div>
        </div>
      </div>
    `;
    document.body.appendChild(modal);

    try {
      const res = await Auth.apiFetch(`/api/bff/admin/intel/facility/${facilityId}/departments`);
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();
      const body = modal.querySelector("#facDetailBody");

      if (!d.departments || d.departments.length === 0) {
        body.innerHTML = '<p class="text-slate-500 text-sm">No department data clears the k≥5 threshold for this facility yet.</p>';
        return;
      }

      body.innerHTML = d.departments.map(dept => `
        <div class="card p-3">
          <div class="flex justify-between items-start mb-2">
            <div>
              <p class="font-semibold text-slate-200">${dept.department}</p>
              <p class="text-[10px] text-slate-500">${dept.reports} reports • fatigue ${dept.avg_fatigue} • heat ${dept.avg_heat}</p>
            </div>
            <div class="text-right">
              <p class="text-xl font-bold" style="color:${colorFor(dept.wvi)}">${dept.wvi}</p>
              <p class="text-[9px] uppercase tracking-wider text-slate-500">${dept.level}</p>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-2">
            ${dept.shifts.map(s => `
              <div class="bg-slate-800 rounded p-2 text-xs">
                <div class="flex justify-between">
                  <span class="text-slate-400">${s.shift}</span>
                  <span class="font-bold" style="color:${colorFor(s.wvi)}">${s.wvi}</span>
                </div>
                <div class="text-[10px] text-slate-600">${s.reports} reports</div>
              </div>
            `).join("")}
          </div>
        </div>
      `).join("");
    } catch (e) {
      modal.querySelector("#facDetailBody").innerHTML = '<p class="text-rose-400 text-sm">Failed to load department data.</p>';
    }
  };

  // ── Load trends ─────────────────────────────────────────
  async function loadTrends() {
    try {
      const res = await Auth.apiFetch(`/api/bff/admin/intel/county/${encodeURIComponent(COUNTY)}/trends`);
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();
      trendData = d.trend || [];
      anomalyData = d.anomalies || [];

      const dirEl = $("trendDirection");
      if (dirEl) {
        const map = {
          improving: { text: "↓ Improving", cls: "text-emerald-400" },
          worsening: { text: "↑ Worsening", cls: "text-rose-400" },
          stable: { text: "→ Stable", cls: "text-slate-400" },
          insufficient_data: { text: "Insufficient data", cls: "text-slate-500" },
        };
        const m = map[d.direction] || map.stable;
        dirEl.textContent = m.text;
        dirEl.className = "text-xs font-medium " + m.cls;
      }

      renderTrends();
    } catch (e) {
      console.error("Trends load failed", e);
    }
  }

  function renderTrends() {
    const chart = $("trendChart");
    if (!chart || trendData.length === 0) {
      if (chart) chart.innerHTML = '<p class="text-slate-500 text-sm">No trend data available.</p>';
      return;
    }

    const maxWvi = Math.max(...trendData.map(t => t.wvi), 100);
    chart.innerHTML = trendData.map(t => {
      const heightPct = (t.wvi / maxWvi) * 100;
      const color = t.wvi >= 65 ? "bg-rose-500" : t.wvi >= 35 ? "bg-amber-500" : "bg-emerald-500";
      return `
        <div class="flex-1 flex flex-col items-center justify-end h-full group relative min-w-[6px]">
          <div class="absolute -top-8 bg-slate-800 border border-slate-700 text-[10px] px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10 pointer-events-none">
            ${t.day}: WVI ${t.wvi}
          </div>
          <div class="w-full ${color} rounded-t-sm transition-all hover:brightness-125" style="height: ${heightPct}%"></div>
        </div>
      `;
    }).join("");

    const history = $("anomalyHistory");
    if (history) {
      if (anomalyData.length === 0) {
        history.innerHTML = '<p class="text-sm text-slate-500">No anomalies recorded in this county.</p>';
      } else {
        history.innerHTML = anomalyData.map(a => {
          const isResolved = a.status === "resolved";
          const cls = isResolved ? "border-l-emerald-500" : "border-l-rose-500";
          const badge = isResolved
            ? '<span class="text-[10px] bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded">Resolved</span>'
            : '<span class="text-[10px] bg-rose-500/20 text-rose-400 px-2 py-0.5 rounded animate-pulse">Active</span>';
          return `
            <div class="p-3 bg-slate-800/50 rounded border-l-2 ${cls}">
              <div class="flex justify-between items-start mb-1">
                <p class="text-sm font-medium text-slate-200">${a.department} (${a.shift})</p>
                ${badge}
              </div>
              <p class="text-xs text-slate-400">${a.ai_protocol || ""}</p>
              <p class="text-[10px] text-slate-600 mt-1">${fmtDate(a.created_at)}</p>
            </div>
          `;
        }).join("");
      }
    }
  }

  // ── Generate AI report ─────────────────────────────────
  window.generateAIReport = async () => {
    const btn = $("genBtn");
    const body = $("reportBody");
    const engineEl = $("reportEngine");

    // Switch to report tab
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll("section[id^='tab-']").forEach(s => s.classList.add("hidden"));
    document.querySelector('[data-tab="report"]').classList.add("active");
    $("tab-report").classList.remove("hidden");

    btn.disabled = true;
    btn.textContent = "Generating...";
    body.innerHTML = `
      <div class="flex items-center gap-2 text-fuchsia-400">
        <div class="spinner"></div>
        <span>Analyzing facility data, trends, and anomalies... This may take 10–20 seconds.</span>
      </div>
    `;
    engineEl.textContent = "GENERATING";

    try {
      const res = await Auth.apiFetch(`/api/bff/admin/intel/county/${encodeURIComponent(COUNTY)}/report`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": Date.now().toString() }
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();

      // Render markdown
      let html = (d.report || "No report generated.")
        .replace(/^## (.*?)$/gm, '<h2>$1</h2>')
        .replace(/^### (.*?)$/gm, '<h3>$1</h3>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/^- (.*?)$/gm, '<li>$1</li>')
        .replace(/^(\d+)\. (.*?)$/gm, '<li>$2</li>')
        .replace(/(<li>.*?<\/li>)(?!\s*<li>)/gs, '<ul>$1</ul>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>');

      body.innerHTML = '<p>' + html + '</p>';
      engineEl.textContent = "ENGINE: " + (d.engine || "unknown").toUpperCase();
      if (typeof UI !== "undefined") UI.toast("Report generated successfully");
    } catch (e) {
      body.innerHTML = `<p class="text-rose-400">Report generation failed: ${e.message}</p>`;
      engineEl.textContent = "FAILED";
    } finally {
      btn.disabled = false;
      btn.textContent = "🧠 Generate AI Report";
    }
  };

  // ── Export ──────────────────────────────────────────────
  window.exportCountyCSV = async () => {
    try {
      const res = await Auth.apiFetch("/api/bff/admin/export");
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${COUNTY}_sentinel_export.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      if (typeof UI !== "undefined") UI.toast("Export failed", "error");
    }
  };

  // ── Init ────────────────────────────────────────────────
  loadSummary();
  loadFacilities();
  loadTrends();
  setInterval(loadSummary, 60000);
})();
