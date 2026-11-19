/*
  BU AI website launcher. Add one line to any page:
    <script src="https://YOUR-BU-AI-HOST/embed.js" defer></script>
  Optional attributes: data-label="Ask BU AI"  data-app="https://YOUR-BU-AI-HOST"  data-position="right|left"
  Shows an "Ask BU AI" button in the corner; clicking opens the assistant in a panel. It never opens by itself.
*/
(function () {
  if (window.__buaiLauncher) return;
  window.__buaiLauncher = true;
  var script = document.currentScript;
  var base = (script && script.getAttribute("data-app")) || (script ? new URL(script.src).origin : location.origin);
  var label = (script && script.getAttribute("data-label")) || "Ask BU AI";
  var side = (script && script.getAttribute("data-position")) === "left" ? "left" : "right";

  var css = [
    ".buai-fab{position:fixed;" + side + ":24px;bottom:24px;z-index:2147483000;display:flex;align-items:center;gap:10px;",
    "height:56px;padding:0 22px 0 8px;border-radius:999px;border:2px solid #C9A14A;background:#123D35;color:#F6F2E7;",
    "font:600 16px/1 system-ui,-apple-system,'Segoe UI',Arial,sans-serif;cursor:pointer;box-shadow:0 10px 30px rgba(11,43,37,.28)}",
    ".buai-fab:hover{background:#1D5246}",
    ".buai-fab:focus-visible{outline:3px solid #C9A14A;outline-offset:3px}",
    ".buai-mark{width:40px;height:40px;border-radius:50%;background:#0B2B25;border:2px solid #C9A14A;display:flex;align-items:center;",
    "justify-content:center;font:700 14px/1 Georgia,serif;letter-spacing:.5px;color:#fff}",
    ".buai-panel{position:fixed;" + side + ":24px;bottom:96px;z-index:2147483000;width:420px;height:min(680px,calc(100vh - 120px));",
    "border-radius:18px;overflow:hidden;background:#fff;box-shadow:0 24px 70px rgba(0,0,0,.28);display:flex;flex-direction:column}",
    ".buai-panel[hidden]{display:none}",
    ".buai-head{display:flex;align-items:center;gap:10px;padding:10px 12px;background:#123D35;color:#F6F2E7;",
    "font:600 15px/1.2 system-ui,-apple-system,'Segoe UI',Arial,sans-serif}",
    ".buai-head small{display:block;font-weight:400;font-size:12px;color:#C3D6CF}",
    ".buai-head .buai-mark{width:32px;height:32px;font-size:12px}",
    ".buai-x{margin-left:auto;border:0;background:transparent;color:#F6F2E7;font-size:24px;line-height:1;cursor:pointer;padding:4px 8px;border-radius:8px}",
    ".buai-x:focus-visible{outline:2px solid #C9A14A}",
    ".buai-frame{flex:1;border:0;width:100%}",
    "@media (max-width:600px){.buai-fab{padding:0 8px;" + side + ":16px;bottom:16px}.buai-fab .buai-text{display:none}",
    ".buai-panel{left:0;right:0;bottom:0;width:100%;height:88vh;border-radius:18px 18px 0 0}",
    ".buai-fab[aria-expanded=true]{display:none}}",  /* phones: the sheet covers the corner; close with x */
    "@media (prefers-reduced-motion:no-preference){.buai-panel{animation:buai-in .18s ease-out}}",
    "@keyframes buai-in{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}"
  ].join("");
  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  var btn = document.createElement("button");
  btn.type = "button";
  btn.className = "buai-fab";
  btn.setAttribute("aria-expanded", "false");
  btn.setAttribute("aria-controls", "buai-panel");
  btn.setAttribute("aria-label", label);
  btn.innerHTML = '<span class="buai-mark" aria-hidden="true">BU</span><span class="buai-text"></span>';
  btn.querySelector(".buai-text").textContent = label;

  var panel = document.createElement("div");
  panel.className = "buai-panel";
  panel.id = "buai-panel";
  panel.hidden = true;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "BU AI assistant");
  panel.innerHTML = '<div class="buai-head"><span class="buai-mark" aria-hidden="true">BU</span>' +
    '<span>BU AI<small>Independent prototype</small></span>' +
    '<button type="button" class="buai-x" aria-label="Close BU AI">&times;</button></div>';

  var frame = null;
  function open() {
    if (!frame) {
      frame = document.createElement("iframe");
      frame.className = "buai-frame";
      frame.title = "BU AI assistant";
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
