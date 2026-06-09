/* Общие UI-помощники: авто-скрытие уведомлений, копирование, подтверждения. */
(function () {
  "use strict";

  // Авто-скрытие flash-сообщений
  var flashes = document.getElementById("flashes");
  if (flashes) {
    setTimeout(function () {
      Array.prototype.forEach.call(flashes.children, function (el) {
        el.style.transition = "opacity .4s ease, transform .4s ease";
        el.style.opacity = "0";
        el.style.transform = "translateY(-10px)";
      });
      setTimeout(function () { flashes.remove(); }, 450);
    }, 4200);
  }

  // Копирование в буфер обмена: элементы с data-copy="<target-id>"
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy]");
    if (!btn) return;
    var target = document.getElementById(btn.getAttribute("data-copy"));
    if (!target) return;
    var text = target.value || target.textContent || "";

    var done = function () {
      var prev = btn.getAttribute("data-label") || btn.textContent;
      if (!btn.getAttribute("data-label")) btn.setAttribute("data-label", prev);
      btn.textContent = "Скопировано ✓";
      setTimeout(function () { btn.textContent = btn.getAttribute("data-label"); }, 1600);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(target, done); });
    } else {
      fallbackCopy(target, done);
    }
  });

  function fallbackCopy(target, cb) {
    try {
      if (target.select) { target.select(); document.execCommand("copy"); }
      cb();
    } catch (err) { /* ignore */ }
  }

  // Подтверждение опасных действий: forms / links с data-confirm
  document.addEventListener("submit", function (e) {
    var form = e.target;
    var msg = form.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });
})();
