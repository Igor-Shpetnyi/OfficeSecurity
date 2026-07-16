// Періодично підвантажує HTML-фрагмент і підміняє вміст контейнера —
// без повного перезавантаження сторінки, без нових залежностей (без HTMX/React).
(function () {
  function startLiveRefresh(containerId, url, intervalMs) {
    var container = document.getElementById(containerId);
    if (!container) return;

    function refresh() {
      fetch(url, { credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.text() : null; })
        .then(function (html) {
          if (html !== null) container.innerHTML = html;
        })
        .catch(function () {
          // мовчки пропускаємо один цикл — наступний спробує знову
        });
    }

    setInterval(refresh, intervalMs);
  }

  window.startLiveRefresh = startLiveRefresh;
})();
