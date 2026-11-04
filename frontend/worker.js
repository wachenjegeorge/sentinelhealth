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
  ["fatigue","heat","hours"].forEach(id => {
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
      hours_worked: Number($("hours").value), symptoms: Array.from(selectedSymptoms)
    };
    try {
      const res = await Auth.apiFetch("/api/bff/sync/checkins", {
        method: "POST", headers: { "Idempotency-Key": Date.now().toString(), "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error("API error");
      const data = await res.json();
      
      const color = data.level === "Critical" ? "#f43f5e" : data.level === "Moderate" ? "#f59e0b" : "#10b981";
      $("result").className = "mb-5 block card p-5 border-2";
      $("result").style.borderColor = color;
      $("result").innerHTML = `<h3 class="text-lg font-bold" style="color:${color}">Check-in Recorded: ${data.level} Risk</h3><p class="text-sm text-slate-400 mt-1">WVI Score: ${Math.round(data.personal_score)}</p>`;
      
      fetchCoach(); // Refresh AI Coach with new warning status
      loadDashboard();
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
    const warningEl = $("early-warning");
    const warningText = $("early-warning-text");
    try {
      const res = await Auth.apiFetch("/api/bff/worker/coach");
      if (res.ok) {
        const data = await res.json();
        msgEl.innerHTML = data.message.replace(/\n/g, '<br>');
        msgEl.classList.remove("animate-pulse");
        
        if (data.is_warning) {
          warningEl.classList.remove("hidden");
          warningText.textContent = data.message;
        } else {
          warningEl.classList.add("hidden");
        }
      }
    } catch (e) {
      msgEl.textContent = "Stay hydrated and monitor your fatigue today.";
      msgEl.classList.remove("animate-pulse");
    }
  }

  // Sync Wearable
  window.syncDevice = async () => {
    const btn = $("sync-btn");
    btn.textContent = "Syncing..."; btn.disabled = true;
    try {
      const res = await Auth.apiFetch("/api/bff/worker/wearable/sync", { method: "POST", headers: { "Idempotency-Key": Date.now().toString() } });
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
      const res = await Auth.apiFetch("/api/bff/worker/wearable/schedule/upload", { method: "POST", headers: { "Idempotency-Key": Date.now().toString() } });
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
        method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": Date.now().toString() },
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
  loadDashboard();
})();
