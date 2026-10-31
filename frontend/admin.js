(function() {
  const session = Auth.requireRole("health_officer");
  if (!session) return;
  const $ = function(id) { return document.getElementById(id); };
  $("headerSub").textContent = session.county + " County - k >= 5 - " + session.username;

  function colorFor(score) {
    return "hsl(" + Math.max(0, 150 - 1.5 * score) + ",72%,44%)";
  }

  async function refresh() {
    try {
      const res = await Auth.apiFetch("/api/bff/admin/overview");
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();

      const pct = Math.max(0, Math.min(100, d.pooled_wvi));
      $("gauge").setAttribute("stroke-dasharray", (pct * 0.75).toFixed(1) + " 100");
      $("gauge").setAttribute("stroke", colorFor(pct));
      $("gaugeVal").textContent = Math.round(pct);
      $("gaugeLvl").textContent = d.pooled_level.toUpperCase();
      $("gaugeLvl").setAttribute("fill", colorFor(pct));
      $("groupCount").textContent = d.group_count;

      let total = 0;
      d.groups.forEach(function(g) { total += g.reported; });
      $("reportCount").textContent = total;
      $("updatedAt").textContent = "Updated " + new Date().toLocaleTimeString();

      const byDept = {};
      d.groups.forEach(function(g) {
        if (!byDept[g.department]) byDept[g.department] = { t: 0, w: 0 };
        byDept[g.department].t += g.p90_score * g.reported;
        byDept[g.department].w += g.reported;
      });
      const ranked = Object.entries(byDept)
        .map(function(e) { return { name: e[0], avg: e[1].w ? e[1].t / e[1].w : 0 }; })
        .sort(function(a, b) { return b.avg - a.avg; });

      $("deptRanking").innerHTML = ranked.length
        ? ranked.map(function(r) {
            return '<div>' +
              '<div class="flex justify-between text-xs mb-1">' +
                '<span class="font-semibold">' + r.name + '</span>' +
                '<span class="text-slate-500">' + Math.round(r.avg) + '</span>' +
              '</div>' +
              '<div class="h-2 rounded-full bg-slate-800 overflow-hidden">' +
                '<div class="h-full rounded-full" style="width:' + Math.max(2, r.avg) + '%;background:' + colorFor(r.avg) + '"></div>' +
              '</div>' +
            '</div>';
          }).join("")
        : '<p class="text-sm text-slate-500">No data yet.</p>';

      $("heatmap").innerHTML = d.groups.length
        ? d.groups.map(function(g) {
            const bg = colorFor(g.p90_score);
            return '<div class="heat-cell" style="background:' + bg + '">' +
              '<div class="text-[10px] leading-tight opacity-90">' + g.department + '</div>' +
              '<div class="text-[9px] opacity-70">' + g.shift + '</div>' +
              '<div class="text-lg leading-none mt-0.5">' + Math.round(g.p90_score) + '</div>' +
            '</div>';
          }).join("")
        : '<p class="text-sm text-slate-500">No groups have reached k >= 5 yet.</p>';

      $("live").textContent = "Live";
      $("errorBanner").classList.add("hidden");
    } catch (err) {
      $("live").textContent = "Disconnected";
      $("errorText").textContent = "Refresh failed: " + err.message;
      $("errorBanner").classList.remove("hidden");
    }
  }

  refresh();
  setInterval(refresh, 15000);
})();
