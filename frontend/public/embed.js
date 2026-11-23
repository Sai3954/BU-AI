/*
  Ask Bela website launcher. Add one line to any page (this prototype's address shown; use the
  address where Bela is hosted):
    <script src="https://bu-ai-v2-web.onrender.com/embed.js" defer></script>
  Optional attributes: data-label="Ask Bela"  data-app="https://bu-ai-v2-web.onrender.com"  data-position="right|left"
  Shows an "Ask Bela" button in the corner; clicking opens the assistant in a panel. It never opens by itself.
*/
(function () {
  if (window.__buaiLauncher) return;
  window.__buaiLauncher = true;
  var script = document.currentScript;
  var base = (script && script.getAttribute("data-app")) || (script ? new URL(script.src).origin : location.origin);
  var label = (script && script.getAttribute("data-label")) || "Ask Bela";
  var side = (script && script.getAttribute("data-position")) === "left" ? "left" : "right";

  var css = [
    ".buai-fab{position:fixed;" + side + ":24px;bottom:24px;z-index:2147483000;display:flex;align-items:center;gap:10px;",
    "height:56px;padding:0 20px 0 5px;border-radius:999px;border:2px solid #C9A14A;background:#123D35;color:#F6F2E7;",
    "font:600 16px/1 system-ui,-apple-system,'Segoe UI',Arial,sans-serif;cursor:pointer;box-shadow:0 10px 30px rgba(11,43,37,.28)}",
    ".buai-fab:hover{background:#1D5246}",
    ".buai-fab:focus-visible{outline:3px solid #C9A14A;outline-offset:3px}",
    ".buai-mark{width:44px;height:44px;flex:none;display:block}",
    ".buai-spark{width:16px;height:16px;flex:none;margin-left:-4px}",
    ".buai-panel{position:fixed;" + side + ":24px;bottom:96px;z-index:2147483000;width:420px;height:min(680px,calc(100vh - 120px));",
    "border-radius:18px;overflow:hidden;background:#fff;box-shadow:0 24px 70px rgba(0,0,0,.28);display:flex;flex-direction:column}",
    ".buai-panel[hidden]{display:none}",
    ".buai-head{display:flex;align-items:center;gap:10px;padding:10px 12px;background:#123D35;color:#F6F2E7;",
    "font:600 15px/1.2 system-ui,-apple-system,'Segoe UI',Arial,sans-serif}",
    ".buai-head small{display:block;font-weight:400;font-size:12px;color:#C3D6CF}",
    ".buai-head .buai-mark{width:34px;height:34px}",
    ".buai-x{margin-left:auto;border:0;background:transparent;color:#F6F2E7;font-size:24px;line-height:1;cursor:pointer;padding:4px 8px;border-radius:8px}",
    ".buai-x:focus-visible{outline:2px solid #C9A14A}",
    ".buai-frame{flex:1;border:0;width:100%}",
    "@media (max-width:600px){.buai-fab{padding:0 4px;" + side + ":16px;bottom:16px}.buai-fab .buai-text,.buai-fab .buai-spark{display:none}",
    ".buai-panel{left:0;right:0;bottom:0;width:100%;height:88vh;border-radius:18px 18px 0 0}",
    ".buai-fab[aria-expanded=true]{display:none}}",  /* phones: the sheet covers the corner; close with x */
    "@media (prefers-reduced-motion:no-preference){.buai-panel{animation:buai-in .18s ease-out}}",
    "@keyframes buai-in{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}"
  ].join("");
  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  var MARK = '<svg class="buai-mark" viewBox="0 0 128 128" aria-hidden="true" focusable="false"><circle cx="64" cy="64" r="62" fill="#123D35"/>' +
    '<path d="M64 22a42 42 0 1 1-26 75l-14 6 5-14A42 42 0 0 1 64 22z" fill="none" stroke="#FFFFFF" stroke-width="9" stroke-linejoin="round"/>' +
    '<path d="M64 30C75 44 88 54 86 74 84 90 74 98 64 98 54 98 43 90 42 75 41 61 50 55 52 45 56 53 59 55 61 51 63 44 61 37 64 30Z" fill="#EFA31A"/><path d="M75.59 84.54Q75.59 88.1 72.92 90.05Q70.24 92 65.49 92H52.41V65.86H64.38Q69.17 65.86 71.63 67.52Q74.08 69.18 74.08 72.42Q74.08 74.65 72.85 76.18Q71.62 77.71 69.09 78.25Q72.27 78.62 73.93 80.25Q75.59 81.87 75.59 84.54ZM68.57 73.17Q68.57 71.4 67.45 70.66Q66.33 69.92 64.12 69.92H57.89V76.4H64.16Q66.48 76.4 67.53 75.59Q68.57 74.78 68.57 73.17ZM70.1 84.11Q70.1 80.44 64.83 80.44H57.89V87.94H65.03Q67.66 87.94 68.88 86.98Q70.1 86.03 70.1 84.11Z" fill="#123D35"/></svg>';
  var SPARK = '<svg class="buai-spark" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M10 3l1.6 4.4L16 9l-4.4 1.6L10 15l-1.6-4.4L4 9l4.4-1.6z" fill="#EFA31A"/>' +
    '<path d="M18 2l.8 2.2L21 5l-2.2.8L18 8l-.8-2.2L15 5l2.2-.8z" fill="#EFA31A"/><path d="M18 14l.8 2.2L21 17l-2.2.8L18 20l-.8-2.2L15 17l2.2-.8z" fill="#EFA31A"/></svg>';

  var btn = document.createElement("button");
  btn.type = "button";
  btn.className = "buai-fab";
  btn.setAttribute("aria-expanded", "false");
  btn.setAttribute("aria-controls", "buai-panel");
  btn.setAttribute("aria-label", label);
  btn.innerHTML = MARK + '<span class="buai-text"></span>' + SPARK;
  btn.querySelector(".buai-text").textContent = label;

  var panel = document.createElement("div");
  panel.className = "buai-panel";
  panel.id = "buai-panel";
  panel.hidden = true;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Bela assistant");
  panel.innerHTML = '<div class="buai-head">' + MARK +
    '<span>Ask Bela<small>Independent prototype</small></span>' +
    '<button type="button" class="buai-x" aria-label="Close Bela">&times;</button></div>';

  var frame = null;
  function open() {
    if (!frame) {
      frame = document.createElement("iframe");
      frame.className = "buai-frame";
      frame.title = "Bela assistant";
      frame.src = base.replace(/\/$/, "") + "/?embed=1";
      frame.setAttribute("allow", "microphone");
      panel.appendChild(frame);
    }
    panel.hidden = false;
    btn.setAttribute("aria-expanded", "true");
    panel.querySelector(".buai-x").focus();
  }
  function close() {
    panel.hidden = true;
    btn.setAttribute("aria-expanded", "false");
    btn.focus();
  }
  btn.addEventListener("click", function () { panel.hidden ? open() : close(); });
  panel.querySelector(".buai-x").addEventListener("click", close);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !panel.hidden) close(); });
  // Escape pressed inside the assistant (an iframe) is forwarded here.
  window.addEventListener("message", function (e) {
    if (frame && e.source === frame.contentWindow && e.data && e.data.type === "buai-close") close();
  });

  function mount() { document.body.appendChild(panel); document.body.appendChild(btn); }
  if (document.body) mount(); else document.addEventListener("DOMContentLoaded", mount);
})();
