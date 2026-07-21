// Періодично підвантажує HTML-фрагмент і підміняє вміст контейнера —
// без повного перезавантаження сторінки, без нових залежностей (без HTMX/React).
(function () {
  // Підсвітка елемента за location.hash (посилання "Джерело" з
  // /channels/state на конкретну подію) — не нативний CSS :target (губиться
  // після заміни innerHTML нижче — елемент з тим самим id з'являється
  // заново, але браузер уже не вважає його "тим самим target"). Одноразова
  // дія за завантаження сторінки: прокручує в центр в'юпорта, підсвічує на
  // кілька секунд, потім знімає — і одразу чистить hash з URL, щоб наступні
  // цикли live-refresh (кожні 5с) не намагались повторити те саме знову.
  function highlightHashTarget(container) {
    if (!location.hash) return;
    var target;
    try {
      target = container.querySelector(location.hash);
    } catch (e) {
      target = null; // невалідний селектор у hash — просто пропускаємо
    }
    if (!target) return;

    target.classList.add('hash-highlight');
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    history.replaceState(null, '', location.pathname + location.search);
    setTimeout(function () {
      target.classList.remove('hash-highlight');
    }, 3000);
  }

  function startLiveRefresh(containerId, url, intervalMs) {
    var container = document.getElementById(containerId);
    if (!container) return;

    highlightHashTarget(container);

    function refresh() {
      // <details data-key> (розгорнутий довгий текст, історія редагувань,
      // ланцюжок відповідей) інакше миттєво згортається щоразу після
      // заміни innerHTML — запам'ятовуємо відкриті ключі й відновлюємо їх
      // у щойно підставленому HTML.
      var openKeys = Array.prototype.slice
        .call(container.querySelectorAll('details[open][data-key]'))
        .map(function (d) { return d.dataset.key; });

      fetch(url, { credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.text() : null; })
        .then(function (html) {
          if (html === null) return;
          container.innerHTML = html;
          openKeys.forEach(function (key) {
            var d = container.querySelector('details[data-key="' + key + '"]');
            if (d) d.open = true;
          });
          highlightHashTarget(container);
        })
        .catch(function () {
          // мовчки пропускаємо один цикл — наступний спробує знову
        });
    }

    setInterval(refresh, intervalMs);
  }

  // Посекундний відлік TTL між циклами live-refresh (5с) — рахує з
  // data-ttl-until (epoch ms, проставлений сервером у момент рендеру
  // фрагмента), не чекаючи наступного fetch(). Читає DOM щосекунди наново
  // (querySelectorAll), тому автоматично підхоплює елементи, підставлені
  // startLiveRefresh() через заміну innerHTML — окремого перезв'язування не треба.
  function startTtlTicker() {
    function tick() {
      var now = Date.now();
      Array.prototype.forEach.call(document.querySelectorAll('[data-ttl-until]'), function (el) {
        var remainingMs = Number(el.dataset.ttlUntil) - now;
        var totalSeconds = Math.max(0, Math.floor(remainingMs / 1000));
        var minutes = Math.floor(totalSeconds / 60);
        var seconds = totalSeconds % 60;
        el.textContent = minutes + ':' + (seconds < 10 ? '0' : '') + seconds;
      });
    }
    tick();
    setInterval(tick, 1000);
  }

  window.startLiveRefresh = startLiveRefresh;
  window.startTtlTicker = startTtlTicker;
})();
