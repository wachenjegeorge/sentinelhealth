"""Fix frontend wiring bugs."""
import pathlib, re
ROOT = pathlib.Path(".")
FRONTEND = ROOT / "frontend"

def patch(path, replacements, label=""):
    p = ROOT / path
    if not p.exists(): print(f"SKIP {path}"); return
    s = p.read_text(encoding="utf-8"); o = s; hits = 0
    for old, new in replacements:
        if old in s: s = s.replace(old, new); hits += 1
    if s != o: p.write_text(s, encoding="utf-8"); print(f"OK {path} ({hits}) {label}")
    else: print(f"=  {path} (no match)")

# 1. admin.js loadDepartments
admin_js = FRONTEND / "admin.js"
if admin_js.exists():
    s = admin_js.read_text(encoding="utf-8")
    FN = '''  async function loadDepartments() {
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

'''
    if "async function loadDepartments()" not in s:
        anchor = "  // ── 10. Init ──"
        s = s.replace(anchor, FN + anchor) if anchor in s else s.replace("})();", FN + "})();")
    admin_js.write_text(s, encoding="utf-8")
    print("OK admin.js: loadDepartments")

# 2. admin.html dead panel
p = FRONTEND / "admin.html"
if p.exists():
    s = p.read_text(encoding="utf-8")
    s = re.sub(r"<!-- COUNTY DEEP DIVE WORKSPACE -->.*?</div>\s*</div>\s*</body>", "</body>", s, flags=re.DOTALL)
    p.write_text(s, encoding="utf-8")
    print("OK admin.html: dead panel removed")

# 3. role gates
patch("frontend/admin-users.html", [('Auth.requireRole("health_officer")', 'Auth.requireRole(["county_officer", "admin"])')], "(role)")
patch("frontend/admin-incidents.html", [('Auth.requireRole("health_officer")', 'Auth.requireRole(["county_officer", "admin"])')], "(role)")

# 4. admin-facilities admin
patch("frontend/admin-facilities.html", [
    ('const res = await Auth.apiFetch("/api/bff/facilities?county=" + (session.county || ""));',
     'const qs = session.county ? ("?county=" + encodeURIComponent(session.county)) : "";\n    const res = await Auth.apiFetch("/api/bff/facilities" + qs);'),
    ('$("headerSub").textContent = (session.county || "National") + " County";',
     '$("headerSub").textContent = session.county ? (session.county + " County") : "National";'),
], "(admin)")

# 5. worker.js score
patch("frontend/worker.js", [
    ('WVI Score: ${Math.round(data.personal_score)}',
     'WVI Score: ${Math.round(data.personal_score ?? data.score ?? data.wvi ?? 0)}'),
], "(score)")

# 6. random idempotency
RAND = 'crypto.randomUUID ? crypto.randomUUID() : (Date.now() + "-" + Math.random().toString(36).slice(2))'
for f in list(FRONTEND.glob("*.js")) + list(FRONTEND.glob("*.html")):
    s = f.read_text(encoding="utf-8"); o = s
    s = s.replace('"Idempotency-Key": Date.now().toString()', f'"Idempotency-Key": {RAND}')
    s = s.replace('"Idempotency-Key": "ai-" + Date.now()', f'"Idempotency-Key": "ai-" + ({RAND})')
    s = s.replace('"Idempotency-Key": "deptai-" + Date.now()', f'"Idempotency-Key": "deptai-" + ({RAND})')
    s = s.replace('headers: { "Idempotency-Key": Date.now().toString() }', f'headers: {{ "Idempotency-Key": {RAND} }}')
    if s != o: f.write_text(s, encoding="utf-8"); print(f"OK {f.name}: idem")

print("Done.")
