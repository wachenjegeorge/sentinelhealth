(function() {
  const session = Auth.requireRole("worker");
  if (!session) return;
  const $ = id => document.getElementById(id);
  const selectedSymptoms = new Set();
  let kephDepartments = [];

  $("userLabel").textContent = session.username || "Worker";
  $("facilityLabel").textContent = session.facility_id.replace(/-/g, " ").toUpperCase();

  // Tabs
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('section[id^="tab-"]').forEach(s => s.classList.add('hidden'));
      e.target.classList.add('active');
      $(e.target.getAttribute('data-target')).classList.remove('hidden');
    });
  });

  // Load KEPH Departments
  async function loadDepartments() {
    try {
      const res = await Auth.apiFetch("/api/bff/worker/departments");
      if (res.ok) kephDepartments = (await res.json()).departments;
      else kephDepartments = ["Outpatient (OPD)", "Maternity", "Emergency Department"];
    } catch (e) {
      kephDepartments = ["Outpatient (OPD)", "Maternity", "Emergency Department"];
    }
    $("department").innerHTML = kephDepartments.map(d => `<option>${d}</option>`).join("");
  }

  // Sliders
  ["fatigue","heat","hours","cfatigue","clarity","stress","sleepq","sleeph"].forEach(id => {
    const input = $(id), val = $(id + "Val");
    input.oninput = () => val.textContent = input.value;
  });

  // Symptoms
  const SYMPTOMS = [["headache","Headache"],["dizziness","Dizziness"],["nausea","Nausea"],["cough","Cough"],["sore_throat","Sore Throat"],["shortness_of_breath","Shortness of Breath"],["muscle_strain","Muscle Strain"],["eye_irritation","Eye Irritation"]];
  $("symptoms").innerHTML = SYMPTOMS.map(p => `<button type="button" class="chip" data-sym="${p[0]}">${p[1]}</button>`).join("");
  document.querySelectorAll("#symptoms .chip").forEach(ch => {
    ch.onclick = () => {
      const k = ch.dataset.sym;
      if (selectedSymptoms.has(k)) { selectedSymptoms.delete(k); ch.dataset.active = "false"; }
      else { selectedSymptoms.add(k); ch.dataset.active = "true"; }
    };
  });

  // Submit Check-in
  $("form").onsubmit = async (e) => {
    e.preventDefault();
    const btn = $("submit");
    btn.disabled = true; btn.textContent = "Submitting...";
    const payload = {
      department: $("department").value, shift: $("shift").value,
      fatigue: Number($("fatigue").value), heat_exposure: Number($("heat").value),
      hours_worked: Number($("hours").value), symptoms: Array.from(selectedSymptoms),
      cognitive_fatigue: Number($("cfatigue")?.value ?? 5),
      mental_clarity: Number($("clarity")?.value ?? 5),
      stress: Number($("stress")?.value ?? 5),
      sleep_quality: Number($("sleepq")?.value ?? 3),
      sleep_hours: Number($("sleeph")?.value ?? 7),
    };
    try {
      const res = await Auth.apiFetch("/api/bff/sync/checkins", {
        method: "POST", headers: { "Idempotency-Key": crypto.randomUUID ? crypto.randomUUID() : (Date.now() + "-" + Math.random().toString(36).slice(2)), "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error("API error");
      const data = await res.json();
      
      const color = data.level === "Critical" ? "#f43f5e" : data.level === "Moderate" ? "#f59e0b" : "#10b981";
      $("result").className = "mb-5 block card p-5 border-2";
      $("result").style.borderColor = color;
      $("result").innerHTML = `<h3 class="text-lg font-bold" style="color:${color}">Check-in Recorded: ${data.level} Risk</h3><p class="text-sm text-slate-400 mt-1">WVI Score: ${Math.round(data.personal_score ?? data.score ?? data.wvi ?? 0)}</p>`;
      
      fetchCoach();
      loadCognitiveBaseline();
      loadDashboard();
      if (window._onCheckinSuccess) window._onCheckinSuccess();
      selectedSymptoms.clear();
      document.querySelectorAll("#symptoms .chip").forEach(c => c.dataset.active = "false");
    } catch (err) {
      UI.toast("Failed to submit. Check connection.", "error");
    } finally {
      btn.disabled = false; btn.textContent = "Submit Check-In";
    }
  };

  // AI Coach & Early Warning
  async function fetchCoach() {
    const msgEl = $("coach-msg");
    const sigEl = $("coach-signals");
    const actEl = $("coach-action");
    const warningEl = $("early-warning");
    const warningText = $("early-warning-text");
    try {
      const res = await Auth.apiFetch("/api/bff/worker/coach");
      if (res.ok) {
        const data = await res.json();
        const narrative = data.narrative || data.message || "";
        msgEl.innerHTML = narrative.replace(/\n/g, '<br>');
        msgEl.classList.remove("animate-pulse");

        if (sigEl) {
          const signals = data.signals || [];
          sigEl.innerHTML = signals.map(s => {
            const sev = s.severity === "high"
              ? "border-rose-500/60 text-rose-300"
              : "border-amber-500/50 text-amber-300";
            return `<span class="px-2 py-1 rounded-full border ${sev} text-[10px] font-medium">${s.label}: ${s.delta}</span>`;
          }).join("");
        }

        if (actEl && data.action) {
          actEl.classList.remove("hidden");
          actEl.innerHTML = "💡 " + data.action;
        }

        if (data.is_warning) {
          warningEl.classList.remove("hidden");
          warningText.textContent = narrative;
        } else {
          warningEl.classList.add("hidden");
        }
      }
    } catch (e) {
      msgEl.textContent = "Stay hydrated and monitor your fatigue today.";
      msgEl.classList.remove("animate-pulse");
    }
  }

  async function loadCognitiveBaseline() {
    const card = $("cog-baseline");
    const body = $("cog-baseline-body");
    const meta = $("cog-baseline-meta");
    if (!card || !body) return;
    try {
      const res = await Auth.apiFetch("/api/bff/cognitive/baseline");
      if (!res.ok) return;
      const d = await res.json();
      card.classList.remove("hidden");
      if (!d.ready) {
        meta.textContent = d.sample_count + "/" + d.min_samples + " samples";
        body.innerHTML = '<p class="text-slate-500">Complete ' + (d.min_samples - d.sample_count) + ' more cognitive check-ins to unlock baseline deltas.</p>';
        return;
      }
      meta.textContent = d.sample_count + " samples · " + d.window_days + "d window";
      const deltas = d.deltas || {};
      const rows = [
        ["Mental fatigue", "cognitive_fatigue", "pts", true],
        ["Mental clarity", "mental_clarity", "pts", false],
        ["Stress", "stress", "pts", true],
        ["Sleep quality", "sleep_quality", "pts", false],
        ["Sleep hours", "sleep_hours", "h", true],
        ["CWI", "cwi", "", true],
      ];
      body.innerHTML = rows.filter(r => deltas[r[1]] !== undefined).map(([label, key, unit, worseUp]) => {
        const v = deltas[key];
        const isBad = worseUp ? v > 0 : v < 0;
        const color = Math.abs(v) < 0.5 ? "text-slate-400" : (isBad ? "text-rose-400" : "text-emerald-400");
        const arrow = v > 0 ? "↑" : v < 0 ? "↓" : "→";
        return '<div class="flex justify-between py-0.5"><span>' + label + '</span><span class="' + color + ' font-mono">' + arrow + ' ' + (v > 0 ? "+" : "") + v + unit + '</span></div>';
      }).join("") || '<p class="text-slate-500">No deltas to show yet.</p>';
    } catch (e) {
      console.error("baseline load failed", e);
    }
  }

  // Sync Wearable
  window.syncDevice = async () => {
    const btn = $("sync-btn");
    btn.textContent = "Syncing..."; btn.disabled = true;
    try {
      const res = await Auth.apiFetch("/api/bff/worker/wearable/sync", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID ? crypto.randomUUID() : (Date.now() + "-" + Math.random().toString(36).slice(2)) } });
      if (res.ok) {
        const d = await res.json();
        $("w-steps").textContent = d.steps.toLocaleString();
        $("w-sleep").textContent = d.sleep + "h";
        $("w-kcal").textContent = d.calories;
        $("sync-status").textContent = "Synced just now";
        UI.toast("Device synced!");
        fetchCoach(); // Recalculate warnings
      }
    } catch (e) {
      UI.toast("Sync failed", "error");
    } finally {
      btn.textContent = "Sync Device"; btn.disabled = false;
    }
  };

  // Upload Roster
  window.uploadRoster = async () => {
    try {
      const res = await Auth.apiFetch("/api/bff/worker/wearable/schedule/upload", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID ? crypto.randomUUID() : (Date.now() + "-" + Math.random().toString(36).slice(2)) } });
      if (res.ok) {
        UI.toast("Roster uploaded successfully!");
        loadDashboard();
      }
    } catch (e) {
      UI.toast("Upload failed", "error");
    }
  };

  // Shift Request Logic
  window.openShiftModal = (scheduleId) => {
    $("req-shift-id").value = scheduleId;
    $("shift-request-modal").classList.remove("hidden");
    $("shift-request-modal").classList.add("flex");
  };

  window.closeShiftModal = () => {
    $("shift-request-modal").classList.add("hidden");
    $("shift-request-modal").classList.remove("flex");
  };

  window.submitShiftRequest = async () => {
    const payload = {
      schedule_id: $("req-shift-id").value,
      request_type: $("req-type").value,
      reason: $("req-reason").value
    };
    if (!payload.reason) return UI.toast("Please provide a reason.", "error");

    try {
      const res = await Auth.apiFetch("/api/bff/worker/shifts/request", {
        method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID ? crypto.randomUUID() : (Date.now() + "-" + Math.random().toString(36).slice(2)) },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        UI.toast("Request sent to Health Officer.");
        closeShiftModal();
        $("req-reason").value = "";
      } else {
        UI.toast("Failed to send request.", "error");
      }
    } catch (e) {
      UI.toast("Network error.", "error");
    }
  };

  // Load Dashboard
  async function loadDashboard() {
    try {
      const res = await Auth.apiFetch("/api/bff/worker/dashboard");
      if (!res.ok) return;
      const d = await res.json();

      if (d.schedules && d.schedules.length > 0) {
        $("scheduleList").innerHTML = d.schedules.map(s => {
          const start = new Date(s.start_time);
          const end = new Date(s.end_time);
          const isNight = s.shift_type === "night";
          return `
            <div class="flex items-center justify-between p-3 rounded-lg bg-slate-900/50 border border-slate-800">
              <div class="flex items-center gap-3">
                <div class="grid h-10 w-10 place-items-center rounded-lg ${isNight ? 'bg-indigo-900/50 text-indigo-300' : 'bg-amber-900/50 text-amber-300'}">${isNight ? '🌙' : '☀️'}</div>
                <div><p class="font-semibold text-sm">${s.department} (${s.shift_type})</p><p class="text-xs text-slate-500">${start.toLocaleDateString()} • ${start.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})} - ${end.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</p></div>
              </div>
              <button onclick="openShiftModal('${s.id}')" class="rounded bg-slate-800 border border-slate-700 px-3 py-1.5 text-[10px] font-semibold text-slate-300 hover:border-cyan-500 transition">Request Change</button>
            </div>`;
        }).join("");
      } else {
        $("scheduleList").innerHTML = '<p class="text-sm text-slate-500">No upcoming shifts scheduled.</p>';
      }

      if (d.checkins && d.checkins.length > 0) {
        $("checkinList").innerHTML = d.checkins.map(c => {
          const color = c.level === "Critical" ? "text-rose-400" : c.level === "Moderate" ? "text-amber-400" : "text-emerald-400";
          return `
            <div class="flex items-center justify-between p-3 rounded-lg bg-slate-900/50 border border-slate-800">
              <div><p class="text-sm font-semibold">${new Date(c.date).toLocaleDateString()}</p><p class="text-xs text-slate-500">${c.department} • Fatigue: ${c.fatigue}/10</p></div>
              <div class="text-right"><p class="text-lg font-black ${color}">${Math.round(c.score)}</p><p class="text-[10px] uppercase text-slate-500">${c.level}</p></div>
            </div>`;
        }).join("");
      }

      if (d.medical_history && d.medical_history.length > 0) {
        $("medList").innerHTML = d.medical_history.map(m => `
          <div class="p-3 rounded-lg bg-slate-900/50 border border-slate-800">
            <div class="flex justify-between items-start mb-1"><p class="font-semibold text-sm text-cyan-300">${m.type.replace('_', ' ').toUpperCase()}</p><p class="text-xs text-slate-500">${new Date(m.date).toLocaleDateString()}</p></div>
            <p class="text-sm text-slate-300">${m.description}</p>
            ${m.restricted ? '<p class="text-[10px] text-rose-400 mt-2">⚠️ Restricted Duty</p>' : ''}
          </div>`).join("");
      }
    } catch (err) {
      console.error(err);
    }
  }

  // Init
  loadDepartments();
  fetchCoach();
  loadCognitiveBaseline();
  loadDashboard();
  // ═══════════════════════════════════════════════════════════════
  // LIVE SYSTEM — pill, polling, AI intervention
  // ═══════════════════════════════════════════════════════════════
  let _liveTimer = null;
  let _liveVisible = true;
  let _lastCheckinCount = -1;
  let _currentIntervention = null;

  // Pause polling when tab hidden (battery)
  document.addEventListener("visibilitychange", () => {
    _liveVisible = !document.hidden;
    if (_liveVisible) startLivePolling();
  });

  function startLivePolling() {
    if (_liveTimer) clearInterval(_liveTimer);
    _liveTimer = setInterval(pollLive, 10000);
    pollLive(); // immediate first poll
  }

  async function pollLive() {
    if (!_liveVisible) return;
    try {
      const res = await Auth.apiFetch("/api/bff/cognitive/live");
      if (!res.ok) return;
      const d = await res.json();

      // Update live pill
      const pill = $("live-pill");
      const label = $("live-label");
      if (pill && label) {
        pill.classList.remove("hidden");
        pill.classList.add("flex");
        const ago = d.last_checkin_at
          ? Math.round((Date.now() - new Date(d.last_checkin_at).getTime()) / 1000)
          : null;
        let txt = "Live";
        if (ago !== null) {
          if (ago < 60) txt = "Live · just now";
          else if (ago < 3600) txt = "Live · " + Math.round(ago/60) + "m ago";
          else txt = "Live · " + Math.round(ago/3600) + "h ago";
        }
        if (d.pending_escalations > 0) {
          txt += " · " + d.pending_escalations + " pending review";
        }
        label.textContent = txt;
      }

      // Detect new check-in → refresh intervention
      if (_lastCheckinCount >= 0 && d.checkin_count > _lastCheckinCount) {
        refreshIntervention();
      }
      _lastCheckinCount = d.checkin_count;
    } catch (e) { /* silent */ }
  }

  // ── AI intervention ──
  async function loadIntervention() {
    const card = $("ai-intervention-card");
    if (!card) return;
    try {
      const res = await Auth.apiFetch("/api/bff/cognitive/intervention");
      if (!res.ok) return;
      const d = await res.json();
      _currentIntervention = d.intervention;

      card.classList.remove("hidden");
      const titleEl = $("ai-int-title");
      const whyEl = $("ai-int-why");
      const howEl = $("ai-int-how");
      const durEl = $("ai-int-duration");
      const evEl = $("ai-int-evidence");
      const patEl = $("ai-int-patterns");

      if (d.patterns.length === 0) {
        titleEl.textContent = "No strong patterns yet";
        whyEl.textContent = "Complete more cognitive check-ins to unlock AI pattern analysis. Currently analyzed: " + d.days_analyzed + " day(s).";
        howEl.textContent = "Keep checking in. Your patterns will emerge within a few days.";
        durEl.textContent = "";
        evEl.textContent = "";
        patEl.innerHTML = "";
        return;
      }

      titleEl.textContent = d.intervention.title || "One small thing";
      whyEl.textContent = d.intervention.why || "";
      howEl.textContent = d.intervention.how || "";
      durEl.textContent = "⏱ " + (d.intervention.duration || "");
      evEl.textContent = d.intervention.evidence_hint || "";

      patEl.innerHTML = d.patterns.slice(0, 4).map(p => {
        const sev = p.severity === "high" ? "border-rose-500/60 text-rose-300 bg-rose-500/10"
                  : p.severity === "moderate" ? "border-amber-500/50 text-amber-300 bg-amber-500/10"
                  : "border-emerald-500/50 text-emerald-300 bg-emerald-500/10";
        return `<span class="px-2 py-0.5 rounded-full border ${sev} text-[9px] font-medium">${p.label}</span>`;
      }).join("");
    } catch (e) { console.error("intervention load failed", e); }
  }

  async function refreshIntervention() {
    const btn = $("ai-int-refresh");
    if (btn) { btn.disabled = true; btn.textContent = "🔄 Thinking..."; }
    try {
      // Invalidate cache on backend by posting skip → forces regen on next GET
      await Auth.apiFetch("/api/bff/cognitive/intervention/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json",
                   "Idempotency-Key": crypto.randomUUID ? crypto.randomUUID() : Date.now().toString() },
        body: JSON.stringify({ action: "skip", note: "refresh" })
      });
      await loadIntervention();
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "🔄 Refresh"; }
    }
  }

  async function acceptIntervention() {
    try {
      await Auth.apiFetch("/api/bff/cognitive/intervention/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json",
                   "Idempotency-Key": crypto.randomUUID ? crypto.randomUUID() : Date.now().toString() },
        body: JSON.stringify({ action: "accept" })
      });
      UI.toast("Logged. Your patterns will refine as you try things.");
      // Dim the card
      const card = $("ai-intervention-card");
      if (card) card.style.opacity = "0.6";
      setTimeout(() => { if (card) card.style.opacity = "1"; }, 3000);
    } catch (e) { UI.toast("Could not record", "error"); }
  }

  async function skipIntervention() {
    try {
      await Auth.apiFetch("/api/bff/cognitive/intervention/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json",
                   "Idempotency-Key": crypto.randomUUID ? crypto.randomUUID() : Date.now().toString() },
        body: JSON.stringify({ action: "skip" })
      });
      await loadIntervention();
      UI.toast("Noted. Fresh suggestion coming.");
    } catch (e) { UI.toast("Could not record", "error"); }
  }

  // Expose to onclick handlers (IIFE scope)
  window.acceptIntervention = acceptIntervention;
  window.skipIntervention = skipIntervention;
  window.refreshIntervention = refreshIntervention;

  // ── Kick off on load ──
  startLivePolling();
  setTimeout(loadIntervention, 800);

  // Refresh intervention + baseline when a check-in succeeds
  const _origSubmitResultHook = window._onCheckinSuccess;
  window._onCheckinSuccess = function() {
    loadIntervention();
    loadCognitiveBaseline();
    pollLive();
    if (_origSubmitResultHook) _origSubmitResultHook();
  };

})();
