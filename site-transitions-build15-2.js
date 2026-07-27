"use strict";
(() => {
  const leave = url => {
    if (document.body.classList.contains("page-leaving")) return;
    document.body.classList.add("page-leaving");
    window.setTimeout(() => { window.location.href = url; }, 180);
  };
  document.addEventListener("click", event => {
    const link = event.target.closest("a[href]");
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (link.target && link.target !== "_self") return;
    if (link.hasAttribute("download") || link.getAttribute("rel")?.includes("external")) return;
    let url;
    try { url = new URL(link.href, location.href); } catch { return; }
    if (url.origin !== location.origin) return;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return;
    event.preventDefault();
    leave(url.href);
  });
  window.addEventListener("pageshow", () => document.body.classList.remove("page-leaving"));
})();
