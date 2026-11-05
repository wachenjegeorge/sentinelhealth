// Shared auth: session storage, role check, authenticated fetch.
const Auth = (() => {
  const KEY = "sh_session";

  function readSession() {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return null;
      const s = JSON.parse(raw);
      if (s.expires_at && Date.now() > s.expires_at) {
        localStorage.removeItem(KEY);
        return null;
      }
      return s;
    } catch (e) { return null; }
  }

  function saveSession(r) {
    const p = decode(r.access_token);
    const expires = p.exp ? p.exp * 1000 : Date.now() + 12*60*60*1000;
    localStorage.setItem(KEY, JSON.stringify({
      token: r.access_token, role: r.role, facility_id: r.facility_id,
      county: r.county, username: p.username, expires_at: expires,
    }));
  }

  function clearSession() { localStorage.removeItem(KEY); }

  function decode(t) {
    try {
      const parts = t.split(".");
      if (parts.length !== 3) return {};
      const p = parts[1].replace(/-/g, "+").replace(/_/g, "/");
      return JSON.parse(atob(p));
    } catch (e) { return {}; }
  }

  // Determines the correct home page for each role
  function getRedirectPath(role) {
    if (role === "admin" || role === "county_officer" || role === "health_officer" || role === "hospital_head") {
      return "/admin";
    }
    if (role === "department_head") return "/dept-head";
    return "/worker";
  }

  function requireRole(roles) {
    const s = readSession();
    if (!s) { window.location.href = "/"; return null; }
    
    if (roles) {
      const allowed = Array.isArray(roles) ? roles : [roles];
      if (!allowed.includes(s.role)) { 
        // Kick them to their correct dashboard, not the login page
        window.location.href = getRedirectPath(s.role); 
        return null; 
      }
    }
    return s;
  }

  async function apiFetch(url, opts) {
    const s = readSession();
    if (!s) { window.location.href = "/"; throw new Error("not authenticated"); }
    opts = opts || {};
    opts.headers = opts.headers || {};
    opts.headers["Authorization"] = "Bearer " + s.token;
    const res = await fetch(url, opts);
    if (res.status === 401) {
      clearSession();
      window.location.href = "/";
      throw new Error("session expired");
    }
    return res;
  }

  function logout() { clearSession(); window.location.href = "/"; }

  return { readSession, saveSession, clearSession, requireRole, apiFetch, logout, getRedirectPath };
})();
