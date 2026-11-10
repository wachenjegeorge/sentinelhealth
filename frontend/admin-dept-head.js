(function() {
  const session = Auth.requireRole("department_head");
  if (!session) return;
  const $ = id => document.getElementById(id);

  const colorFor = s => s >= 65 ? "#e11d48" : s >= 35 ? "#d97706" : "#059669";

  let currentData = null;

  async function load() {
    try {
      const res = await Auth.apiFetch("/api/bff/dept-head/overview");
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();
      currentData = d;

      $("headerSub").textContent = d.department + " • " + d.facility_id.replace(/-/g, " ").toUpperCase();

      // KPIs
      Anim.countUp($("kpi-wvi"), Math.round(d.pooled_wvi));
      $("kpi-wvi").style.color = colorFor(d.pooled_wvi);
      Anim.countUp($("kpi-pending"), d.pending_count);
      const today = new Date().toISOString().split("T")[0];
      let reportsToday = 0, confirmedToday = 0;
      (d.groups || []).forEach(g => { if ((g.day || "").startsWith(today)) reportsToday += g.n; });
      (d.confirmation_queue || []).forEach(q => {
        if (q.status === "confirmed" && (q.created_at || "").startsWith(today)) confirmedToday++;
      });
      Anim.countUp($("kpi-reports"), reportsToday);
      Anim.countUp($("kpi-confirmed"), confirmedToday);

      // Queue
      const pending = (d.confirmation_queue || []).filter(q => q.status === "pending");
      $("queue-count").textContent = pending.length + " awaiting review";
      if (pending.length === 0) {
        $("queue").innerHTML = '<div class="p-4 text-center text-sm text-slate-500">No pending confirmations. Your team is stable.</div>';
      } else {
        $("queue").innerHTML = pending.map(q => {
          const verdictColor = q.ai_verdict === "likely_real" ? "emerald" : q.ai_verdict === "outlier" ? "rose" : "slate";
          const verdictLabel = q.ai_verdict ? q.ai_verdict.replace("_", " ").toUpperCase() : "NOT YET ANALYZED";
          return `
            <div class="p-3 bg-slate-800/60 border border-slate-700 rounded-lg" id="qc-${q.id}">
              <div class="flex justify-between items-start mb-2">
                <div>
                  <p class="text-sm font-medium text-slate-200">${q.worker_display_name || q.worker_username}</p>
                  <p class="text-[10px] text-slate-500">Shift: ${q.shift} • ${new Date(q.created_at).toLocaleTimeString()}</p>
                </div>
                <div class="text-right">
                  <p class="text-xs font-bold text-rose-400">Fatigue ${q.fatigue}/10</p>
                  <p class="text-[10px] text-amber-400">Heat ${q.heat_exposure}/10</p>
                </div>
              </div>
              ${q.ai_verdict ? `
                <div class="mb-2 p-2 bg-${verdictColor}-950/30 border border-${verdictColor}-900/40 rounded">
                  <p class="text-[10px] font-bold text-${verdictColor}-400">AI: ${verdictLabel}</p>
                  <p class="text-xs text-slate-400">${q.ai_reasoning || ""}</p>
                </div>
              ` : ""}
              <div class="flex gap-2">
                <button onclick="confirmReport('${q.id}', 'confirm')" class="flex-1 rounded bg-emerald-600 hover:bg-emerald-500 py-1.5 text-xs font-bold">Confirm</button>
                <button onclick="confirmReport('${q.id}', 'deny')" class="flex-1 rounded bg-slate-700 hover:bg-slate-600 py-1.5 text-xs font-bold">Deny</button>
                <button onclick="scheduleOneOnOne('${q.id}')" class="rounded bg-indigo-600 hover:bg-indigo-500 px-2 py-1.5 text-xs font-bold">1-on-1</button>
              </div>
            </div>
          `;
        }).join("");
        Anim.stagger($("queue"));
      }

      // Trend
      const trend = d.trend || [];
      if (trend.length === 0) {
        $("trend").innerHTML = '<p class="text-sm text-slate-500">No trend data.</p>';
      } else {
        const maxWvi = Math.max(...trend.map(t => t.wvi), 100);
        $("trend").innerHTML = trend.map(t => {
          const h = (t.wvi / maxWvi) * 100;
          const c = t.wvi >= 65 ? "bg-rose-500" : t.wvi >= 35 ? "bg-amber-500" : "bg-emerald-500";
          return `<div class="flex-1 flex flex-col items-center justify-end h-full group relative min-w-[4px]">
            <div class="absolute -top-8 bg-slate-800 text-[10px] px-2 py-1 rounded opacity-0 group-hover:opacity-100 whitespace-nowrap z-10 pointer-events-none">${t.day}: ${t.wvi}</div>
            <div class="w-full ${c} rounded-t-sm" style="height:${h}%"></div>
          </div>`;
        }).join("");
      }

      // AI insights - generate a quick summary
      fetchAiSummary(d);
    } catch (e) {
      console.error("Load failed", e);
      UI.toast("Failed to load department data", "error");
    }
  }

  async function fetchAiSummary(d) {
    try {
      const res = await Auth.apiFetch("/api/bff/assistant/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": "deptai-" + (crypto.randomUUID ? crypto.randomUUID() : (Date.now() + "-" + Math.random().toString(36).slice(2))) },
        body: JSON.stringify({ question: `Summarize the health of my ${d.department} department in 2 sentences and give me one action.` })
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      $("ai-insights").innerHTML = (data.answer || "").replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>").replace(/\n/g, "<br>");
    } catch (e) {
      $("ai-insights").innerHTML = "<span class='text-slate-400'>Review the queue below. Confirm the likely-real reports, deny the outliers.</span>";
    }
  }

  window.analyzeQueue = async () => {
    const btn = $("analyzeBtn");
    btn.disabled = true;
    btn.textContent = "Analyzing...";
    try {
      const res = await Auth.apiFetch("/api/bff/dept-head/analyze-queue", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID ? crypto.randomUUID() : (Date.now() + "-" + Math.random().toString(36).slice(2)) }
      });
      if (res.ok) {
        const d = await res.json();
        UI.toast("AI triage complete: " + d.analyzed + " reports analyzed");
      
  async function loadAlerts() {
    try {
      const res = await Auth.apiFetch("/api/bff/dept-head/alerts");
      if (!res.ok) return;
      const d = await res.json();
      const alerts = d.alerts || [];
      if ($("alert-count")) $("alert-count").textContent = alerts.length + " active";
      const list = $("alert-list");
      if (!list) return;
      if (alerts.length === 0) {
        list.innerHTML = '<p class="text-sm text-slate-500 text-center py-4">No active anomalies.</p>';
        return;
      }
      list.innerHTML = alerts.map(a => {
        const sev = a.severity === "critical" ? "rose" : "amber";
        const badge = a.status === "escalated"
          ? '<span class="text-[10px] bg-purple-500/20 text-purple-300 px-2 py-0.5 rounded">Escalated</span>'
          : a.status === "acknowledged"
            ? '<span class="text-[10px] bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded">Acknowledged</span>'
            : '<span class="text-[10px] bg-rose-500/20 text-rose-300 px-2 py-0.5 rounded animate-pulse">Active</span>';
        return `
          <div class="p-3 bg-slate-800/60 border border-slate-700 rounded-lg">
            <div class="flex justify-between items-start mb-1">
              <div>
                <p class="text-xs font-bold text-${sev}-400 uppercase tracking-widest">${(a.alert_type||"").replace("_"," ")}</p>
                <p class="text-sm font-medium text-slate-200">${a.department} (${a.shift})</p>
              </div>
              ${badge}
            </div>
            <p class="text-xs text-slate-400 mb-2">${a.ai_protocol || ""}</p>
            ${a.status === "active" ? `
              <div class="flex gap-2">
                <button onclick="triageAlert('${a.id}','acknowledge')" class="flex-1 rounded bg-amber-600 hover:bg-amber-500 py-1.5 text-xs font-bold">Acknowledge</button>
                <button onclick="triageAlert('${a.id}','false_positive')" class="rounded bg-slate-700 hover:bg-slate-600 px-2 py-1.5 text-xs font-bold">Dismiss</button>
                <button onclick="triageAlert('${a.id}','escalate')" class="rounded bg-purple-600 hover:bg-purple-500 px-2 py-1.5 text-xs font-bold">Escalate</button>
              </div>` : ""}
          </div>`;
      }).join("");
    } catch (e) { console.error("alerts:", e); }
  }

  load();
      }
    } catch (e) {
      UI.toast("Analysis failed", "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Analyze Queue";
    }
  };

  window.confirmReport = async (id, action) => {
    const notes = action === "deny" ? prompt("Reason for denial (optional):") : null;
    try {
      const res = await Auth.apiFetch(`/api/bff/dept-head/confirm/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID ? crypto.randomUUID() : (Date.now() + "-" + Math.random().toString(36).slice(2)) },
        body: JSON.stringify({ action, notes })
      });
      if (res.ok) {
        UI.toast(action === "confirm" ? "Report confirmed — escalated to Hospital Head" : "Report marked as invalid");
        const card = document.getElementById("qc-" + id);
        if (card) { card.style.opacity = "0"; card.style.transform = "translateX(20px)"; setTimeout(() => card.remove(), 300); }
        setTimeout(load, 400);
      }
    } catch (e) {
      UI.toast("Failed", "error");
    }
  };

  window.scheduleOneOnOne = async (id) => {
    try {
      await Auth.apiFetch(`/api/bff/dept-head/checkin/${id}`, {
        method: "POST", headers: { "Idempotency-Key": crypto.randomUUID ? crypto.randomUUID() : (Date.now() + "-" + Math.random().toString(36).slice(2)) }
      });
      UI.toast("1-on-1 scheduled");
    } catch (e) {
      UI.toast("Failed", "error");
    }
  };

  load();
  loadAlerts();
  setInterval(load, 30000);
  setInterval(loadAlerts, 30000);

  window.triageAlert = async function(id, action) {
    let payload = { action };
    if (action === "false_positive") {
      const reason = prompt("Reason for false positive?");
      if (!reason) return;
      payload.reason = reason;
    }
    if (action === "escalate") {
      payload.notes = prompt("Escalation notes:") || "Escalated to hospital head";
    }
    const key = crypto.randomUUID ? crypto.randomUUID() : (Date.now()+"-"+Math.random());
    try {
      const res = await Auth.apiFetch(`/api/bff/dept-head/alerts/${id}/triage`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": key },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        UI.toast(action === "escalate" ? "Escalated" : action === "false_positive" ? "Dismissed" : "Acknowledged");
        loadAlerts();
      } else { UI.toast("Triage failed", "error"); }
    } catch (e) { UI.toast("Network error", "error"); }
  };



  window.generateDeepReport = async function() {
  const btn = document.getElementById("gen-deep-report");
  const body = document.getElementById("deep-report-body");
  if (!btn || !body) return;
  btn.disabled = true;
  btn.textContent = "Analyzing...";
  body.classList.remove("hidden");
  body.innerHTML = '<div class="flex items-center gap-2 text-fuchsia-400"><span>Analyzing department data... 15-20 seconds.</span></div>';
  const key = (crypto.randomUUID ? crypto.randomUUID() : (Date.now() + "-" + Math.random()));
  try {
    const res = await Auth.apiFetch("/api/bff/dept-head/report", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": key },
      body: JSON.stringify({}),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const d = await res.json();
    const report = String(d.report || "No report generated");
    const html = renderMd(report);
    const m = d.metrics || {};
    const info = m.total_reports != null ? (m.total_reports + " reports, WVI " + m.avg_wvi) : "";
    const header = '<div class="flex justify-between items-center mb-3 pb-2 border-b border-slate-800"><span class="text-xs text-fuchsia-400 font-mono">ENGINE: ' + String(d.engine || "?").toUpperCase() + '</span><span class="text-[10px] text-slate-500">' + info + '</span></div>';
    body.innerHTML = header + '<div class="text-sm text-slate-300 leading-relaxed">' + html + '</div>';
  } catch (e) {
    body.innerHTML = '<p class="text-rose-400">Report failed: ' + (e && e.message ? e.message : "unknown") + '</p>';
  } finally {
    btn.disabled = false;
    btn.textContent = "Regenerate";
  }
};

function escHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function inlineMd(s) {
  let x = escHtml(s);
  x = x.replace(/\*\*(.+?)\*\*/g, '<strong class="text-white">$1</strong>');
  x = x.replace(/`([^`]+)`/g, '<code class="bg-slate-800 px-1 rounded text-cyan-300">$1</code>');
  return x;
}

function renderMd(md) {
  const lines = md.split("\n");
  const out = [];
  let inList = false;
  for (let i = 0; i < lines.length; i++) {
    const t = lines[i].trim();
    if (t.startsWith("### ")) {
      if (inList) { out.push("</ul>"); inList = false; }
      out.push('<h3 class="text-sm font-semibold text-slate-100 mt-3 mb-1">' + inlineMd(t.slice(4)) + '</h3>');
    } else if (t.startsWith("## ")) {
      if (inList) { out.push("</ul>"); inList = false; }
      out.push('<h2 class="text-base font-bold text-white mt-4 mb-2">' + inlineMd(t.slice(3)) + '</h2>');
    } else if (/^[-\u2022]\s+/.test(t)) {
      if (!inList) { out.push('<ul class="list-disc ml-5 my-2">'); inList = true; }
      out.push('<li class="mb-1">' + inlineMd(t.replace(/^[-\u2022]\s+/, "")) + '</li>');
    } else if (/^\d+\.\s+/.test(t)) {
      if (!inList) { out.push('<ul class="list-disc ml-5 my-2">'); inList = true; }
      out.push('<li class="mb-1">' + inlineMd(t.replace(/^\d+\.\s+/, "")) + '</li>');
    } else if (t === "") {
      if (inList) { out.push("</ul>"); inList = false; }
    } else {
      if (inList) { out.push("</ul>"); inList = false; }
      out.push('<p class="mb-2">' + inlineMd(t) + '</p>');
    }
  }
  if (inList) out.push("</ul>");
  return out.join("");
}

})();
