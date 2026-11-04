// Global UI Helpers (Toasts & Markdown)
const UI = (() => {
  // 1. Toast System
  function toast(message, type = "success") {
    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.className = "fixed top-4 right-4 z-[100] flex flex-col gap-2";
      document.body.appendChild(container);
    }
    const toast = document.createElement("div");
    const bg = type === "error" ? "bg-rose-500/90" : "bg-emerald-500/90";
    toast.className = `px-4 py-3 rounded-lg shadow-lg text-white text-sm font-semibold transform transition-all duration-300 translate-x-full ${bg}`;
    toast.textContent = message;
    container.appendChild(toast);
    
    // Animate in
    requestAnimationFrame(() => toast.classList.remove("translate-x-full"));
    
    // Animate out
    setTimeout(() => {
      toast.classList.add("translate-x-full", "opacity-0");
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  // 2. Markdown Parser (Lightweight)
  function md(text) {
    if (!text) return "";
    return text
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") // escape HTML
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>") // bold
      .replace(/\*(.*?)\*/g, "<em>$1</em>") // italic
      .replace(/`([^`]+)`/g, '<code class="bg-slate-800 px-1 py-0.5 rounded text-cyan-300">$1</code>') // code
      .replace(/\n/g, "<br>"); // newlines
  }

  return { toast, md };
})();
