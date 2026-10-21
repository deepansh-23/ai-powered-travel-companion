/**
 * Thin reading-progress bar fixed at the very top of every page.
 * It fills left to right as the page is scrolled. It never takes clicks (pointer-events: none),
 * uses a GPU-friendly transform and updates at most once per animation frame.
 *
 * It is attached to the <html> element (not <body>) so page layout rules cannot move or hide it, and it
 * re-measures whenever the page height can change: results appearing, images loading, a phone's address
 * bar moving, going back to a page, rotating the screen.
 */

/** 0..1: how far the page is scrolled. Pure, so it can be tested. */
export function computeProgress({ scrollY, scrollHeight, viewportHeight }) {
  const scrollable = scrollHeight - viewportHeight;
  if (!(scrollable > 1)) return 0;
  return Math.min(1, Math.max(0, scrollY / scrollable));
}

export function initScrollProgress() {
  if (document.getElementById("scrollProgress")) return;

  const doc = document.documentElement;
  const wrap = document.createElement("div");
  wrap.id = "scrollProgress";
  wrap.className = "scroll-progress";
  wrap.setAttribute("aria-hidden", "true");
  // The essentials are also set inline, so the bar still works if the stylesheet is slow or cached
  wrap.style.cssText = "position:fixed;top:0;left:0;right:0;pointer-events:none;";
  const bar = document.createElement("div");
  bar.className = "scroll-progress-bar";
  wrap.appendChild(bar);
  doc.appendChild(wrap);

  let queued = false;
  const update = () => {
    queued = false;
    const scroller = document.scrollingElement || doc;
    const body = document.body;
    const ratio = computeProgress({
      scrollY: window.pageYOffset || scroller.scrollTop || 0,
      scrollHeight: Math.max(scroller.scrollHeight, doc.scrollHeight, body ? body.scrollHeight : 0),
      viewportHeight: doc.clientHeight || window.innerHeight
    });
    bar.style.transform = `scaleX(${ratio})`;
  };
  const queue = () => {
    if (!queued) {
      queued = true;
      requestAnimationFrame(update);
    }
  };

  window.addEventListener("scroll", queue, { passive: true });
  window.addEventListener("resize", queue, { passive: true });
  window.addEventListener("orientationchange", queue);
  window.addEventListener("load", queue);
  window.addEventListener("pageshow", queue);      // coming back to the page with the Back button
  window.addEventListener("hashchange", queue);
  if (window.visualViewport) window.visualViewport.addEventListener("resize", queue); // mobile address bar
  if (typeof ResizeObserver !== "undefined") {
    const ro = new ResizeObserver(queue);
    ro.observe(doc);
    if (document.body) ro.observe(document.body);
  }
  if (typeof MutationObserver !== "undefined" && document.body) {
    new MutationObserver(queue).observe(document.body, { childList: true, subtree: true }); // results rendered, panels opened
  }
  document.addEventListener("transitionend", queue, true);
  update();
}
