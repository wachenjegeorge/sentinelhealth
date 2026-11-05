/* SentinelHealth — animation helpers */
const Anim = {
  countUp(el, target, duration) {
    if (!el) return;
    duration = duration || 800;
    const start = performance.now();
    const startVal = parseFloat(el.textContent) || 0;
    const delta = target - startVal;
    function tick(now) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = Math.round(startVal + delta * eased);
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  },

  stagger(container) {
    if (!container) return;
    container.classList.remove("sh-stagger");
    void container.offsetWidth;
    container.classList.add("sh-stagger");
  },

  fadeIn(el) {
    if (!el) return;
    el.classList.add("sh-fade-up");
  },

  flash(el, color) {
    if (!el) return;
    const original = el.style.backgroundColor;
    el.style.transition = "background-color 0.3s ease";
    el.style.backgroundColor = color || "rgba(34, 211, 238, 0.2)";
    setTimeout(() => { el.style.backgroundColor = original; }, 500);
  },

  shake(el) {
    if (!el) return;
    el.style.animation = "none";
    void el.offsetWidth;
    el.style.animation = "sh-shake 0.4s ease";
  }
};

/* Add shake keyframes dynamically */
(function addShakeKeyframes() {
  const style = document.createElement("style");
  style.textContent = `
@keyframes sh-shake {
  0%, 100% { transform: translateX(0); }
  25%      { transform: translateX(-4px); }
  75%      { transform: translateX(4px); }
}`;
  document.head.appendChild(style);
})();
