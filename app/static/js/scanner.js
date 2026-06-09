/* ============================================================
   CCU Invite — сканер QR на входе
   Использует html5-qrcode для доступа к камере и распознавания.
   ============================================================ */
(function () {
  "use strict";

  var CFG = window.CCU || {};
  var reader = null;          // экземпляр Html5Qrcode
  var running = false;
  var transitioning = false;  // идёт start()/stop() — не пускаем повторный вызов
  var paused = false;         // сканер на паузе (можно вызывать resume)
  var busy = false;           // обрабатываем результат — не реагируем на новые сканы
  var lastToken = null;       // защита от повторного срабатывания на тот же код

  var els = {
    start: document.getElementById("btnStart"),
    stop: document.getElementById("btnStop"),
    hint: document.getElementById("scanHint"),
    frame: document.getElementById("scanFrame"),
    placeholder: document.getElementById("scanPlaceholder"),
    result: document.getElementById("result"),
    manualForm: document.getElementById("manualForm"),
    manualToken: document.getElementById("manualToken")
  };

  function qrboxFn(vw, vh) {
    var min = Math.min(vw, vh);
    var size = Math.floor(min * 0.7);
    return { width: size, height: size };
  }

  function vibrate(pattern) {
    if (navigator.vibrate) { try { navigator.vibrate(pattern); } catch (e) {} }
  }

  // ----- управление камерой ---------------------------------------------
  function setIdleUI() {
    els.start.hidden = false;
    els.stop.hidden = true;
    els.hint.hidden = true;
    els.frame.hidden = true;
    els.placeholder.hidden = false;
  }

  function startCamera() {
    if (typeof Html5Qrcode === "undefined") {
      renderError("Не удалось загрузить модуль камеры. Обновите страницу или введите код вручную.");
      return;
    }
    // не пускаем повторный запуск, пока идёт start/stop (защита от двойного тапа)
    if (running || transitioning) return;
    transitioning = true;
    els.start.disabled = true;
    reader = reader || new Html5Qrcode("qr-reader", { verbose: false });

    var startPromise;
    try {
      startPromise = reader.start(
        { facingMode: "environment" },
        { fps: 10, qrbox: qrboxFn, aspectRatio: 1.0 },
        onScan,
        function () { /* ошибки кадра игнорируем */ }
      );
    } catch (err) {
      // start() может бросить синхронно, если предыдущий переход не завершён
      transitioning = false;
      els.start.disabled = false;
      renderError("Камера недоступна: " + describeCamError(err) +
        " Разрешите доступ к камере или введите код вручную.");
      return;
    }

    startPromise.then(function () {
      running = true;
      transitioning = false;
      paused = false;
      els.start.disabled = false;
      els.start.hidden = true;
      els.stop.hidden = false;
      els.hint.hidden = false;
      els.frame.hidden = false;
      els.placeholder.hidden = true;
    }).catch(function (err) {
      running = false;
      transitioning = false;
      els.start.disabled = false;
      renderError("Камера недоступна: " + describeCamError(err) +
        " Разрешите доступ к камере или введите код вручную.");
    });
  }

  function stopCamera() {
    if (!reader || (!running && !transitioning)) {
      setIdleUI();
      return;
    }
    transitioning = true;
    els.stop.disabled = true;
    reader.stop()
      .then(function () { try { reader.clear(); } catch (e) {} })
      .catch(function () {})
      .then(function () {
        running = false;
        paused = false;
        transitioning = false;
        els.stop.disabled = false;
        setIdleUI();
      });
  }

  function pauseScanning() {
    if (reader && running && !paused && reader.pause) {
      try { reader.pause(true); paused = true; } catch (e) {}
    }
  }
  function resumeScanning() {
    busy = false;
    lastToken = null;
    // resume() в html5-qrcode бросает, если сканер не на паузе — вызываем только при paused
    if (reader && running && paused && reader.resume) {
      try { reader.resume(); } catch (e) {}
    }
    paused = false;
  }

  function describeCamError(err) {
    var name = (err && (err.name || err.toString())) || "";
    if (/NotAllowed/i.test(name)) return "доступ запрещён.";
    if (/NotFound/i.test(name)) return "камера не найдена.";
    if (/NotReadable/i.test(name)) return "камера занята другим приложением.";
    if (/secure|https/i.test(String(err))) return "нужен HTTPS.";
    return "" + name;
  }

  // ----- обработка кода -------------------------------------------------
  function onScan(decodedText) {
    if (busy) return;
    if (decodedText === lastToken) return;
    busy = true;
    lastToken = decodedText;
    vibrate(60);
    pauseScanning();
    lookup(decodedText);
  }

  function lookup(token) {
    renderLoading();
    fetch(CFG.lookupUrl + "?token=" + encodeURIComponent(token), {
      headers: { "Accept": "application/json" },
      credentials: "same-origin"
    })
      .then(toJson)
      .then(function (data) {
        if (!data.ok) { renderError(data.message || "Гость не найден."); return; }
        renderGuest(data.guest, token);
      })
      .catch(function () { renderError("Ошибка сети. Повторите попытку."); });
  }

  function checkin(token) {
    renderLoading();
    fetch(CFG.checkinUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": CFG.csrf,
        "Accept": "application/json"
      },
      credentials: "same-origin",
      body: JSON.stringify({ token: token })
    })
      .then(toJson)
      .then(function (data) {
        if (!data.ok) { renderError(data.message || "Не удалось отметить."); return; }
        vibrate([40, 60, 40]);
        renderConfirmed(data.guest, data.already);
      })
      .catch(function () { renderError("Ошибка сети. Повторите попытку."); });
  }

  function toJson(r) { return r.json().catch(function () { return { ok: false, message: "Ошибка сервера." }; }); }

  // ----- отрисовка ------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function rows(guest) {
    var html =
      '<div class="result__row"><dt>Студент</dt><dd>' + esc(guest.student) + "</dd></div>" +
      '<div class="result__row"><dt>Группа</dt><dd>' + esc(guest.group || "—") + "</dd></div>" +
      '<div class="result__row"><dt>Кем приходится</dt><dd>' + esc(guest.relation) + "</dd></div>";
    if (guest.specialty) {
      html += '<div class="result__row"><dt>Специальность</dt><dd>' + esc(guest.specialty) + "</dd></div>";
    }
    return html;
  }

  function scanNextBtn() {
    return '<button class="btn btn--lg btn--block" id="btnNext" type="button" style="margin-top:14px;">Сканировать следующего</button>';
  }

  function renderLoading() {
    els.result.innerHTML =
      '<div class="result"><div class="center" style="padding:18px;">' +
      '<span class="spinner" style="border-color:rgba(10,46,92,.2);border-top-color:var(--navy);"></span>' +
      '<div class="muted" style="margin-top:10px;">Проверяем…</div></div></div>';
  }

  function renderError(msg) {
    els.result.innerHTML =
      '<div class="result result--error">' +
      '<div class="result__icon">✕</div>' +
      '<div class="result__name" style="font-size:1.1rem;">Ошибка</div>' +
      '<p class="center muted" style="margin-top:6px;">' + esc(msg) + "</p>" +
      scanNextBtn() + "</div>";
    bindNext();
  }

  function renderGuest(guest, token) {
    if (guest.present) {
      els.result.innerHTML =
        '<div class="result result--present">' +
        '<div class="result__icon">!</div>' +
        '<div class="result__name">' + esc(guest.name) + "</div>" +
        '<div class="result__rel">уже отмечен(а) как присутствующий</div>' +
        "<dl style='margin:0;'>" + rows(guest) +
        '<div class="result__row"><dt>Отмечен</dt><dd>' + esc(guest.checked_in_at || "—") + "</dd></div></dl>" +
        scanNextBtn() + "</div>";
      bindNext();
      return;
    }

    var expiredWarn = guest.expired
      ? '<p class="center" style="color:var(--warning);font-weight:600;margin-top:8px;">⚠ Срок ссылки истёк, но отметка возможна.</p>'
      : "";

    els.result.innerHTML =
      '<div class="result result--ok">' +
      '<div class="result__icon">✓</div>' +
      '<div class="result__name">' + esc(guest.name) + "</div>" +
      '<div class="result__rel">' + esc(guest.relation) + " · " + esc(guest.phrase) + "</div>" +
      "<dl style='margin:0;'>" + rows(guest) + "</dl>" +
      expiredWarn +
      '<button class="btn btn--lg btn--success btn--block" id="btnConfirm" type="button" style="margin-top:16px;">Подтвердить присутствие</button>' +
      '<button class="btn btn--block btn--ghost" id="btnCancel" type="button" style="margin-top:10px;">Отмена</button>' +
      "</div>";

    document.getElementById("btnConfirm").addEventListener("click", function () {
      checkin(token);
    });
    document.getElementById("btnCancel").addEventListener("click", function () {
      els.result.innerHTML = "";
      resumeScanning();
    });
  }

  function renderConfirmed(guest, already) {
    var title = already ? "Уже был отмечен" : "Присутствие подтверждено";
    var cls = already ? "result--present" : "result--ok";
    var icon = already ? "!" : "✓";
    els.result.innerHTML =
      '<div class="result ' + cls + '">' +
      '<div class="result__icon">' + icon + "</div>" +
      '<div class="result__name">' + esc(guest.name) + "</div>" +
      '<div class="result__rel">' + esc(title) + "</div>" +
      "<dl style='margin:0;'>" + rows(guest) +
      '<div class="result__row"><dt>Время</dt><dd>' + esc(guest.checked_in_at || "—") + "</dd></div></dl>" +
      scanNextBtn() + "</div>";
    bindNext();
  }

  function bindNext() {
    var b = document.getElementById("btnNext");
    if (b) b.addEventListener("click", function () {
      els.result.innerHTML = "";
      if (running) { resumeScanning(); } else { busy = false; lastToken = null; }
    });
  }

  // ----- события --------------------------------------------------------
  if (els.start) els.start.addEventListener("click", startCamera);
  if (els.stop) els.stop.addEventListener("click", stopCamera);

  if (els.manualForm) {
    els.manualForm.addEventListener("submit", function (e) {
      e.preventDefault();
      if (busy) return;               // не плодим параллельные запросы при двойном тапе
      var val = (els.manualToken.value || "").trim();
      if (!val) return;
      busy = true;
      lookup(val);
    });
  }

  // Корректно освобождаем камеру и сбрасываем состояние при уходе со страницы.
  window.addEventListener("pagehide", function () {
    if (reader && running) {
      try {
        reader.stop().then(function () { try { reader.clear(); } catch (e) {} }).catch(function () {});
      } catch (e) {}
    }
    running = false; transitioning = false; paused = false; busy = false; lastToken = null;
  });

  // bfcache-восстановление (частое на iOS Safari): сбрасываем UI в исходное состояние,
  // иначе кнопка «Включить камеру» не сработает после возврата на страницу.
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) {
      running = false; transitioning = false; paused = false; busy = false; lastToken = null;
      if (els.start) els.start.disabled = false;
      if (els.result) els.result.innerHTML = "";
      setIdleUI();
    }
  });
})();
