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

  function requireRole(role) {
    const s = readSession();
    if (!s) { window.location.href = "/"; return null; }
    if (role && s.role !== role) { window.location.href = "/"; return null; }
    return s;
  }

  async function apiFetch(url, opts) {
    const s = readSession();
    if (!s) { window.location.href = "/"; throw new Error("no session"); }
    opts = opts || {};
    opts.headers = opts.headers || {};
    opts.headers["Authorization"] = "Bearer " + s.token;
    const res = await fetch(url, opts);
    if (res.status === 401) {
      clearSession();
      window.location.href = "/";
      throw new Error("expired");
    }
    return res;
  }

  function logout() { clearSession(); window.location.href = "/"; }

  return { readSession, saveSession, clearSession, requireRole, apiFetch, logout };
})();
