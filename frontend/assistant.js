(function() {
  if (typeof Auth === 'undefined') return;
  const session = Auth.readSession();
  if (!session) return;

  const widget = document.createElement('div');
  widget.innerHTML = `
    <button id="ai-fab" class="fixed bottom-6 right-6 h-14 w-14 rounded-full bg-gradient-to-r from-fuchsia-500 to-cyan-500 text-white shadow-lg flex items-center justify-center text-2xl z-50 hover:scale-105 transition-transform" title="Ask AI Assistant">
      🤖
    </button>
    <div id="ai-panel" class="fixed bottom-24 right-6 w-[350px] max-w-[calc(100vw-3rem)] h-[450px] max-h-[calc(100vh-8rem)] bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl flex flex-col z-50 hidden">
      <div class="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-950/50 rounded-t-2xl">
        <div class="flex items-center gap-2">
          <span class="text-xl">🤖</span>
          <div>
            <p class="text-sm font-bold text-white">Sentinel AI</p>
            <p class="text-[10px] text-cyan-400">Powered by Groq</p>
          </div>
        </div>
        <button id="ai-close" class="text-slate-400 hover:text-white">✕</button>
      </div>
      <div id="ai-log" class="flex-1 overflow-y-auto p-4 space-y-4 text-sm">
        <div class="bg-slate-800 text-slate-200 p-3 rounded-lg rounded-tl-none w-5/6">
          Hello ${session.username}! I am your AI health assistant. Ask me about facility risk, heat protocols, or fatigue management.
        </div>
      </div>
      <form id="ai-form" class="p-3 border-t border-slate-800 bg-slate-950/50 rounded-b-2xl flex gap-2">
        <input id="ai-input" class="flex-1 bg-slate-800 border-none rounded-lg px-3 py-2 text-sm text-white focus:ring-1 focus:ring-cyan-500 outline-none" placeholder="Ask me anything..." autocomplete="off">
        <button type="submit" class="bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg px-4 py-2 font-semibold text-sm">Send</button>
      </form>
    </div>
  `;
  document.body.appendChild(widget);

  const fab = document.getElementById('ai-fab');
  const panel = document.getElementById('ai-panel');
  const closeBtn = document.getElementById('ai-close');
  const log = document.getElementById('ai-log');
  const form = document.getElementById('ai-form');
  const input = document.getElementById('ai-input');

  fab.onclick = () => {
    panel.classList.toggle('hidden');
    if (!panel.classList.contains('hidden')) input.focus();
  };
  closeBtn.onclick = () => panel.classList.add('hidden');

  // Native Markdown Parser
  function md(text) {
    if (!text) return "";
    return text
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.*?)\*/g, "<em>$1</em>")
      .replace(/`([^`]+)`/g, '<code class="bg-slate-800 px-1 py-0.5 rounded text-cyan-300">$1</code>')
      .replace(/\n/g, "<br>");
  }

  form.onsubmit = async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    
    log.innerHTML += `
      <div class="flex justify-end">
        <div class="bg-cyan-900 text-cyan-50 p-3 rounded-lg rounded-tr-none max-w-[85%]">${text}</div>
      </div>`;
    log.scrollTop = log.scrollHeight;

    const loadingId = 'loading-' + Date.now();
    log.innerHTML += `
      <div id="${loadingId}" class="flex justify-start">
        <div class="bg-slate-800 text-slate-400 p-3 rounded-lg rounded-tl-none italic">Thinking...</div>
      </div>`;
    log.scrollTop = log.scrollHeight;

    try {
      const res = await Auth.apiFetch("/api/bff/assistant/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID ? crypto.randomUUID() : (Date.now() + "-" + Math.random().toString(36).slice(2)) },
        body: JSON.stringify({ question: text })
      });
      
      const loadEl = document.getElementById(loadingId);
      if (loadEl) loadEl.remove();
      
      if (!res.ok) throw new Error("API Error");
      const data = await res.json();
      
      log.innerHTML += `
        <div class="flex justify-start">
          <div class="bg-slate-800 text-slate-200 p-3 rounded-lg rounded-tl-none max-w-[85%]">
            ${md(data.answer)}
            <div class="mt-2 text-[9px] text-slate-500 uppercase tracking-wider">Engine: ${data.engine} | Verified: ${data.verified}</div>
          </div>
        </div>`;
    } catch (err) {
      const loadEl = document.getElementById(loadingId);
      if (loadEl) loadEl.remove();
      log.innerHTML += `
        <div class="flex justify-start">
          <div class="bg-rose-900/50 text-rose-200 p-3 rounded-lg rounded-tl-none border border-rose-800">
            System is offline. Please try again in a moment.
          </div>
        </div>`;
    }
    log.scrollTop = log.scrollHeight;
  };
})();
