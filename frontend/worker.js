(function() {
  const session = Auth.requireRole("worker");
  if (!session) return;
  const $ = function(id) { return document.getElementById(id); };
  const selected = new Set();

  $("userLabel").textContent = session.username || "Worker";
  $("facilityLabel").textContent = session.facility_id.replace(/-/g, " ");

  ["fatigue","heat","hours"].forEach(function(id) {
    const input = $(id), val = $(id + "Val");
    input.oninput = function() { val.textContent = input.value; };
  });

  const SYMPTOMS = [
    ["headache","Headache"],["dizziness","Dizziness"],["nausea","Nausea"],
    ["cough","Cough"],["sore_throat","Sore Throat"],
    ["shortness_of_breath","Shortness of Breath"],
    ["muscle_strain","Muscle Strain"],["eye_irritation","Eye Irritation"]
  ];
  $("symptoms").innerHTML = SYMPTOMS.map(function(p) {
    return '<button type="button" class="chip" data-sym="' + p[0] + '">' + p[1] + '</button>';
  }).join("");
  document.querySelectorAll("#symptoms .chip").forEach(function(ch) {
    ch.onclick = function() {
      const k = ch.dataset.sym;
      if (selected.has(k)) { selected.delete(k); ch.dataset.active = "false"; }
      else { selected.add(k); ch.dataset.active = "true"; }
    };
  });

  function queueKey() { return "sh_queue_" + session.username; }
  function loadQueue() { try { return JSON.parse(localStorage.getItem(queueKey()) || "[]"); } catch (e) { return []; } }
  function saveQueue(q) { localStorage.setItem(queueKey(), JSON.stringify(q)); updatePending(); }
  function enqueue(payload, idemKey) { const q = loadQueue(); q.push({ payload: payload, idemKey: idemKey }); saveQueue(q); }
  function updatePending() {
    const q = loadQueue(), el = $("pending");
    if (!q.length) { el.classList.add("hidden"); return; }
    el.textContent = q.length + " check-in(s) pending sync.";
    el.classList.remove("hidden");
  }

  async function submitCheckin(payload, idemKey) {
    const res = await Auth.apiFetch("/api/bff/sync/checkins", {
      method: "POST",
      headers: { "Idempotency-Key": idemKey, "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const body = await res.json().catch(function() { return {}; });
      throw new Error(body.detail || ("error " + res.status));
    }
    return await res.json();
  }

  async function drainQueue() {
    const q = loadQueue();
    if (!q.length) return;
    const remaining = [];
    for (const item of q) {
      try { await submitCheckin(item.payload, item.idemKey); }
      catch (e) { remaining.push(item); }
    }
    saveQueue(remaining);
  }

  function renderResult(data, queued) {
    const color = data.level === "Critical" ? "#f43f5e"
      : data.level === "Moderate" ? "#f59e0b" : "#10b981";
    const el = $("result");
    el.className = "mb-5";
    el.innerHTML =
      '<div class="card overflow-hidden">' +
        '<div class="px-5 py-4 border-b" style="background:' + color + '22;border-color:' + color + '55">' +
          '<div class="flex items-center gap-4">' +
            '<div class="grid h-16 w-16 place-items-center rounded-2xl border-2 font-black" style="border-color:' + color + ';color:' + color + '">' +
              Math.round(data.personal_score) +
            '</div>' +
            '<div>' +
              '<p class="text-xs uppercase tracking-widest" style="color:' + color + '">' + data.level + ' Risk</p>' +
              '<h3 class="text-lg font-semibold">Check-in ' + (queued ? 'queued' : 'recorded') + '</h3>' +
            '</div>' +
          '</div>' +
        '</div>' +
        '<div class="p-5"><button onclick="document.getElementById(\'result\').classList.add(\'hidden\')" class="w-full rounded-lg border border-slate-700 py-2 text-sm">Submit another</button></div>' +
      '</div>';
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  $("form").onsubmit = async function(e) {
    e.preventDefault();
    const btn = $("submit");
    btn.disabled = true; btn.textContent = "Submitting...";
    const payload = {
      department: $("department").value,
      shift: $("shift").value,
      fatigue: Number($("fatigue").value),
      heat_exposure: Number($("heat").value),
      hours_worked: Number($("hours").value),
      symptoms: Array.from(selected)
    };
    const idem = (crypto.randomUUID ? crypto.randomUUID() : Date.now() + "-" + Math.random()).replace(/-/g, "");
    try {
      const data = await submitCheckin(payload, idem);
      renderResult(data, false);
      selected.clear();
      document.querySelectorAll("#symptoms .chip").forEach(function(c) { c.dataset.active = "false"; });
    } catch (err) {
      enqueue(payload, idem);
      renderResult({ personal_score: 0, level: "Moderate" }, true);
    } finally {
      btn.disabled = false; btn.textContent = "Submit Check-In";
    }
  };

  window.addEventListener("online", function() { $("offlineBanner").classList.remove("show"); drainQueue(); });
  window.addEventListener("offline", function() { $("offlineBanner").classList.add("show"); });

  updatePending();
  if (!navigator.onLine) $("offlineBanner").classList.add("show");
  drainQueue();
})();

  function renderResult(data, queued) {
    const color = data.level === "Critical" ? "#f43f5e"
      : data.level === "Moderate" ? "#f59e0b" : "#10b981";
    const el = $("result");
    el.className = "mb-5";
    el.innerHTML =
      '<div class="card overflow-hidden">' +
        '<div class="px-5 py-4 border-b" style="background:' + color + '22;border-color:' + color + '55">' +
          '<div class="flex items-center gap-4">' +
            '<div class="grid h-16 w-16 place-items-center rounded-2xl border-2 font-black" style="border-color:' + color + ';color:' + color + '">' +
              Math.round(data.personal_score) +
            '</div>' +
            '<div>' +
              '<p class="text-xs uppercase tracking-widest" style="color:' + color + '">' + data.level + ' Risk</p>' +
              '<h3 class="text-lg font-semibold">Check-in ' + (queued ? 'queued' : 'recorded') + '</h3>' +
            '</div>' +
          '</div>' +
        '</div>' +
        '<div class="p-5"><button onclick="document.getElementById(\'result\').classList.add(\'hidden\')" class="w-full rounded-lg border border-slate-700 py-2 text-sm">Submit another</button></div>' +
      '</div>';
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  $("form").onsubmit = async function(e) {
    e.preventDefault();
    const btn = $("submit");
    btn.disabled = true; btn.textContent = "Submitting...";
    const payload = {
      department: $("department").value,
      shift: $("shift").value,
      fatigue: Number($("fatigue").value),
      heat_exposure: Number($("heat").value),
      hours_worked: Number($("hours").value),
      symptoms: Array.from(selected)
    };
    const idem = (crypto.randomUUID ? crypto.randomUUID() : Date.now() + "-" + Math.random()).replace(/-/g, "");
    try {
      const data = await submitCheckin(payload, idem);
      renderResult(data, false);
      selected.clear();
      document.querySelectorAll("#symptoms .chip").forEach(function(c) { c.dataset.active = "false"; });
    } catch (err) {
      enqueue(payload, idem);
      renderResult({ personal_score: 0, level: "Moderate" }, true);
    } finally {
      btn.disabled = false; btn.textContent = "Submit Check-In";
    }
  };

  window.addEventListener("online", function() { $("offlineBanner").classList.remove("show"); drainQueue(); });
  window.addEventListener("offline", function() { $("offlineBanner").classList.add("show"); });

  updatePending();
  if (!navigator.onLine) $("offlineBanner").classList.add("show");
  drainQueue();
})();
