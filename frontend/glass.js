// glass.js — ambient liquid cursor glow + progressive enhancement
(function() {
  'use strict';

  // 1. Ambient cursor glow (desktop with fine pointer only)
  if (window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
    var glow = document.createElement('div');
    glow.id = 'glass-ambient';
    document.body.appendChild(glow);

    var tx = window.innerWidth / 2, ty = window.innerHeight / 2;
    var cx = tx, cy = ty;
    var raf = null;

    function loop() {
      cx += (tx - cx) * 0.15;
      cy += (ty - cy) * 0.15;
      glow.style.transform = 'translate(' + cx + 'px, ' + cy + 'px) translate(-50%, -50%)';
      raf = requestAnimationFrame(loop);
    }

    document.addEventListener('mousemove', function(e) {
      tx = e.clientX;
      ty = e.clientY;
      if (glow.style.opacity !== '1') glow.style.opacity = '1';
      if (!raf) loop();
    }, { passive: true });

    document.addEventListener('mouseleave', function() {
      glow.style.opacity = '0';
    });
  }

  // 2. Fade-in cards on scroll
  if ('IntersectionObserver' in window) {
    var observer = new IntersectionObserver(function(entries) {
      entries.forEach(function(entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('glass-in');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.05, rootMargin: '0px 0px -40px 0px' });

    function observeCards(root) {
      (root.querySelectorAll ? root.querySelectorAll('.card') : []).forEach(function(c) {
        observer.observe(c);
      });
      if (root.classList && root.classList.contains('card')) observer.observe(root);
    }

    observeCards(document);

    // Watch for dynamically added cards (dashboards inject them)
    if ('MutationObserver' in window) {
      var mo = new MutationObserver(function(muts) {
        muts.forEach(function(m) {
          m.addedNodes.forEach(function(node) {
            if (node.nodeType === 1) observeCards(node);
          });
        });
      });
      mo.observe(document.body, { childList: true, subtree: true });
    }
  }
})();
